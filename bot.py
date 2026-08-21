import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from html import escape
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ButtonStyle
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand, MenuButtonCommands,
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("grok-bot")

BOT_TOKEN   = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID    = int(os.getenv("ADMIN_ID", "0"))
DATA_FILE   = Path(os.getenv("DATA_FILE",   "accounts.json"))
CDK_FILE    = Path(os.getenv("CDK_FILE",    "cdk.json"))
GEMINI_FILE = Path(os.getenv("GEMINI_FILE", "gemini.json"))
CHATGPT_FILE = Path(os.getenv("CHATGPT_FILE", "chatgpt.json"))
CAPCUT_FILE  = Path(os.getenv("CAPCUT_FILE",  "capcut.json"))
AUTOBUY_FILE = Path(os.getenv("AUTOBUY_FILE", "autobuy.json"))
PRODUCTS_SEEN_FILE = Path(os.getenv("PRODUCTS_SEEN_FILE", "products_seen.json"))
SHOPS_FILE = Path(os.getenv("SHOPS_FILE", "shops.json"))
CATS_FILE  = Path(os.getenv("CATS_FILE",  "custom_cats.json"))

# Shop API (наследие одиночного шопа — используется как миграция в shops.json)
SHOP_API_BASE = os.getenv("SHOP_API_BASE", "https://tunvnmmo.duckdns.org").rstrip("/")
SHOP_API_KEY  = os.getenv("SHOP_API_KEY", "").strip()
AUTOBUY_INTERVAL = int(os.getenv("AUTOBUY_INTERVAL", "30"))  # сек между проверками наличия

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN env var is required")
if not ADMIN_ID:
    raise SystemExit("ADMIN_ID env var is required")


# ─── Кастомные эмодзи (только в parse_mode="HTML") ───────────────────────────

def _e(eid: str, fb: str) -> str:
    """Обернуть кастомный эмодзи Telegram в HTML-тег."""
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

# Главное меню / разделы — сначала ID (для иконок кнопок), потом HTML-обёртки
ID_GROK   = "5319288443153445517"
ID_GEMINI = "5321197740800120767"
ID_GPT    = "5310259124817134249"
ID_CAPCUT = "5474521476197536994"
ID_LIST   = "5251308525426075254"
ID_COUNT  = "5251579679596372458"
ID_HELP   = "5251588462804491181"
# Действия
ID_BOX    = "5251382119690688965"
ID_OUT    = "5251748480401036448"
ID_IN     = "5251748480401036448"
ID_EMPTY  = "5251650168599632938"
ID_OK     = "5251468620332032765"
ID_NO     = "5249143075929873801"
ID_WARN   = "5251753939304471410"
ID_TRASH  = "5251625210544677220"
ID_KEY    = "5251329076844584285"
ID_EMAIL  = "5251519597298868587"
ID_UP     = "5251625880559574052"
ID_TIP    = "5251621409498619170"
ID_KBD    = "5251317888454777310"
ID_HOME   = "5251606986998439430"
ID_PIN    = "5251504131121634870"
# Дни подписки
ID_D3   = "5251356470145996194"
ID_D7   = "5251521246566307049"
ID_D14  = "5251307915540716107"
ID_D30  = "5251443675161976035"
ID_D60  = "5249101449106840434"

# HTML-обёртки (для текста сообщений, parse_mode="HTML")
CE_GROK   = _e(ID_GROK,   "🤖")
CE_GEMINI = _e(ID_GEMINI, "💎")
CE_GPT    = _e(ID_GPT,    "💬")
CE_CAPCUT = _e(ID_CAPCUT, "✂️")
CE_LIST   = _e(ID_LIST,   "📋")
CE_COUNT  = _e(ID_COUNT,  "📊")
CE_HELP   = _e(ID_HELP,   "❓")
CE_BOX    = _e(ID_BOX,    "📦")
CE_OUT    = _e(ID_OUT,    "📤")
CE_IN     = _e(ID_IN,     "📥")
CE_EMPTY  = _e(ID_EMPTY,  "📭")
CE_OK     = _e(ID_OK,     "✅")
CE_NO     = _e(ID_NO,     "❌")
CE_WARN   = _e(ID_WARN,   "⚠️")
CE_TRASH  = _e(ID_TRASH,  "🗑")
CE_KEY    = _e(ID_KEY,    "🔑")
CE_EMAIL  = _e(ID_EMAIL,  "📧")
CE_UP     = _e(ID_UP,     "⬆️")
CE_TIP    = _e(ID_TIP,    "💡")
CE_KBD    = _e(ID_KBD,    "⌨️")
CE_HOME   = _e(ID_HOME,   "🏠")
CE_PIN    = _e(ID_PIN,    "📌")
CE_D3   = _e(ID_D3,  "⚡")
CE_D7   = _e(ID_D7,  "📅")
CE_D14  = _e(ID_D14, "🌟")
CE_D30  = _e(ID_D30, "👑")
CE_D60  = _e(ID_D60, "🔥")
# Маркер строк в тексте сообщения «выбери срок подписки»
CE_DAY  = _e("5307843983102204243", "📋")

# Встроенные категории шопа: подстрока в названии товара → раздел
SHOP_CATS = {
    "grok":   {"title": "Grok",    "icon": ID_GROK,   "ce": CE_GROK,   "match": "grok"},
    "gemini": {"title": "Gemini",  "icon": ID_GEMINI, "ce": CE_GEMINI, "match": "gemini"},
    "gpt":    {"title": "ChatGPT", "icon": ID_GPT,    "ce": CE_GPT,    "match": "gpt"},
    "capcut": {"title": "CapCut",  "icon": ID_CAPCUT, "ce": CE_CAPCUT, "match": "capcut"},
}


# ─── Паттерны парсинга аккаунтов ─────────────────────────────────────────────
RE_LABELED = re.compile(
    r"(?:E-?mail|Login|User(?:name)?|Логин|Почта|Account)\s*[:\-]\s*(\S+)"
    r"\s*[\r\n]+\s*"
    r"(?:Password|Pass|Пароль|Pwd|Пасс)\s*[:\-]\s*(\S+)",
    re.IGNORECASE,
)
RE_INLINE = re.compile(
    r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"
    r"\s*[|;:\t]\s*"
    r"(?!//)(\S+)"
)
RE_TWO_LINE = re.compile(
    r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"
    r"\s*[\r\n]+\s*"
    r"([^\r\n\s@|;:]{4,})"
)
RE_SPACE = re.compile(
    r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"
    r"\s{1,3}"
    r"([^\r\n\s@|;:]{4,})"
)
RE_GEMINI_URL = re.compile(
    r"https://serviceactivation\.google\.com/subscription/new/\S+"
)

VALID_DAYS = (3, 7, 14, 30, 60)

# Кастомные эмодзи для сроков (в тексте сообщений, HTML)
DAYS_EMOJI = {3: CE_D3, 7: CE_D7, 14: CE_D14, 30: CE_D30, 60: CE_D60}
# Обычные эмодзи для сроков (в тексте кнопок — HTML не работает)
DAYS_EMOJI_P = {3: "⚡", 7: "📅", 14: "🌟", 30: "👑", 60: "🔥"}

# Типы подписки, у которых есть CDK
CDK_SUPPORTED = {3, 30, 60}
# Типы подписки, у которых ТОЛЬКО CDK (аккаунтов нет)
CDK_ONLY = {60}

