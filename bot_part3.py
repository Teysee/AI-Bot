# ─── AI-Bot: часть 3 — адаптеры API магазинов ──────────────────────────────
# Legacy (X-API-Key), Reseller API (/v1, ключ rsk_...), Buyer API (ключ tgb_...),
# Dorin API (ключ dk_..., X-Api-Key, /api/v1), Roboticvn (ключ apk_..., x-api-key, /api/v2)

import time
import uuid
import zlib


# ─── Reseller API (/v1) — переходник ──────────────────────────────

def _shop_api_type(shop: dict) -> str:
    """Тип API шопа: 'legacy', 'reseller' (rsk_...), 'tgbuyer' (tgb_...), 'dorin' (dk_...)
    или 'roboticvn' (apk_...)."""
    t = shop.get("api_type")
    if t in ("legacy", "reseller", "tgbuyer", "dorin", "roboticvn"):
        return t
    key = str(shop.get("key", ""))
    if key.startswith("rsk_"):
        return "reseller"
    if key.startswith("tgb_"):
        return "tgbuyer"
    if key.startswith("dk_"):
        return "dorin"
    if key.startswith("apk_"):
        return "roboticvn"
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
    """Переходник Buyer API (/api[/v2]/telegram-buyer/...) -> формат первого шопа."""
    base = str(shop.get("base", "")).rstrip("/")
    if "/api/v2/telegram-buyer" in base:
        pass
    elif base.endswith("/api/telegram-buyer"):
        pass
    elif "canboso.com" in base.lower():
        base += "/api/v2/telegram-buyer"
    else:
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


_dorin_ids: dict[str, str] = {}


def _dorin_num_id(sid, sku) -> int:
    num = zlib.crc32(str(sku).encode("utf-8")) & 0x7FFFFFFF
    _dorin_ids[f"{sid}:{num}"] = str(sku)
    return num


def _dorin_err(data) -> str:
    if isinstance(data, dict):
        for k in ("message", "error", "detail"):
            if data.get(k):
                v = data[k]
                return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)[:300]
    return str(data)[:300]


