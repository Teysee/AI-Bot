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
# Цены и наличие есть только в карточке товара (1 запрос на товар, их ~60), а лимит
# магазина — 120 запросов/мин на ключ. Поэтому каталог грузится целиком один раз, дальше
# карточки обновляются понемногу (самые старые, по _RVN_PER_PASS за проход), а после
# ответа 429 — пауза _RVN_COOLDOWN, всё это время отдаётся уже загруженный каталог.

_rvn_ids: dict[str, tuple[str, str]] = {}  # "sid:num" -> (product_id, variant_id)
_rvn_state: dict = {}                      # sid -> состояние каталога (см. _rvn_st)
_rvn_locks: dict = {}                      # sid -> asyncio.Lock: один проход обновления за раз
_rvn_names: dict = {}                      # sid -> имя аккаунта из /me (запрашиваем один раз)
_RVN_LIST_TTL = 300    # список товаров перечитываем раз в 5 мин (новинки)
_RVN_CARD_TTL = 240    # карточку старше 4 мин — обновить
_RVN_PER_PASS = 8      # не больше 8 карточек за проход (~16 запросов/мин при проходе раз в 30 с)
_RVN_PASS_GAP = 20     # проходы не чаще раза в 20 с — остальные вызовы берут готовое
_RVN_COOLDOWN = 65     # после 429 — минута тишины
_RVN_BAL_TTL = 20      # баланс кэшируем на 20 с; при автопокупке его заранее освежают раз в 10 с


def _rvn_st(sid) -> dict:
    return _rvn_state.setdefault(sid, {
        "order": [],         # id товаров в порядке магазина
        "cards": {},         # product_id -> (ts, карточка)
        "list_ts": 0.0,
        "pass_ts": 0.0,
        "cooldown": 0.0,
        "products": None,    # последний собранный список для бота (None — ещё ни разу полный)
        "bal": None,         # (ts, ответ /api/balance)
    })


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


def _rvn_build(sid, st: dict) -> list[dict]:
    """Собрать список для бота из загруженных карточек (каждый вариант — позиция)."""
    prods = []
    for pid in st["order"]:
        card = st["cards"].get(pid)
        if not card:
            continue
        prod = card[1]
        ptitle = re.sub(r"^[^\w]+", "", prod.get("title") or "").strip() or prod.get("title", "?")
        for v in prod.get("variants") or []:
            prices = v.get("prices") or {}
            num = zlib.crc32(str(v["id"]).encode("utf-8")) & 0x7FFFFFFF
            _rvn_ids[f"{sid}:{num}"] = (prod.get("id") or pid, v["id"])
            parts = (v.get("description"), v.get("delivery_instructions"), prod.get("description"))
            # остаток: число из available_quantity; «в наличии» без числа — считаем, что есть
            # (покупка всё равно сверяется с котировкой магазина)
            qty = v.get("available_quantity")
            if isinstance(qty, (int, float)) and qty > 0:
                stock = int(qty)
            else:
                stock = 999 if v.get("in_stock") and qty is None else 0
            prods.append({
                "id": num,
                "name": f"{ptitle} · {(v.get('title') or '').strip()}",
                "group": (prod.get("title") or ptitle).strip(),  # товар целиком, с 🔥 — для каталога-сетки
                "price_usdt": float(prices.get("usd") or 0),
                "price_vnd": 0,
                "stock": stock,
                "description": "\n\n".join(_strip_html(x) for x in parts if x),
            })
    return prods