# Паттерны CDK-ключей: (regex, days)
CDK_PATTERNS = [
    (re.compile(r"^3TG-[A-Z0-9]+$",   re.IGNORECASE), 3),   # ⚡ 3 дня
    (re.compile(r"^bbg[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                                       re.IGNORECASE), 30),  # 👑 30 дней (1 мес)
    (re.compile(r"^GGG-[A-Z0-9]+$",   re.IGNORECASE), 60),  # 🔥 60 дней (2 мес)
]

HELP_TEXT = (
    f"{CE_BOX} <b>Склад подписок</b>\n\n"
    f"{CE_OUT} <b>Как выдавать:</b>\n"
    f"Нажми {CE_GROK} <b>Grok</b>, {CE_GEMINI} <b>Gemini</b>, {CE_GPT} <b>ChatGPT</b> "
    f"или {CE_CAPCUT} <b>CapCut</b> → выбери раздел\n\n"
    f"{CE_TIP} В каждом разделе: <b>Купить</b> — покупка через шоп "
    f"(сейчас или автопокупка при появлении), <b>Хранилище</b> — выдача со склада\n\n"
    f"{CE_LIST} /list — список Grok-аккаунтов\n"
    f"{CE_COUNT} /count — статистика всего склада\n"
    f"{CE_TRASH} /use N — удалить аккаунт №N\n"
    f"{CE_WARN} /clear — очистить Grok-склад\n"
    f"{CE_KEY} /settoken TOKEN — сменить токен бота\n"
    f"{CE_KEY} /setapikey КЛЮЧ — API-ключ шопа\n"
    f"{CE_BOX} /shops — магазины и балансы\n"
    f"{CE_IN} /addshop — подключить новый шоп\n"
    f"{CE_PIN} /newcat Название — новый раздел товаров\n"
    f"{CE_TIP} /setemoji — сменить эмодзи раздела\n"
    f"{CE_UP} /update — обновить бота с GitHub\n\n"
    f"{CE_TIP} Кнопки пропали? Отправь /start"
)

_lock = asyncio.Lock()
pending_add: dict[int, list[dict]] = {}
pending_clear: set[int] = set()
pending_buy: dict[int, dict] = {}      # user_id -> {"p": product, "cat": str, "shop_id": int, "qty": int}
pending_store: dict[int, list[str]] = {}  # user_id -> строки "mail | pass [| 2fa]" для добавления
pending_emoji: dict[int, str] = {}     # user_id -> ключ раздела, ждём эмодзи для кнопки
gpt_prod_cache: dict[str, dict] = {}   # "shop_id:product_id" -> product (снимок /api/products)


# ─── Работа с файлами ─────────────────────────────────────────────────────

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
    """Загрузить JSON любого типа (dict/list), None если файла нет или битый."""
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


# ─── Шопы (несколько магазинов) ──────────────────────────────────────────

def load_shops() -> list[dict]:
    shops = _load_json(SHOPS_FILE)
    if not shops and SHOP_API_KEY:
        # миграция со старого одиночного шопа из .env
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


# ─── Пользовательские разделы товаров ────────────────────────────────────

def load_custom_cats() -> list[dict]:
    return _load_json(CATS_FILE)

def save_custom_cats(cats: list[dict]) -> None:
    _save_json(CATS_FILE, cats)

def all_cats() -> dict[str, dict]:
    """Встроенные + пользовательские разделы."""
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


RAW_STORES = {  # встроенные разделы со складом формата "raw"-строк
    "gpt":    (load_chatgpt, save_chatgpt),
    "capcut": (load_capcut,  save_capcut),
}

def store_funcs(cat: str):
    """(load, save) для склада раздела. Для новых разделов — файл store_<key>.json."""
    if cat in RAW_STORES:
        return RAW_STORES[cat]
    p = Path(f"store_{cat}.json")
    return (lambda: _load_json(p)), (lambda data: _save_json(p, data))


# Аккаунт через "|": "mail | password" или "mail | password | 2fa" (форматы шопа)
RE_PIPE_LINE = re.compile(
    r"^([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\s*\|\s*(\S+)(?:\s*\|\s*(\S+))?$"
)


# ─── Shop API ───────────────────────────────────────────────────────────────

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


# Словарь перевода частых фраз из описаний магазина (VN/EN → RU)
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


def translate_desc(text: str) -> str:
    """Взять англ. часть описания (после разделителя ===) и перевести частые фразы на RU."""
    if not text:
        return ""
    # Многие описания: вьетнамская часть === английская часть. Берём английскую.
    parts = re.split(r"={3,}", text)
    chunk = text
    for part in parts:
        if re.search(r"[A-Za-z]", part) and not re.search(r"[àáảãạăâđêôơưọầấ]", part.lower()):
            chunk = part
            break
    lines = [ln.strip() for ln in chunk.splitlines()]
    out = []
    for ln in lines:
        if not ln:
            continue
        for en, ru in DESC_PHRASES:
            # \b — только целые слова, чтобы не портить URL (email и т.п.)
            ln = re.sub(rf"\b{re.escape(en)}\b", ru, ln, flags=re.IGNORECASE)
        out.append(ln)
    return "\n".join(out).strip()


def cat_filter(products: list[dict], cat: str) -> list[dict]:
    match = get_cat(cat)["match"]
    return [p for p in products if match in p.get("name", "").lower()]

def prod_short_name(name: str, cat: str) -> str:
    """Убрать название категории из имени товара для кнопки."""
    n = re.sub(r"^[^A-Za-z0-9]+", "", name)  # срезать эмодзи/символы в начале
    n = re.sub(r"(?i)^(chat\s*gpt|grok|link\s+gemini|gemini|capcut)\s*(plus|super|pro(\s+team)?)?\s*", "", n).strip(" -")
    return n or name


async def pick_currency(shop: dict, total_vnd: float, total_usdt: float) -> tuple[str | None, dict]:
    """Выбрать валюту, на которую хватает баланса. Возвращает (валюта|None, balance-ответ)."""
    bal = await shop_api(shop, "GET", "/api/balance")
    if not bal.get("success"):
        return None, bal
    if bal.get("balance_vnd", 0) >= total_vnd:
        return "vnd", bal
    if bal.get("balance_usdt", 0) >= total_usdt:
        return "usdt", bal
    return None, bal


async def send_items_chunks(send_func, header: str, items: list[str]) -> None:
    """Отправить купленные аккаунты порциями (лимит Telegram 4096)."""
    blocks = [f"<code>{escape(str(i))}</code>" for i in items]
    cur = header
    parts: list[str] = []
    for b in blocks:
        if len(cur) + len(b) + 2 > 3800:
            parts.append(cur)
            cur = b
        else:
            cur = f"{cur}\n\n{b}" if cur else b
    if cur:
        parts.append(cur)
    for part in parts:
        await send_func(part)


def parse_accounts(text: str) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()

    def add(email: str, password: str) -> None:
        e = email.strip().lower()
        p = password.strip()
        if not e or not p or len(p) < 3:
            return
        if e in seen:
            return
        seen.add(e)
        results.append({"email": email.strip(), "password": p})

    for m in RE_LABELED.finditer(text):
        add(m.group(1), m.group(2))
    for m in RE_INLINE.finditer(text):
        add(m.group(1), m.group(2))
    for m in RE_TWO_LINE.finditer(text):
        add(m.group(1), m.group(2))
    for m in RE_SPACE.finditer(text):
        add(m.group(1), m.group(2))

    return results


# ─── Форматирование ─────────────────────────────────────────────────────────

def days_label(days: int) -> str:
    """Метка срока для использования внутри HTML-сообщений."""
    return f"{DAYS_EMOJI.get(days, CE_PIN)} {days}д"


def format_account_block(a: dict) -> str:
    return (
        f"<code>Email : {escape(a['email'])}\n"
        f"Password : {escape(a['password'])}</code>"
    )


def format_grok_list(accounts: list[dict]) -> str:
    if not accounts:
        return "Хранилище пустое."
    groups: dict[int, list[tuple[int, dict]]] = {}
    for i, a in enumerate(accounts, 1):
        d = a.get("days", 30)
        groups.setdefault(d, []).append((i, a))
    lines = []
    for d in sorted(groups.keys()):
        em = DAYS_EMOJI.get(d, CE_PIN)
        lines.append(f"\n{em} <b>{d} дней</b> — {len(groups[d])} шт.")
        for idx, a in groups[d]:
            lines.append(
                f"  {idx}. <code>{escape(a['email'])}</code>  |  "
                f"<code>{escape(a['password'])}</code>"
            )
    return "\n".join(lines)


# ─── Клавиатуры ─────────────────────────────────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    # Кастомные эмодзи на кнопках через icon_custom_emoji_id (Bot API 9.4+).
    # Разделы (встроенные + пользовательские) — по 2 кнопки в ряд.
    cats = all_cats()
    cat_btns = [
        KeyboardButton(text=c["title"], icon_custom_emoji_id=c["icon"])
        for c in cats.values()
    ]
    rows = [cat_btns[i:i + 2] for i in range(0, len(cat_btns), 2)]
    rows.append([
        KeyboardButton(text="Список", icon_custom_emoji_id=ID_LIST),
        KeyboardButton(text="Счёт",   icon_custom_emoji_id=ID_COUNT),
    ])
    rows.append([KeyboardButton(text="Помощь", icon_custom_emoji_id=ID_HELP)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
    )

MK = main_keyboard()

def refresh_mk() -> None:
    """Перестроить нижнюю клавиатуру после изменения разделов."""
    global MK
    MK = main_keyboard()


def grok_days_keyboard() -> InlineKeyboardMarkup:
    # Inline-кнопки — тоже plain text
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="3 дня",         callback_data="grok_d:3",  style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_D3),
            InlineKeyboardButton(text="7 дней",        callback_data="grok_d:7",  style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_D7),
        ],
        [
            InlineKeyboardButton(text="14 дней",       callback_data="grok_d:14", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_D14),
            InlineKeyboardButton(text="30 дней",       callback_data="grok_d:30", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_D30),
        ],
        [
            InlineKeyboardButton(text="60 дней (CDK)", callback_data="grok_d:60", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_D60),
        ],
        [InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
    ])


