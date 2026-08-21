# ─── AI-Bot: часть 3 — адаптеры API магазинов ──────────────────────────────
# Legacy (X-API-Key), Reseller API (/v1, ключ rsk_...), Buyer API (ключ tgb_...)

import uuid
import zlib


# ─── Reseller API (/v1) — переходник ──────────────────────────────

def _shop_api_type(shop: dict) -> str:
    """Тип API шопа: 'legacy', 'reseller' (rsk_...) или 'tgbuyer' (tgb_...)."""
    t = shop.get("api_type")
    if t in ("legacy", "reseller", "tgbuyer"):
        return t
    key = str(shop.get("key", ""))
    if key.startswith("rsk_"):
        return "reseller"
    if key.startswith("tgb_"):
        return "tgbuyer"
    return "legacy"


def _strip_html(text: str) -> str:
    """Убрать HTML-теги из описаний Reseller API."""
    from html import unescape
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def _reseller_err(data) -> str:
    if isinstance(data, dict):
        d = data.get("detail")
        if isinstance(d, str):
            return d
        if d is not None:
            return json.dumps(d, ensure_ascii=False)[:300]
    return str(data)[:300]


async def _reseller_api(shop: dict, method: str, path: str, payload: dict | None = None) -> dict:
    """Переходник Reseller API (/v1/...) -> формат ответов первого шопа."""
    base = str(shop.get("base", "")).rstrip("/")
    headers = {"Authorization": f"Bearer {shop['key']}"}

    async def call(m: str, p: str, body: dict | None = None):
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.request(m, f"{base}{p}", json=body, headers=headers) as resp:
                return resp.status, await resp.json(content_type=None)

    try:
        if method == "GET" and path == "/api/balance":
            status, data = await call("GET", "/v1/me")
            if status != 200 or not isinstance(data, dict):
                return {"success": False, "error": _reseller_err(data)}
            return {
                "success": True,
                "username": data.get("name") or data.get("telegram_username", "?"),
                "balance_usdt": float(data.get("balance") or 0),
                "balance_vnd": -1,
            }

        if method == "GET" and path == "/api/products":
            status, data = await call("GET", "/v1/products")
            if status != 200 or not isinstance(data, dict):
                return {"success": False, "error": _reseller_err(data)}
            prods = []
            for p in data.get("products", []):
                stock = p.get("stock")
                desc = _strip_html(p.get("description") or "")
                if p.get("inputs"):
                    need = ", ".join(str(i.get("name", "?")) for i in p["inputs"])
                    desc = f"{desc}\n[!] Шоп требует при заказе: {need}".strip()
                prods.append({
                    "id": p.get("id"),
                    "name": p.get("name", "?"),
                    "price_usdt": float(p.get("your_unit_price") or p.get("retail_price") or 0),
                    "price_vnd": 0,
                    "stock": 999 if stock is None else int(stock),
                    "description": desc,
                })
            return {"success": True, "products": prods}

        if method == "POST" and path == "/api/buy":
            payload = payload or {}
            status, data = await call("POST", "/v1/orders", {
                "product_id": payload.get("product_id"),
                "quantity": payload.get("quantity", 1),
            })
            if status not in (200, 201) or not isinstance(data, dict) or "order_id" not in data:
                return {"success": False, "error": _reseller_err(data)}
            items = [str(c) for c in (data.get("delivered_codes") or [])]
            if not items:
                items = [
                    f"Заказ #{data.get('order_id')} принят (статус: {data.get('status')}). "
                    f"Коды придут позже — проверь заказ в шопе."
                ]
            instr = _strip_html(data.get("delivery_instructions") or "")
            if instr:
                items.append(f"Инструкция:\n{instr}")
            nb = None
            st_me, me = await call("GET", "/v1/me")
            if st_me == 200 and isinstance(me, dict):
                nb = f"{float(me.get('balance') or 0):g}$"
            return {
                "success": True,
                "order": {
                    "product": data.get("product_name", ""),
                    "total_items": data.get("delivered_count") or data.get("quantity", 0),
                    "total_price": data.get("amount"),
                    "currency": "USD",
                },
                "items": items,
                "new_balance": nb,
            }

        status, data = await call(method, path, payload)
        return data if isinstance(data, dict) else {"success": False, "error": str(data)[:300]}
    except Exception as e:
        return {"success": False, "error": f"Сеть/API недоступен: {e}"}


# ─── Buyer API (tgb_...) — переходник ──────────────────────────────

_tgb_ids: dict[str, str] = {}


def _tgb_num_id(sid, real_id) -> int:
    """Строковый _id товара -> стабильный числовой id для кнопок бота."""
    num = zlib.crc32(str(real_id).encode("utf-8")) & 0x7FFFFFFF
    _tgb_ids[f"{sid}:{num}"] = str(real_id)
    return num