def _dorin_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("products", "items", "data"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def _dorin_num(p: dict, keys: tuple[str, ...], default=0):
    for k in keys:
        if p.get(k) is not None:
            try:
                return float(p[k])
            except (TypeError, ValueError):
                pass
    return default


async def _dorin_api(shop: dict, method: str, path: str, payload: dict | None = None) -> dict:
    """Переходник Dorin API (/api/v1, X-Api-Key, sku) -> формат первого шопа."""
    base = str(shop.get("base", "")).rstrip("/")
    if not base.endswith("/api/v1"):
        base += "/api/v1"
    headers = {"X-Api-Key": shop["key"]}

    async def call(m: str, p: str, body: dict | None = None):
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.request(m, f"{base}{p}", json=body, headers=headers) as resp:
                return resp.status, await resp.json(content_type=None)

    try:
        if method == "GET" and path == "/api/balance":
            status, data = await call("GET", "/balance")
            if status != 200 or not isinstance(data, dict):
                return {"success": False, "error": _dorin_err(data)}
            if data.get("success") is False:
                return {"success": False, "error": _dorin_err(data)}
            bal = _dorin_num(data, ("balance", "balance_usd", "balance_usdt", "usd", "amount"))
            return {
                "success": True,
                "username": data.get("username") or data.get("name") or shop.get("name", "?"),
                "balance_usdt": bal,
                "balance_vnd": -1,
            }

        if method == "GET" and path == "/api/products":
            status, data = await call("GET", "/products")
            if status != 200:
                return {"success": False, "error": _dorin_err(data)}
            sid = shop.get("id")
            prods = []
            for p in _dorin_list(data):
                if not isinstance(p, dict):
                    continue
                sku = p.get("sku") or p.get("id") or p.get("code")
                if sku is None:
                    continue
                stock = _dorin_num(p, ("stock", "available", "qty", "quantity", "count"), 999)
                price = _dorin_num(p, ("price", "price_usd", "price_usdt", "your_price", "amount"))
                prods.append({
                    "id": _dorin_num_id(sid, sku),
                    "name": str(p.get("name") or p.get("title") or sku),
                    "price_usdt": price,
                    "price_vnd": 0,
                    "stock": int(stock),
                    "description": str(p.get("description") or p.get("sku") or ""),
                })
            return {"success": True, "products": prods}

        if method == "POST" and path == "/api/buy":
            payload = payload or {}
            sid = shop.get("id")
            sku = _dorin_ids.get(f"{sid}:{payload.get('product_id')}")
            if sku is None:
                st, d = await call("GET", "/products")
                if st == 200:
                    for p in _dorin_list(d):
                        if isinstance(p, dict):
                            _dorin_num_id(sid, p.get("sku") or p.get("id") or p.get("code"))
                sku = _dorin_ids.get(f"{sid}:{payload.get('product_id')}")
            if sku is None:
                return {"success": False, "error": "Товар не найден — открой список товаров заново."}
            status, data = await call("POST", "/buy", {
                "sku": sku,
                "quantity": payload.get("quantity", 1),
            })
            if status not in (200, 201) or not isinstance(data, dict):
                return {"success": False, "error": _dorin_err(data)}
            if data.get("success") is False:
                return {"success": False, "error": _dorin_err(data)}
            items = [str(c) for c in (data.get("codes") or data.get("items") or data.get("keys") or [])]
            if not items:
                items = [f"Заказ принят (sku {sku}) — проверь выдачу в шопе."]
            nb = data.get("balance")
            if nb is None and isinstance(data.get("new_balance"), (int, float, str)):
                nb = data.get("new_balance")
            return {
                "success": True,
                "order": {
                    "product": data.get("name") or sku,
                    "total_items": data.get("quantity") or len(items),
                    "total_price": data.get("amount") or data.get("total"),
                    "currency": "USD",
                },
                "items": items,
                "new_balance": f"{nb}$" if nb is not None else None,
            }

        status, data = await call(method, path.replace("/api", "", 1), payload)
        return data if isinstance(data, dict) else {"success": False, "error": str(data)[:300]}
    except Exception as e:
        return {"success": False, "error": f"Сеть/API недоступен: {e}"}


# ─── Roboticvn Customer API v2 (ключ apk_...) — переходник ───────────────────
# Товар -> варианты (тарифы). Для бота каждый вариант — отдельный товар.
# Цены и наличие есть только в карточке товара, поэтому список товаров = N запросов;
# кэшируем на _RVN_TTL секунд, чтобы фоновая проверка (раз в 30 с) не упиралась в лимит 120/мин.

_rvn_ids: dict[str, tuple[str, str]] = {}  # "sid:num" -> (product_id, variant_id)
_rvn_cache: dict = {}                      # sid -> {"ts": float, "products": [...]}
_rvn_locks: dict = {}                      # sid -> asyncio.Lock: одна загрузка каталога за раз
_RVN_TTL = 120


def _rvn_base(shop: dict) -> str:
    base = str(shop.get("base", "")).rstrip("/")
    for suffix in ("/docs", "/api/v2"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base + "/api/v2"


def _rvn_ok(status: int, data) -> bool:
    return status < 400 and isinstance(data, dict) and "error" not in data


def _rvn_err(status: int, data) -> str:
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        return str(data["error"].get("message") or data["error"].get("code"))[:300]
    return f"HTTP {status}: {str(data)[:200]}"


def _rvn_delivery_items(data) -> list[str]:
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    if not isinstance(data, dict):
        return []
    items = []
    for a in data.get("delivered_accounts") or data.get("deliveredAccount") or []:
        line = " | ".join(str(v).strip() for v in (a.get("account"), a.get("password")) if v)
        if a.get("additional_info"):
            line = f"{line}\n{a['additional_info']}" if line else str(a["additional_info"])
        items.append(line or str(a.get("display_title") or "?"))
    return items


async def _rvn_load_products(shop: dict, sess, call, cached: dict | None) -> dict:
    """Полная загрузка каталога: список товаров + карточка каждого (варианты, цены, наличие)."""
    sid = shop.get("id")
    stale = {"success": True, "products": cached["products"]} if cached else None
    summaries, offset = [], 0
    while True:
        status, data = await call(sess, "GET", "/products", params={"limit": 100, "offset": offset})
        if not _rvn_ok(status, data):
            return stale or {"success": False, "error": _rvn_err(status, data)}
        batch = data.get("data") or []
        summaries += batch
        if len(batch) < 100:
            break
        offset += 100

    sem = asyncio.Semaphore(6)

    async def detail(pid):
        async with sem:
            return await call(sess, "GET", f"/products/{pid}")

    pids = [p["id"] for p in summaries]
    results = dict(zip(pids, await asyncio.gather(*(detail(x) for x in pids), return_exceptions=True)))
    for x in pids:  # одна повторная попытка для упавших карточек
        r = results[x]
        if isinstance(r, Exception) or not _rvn_ok(*r):
            await asyncio.sleep(1)
            try:
                results[x] = await detail(x)
            except Exception as e:
                results[x] = e
    prods, failed = [], 0
    for res in results.values():
        if isinstance(res, Exception) or not _rvn_ok(*res):
            failed += 1
            continue
        prod = res[1].get("data") or {}
        ptitle = re.sub(r"^[^\w]+", "", prod.get("title") or "").strip() or prod.get("title", "?")
        for v in prod.get("variants") or []:
            prices = v.get("prices") or {}
            num = zlib.crc32(str(v["id"]).encode("utf-8")) & 0x7FFFFFFF
            _rvn_ids[f"{sid}:{num}"] = (prod.get("id"), v["id"])
            parts = (v.get("description"), v.get("delivery_instructions"), prod.get("description"))
            prods.append({
                "id": num,
                "name": f"{ptitle} · {(v.get('title') or '').strip()}",
                "price_usdt": float(prices.get("usd") or 0),
                "price_vnd": 0,
                "stock": int(v.get("available_quantity") or 0) if v.get("in_stock") else 0,
                "description": "\n\n".join(_strip_html(x) for x in parts if x),
            })
    if failed:
        # неполный список нельзя отдавать: его запомнят как снимок, и пропавшие
        # товары потом придут ложными «новинками». Старый полный — можно.
        return stale or {"success": False, "error": f"Roboticvn: не загрузились {failed} карточек, повторю позже."}
    _rvn_cache[sid] = {"ts": time.time(), "products": prods}
    return {"success": True, "products": prods}


async def _rvn_api(shop: dict, method: str, path: str, payload: dict | None = None) -> dict:
    """Переходник Roboticvn (/api/v2, x-api-key) -> формат ответов первого шопа."""
    base = _rvn_base(shop)
    headers = {"x-api-key": shop["key"]}
    sid = shop.get("id")

    async def call(sess, m: str, p: str, body: dict | None = None, params: dict | None = None):
        q = {"locale": "en-US", **(params or {})}
        async with sess.request(m, f"{base}{p}", params=q, json=body, headers=headers) as resp:
            return resp.status, await resp.json(content_type=None)

    try:
        timeout = aiohttp.ClientTimeout(total=90)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            if method == "GET" and path == "/api/balance":
                status, data = await call(sess, "GET", "/wallet/balance")
                if not _rvn_ok(status, data):
                    return {"success": False, "error": _rvn_err(status, data)}
                bal = data.get("data") or {}
                st_me, me = await call(sess, "GET", "/me")
                name = (me.get("data") or {}).get("first_name") if _rvn_ok(st_me, me) else None
                return {
                    "success": True,
                    "username": name or shop.get("name", "?"),
                    "balance_usdt": float(bal.get("usd") or 0),
                    "balance_vnd": -1,
                }

            if method == "GET" and path == "/api/products":
                cached = _rvn_cache.get(sid)
                if cached and time.time() - cached["ts"] < _RVN_TTL:
                    return {"success": True, "products": cached["products"]}
                lock = _rvn_locks.setdefault(sid, asyncio.Lock())
                if lock.locked():
                    # каталог уже грузится (фоновая проверка/другой экран) — ждём его результат,
                    # а не запускаем вторые ~60 запросов в упор в лимит 120/мин
                    async with lock:
                        pass
                    fresh = _rvn_cache.get(sid)
                    if fresh:
                        return {"success": True, "products": fresh["products"]}
                    return {"success": False, "error": "Roboticvn: каталог сейчас недоступен, повторю позже."}
                async with lock:
                    return await _rvn_load_products(shop, sess, call, cached)

            if method == "POST" and path == "/api/buy":
                payload = payload or {}
                ref = _rvn_ids.get(f"{sid}:{payload.get('product_id')}")
                if ref is None:
                    _rvn_cache.pop(sid, None)
                    await _rvn_api(shop, "GET", "/api/products")
                    ref = _rvn_ids.get(f"{sid}:{payload.get('product_id')}")
                if ref is None:
                    return {"success": False, "error": "Товар не найден — открой список товаров заново."}
                pid, vid = ref
                qty = int(payload.get("quantity", 1))

                st_q, q = await call(sess, "POST", f"/products/{pid}/quote",
                                     {"variant_id": vid, "quantity": qty, "currency_code": "usd"})
                if _rvn_ok(st_q, q) and not (q.get("data") or {}).get("can_purchase"):
                    avail = (q.get("data") or {}).get("available_quantity")
                    return {"success": False, "error": f"Нет в наличии столько (есть {avail} шт.)." if avail is not None else "Нет в наличии."}

                status, data = await call(sess, "POST", "/orders", {
                    "items": [{"variant_id": vid, "quantity": qty}],
                    "currency_code": "usd", "payment_method": "wallet",
                })
                if not _rvn_ok(status, data):
                    return {"success": False, "error": _rvn_err(status, data)}
                co = data.get("data") or {}
                order_id = co.get("order_id")
                items: list[str] = []
                for _ in range(5):  # выдача обычно сразу, но даём магазину немного времени
                    st_d, d = await call(sess, "GET", f"/orders/{order_id}/delivery")
                    if st_d < 400:
                        items = _rvn_delivery_items(d)
                        if items:
                            break
                    await asyncio.sleep(3)
                if not items:
                    items = [
                        f"Заказ #{co.get('order_display_id') or order_id} оплачен — магазин ещё выдаёт товар "
                        f"(у некоторых позиций до 24–48 ч). Проверь заказ в боте Roboticvn."
                    ]
                pay = co.get("payment") or {}
                st_b, b = await call(sess, "GET", "/wallet/balance")
                nb = f"{float((b.get('data') or {}).get('usd') or 0):g}$" if _rvn_ok(st_b, b) else None
                name = next((p["name"] for p in (_rvn_cache.get(sid) or {}).get("products", [])
                             if p["id"] == payload.get("product_id")), "")
                _rvn_cache.pop(sid, None)  # остатки изменились
                return {
                    "success": True,
                    "order": {
                        "product": name,
                        "total_items": qty,
                        "total_price": pay.get("amount"),
                        "currency": str(pay.get("currency_code") or "usd").upper(),
                    },
                    "items": items,
                    "new_balance": nb,
                }

            status, data = await call(sess, method, path.replace("/api", "", 1), payload)
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
        if t == "dorin":
            return await _dorin_api(shop, method, path, payload)
        if t == "roboticvn":
            return await _rvn_api(shop, method, path, payload)
    return await _legacy_shop_api(shop, method, path, payload)