def grok_type_keyboard(days: int, has_cdk: bool = True) -> InlineKeyboardMarkup:
    acc_btn = InlineKeyboardButton(
        text="Аккаунт", callback_data=f"grok_acc:{days}", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_EMAIL
    )
    cdk_btn = InlineKeyboardButton(
        text="CDK", callback_data=f"grok_cdk:{days}", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_KEY
    ) if has_cdk else InlineKeyboardButton(
        text="CDK (скоро)", callback_data="grok_cdk_soon", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_KEY
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [acc_btn, cdk_btn],
        [InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
    ])


def cat_menu_keyboard(cat: str, watch_count: int = 0) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="Купить",    callback_data=f"shop_buy:{cat}",   style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_OUT),
        InlineKeyboardButton(text="Хранилище", callback_data=f"shop_store:{cat}", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_BOX),
    ]]
    if watch_count:
        rows.append([InlineKeyboardButton(
            text=f"Автопокупки ({watch_count})", callback_data=f"shop_watch:{cat}",
            style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_PIN,
        )])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_days_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="3 дня",   callback_data="add_days:3",  style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_D3),
            InlineKeyboardButton(text="7 дней",  callback_data="add_days:7",  style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_D7),
        ],
        [
            InlineKeyboardButton(text="14 дней", callback_data="add_days:14", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_D14),
            InlineKeyboardButton(text="30 дней", callback_data="add_days:30", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_D30),
        ],
        [InlineKeyboardButton(text="Отмена", callback_data="add_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
    ])


def _shops_keyboard(cat: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=s.get("name", f"Шоп {s.get('id', '?')}"),
            callback_data=f"shop_sel:{cat}:{s.get('id')}",
            style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_BOX,
        )]
        for s in load_shops()
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"shop_menu:{cat}", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_admin(msg: Message) -> bool:
    return msg.from_user is not None and msg.from_user.id == ADMIN_ID

def is_admin_cb(cb: CallbackQuery) -> bool:
    return cb.from_user is not None and cb.from_user.id == ADMIN_ID


dp = Dispatcher()


# ─── /start, /help ──────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message):
        return
    refresh_mk()
    await message.answer(HELP_TEXT, parse_mode="HTML")
    await message.answer(
        f"{CE_KBD} <b>Панель управления</b>\n"
        f"<i>Не удаляй это сообщение — оно держит кнопки внизу.</i>",
        parse_mode="HTML",
        reply_markup=MK,
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not is_admin(message):
        return
    await message.answer(HELP_TEXT, parse_mode="HTML", reply_markup=MK)


# ─── /update — обновление с GitHub ─────────────────────────────────────────

@dp.message(Command("update"))
async def cmd_update(message: Message):
    """Подтянуть свежий код с GitHub и перезапуститься."""
    if not is_admin(message):
        return
    await message.answer(f"{CE_UP} Проверяю обновления на GitHub...", parse_mode="HTML")
    repo_dir = Path(__file__).resolve().parent
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo_dir), "pull", "--ff-only",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        result = (out_b or b"").decode("utf-8", "replace").strip()
    except Exception as e:
        await message.answer(
            f"{CE_NO} Не удалось выполнить git pull:\n<code>{escape(str(e))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    if "Already up to date" in result or "Already up-to-date" in result:
        await message.answer(f"{CE_OK} Уже стоит последняя версия.", parse_mode="HTML", reply_markup=MK)
        return
    if proc.returncode != 0:
        await message.answer(
            f"{CE_NO} git pull завершился с ошибкой:\n<code>{escape(result[-1500:])}</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    await message.answer(
        f"{CE_OK} <b>Код обновлён!</b>\n<code>{escape(result[-1000:])}</code>\n\n"
        f"{CE_UP} Перезапускаюсь...",
        parse_mode="HTML", reply_markup=MK,
    )
    try:
        subprocess.Popen(["sudo", "systemctl", "restart", "grok-bot"])
    except Exception:
        os.execv(sys.executable, [sys.executable] + sys.argv)


# ─── /count, /list ──────────────────────────────────────────────────────────

@dp.message(Command("count"))
async def cmd_count(message: Message):
    if not is_admin(message):
        return
    await _send_count(message)


@dp.message(Command("list"))
async def cmd_list(message: Message):
    if not is_admin(message):
        return
    await _send_list(message)


async def _send_count(message: Message) -> None:
    accounts   = load_accounts()
    cdk_list   = load_cdk()
    gemini_lst = load_gemini()

    lines = [f"{CE_COUNT} <b>Склад подписок</b>\n"]

    # Grok accounts
    lines.append(f"{CE_GROK} <b>Grok аккаунты:</b>")
    if accounts:
        bd: dict[int, int] = {}
        for a in accounts:
            d = a.get("days", 30)
            bd[d] = bd.get(d, 0) + 1
        for d in VALID_DAYS:
            if d in CDK_ONLY:
                continue
            lines.append(f"  {DAYS_EMOJI.get(d, CE_PIN)} {d}д: <b>{bd.get(d, 0)}</b> шт.")
        lines.append(f"  Итого: <b>{len(accounts)}</b> шт.")
    else:
        lines.append("  <i>пусто</i>")

    # CDK
    lines.append(f"\n{CE_KEY} <b>CDK коды:</b>")
    if cdk_list:
        cbd: dict[int, int] = {}
        for c in cdk_list:
            d = c.get("days", 3)
            cbd[d] = cbd.get(d, 0) + 1
        for d, cnt in sorted(cbd.items()):
            lines.append(f"  {DAYS_EMOJI.get(d, CE_PIN)} {d}д: <b>{cnt}</b> шт.")
        lines.append(f"  Итого: <b>{len(cdk_list)}</b> шт.")
    else:
        lines.append("  <i>пусто</i>")

    # Gemini
    lines.append(f"\n{CE_GEMINI} <b>Gemini ссылки:</b> <b>{len(gemini_lst)}</b> шт.")
    if not gemini_lst:
        lines.append("  <i>пусто</i>")

    # ChatGPT
    gpt_store = load_chatgpt()
    lines.append(f"\n{CE_GPT} <b>ChatGPT аккаунты:</b> <b>{len(gpt_store)}</b> шт.")
    if not gpt_store:
        lines.append("  <i>пусто</i>")

    # CapCut
    cc_store = load_capcut()
    lines.append(f"\n{CE_CAPCUT} <b>CapCut аккаунты:</b> <b>{len(cc_store)}</b> шт.")
    if not cc_store:
        lines.append("  <i>пусто</i>")

    # Пользовательские разделы
    for key, c in all_cats().items():
        if not c.get("custom"):
            continue
        load_fn, _ = store_funcs(key)
        lines.append(f"\n{c['ce']} <b>{escape(c['title'])} аккаунты:</b> <b>{len(load_fn())}</b> шт.")

    watches = load_autobuy()
    if watches:
        total = sum(w.get("qty_left", 0) for w in watches)
        lines.append(f"  {CE_PIN} Автопокупок активно: <b>{len(watches)}</b> (ждём {total} шт.)")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=MK)