def _tgb_err(data) -> str:
    if isinstance(data, dict) and data.get("message"):
        return str(data["message"])[:300]
    return str(data)[:300]


async def _tgbuyer_api(shop: dict, method: str, path: str, payload: dict | None = None) -> dict:
    """Переходник Buyer API (/api/telegram-buyer/...) -> формат первого шопа."""
    base = str(shop.get("base", "")).rstrip("/")
    if not base.endswith("/api/telegram-buyer"):
        base += "/api/telegram-buyer"
    headers = {"Authorization": f"Bearer {shop['key']}"}

    async def call(m: str, p: str, body: dict | None = None, extra: dict | None = None):
        h = dict(headers)
        if extra:
            h.update(extra)
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.request(m, f"{base}{p}", json=body, headers=h) as resp:
                return resp.status, await resp.json(content_type=None)

    try:
        if method == "GET" and path == "/api/balance":
            status, data = await call("GET", "/balance")
            if status != 200 or not isinstance(data, dict) or not data.get("success"):
                return {"success": False, "error": _tgb_err(data)}
            cur = str(data.get("walletCurrency") or "USDT").upper()
            bal = float(data.get("balance") or 0)
            if cur == "VND":
                return {"success": True, "username": shop.get("name", "?"), "balance_usdt": -1, "balance_vnd": bal}
            return {"success": True, "username": shop.get("name", "?"), "balance_usdt": bal, "balance_vnd": -1}

        if method == "GET" and path == "/api/products":
            status, data = await call("GET", "/products")
            if status != 200 or not isinstance(data, dict) or not data.get("success"):
                return {"success": False, "error": _tgb_err(data)}
            sid = shop.get("id")
            wallet_cur = str(data.get("walletCurrency") or "USDT").upper()
            prods = []
            for p in data.get("products", []):
                cur = str(p.get("walletCurrency") or wallet_cur).upper()
                price = float(p.get("pricing") or 0)
                stock = (p.get("stats") or {}).get("available")
                desc = f"Тип: {p.get('slotProductType')}" if p.get("slotProductType") else ""
                prods.append({
                    "id": _tgb_num_id(sid, p.get("_id")),
                    "name": p.get("product_name", "?"),
                    "price_usdt": price if cur != "VND" else 0,
                    "price_vnd": price if cur == "VND" else 0,
                    "stock": int(stock or 0),
                    "description": desc,
                })
            return {"success": True, "products": prods}

        if method == "POST" and path == "/api/buy":
            payload = payload or {}
            sid = shop.get("id")
            real = _tgb_ids.get(f"{sid}:{payload.get('product_id')}")
            if real is None:
                st, d = await call("GET", "/products")
                if st == 200 and isinstance(d, dict):
                    for p in d.get("products", []):
                        _tgb_num_id(sid, p.get("_id"))
                real = _tgb_ids.get(f"{sid}:{payload.get('product_id')}")
            if real is None:
                return {"success": False, "error": "Товар не найден — открой список товаров заново."}
            status, data = await call("POST", "/purchase",
                                      {"product_id": real, "quantity": payload.get("quantity", 1)},
                                      extra={"Idempotency-Key": uuid.uuid4().hex})
            if status not in (200, 201) or not isinstance(data, dict) or not data.get("success"):
                return {"success": False, "error": _tgb_err(data)}
            items = []
            for acc in data.get("deliveredAccounts") or []:
                raw = acc.get("raw") or " | ".join(
                    str(v).strip() for v in (acc.get("user"), acc.get("password")) if v
                )
                if raw:
                    items.append(str(raw).strip())
            if not items:
                items = [f"Заказ #{data.get('orderCode')} принят — проверь выдачу в шопе."]
            cur = str(data.get("walletCurrency") or "USDT").upper()
            nb = data.get("balance")
            return {
                "success": True,
                "order": {
                    "total_items": data.get("finalQuantity") or data.get("quantity", 0),
                    "total_price": data.get("amount"),
                    "currency": cur,
                },
                "items": items,
                "new_balance": f"{nb} {cur}" if nb is not None else None,
            }

        status, data = await call(method, path.replace("/api", "", 1), payload)
        return data if isinstance(data, dict) else {"success": False, "error": str(data)[:300]}
    except Exception as e:
        return {"success": False, "error": f"Сеть/API недоступен: {e}"}


_legacy_shop_api = shop_api


async def shop_api(shop: dict | None, method: str, path: str, payload: dict | None = None) -> dict:
    """Роутер: выбирает переходник по типу API шопа."""
    if shop and shop.get("key"):
        t = _shop_api_type(shop)
        if t == "reseller":
            return await _reseller_api(shop, method, path, payload)
        if t == "tgbuyer":
            return await _tgbuyer_api(shop, method, path, payload)
    return await _legacy_shop_api(shop, method, path, payload)
