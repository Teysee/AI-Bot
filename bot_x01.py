def _load_json(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        log.exception("Failed to load %s: %s", path, e)
        return []


def _load_json_any(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("Failed to load %s", path)
        return None


def _save_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_accounts() -> list[dict]:
    data = _load_json(DATA_FILE)
    changed = False
    for acc in data:
        if "days" not in acc:
            acc["days"] = 30
            changed = True
    if changed:
        _save_json(DATA_FILE, data)
    return data

def save_accounts(accounts: list[dict]) -> None:
    _save_json(DATA_FILE, accounts)

def load_cdk() -> list[dict]:
    return _load_json(CDK_FILE)

def save_cdk(data: list[dict]) -> None:
    _save_json(CDK_FILE, data)

def load_gemini() -> list[dict]:
    return _load_json(GEMINI_FILE)

def save_gemini(data: list[dict]) -> None:
    _save_json(GEMINI_FILE, data)

def load_chatgpt() -> list[dict]:
    return _load_json(CHATGPT_FILE)

def save_chatgpt(data: list[dict]) -> None:
    _save_json(CHATGPT_FILE, data)

def load_capcut() -> list[dict]:
    return _load_json(CAPCUT_FILE)

def save_capcut(data: list[dict]) -> None:
    _save_json(CAPCUT_FILE, data)

def load_autobuy() -> list[dict]:
    return _load_json(AUTOBUY_FILE)

def save_autobuy(data: list[dict]) -> None:
    _save_json(AUTOBUY_FILE, data)


def load_shops() -> list[dict]:
    shops = _load_json(SHOPS_FILE)
    if not shops and SHOP_API_KEY:
        shops = [{"id": 1, "name": "Основной шоп", "base": SHOP_API_BASE, "key": SHOP_API_KEY, "link": ""}]
        _save_json(SHOPS_FILE, shops)
    return shops

def save_shops(shops: list[dict]) -> None:
    _save_json(SHOPS_FILE, shops)

def get_shop(shop_id: int) -> dict | None:
    return next((s for s in load_shops() if s.get("id") == shop_id), None)

def default_shop() -> dict | None:
    shops = load_shops()
    return shops[0] if shops else None


def load_custom_cats() -> list[dict]:
    return _load_json(CATS_FILE)

def save_custom_cats(cats: list[dict]) -> None:
    _save_json(CATS_FILE, cats)

def all_cats() -> dict[str, dict]:
    cats: dict[str, dict] = dict(SHOP_CATS)
    for c in load_custom_cats():
        key = c.get("key")
        if not key or key in cats:
            continue
        eid = c.get("emoji_id") or ID_BOX
        cats[key] = {
            "title": c.get("title", key),
            "icon": eid,
            "ce": _e(eid, "📦"),
            "match": c.get("match", key.lower()),
            "custom": True,
        }
    return cats

def get_cat(cat: str) -> dict:
    return all_cats().get(cat) or {
        "title": cat, "icon": ID_BOX, "ce": CE_BOX, "match": cat.lower(), "custom": True,
    }


RAW_STORES = {
    "gpt":    (load_chatgpt, save_chatgpt),
    "capcut": (load_capcut,  save_capcut),
}

def store_funcs(cat: str):
    if cat in RAW_STORES:
        return RAW_STORES[cat]
    p = Path(f"store_{cat}.json")
    return (lambda: _load_json(p)), (lambda data: _save_json(p, data))


RE_PIPE_LINE = re.compile(
    r"^([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\s*\|\s*(\S+)(?:\s*\|\s*(\S+))?$"
)


async def shop_api(shop: dict | None, method: str, path: str, payload: dict | None = None) -> dict:
    if not shop or not shop.get("key"):
        return {"success": False, "error": "Шоп не настроен. Добавь: /addshop Название | URL | КЛЮЧ"}
    headers = {"X-API-Key": shop["key"]}
    base = str(shop.get("base", "")).rstrip("/")
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.request(
                method, f"{base}{path}", json=payload, headers=headers
            ) as resp:
                return await resp.json(content_type=None)
    except Exception as e:
        return {"success": False, "error": f"Сеть/API недоступен: {e}"}


def fmt_usdt(v) -> str:
    return f"{float(v):g}$"


DESC_PHRASES = [
    ("Full warranty", "Полная гарантия"),
    ("Non warranty", "Без гарантии"),
    ("No warranty", "Без гарантии"),
    ("7 Days Warranty", "Гарантия 7 дней"),
    ("24 hours holding warranty", "Гарантия удержания 24 часа"),
    ("This product is full warranty", "Товар с полной гарантией"),
    ("Log in directly by Email and Password to Grok", "Вход напрямую по почте и паролю в Grok"),
    ("Log in 2 Devices", "Вход на 2 устройствах"),
    ("DO NOT unlink X account", "НЕ отвязывай аккаунт X"),
    ("DO NOT unlink X", "НЕ отвязывай X"),
    ("DO NOT change mail", "НЕ меняй почту"),
    ("CAN change password", "Можно менять пароль"),
    ("Can be used on any accounts", "Можно активировать на любом аккаунте"),
    ("Do not need Card", "Карта не нужна"),
    ("Can invite 5 more members to family", "Можно пригласить ещё 5 человек в семью"),
    ("Click on the link and confirm", "Перейди по ссылке и подтверди"),
    ("Password Capcut", "Пароль Capcut"),
    ("Password Mail", "Пароль почты"),
    ("Mail website", "Сайт почты"),
    ("2FA site", "Сайт 2FA"),
    ("using hotmail", "используется hotmail"),
    ("NO Renew", "без продления"),
    ("Team Plan", "командный план"),
    ("Month", "мес"),
    ("Year", "год"),
    ("Days", "дней"),
    ("Devices", "устройства"),
    ("Format", "Формат"),
    ("Duration", "Срок"),
    ("Mail", "Почта"),
    ("Password", "Пароль"),
    ("Pay by", "Оплата через"),
]

# continue bot_x02.py
_NEXT = Path(__file__).resolve().with_name('bot_x02.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