async def _send_list(message: Message) -> None:
    accounts = load_accounts()
    if not accounts:
        await message.answer(f"{CE_EMPTY} Grok-склад пустой.", parse_mode="HTML", reply_markup=MK)
        return
    full = f"{CE_LIST} <b>Grok аккаунты — {len(accounts)} шт.</b>\n" + format_grok_list(accounts)
    for chunk_start in range(0, len(full), 3800):
        chunk = full[chunk_start:chunk_start + 3800]
        if chunk_start + 3800 >= len(full):
            await message.answer(chunk, parse_mode="HTML", reply_markup=MK)
        else:
            await message.answer(chunk, parse_mode="HTML")


# ─── /get, /use, /clear ─────────────────────────────────────────────────────

@dp.message(Command("get"))
async def cmd_get(message: Message, command):
    if not is_admin(message):
        return
    args = (command.args or "").strip().split()
    if len(args) != 1 or not args[0].isdigit():
        await message.answer("Использование: /get N", reply_markup=MK)
        return
    n = int(args[0])
    accounts = load_accounts()
    if n < 1 or n > len(accounts):
        await message.answer(f"Нет аккаунта №{n}. Всего: {len(accounts)}.", reply_markup=MK)
        return
    a = accounts[n - 1]
    await message.answer(
        f"#{n} {days_label(a.get('days', 30))}\n{format_account_block(a)}",
        parse_mode="HTML", reply_markup=MK,
    )


@dp.message(Command("use"))
async def cmd_use(message: Message, command):
    if not is_admin(message):
        return
    args = (command.args or "").strip().split()
    if not args or not all(x.isdigit() for x in args):
        await message.answer("Использование: /use N  или  /use N1 N2 N3 ...", reply_markup=MK)
        return
    indexes = sorted({int(x) for x in args}, reverse=True)
    async with _lock:
        accounts = load_accounts()
        removed, skipped = [], []
        for n in indexes:
            if 1 <= n <= len(accounts):
                removed.append((n, accounts.pop(n - 1)))
            else:
                skipped.append(n)
        save_accounts(accounts)
    parts = []
    if removed:
        lines = [f"  №{n}: {escape(a['email'])} {days_label(a.get('days',30))}" for n, a in sorted(removed)]
        parts.append(f"{CE_TRASH} <b>Удалены:</b>\n" + "\n".join(lines))
    if skipped:
        parts.append(f"{CE_WARN} Не найдены: " + ", ".join(f"№{n}" for n in skipped))
    parts.append(f"<i>Осталось: {len(accounts)} шт.</i>")
    await message.answer("\n\n".join(parts), parse_mode="HTML", reply_markup=MK)


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    if not is_admin(message):
        return
    pending_clear.add(message.from_user.id)
    await message.answer(
        f"{CE_WARN} <b>Точно очистить ВСЁ Grok-хранилище?</b>\n/yes — подтвердить  |  /no — отмена",
        parse_mode="HTML", reply_markup=MK,
    )

@dp.message(Command("yes"))
async def cmd_yes(message: Message):
    if not is_admin(message):
        return
    if message.from_user.id in pending_clear:
        pending_clear.discard(message.from_user.id)
        async with _lock:
            save_accounts([])
        await message.answer(f"{CE_OK} Grok-хранилище очищено.", parse_mode="HTML", reply_markup=MK)

@dp.message(Command("no"))
async def cmd_no(message: Message):
    if not is_admin(message):
        return
    if message.from_user.id in pending_clear:
        pending_clear.discard(message.from_user.id)
        await message.answer(f"{CE_NO} Отменено.", parse_mode="HTML", reply_markup=MK)


# ─── /getchar — вытащить сырой символ кастомного эмодзи для кнопок ──────────

@dp.message(Command("getchar"))
async def cmd_getchar(message: Message):
    if not is_admin(message):
        return
    # Работает и с ответом на сообщение, и с самим сообщением
    target = message.reply_to_message or message
    entities = target.entities or []
    custom = [e for e in entities if e.type == "custom_emoji"]
    if not custom:
        await message.answer(
            "Не нашёл кастомных эмодзи.\n"
            "Отправь сообщение с кастомным эмодзи из пака, затем ответь на него /getchar",
            reply_markup=MK,
        )
        return
    txt = target.text or ""
    lines = ["<b>Символы кастомных эмодзи:</b>\n"]
    for ent in custom:
        char = txt[ent.offset : ent.offset + ent.length]
        codepoints = " ".join(f"U+{ord(c):04X}" for c in char)
        py_repr = repr(char)
        lines.append(
            f"ID: <code>{ent.custom_emoji_id}</code>\n"
            f"Символ: {char}\n"
            f"Python repr: <code>{escape(py_repr)}</code>\n"
            f"Codepoints: <code>{codepoints}</code>\n"
        )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=MK)


# ─── /settoken ──────────────────────────────────────────────────────────────