async def _rvn_load_products(shop: dict, sess, call) -> dict:
    """Один проход обновления каталога (вызывать под _rvn_locks[sid])."""
    sid = shop.get("id")
    st = _rvn_st(sid)
    now = time.time()
    ready = {"success": True, "products": st["products"]} if st["products"] is not None else None
    if now < st["cooldown"] or (ready and now - st["pass_ts"] < _RVN_PASS_GAP):
        return ready or {
            "success": False,
            "error": "Roboticvn: магазин ограничил частоту запросов, каталог догрузится через минуту.",
        }
    st["pass_ts"] = now
    limited = False

    # 1) список товаров — редко: он нужен только чтобы заметить новые/убранные товары
    if not st["order"] or now - st["list_ts"] > _RVN_LIST_TTL:
        summaries, offset = [], 0
        while True:
            status, data = await call(sess, "GET", "/products", params={"limit": 100, "offset": offset})
            if status == 429:
                limited = True
                break
            if not _rvn_ok(status, data):
                return ready or {"success": False, "error": _rvn_err(status, data)}
            batch = data.get("data") or []
            summaries += batch
            if len(batch) < 100:
                break
            offset += 100
        if not limited:
            st["order"] = [p["id"] for p in summaries]
            st["list_ts"] = now
            alive = set(st["order"])
            for pid in [p for p in st["cards"] if p not in alive]:
                del st["cards"][pid]

    # 2) карточки: все недостающие + несколько самых старых
    if not limited:
        missing = [pid for pid in st["order"] if pid not in st["cards"]]
        old = sorted((ts, pid) for pid, (ts, _) in st["cards"].items() if now - ts > _RVN_CARD_TTL)
        todo = missing + [pid for _, pid in old[:_RVN_PER_PASS]]
        sem = asyncio.Semaphore(4)

        async def detail(pid):
            nonlocal limited
            async with sem:
                if limited:
                    return  # после первого 429 новые запросы не шлём
                try:
                    status, data = await call(sess, "GET", f"/products/{pid}")
                except Exception:
                    return
                if status == 429:
                    limited = True
                elif _rvn_ok(status, data):
                    st["cards"][pid] = (time.time(), data.get("data") or {})

        await asyncio.gather(*(detail(pid) for pid in todo))

    if limited:
        st["cooldown"] = time.time() + _RVN_COOLDOWN
        log.warning("Roboticvn (shop %s): 429, pause %ss", sid, _RVN_COOLDOWN)

    complete = bool(st["order"]) and all(pid in st["cards"] for pid in st["order"])
    if st["products"] is None and not complete:
        # первый полный каталог ещё не собран: неполный не отдаём — его запомнят как снимок,
        # и недогруженные товары потом придут ложными «новинками»
        got = sum(1 for pid in st["order"] if pid in st["cards"])
        return {
            "success": False,
            "error": f"Roboticvn: загружаю каталог ({got}/{len(st['order']) or '?'}), повтори через минуту.",
        }
    st["products"] = _rvn_build(sid, st)
    return {"success": True, "products": st["products"]}


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
                st = _rvn_st(sid)
                if st["bal"] and time.time() - st["bal"][0] < _RVN_BAL_TTL:
                    return st["bal"][1]
                status, data = await call(sess, "GET", "/wallet/balance")
                if not _rvn_ok(status, data):
                    if status == 429 and st["bal"]:
                        return st["bal"][1]  # упёрлись в лимит — последний известный баланс
                    return {"success": False, "error": _rvn_err(status, data)}
                bal = data.get("data") or {}
                if sid not in _rvn_names:
                    st_me, me = await call(sess, "GET", "/me")
                    if _rvn_ok(st_me, me):
                        _rvn_names[sid] = (me.get("data") or {}).get("first_name")
                res = {
                    "success": True,
                    "username": _rvn_names.get(sid) or shop.get("name", "?"),
                    "balance_usdt": float(bal.get("usd") or 0),
                    "balance_vnd": -1,
                }
                st["bal"] = (time.time(), res)
                return res

            if method == "GET" and path == "/api/products":
                # фоновая проверка и экраны бота встают в очередь: проход обновления один за раз,
                # а пока между проходами < _RVN_PASS_GAP, все получают готовый список
                async with _rvn_locks.setdefault(sid, asyncio.Lock()):
                    return await _rvn_load_products(shop, sess, call)

            if method == "GET" and path == "/api/products/fresh":
                # для автопокупки: свежие карточки только нужных товаров, мимо кэша каталога
                ids = list((payload or {}).get("ids") or [])
                if any(f"{sid}:{i}" not in _rvn_ids for i in ids):
                    await _rvn_api(shop, "GET", "/api/products")  # после перезапуска — узнать id
                st = _rvn_st(sid)
                if time.time() < st["cooldown"]:
                    return {"success": False, "error": "Roboticvn: пауза после лимита запросов."}
                pids = {_rvn_ids[f"{sid}:{i}"][0] for i in ids if f"{sid}:{i}" in _rvn_ids}
                async with _rvn_locks.setdefault(sid, asyncio.Lock()):
                    for pid in pids:
                        status, data = await call(sess, "GET", f"/products/{pid}")
                        if status == 429:
                            st["cooldown"] = time.time() + _RVN_COOLDOWN
                            log.warning("Roboticvn (shop %s): 429 on autobuy check, pause %ss", sid, _RVN_COOLDOWN)
                            # свежих данных нет — не выдаём старые за свежие (автопокупка/диагностика)
                            return {"success": False, "error": "Roboticvn: лимит запросов, пауза."}
                        if _rvn_ok(status, data):
                            st["cards"][pid] = (time.time(), data.get("data") or {})
                    if st["products"] is not None:
                        st["products"] = _rvn_build(sid, st)
                    wanted = set(ids)
                    found = [p for p in _rvn_build(sid, st) if p["id"] in wanted]
                return {"success": True, "products": found}

            if method == "POST" and path == "/api/buy":
                payload = payload or {}
                ref = _rvn_ids.get(f"{sid}:{payload.get('product_id')}")
                if ref is None:
                    st = _rvn_st(sid)
                    st["list_ts"] = st["pass_ts"] = 0.0  # перечитать список при следующем проходе
                    await _rvn_api(shop, "GET", "/api/products")
                    ref = _rvn_ids.get(f"{sid}:{payload.get('product_id')}")
                if ref is None:
                    return {"success": False, "error": "Товар не найден — открой список товаров заново."}
                pid, vid = ref
                qty = int(payload.get("quantity", 1))

                # автопокупка гонится за секундами — пропускает котировку: заказ магазин всё равно
                # проверяет по остатку сам, а лишний запрос перед ним — время, за которое разберут
                if not payload.get("skip_quote"):
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
                st = _rvn_st(sid)
                name = next((p["name"] for p in (st["products"] or [])
                             if p["id"] == payload.get("product_id")), "")
                st["cards"].pop(pid, None)  # остаток этого товара изменился — перечитать карточку
                st["bal"] = None
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