@dp.message(Command("settoken"))
async def cmd_settoken(message: Message, command):
    if not is_admin(message):
        return
    new_token = (command.args or "").strip()
    if not new_token or ":" not in new_token:
        await message.answer(
            f"{CE_KEY} Использование: <code>/settoken НОВ_ТОКЕН</code>\nПолучи у @BotFather.",
            parse_mode="HTML", reply_markup=MK,
        )
        return

    env_path = Path(__file__).parent / ".env"
    try:
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
            new_lines, replaced = [], False
            for line in lines:
                if line.startswith("BOT_TOKEN="):
                    new_lines.append(f"BOT_TOKEN={new_token}")
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append(f"BOT_TOKEN={new_token}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            env_path.write_text(f"BOT_TOKEN={new_token}\nADMIN_ID={ADMIN_ID}\n", encoding="utf-8")
    except Exception as e:
        await message.answer(
            f"{CE_NO} Не удалось обновить .env:\n<code>{escape(str(e))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return

    await message.answer(f"{CE_OK} Токен обновлён. Перезапускаю...", parse_mode="HTML", reply_markup=MK)
    try:
        subprocess.Popen(["sudo", "systemctl", "restart", "grok-bot"])
    except Exception:
        os.execv(sys.executable, [sys.executable] + sys.argv)


@dp.message(Command("setapikey"))
async def cmd_setapikey(message: Message, command):
    """Задать API-ключ основного (первого) шопа."""
    if not is_admin(message):
        return
    new_key = (command.args or "").strip()
    if not new_key or len(new_key) < 16:
        await message.answer(
            f"{CE_KEY} Использование: <code>/setapikey КЛЮЧ</code>\n"
            f"Ключ шопа — команда /apikey в боте магазина.\n"
            f"{CE_TIP} Другие магазины: /addshop",
            parse_mode="HTML", reply_markup=MK,
        )
        return

    env_path = Path(__file__).parent / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        new_lines, replaced = [], False
        for line in lines:
            if line.startswith("SHOP_API_KEY="):
                new_lines.append(f"SHOP_API_KEY={new_key}")
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(f"SHOP_API_KEY={new_key}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as e:
        await message.answer(
            f"{CE_NO} Не удалось обновить .env:\n<code>{escape(str(e))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return

    global SHOP_API_KEY
    SHOP_API_KEY = new_key
    shops = load_shops()
    if shops:
        shops[0]["key"] = new_key
        save_shops(shops)
        shop = shops[0]
    else:
        shop = {"id": 1, "name": "Основной шоп", "base": SHOP_API_BASE, "key": new_key, "link": ""}
        save_shops([shop])
    bal = await shop_api(shop, "GET", "/api/balance")
    if bal.get("success"):
        await message.answer(
            f"{CE_OK} API-ключ сохранён и работает!\n"
            f"Аккаунт: <b>{escape(str(bal.get('username', '?')))}</b>\n"
            f"Баланс: <b>{fmt_usdt(bal.get('balance_usdt', 0))}</b>",
            parse_mode="HTML", reply_markup=MK,
        )
    else:
        await message.answer(
            f"{CE_WARN} Ключ сохранён, но проверка не прошла:\n"
            f"<code>{escape(str(bal.get('error')))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )


# ─── Шопы: /shops, /addshop, /delshop, /shoplink ─────────────────────────────

@dp.message(Command("shops"))
async def cmd_shops(message: Message):
    if not is_admin(message):
        return
    shops = load_shops()
    if not shops:
        await message.answer(
            f"{CE_EMPTY} Шопы не подключены.\n"
            f"Добавь: <code>/addshop Название | https://api-url | КЛЮЧ | ссылка_для_пополнения</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    lines = [f"{CE_BOX} <b>Подключённые шопы:</b>\n"]
    for s in shops:
        bal = await shop_api(s, "GET", "/api/balance")
        if bal.get("success"):
            bal_s = fmt_usdt(bal.get("balance_usdt", 0))
        else:
            bal_s = f"{CE_NO} нет связи"
        link = s.get("link") or "—"
        lines.append(
            f"<b>{s.get('id', '?')}. {escape(s.get('name', '?'))}</b>\n"
            f"  Баланс: <b>{bal_s}</b>\n"
            f"  API: <code>{escape(s.get('base', ''))}</code>\n"
            f"  Пополнение: {escape(link)}"
        )
    lines.append(
        f"\n{CE_TIP} <code>/addshop Название | URL | КЛЮЧ | ссылка</code>\n"
        f"/shoplink N ссылка — кнопка пополнения\n"
        f"/delshop N — убрать шоп"
    )
    await message.answer("\n\n".join(lines), parse_mode="HTML", reply_markup=MK)


@dp.message(Command("addshop"))
async def cmd_addshop(message: Message, command):
    if not is_admin(message):
        return
    raw = (command.args or "").strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3 or not parts[0] or not parts[1].startswith("http") or len(parts[2]) < 8:
        await message.answer(
            f"{CE_KEY} Использование:\n"
            f"<code>/addshop Название | https://api-url | API_КЛЮЧ | ссылка_для_пополнения</code>\n"
            f"(ссылка необязательна — можно добавить потом через /shoplink)",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    name, base, key = parts[0], parts[1].rstrip("/"), parts[2]
    link = parts[3] if len(parts) > 3 else ""
    shops = load_shops()
    new_id = max((s.get("id", 0) for s in shops), default=0) + 1
    shop = {"id": new_id, "name": name, "base": base, "key": key, "link": link}
    bal = await shop_api(shop, "GET", "/api/balance")
    shops.append(shop)
    save_shops(shops)
    if bal.get("success"):
        await message.answer(
            f"{CE_OK} <b>Шоп «{escape(name)}» подключён!</b>\n"
            f"Аккаунт: <b>{escape(str(bal.get('username', '?')))}</b>\n"
            f"Баланс: <b>{fmt_usdt(bal.get('balance_usdt', 0))}</b>",
            parse_mode="HTML", reply_markup=MK,
        )
    else:
        await message.answer(
            f"{CE_WARN} Шоп «{escape(name)}» сохранён, но проверка не прошла:\n"
            f"<code>{escape(str(bal.get('error')))}</code>\n"
            f"{CE_TIP} Проверь URL и ключ — можно удалить (/delshop {new_id}) и добавить заново.",
            parse_mode="HTML", reply_markup=MK,
        )


@dp.message(Command("delshop"))
async def cmd_delshop(message: Message, command):
    if not is_admin(message):
        return
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Использование: /delshop N (номер из /shops)", reply_markup=MK)
        return
    sid = int(arg)
    shops = load_shops()
    shop = next((s for s in shops if s.get("id") == sid), None)
    if not shop:
        await message.answer(f"Нет шопа №{sid}.", reply_markup=MK)
        return
    shops = [s for s in shops if s.get("id") != sid]
    save_shops(shops)
    await message.answer(
        f"{CE_TRASH} Шоп «{escape(shop.get('name', '?'))}» удалён.",
        parse_mode="HTML", reply_markup=MK,
    )


@dp.message(Command("shoplink"))
async def cmd_shoplink(message: Message, command):
    if not is_admin(message):
        return
    args = (command.args or "").strip().split(maxsplit=1)
    if len(args) != 2 or not args[0].isdigit() or not args[1].startswith("http"):
        await message.answer(
            "Использование: /shoplink N https://t.me/шоп_бот\n"
            "Эта ссылка будет на кнопке «Пополнить баланс».",
            reply_markup=MK,
        )
        return
    sid, link = int(args[0]), args[1]
    shops = load_shops()
    shop = next((s for s in shops if s.get("id") == sid), None)
    if not shop:
        await message.answer(f"Нет шопа №{sid}.", reply_markup=MK)
        return
    shop["link"] = link
    save_shops(shops)
    await message.answer(
        f"{CE_OK} Ссылка для «{escape(shop.get('name', '?'))}» сохранена — появится кнопка пополнения.",
        parse_mode="HTML", reply_markup=MK,
    )


# ─── Разделы: /newcat, /delcat, /setemoji ────────────────────────────────────

def _make_cat_key(title: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "", title.lower())[:16]
    return key or f"cat{len(load_custom_cats()) + 1}"


async def _create_custom_cat(message: Message, title: str) -> None:
    key = _make_cat_key(title)
    cats = load_custom_cats()
    if any(c.get("key") == key for c in cats) or key in SHOP_CATS:
        await message.answer(f"{CE_WARN} Раздел «{escape(title)}» уже есть.", parse_mode="HTML", reply_markup=MK)
        return
    cats.append({"key": key, "title": title.capitalize(), "match": title.lower(), "emoji_id": None})
    save_custom_cats(cats)
    refresh_mk()
    pending_emoji[ADMIN_ID] = key
    await message.answer(
        f"{CE_OK} <b>Раздел «{escape(title.capitalize())}» создан!</b>\n"
        f"Товары со словом «{escape(title.lower())}» в названии попадут в него.\n\n"
        f"{CE_TIP} Теперь пришли <b>эмодзи</b> для кнопки раздела:\n"
        f"кастомный из премиум-пака станет иконкой, обычный добавится в название.\n"
        f"Или /skip — оставить стандартную иконку.",
        parse_mode="HTML", reply_markup=MK,
    )


@dp.message(Command("newcat"))
async def cmd_newcat(message: Message, command):
    if not is_admin(message):
        return
    title = (command.args or "").strip()
    if not title:
        await message.answer("Использование: /newcat Название (например: /newcat Netflix)", reply_markup=MK)
        return
    await _create_custom_cat(message, title)


@dp.message(Command("delcat"))
async def cmd_delcat(message: Message):
    if not is_admin(message):
        return
    cats = load_custom_cats()
    if not cats:
        await message.answer("Пользовательских разделов нет. Создай: /newcat Название", reply_markup=MK)
        return
    rows = [[InlineKeyboardButton(
        text=c.get("title", c.get("key", "?")), callback_data=f"delcat:{c.get('key')}",
        style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_TRASH,
    )] for c in cats]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_NO)])
    await message.answer(
        f"{CE_TRASH} <b>Какой раздел удалить?</b>\n<i>(склад раздела при этом не стирается)</i>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("delcat:"))
async def cb_delcat(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    key = cb.data.split(":")[1]
    cats = [c for c in load_custom_cats() if c.get("key") != key]
    save_custom_cats(cats)
    refresh_mk()
    await cb.answer("Удалено.")
    await cb.message.edit_text(
        f"{CE_OK} Раздел удалён. Нажми /start, чтобы кнопки внизу обновились.",
        parse_mode="HTML",
    )


@dp.message(Command("setemoji"))
async def cmd_setemoji(message: Message):
    if not is_admin(message):
        return
    cats = load_custom_cats()
    if not cats:
        await message.answer("Пользовательских разделов нет. Создай: /newcat Название", reply_markup=MK)
        return
    rows = [[InlineKeyboardButton(
        text=c.get("title", "?"), callback_data=f"setemoji:{c.get('key')}",
        style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_TIP,
    )] for c in cats]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    await message.answer(
        f"{CE_TIP} <b>Какому разделу сменить эмодзи?</b>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("setemoji:"))
async def cb_setemoji(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    key = cb.data.split(":")[1]
    pending_emoji[cb.from_user.id] = key
    await cb.answer()
    await cb.message.edit_text(
        f"{CE_TIP} Пришли <b>эмодзи</b> для раздела:\n"
        f"кастомный из премиум-пака станет иконкой кнопки, обычный добавится в название.\n"
        f"Или /skip — отмена.",
        parse_mode="HTML",
    )


@dp.message(Command("skip"))
async def cmd_skip(message: Message):
    if not is_admin(message):
        return
    if pending_emoji.pop(message.from_user.id, None):
        await message.answer(f"{CE_OK} Ок, оставил как есть.", parse_mode="HTML", reply_markup=MK)


@dp.callback_query(F.data.startswith("newcat:"))
async def cb_newcat(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    _, sid_s, pid_s = cb.data.split(":")
    p = gpt_prod_cache.get(f"{sid_s}:{pid_s}")
    if p is None:
        await cb.answer("Товар устарел — создай раздел командой /newcat Название", show_alert=True)
        return
    name = p.get("name", "")
    word = ""
    for w in re.sub(r"[^A-Za-z0-9 ]+", " ", name).split():
        if len(w) >= 3 and not w.isdigit():
            word = w
            break
    if not word:
        word = name.strip()[:12] or "Новый"
    await cb.answer()
    await _create_custom_cat(cb.message, word)


# ─── /pop, /Nday ─────────────────────────────────────────────────────────────

@dp.message(Command("pop"))
async def cmd_pop(message: Message):
    if not is_admin(message):
        return
    accounts = load_accounts()
    cdk_list = load_cdk()
    if not accounts and not cdk_list:
        await message.answer(f"{CE_EMPTY} Grok-склад пустой.", parse_mode="HTML", reply_markup=MK)
        return
    bd: dict[int, int] = {}
    for a in accounts:
        bd[a.get("days", 30)] = bd.get(a.get("days", 30), 0) + 1
    summary = "  ".join(f"{DAYS_EMOJI.get(d, CE_PIN)}{d}д:{cnt}" for d, cnt in sorted(bd.items()))
    await message.answer(
        f"{CE_BOX} <b>Grok — выбери срок:</b>\n<i>{summary}</i>",
        reply_markup=grok_days_keyboard(), parse_mode="HTML",
    )


async def _pop_by_days(message: Message, days: int) -> None:
    async with _lock:
        accounts = load_accounts()
        match = next((a for a in accounts if a.get("days", 30) == days), None)
        if not match:
            await message.answer(
                f"{CE_EMPTY} Нет Grok-аккаунтов на {days} дней.",
                parse_mode="HTML", reply_markup=MK,
            )
            return
        accounts.remove(match)
        save_accounts(accounts)
    remain = sum(1 for a in accounts if a.get("days", 30) == days)
    await message.answer(
        f"{CE_OUT} Grok [{days}д]:\n{format_account_block(match)}\n\n"
        f"<i>Осталось {days}д: {remain} шт.</i>",
        parse_mode="HTML", reply_markup=MK,
    )


@dp.message(Command("3day"))
async def cmd_3day(message: Message):
    if not is_admin(message): return
    await _pop_by_days(message, 3)

@dp.message(Command("7day"))
async def cmd_7day(message: Message):
    if not is_admin(message): return
    await _pop_by_days(message, 7)

@dp.message(Command("14day"))
async def cmd_14day(message: Message):
    if not is_admin(message): return
    await _pop_by_days(message, 14)

@dp.message(Command("30day"))
async def cmd_30day(message: Message):
    if not is_admin(message): return
    await _pop_by_days(message, 30)


# ─── Кнопки reply-клавиатуры ─────────────────────────────────────────────────

def _grok_days_view() -> tuple[str, InlineKeyboardMarkup]:
    accounts = load_accounts()
    cdk_list = load_cdk()
    acc_bd: dict[int, int] = {}
    for a in accounts:
        d = a.get("days", 30)
        acc_bd[d] = acc_bd.get(d, 0) + 1
    cdk_bd: dict[int, int] = {}
    for c in cdk_list:
        d = c.get("days", 3)
        cdk_bd[d] = cdk_bd.get(d, 0) + 1

    lines = []
    for d in VALID_DAYS:
        acc_cnt = acc_bd.get(d, 0)
        cdk_cnt = cdk_bd.get(d, 0)
        em = CE_DAY
        if d in CDK_ONLY:
            lines.append(f"{em} {d}д: CDK {cdk_cnt} (только CDK)")
        elif d in CDK_SUPPORTED:
            lines.append(f"{em} {d}д: акк {acc_cnt} | CDK {cdk_cnt}")
        else:
            lines.append(f"{em} {d}д: акк {acc_cnt}")
    return (
        f"{CE_GROK} <b>Grok — выбери срок подписки:</b>\n" + "\n".join(lines),
        grok_days_keyboard(),
    )


@dp.message(F.text.in_({"Grok", "🤖 Grok"}))
async def handle_grok_button(message: Message):
    if not is_admin(message):
        return
    await _send_cat_menu(message, "grok")


@dp.message(F.text.in_({"Gemini", "💎 Gemini"}))
async def handle_gemini_button(message: Message):
    if not is_admin(message):
        return
    await _send_cat_menu(message, "gemini")


@dp.message(F.text.in_({"Список", "📋 Список"}))
async def handle_list_button(message: Message):
    if not is_admin(message): return
    await _send_list(message)

@dp.message(F.text.in_({"Счёт", "📊 Счёт"}))
async def handle_count_button(message: Message):
    if not is_admin(message): return
    await _send_count(message)

@dp.message(F.text.in_({"Помощь", "❓ Помощь"}))
async def handle_help_button(message: Message):
    if not is_admin(message): return
    await message.answer(HELP_TEXT, parse_mode="HTML", reply_markup=MK)


# ─── Шоп-разделы (Grok / Gemini / ChatGPT / CapCut / свои) ───────────────────

def _cat_store_count(cat: str) -> str:
    if cat == "grok":
        return f"{len(load_accounts())} акк. | {len(load_cdk())} CDK"
    if cat == "gemini":
        return f"{len(load_gemini())} ссыл."
    load_fn, _ = store_funcs(cat)
    return f"{len(load_fn())} шт."


def _cat_menu_text(cat: str) -> str:
    c = get_cat(cat)
    txt = (
        f"{c['ce']} <b>{c['title']}</b>\n\n"
        f"{CE_BOX} На складе: <b>{_cat_store_count(cat)}</b>"
    )
    watches = load_autobuy()
    if watches:
        total = sum(w.get("qty_left", 0) for w in watches)
        txt += f"\n{CE_PIN} Автопокупки: <b>{len(watches)}</b> (ждём {total} шт.)"
    return txt


async def _send_cat_menu(message: Message, cat: str) -> None:
    await message.answer(
        _cat_menu_text(cat),
        reply_markup=cat_menu_keyboard(cat, len(load_autobuy())),
        parse_mode="HTML",
    )


@dp.message(F.text == "ChatGPT")
async def handle_chatgpt_button(message: Message):
    if not is_admin(message):
        return
    await _send_cat_menu(message, "gpt")


@dp.message(F.text == "CapCut")
async def handle_capcut_button(message: Message):
    if not is_admin(message):
        return
    await _send_cat_menu(message, "capcut")


@dp.callback_query(F.data.startswith("shop_menu:"))
async def cb_shop_menu(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    cat = cb.data.split(":")[1]
    await cb.answer()
    await cb.message.edit_text(
        _cat_menu_text(cat),
        reply_markup=cat_menu_keyboard(cat, len(load_autobuy())),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("shop_buy:"))
async def cb_shop_buy(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    cat = cb.data.split(":")[1]
    shops = load_shops()
    if not shops:
        await cb.answer()
        await cb.message.edit_text(
            f"{CE_WARN} Нет подключённых шопов.\n"
            f"Добавь: <code>/addshop Название | https://url | КЛЮЧ | ссылка_на_шоп</code>",
            reply_markup=cat_menu_keyboard(cat, len(load_autobuy())), parse_mode="HTML",
        )
        return
    if len(shops) == 1:
        await cb.answer("Загружаю товары...")
        await _show_products(cb, cat, shops[0])
        return
    c = get_cat(cat)
    await cb.answer()
    await cb.message.edit_text(
        f"{c['ce']} <b>{c['title']} — выбери магазин:</b>",
        reply_markup=_shops_keyboard(cat), parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("shop_sel:"))
async def cb_shop_sel(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    _, cat, sid_s = cb.data.split(":")
    shop = get_shop(int(sid_s))
    if not shop:
        await cb.answer("Шоп не найден.", show_alert=True)
        return
    await cb.answer("Загружаю товары...")
    await _show_products(cb, cat, shop)


async def _show_products(cb: CallbackQuery, cat: str, shop: dict) -> None:
    c = get_cat(cat)
    data = await shop_api(shop, "GET", "/api/products")
    if not data.get("success"):
        await cb.message.edit_text(
            f"{CE_NO} Ошибка API ({escape(shop.get('name', '?'))}):\n<code>{escape(str(data.get('error')))}</code>",
            reply_markup=cat_menu_keyboard(cat, len(load_autobuy())), parse_mode="HTML",
        )
        return
    prods = cat_filter(data.get("products", []), cat)
    if not prods:
        await cb.message.edit_text(
            f"{CE_EMPTY} В шопе «{escape(shop.get('name', '?'))}» нет {c['title']}-товаров.",
            reply_markup=cat_menu_keyboard(cat, len(load_autobuy())), parse_mode="HTML",
        )
        return
    bal = await shop_api(shop, "GET", "/api/balance")
    bal_line = ""
    if bal.get("success"):
        bal_line = f"\nБаланс: <b>{fmt_usdt(bal.get('balance_usdt', 0))}</b>"

    lines = [f"{c['ce']} <b>{c['title']} — {escape(shop.get('name', ''))}:</b>{bal_line}\n"]
    rows = []
    for p in prods:
        gpt_prod_cache[f"{shop.get('id')}:{p['id']}"] = p
        stock = p.get("stock", 0)
        mark = CE_OK if stock > 0 else CE_EMPTY
        lines.append(
            f"{mark} <b>{escape(p['name'])}</b>\n"
            f"      {fmt_usdt(p.get('price_usdt', 0))} — в наличии: <b>{stock}</b>"
        )
        rows.append([InlineKeyboardButton(
            text=f"{prod_short_name(p['name'], cat)} · {stock} шт",
            callback_data=f"shop_prod:{cat}:{shop.get('id')}:{p['id']}",
            style=ButtonStyle.SUCCESS if stock > 0 else ButtonStyle.PRIMARY,
            icon_custom_emoji_id=c["icon"],
        )])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"shop_menu:{cat}", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("shop_prod:"))
async def cb_shop_prod(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    _, cat, sid_s, pid_s = cb.data.split(":")
    sid, pid = int(sid_s), int(pid_s)
    shop = get_shop(sid)
    if not shop:
        await cb.answer("Шоп не найден.", show_alert=True)
        return
    c = get_cat(cat)
    p = gpt_prod_cache.get(f"{sid}:{pid}")
    if p is None:
        data = await shop_api(shop, "GET", "/api/products")
        for x in data.get("products", []):
            gpt_prod_cache[f"{sid}:{x['id']}"] = x
        p = gpt_prod_cache.get(f"{sid}:{pid}")
    if p is None:
        await cb.answer("Товар не найден, обнови список.", show_alert=True)
        return
    await cb.answer()
    pending_buy[cb.from_user.id] = {"p": p, "cat": cat, "shop_id": sid}
    desc = translate_desc(p.get("description", ""))
    desc_block = f"\n<blockquote>{escape(desc)}</blockquote>\n" if desc else ""
    await cb.message.edit_text(
        f"{c['ce']} <b>{escape(p['name'])}</b>\n"
        f"Магазин: {escape(shop.get('name', '?'))}\n"
        f"Цена: {fmt_usdt(p.get('price_usdt', 0))}\n"
        f"В наличии: <b>{p.get('stock', 0)}</b> шт.\n"
        f"{desc_block}\n"
        f"{CE_KBD} <b>Отправь количество сообщением</b> (1-100):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data=f"shop_sel:{cat}:{sid}", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
        ]),
        parse_mode="HTML",
    )


def _buy_confirm_keyboard(shop: dict | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Купить сейчас", callback_data="shop_now",  style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_OK)],
        [InlineKeyboardButton(text="Автопокупка (когда появится)", callback_data="shop_auto", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_PIN)],
    ]
    link = (shop or {}).get("link")
    if link:
        rows.append([InlineKeyboardButton(text="Пополнить баланс в шопе", url=link, style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_UP)])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="shop_cancelbuy", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data == "shop_now")
async def cb_shop_now(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    info = pending_buy.get(cb.from_user.id)
    if not info or "qty" not in info:
        await cb.answer("Заказ устарел — начни заново.", show_alert=True)
        return
    shop = get_shop(info.get("shop_id", 0)) or default_shop()
    if not shop:
        await cb.answer("Шоп не найден.", show_alert=True)
        return
    await cb.answer("Покупаю...")
    p, qty = info["p"], info["qty"]
    total_vnd  = p.get("price_vnd", 0) * qty
    total_usdt = p.get("price_usdt", 0) * qty
    currency, bal = await pick_currency(shop, total_vnd, total_usdt)
    if currency is None:
        err = bal.get("error")
        if err:
            msg = f"{CE_NO} Ошибка API:\n<code>{escape(str(err))}</code>"
        else:
            msg = (
                f"{CE_WARN} <b>Недостаточно средств в «{escape(shop.get('name', ''))}».</b>\n"
                f"Нужно: {fmt_usdt(total_usdt)}\n"
                f"Баланс: {fmt_usdt(bal.get('balance_usdt', 0))}"
            )
            if not shop.get("link"):
                msg += f"\n\n{CE_TIP} Добавь ссылку шопа (/shoplink {shop.get('id')} ссылка) — появится кнопка пополнения."
        await cb.message.edit_text(msg, reply_markup=_buy_confirm_keyboard(shop), parse_mode="HTML")
        return

    res = await shop_api(shop, "POST", "/api/buy", {
        "product_id": p["id"], "quantity": qty, "currency": currency,
    })
    if not res.get("success"):
        await cb.message.edit_text(
            f"{CE_NO} Покупка не прошла:\n<code>{escape(str(res.get('error')))}</code>\n\n"
            f"{CE_TIP} Можно включить автопокупку — куплю, как только появится.",
            reply_markup=_buy_confirm_keyboard(shop), parse_mode="HTML",
        )
        return

    pending_buy.pop(cb.from_user.id, None)
    order = res.get("order", {})
    items = res.get("items", [])
    nb = res.get("new_balance")
    head = (
        f"{CE_OK} <b>Куплено: {escape(str(order.get('product', p['name'])))}</b>\n"
        f"Магазин: {escape(shop.get('name', '?'))}\n"
        f"Количество: <b>{order.get('total_items', len(items))}</b>"
        + (f" (бонус +{order.get('bonus')})" if order.get("bonus") else "")
        + f"\nЦена: <b>{order.get('total_price')}</b> {order.get('currency', currency.upper())}"
        + (f"\nНовый баланс: <b>{nb}</b>" if nb is not None else "")
    )
    await cb.message.edit_text(head, parse_mode="HTML")
    ce = get_cat(info.get("cat", "gpt"))["ce"]
    await send_items_chunks(
        lambda t: cb.message.answer(t, parse_mode="HTML"),
        f"{ce} <b>Аккаунты:</b>", items,
    )


@dp.callback_query(F.data == "shop_auto")
async def cb_shop_auto(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    info = pending_buy.pop(cb.from_user.id, None)
    if not info or "qty" not in info:
        await cb.answer("Заказ устарел — начни заново.", show_alert=True)
        return
    p, qty, cat = info["p"], info["qty"], info.get("cat", "gpt")
    sid = info.get("shop_id") or (default_shop() or {}).get("id", 1)
    async with _lock:
        watches = load_autobuy()
        watches.append({
            "product_id": p["id"],
            "name": p["name"],
            "cat": cat,
            "shop_id": sid,
            "qty_left": qty,
            "chat_id": cb.message.chat.id,
            "notified_low_balance": False,
        })
        save_autobuy(watches)
    await cb.answer("Автопокупка создана.")
    ce = get_cat(cat)["ce"]
    shop = get_shop(sid)
    sname = escape(shop.get("name", "?")) if shop else "?"
    await cb.message.edit_text(
        f"{CE_PIN} <b>Автопокупка создана:</b>\n"
        f"{ce} {escape(p['name'])} × <b>{qty}</b> ({sname})\n\n"
        f"Проверяю наличие каждые {AUTOBUY_INTERVAL} сек. "
        f"Как только появится — куплю и пришлю сюда.",
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "shop_cancelbuy")
async def cb_shop_cancelbuy(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    pending_buy.pop(cb.from_user.id, None)
    await cb.answer("Отменено.")
    await cb.message.edit_text(f"{CE_NO} Покупка отменена.", parse_mode="HTML")


@dp.callback_query(F.data.startswith("shop_store:"))
async def cb_shop_store(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    cat = cb.data.split(":")[1]
    c = get_cat(cat)

    # Grok: хранилище = выбор срока подписки (аккаунты + CDK)
    if cat == "grok":
        await cb.answer()
        text, kb = _grok_days_view()
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        return

    # Gemini: выдать ссылку
    if cat == "gemini":
        async with _lock:
            gemini_lst = load_gemini()
            if not gemini_lst:
                await cb.answer()
                await cb.message.edit_text(
                    f"{CE_EMPTY} Нет Gemini-ссылок в хранилище.\n\n"
                    f"{CE_TIP} Кинь ссылки serviceactivation.google.com в чат — добавятся сами.",
                    reply_markup=cat_menu_keyboard(cat, len(load_autobuy())), parse_mode="HTML",
                )
                return
            item = gemini_lst.pop(0)
            save_gemini(gemini_lst)
        await cb.answer()
        await cb.message.edit_text(
            f"{CE_GEMINI} <b>Gemini:</b>\n{item.get('url', '')}\n\n"
            f"<i>Осталось: {len(gemini_lst)} шт.</i>",
            parse_mode="HTML",
        )
        return

    # ChatGPT / CapCut / свои разделы: выдать аккаунт-строку
    load_fn, save_fn = store_funcs(cat)
    async with _lock:
        store = load_fn()
        if not store:
            await cb.answer()
            await cb.message.edit_text(
                f"{CE_EMPTY} {c['title']}-склад пустой.\n\n"
                f"{CE_TIP} Кинь аккаунты в чат в формате:\n"
                f"<code>mail | password</code> или <code>mail | password | код</code>",
                reply_markup=cat_menu_keyboard(cat, len(load_autobuy())), parse_mode="HTML",
            )
            return
        item = store.pop(0)
        save_fn(store)
    await cb.answer()
    await cb.message.edit_text(
        f"{CE_OUT} <b>{c['title']} аккаунт:</b>\n"
        f"<code>{escape(item.get('raw', ''))}</code>\n\n"
        f"<i>Осталось: {len(store)} шт.</i>",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("shop_watch:"))
async def cb_shop_watch(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    cat = cb.data.split(":")[1]
    await cb.answer()
    watches = load_autobuy()
    if not watches:
        await cb.message.edit_text(
            _cat_menu_text(cat),
            reply_markup=cat_menu_keyboard(cat, 0), parse_mode="HTML",
        )
        return
    lines = [f"{CE_PIN} <b>Активные автопокупки:</b>\n"]
    rows = []
    for i, w in enumerate(watches):
        ce = get_cat(w.get("cat", "gpt"))["ce"]
        s = get_shop(w.get("shop_id", 1))
        sn = f" · {escape(s.get('name', ''))}" if s else ""
        lines.append(f"{i + 1}. {ce} {escape(w.get('name', '?'))}{sn} — ждём <b>{w.get('qty_left', 0)}</b> шт.")
        rows.append([InlineKeyboardButton(
            text=f"Убрать №{i + 1}", callback_data=f"shop_unwatch:{cat}:{i}",
            style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_TRASH,
        )])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"shop_menu:{cat}", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_HOME)])
    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("shop_unwatch:"))
async def cb_shop_unwatch(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    _, cat, idx_s = cb.data.split(":")
    idx = int(idx_s)
    async with _lock:
        watches = load_autobuy()
        removed = watches.pop(idx) if 0 <= idx < len(watches) else None
        save_autobuy(watches)
    await cb.answer("Убрано." if removed else "Уже нет.")
    cb2 = cb.model_copy(update={"data": f"shop_watch:{cat}"})
    await cb_shop_watch(cb2)


# ─── Добавление аккаунтов "mail | pass [| код]" — выбор раздела ──────────────

@dp.callback_query(F.data.startswith("store_as:"))
async def cb_store_as(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    cat = cb.data.split(":")[1]
    lines_raw = pending_store.pop(cb.from_user.id, None)
    if not lines_raw:
        await cb.answer("Устарело — кинь аккаунты заново.", show_alert=True)
        return
    await cb.answer()

    if cat == "grok":
        # первые две части — email и пароль
        parsed = []
        for raw in lines_raw:
            parts = [s.strip() for s in raw.split("|")]
            if len(parts) >= 2:
                parsed.append({"email": parts[0], "password": parts[1]})
        if not parsed:
            await cb.message.edit_text(f"{CE_NO} Не удалось разобрать строки.", parse_mode="HTML")
            return
        pending_add[cb.from_user.id] = parsed
        await cb.message.edit_text(
            f"{CE_IN} Найдено <b>{len(parsed)}</b> Grok-аккаунт(ов). Выбери срок подписки:",
            reply_markup=add_days_keyboard(), parse_mode="HTML",
        )
        return

    c = get_cat(cat)
    load_fn, save_fn = store_funcs(cat)
    async with _lock:
        store = load_fn()
        existing = {a.get("raw", "").lower() for a in store}
        added, dupes = 0, 0
        for raw in lines_raw:
            if raw.lower() in existing:
                dupes += 1
            else:
                store.append({"raw": raw})
                existing.add(raw.lower())
                added += 1
        save_fn(store)
    msg = f"{c['ce']} {c['title']} добавлено: <b>{added}</b> шт."
    if dupes:
        msg += f"\n{CE_WARN} Дублей: {dupes}"
    msg += f"\n<i>Всего {c['title']}: {len(store)} шт.</i>"
    await cb.message.edit_text(msg, parse_mode="HTML