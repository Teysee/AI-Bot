import asyncio
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import sys
import time
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

# Shop API (покупка ChatGPT-аккаунтов)
SHOP_API_BASE = os.getenv("SHOP_API_BASE", "https://tunvnmmo.duckdns.org").rstrip("/")
SHOP_API_KEY  = os.getenv("SHOP_API_KEY", "").strip()
AUTOBUY_INTERVAL = int(os.getenv("AUTOBUY_INTERVAL", "30"))  # сек между проверками наличия

# Второй магазин — Roboticvn (API v2, товары с вариантами)
RVN_API_BASE = os.getenv("RVN_API_BASE", "https://api.roboticvn.com").rstrip("/")
RVN_API_KEY  = os.getenv("RVN_API_KEY", "").strip()
RVN_SEEN_FILE    = Path(os.getenv("RVN_SEEN_FILE",    "rvn_seen.json"))     # снапшот товаров/вариантов
RVN_PENDING_FILE = Path(os.getenv("RVN_PENDING_FILE", "rvn_pending.json"))  # заказы, ждущие выдачи
RVN_SCAN_INTERVAL = int(os.getenv("RVN_SCAN_INTERVAL", "600"))  # сек между проверками новинок
SHOP_NAMES = {"tun": "TunVN", "rvn": "Roboticvn"}

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

# Категории шопа: подстрока в названии товара → раздел
SHOP_CATS = {
    "grok":   {"title": "Grok",    "icon": ID_GROK,   "ce": CE_GROK,   "match": "grok"},
    "gemini": {"title": "Gemini",  "icon": ID_GEMINI, "ce": CE_GEMINI, "match": "gemini"},
    "gpt":    {"title": "ChatGPT", "icon": ID_GPT,    "ce": CE_GPT,    "match": "gpt"},
    "capcut": {"title": "CapCut",  "icon": ID_CAPCUT, "ce": CE_CAPCUT, "match": "capcut"},
}
# Каталог Roboticvn — не раздел склада, только для оформления
CATALOG_META = {"title": "Каталог", "icon": ID_BOX, "ce": CE_BOX, "match": None}


def cat_meta(cat: str | None) -> dict:
    return SHOP_CATS.get(cat or "") or CATALOG_META


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
    f"{CE_KEY} /setapikey КЛЮЧ — API-ключ шопа TunVN\n"
    f"{CE_KEY} /setrvnkey КЛЮЧ — API-ключ шопа Roboticvn\n\n"
    f"{CE_BOX} <b>Каталог</b> — все товары Roboticvn (Netflix, Claude, Spotify…)\n\n"
    f"{CE_TIP} Кнопки пропали? Отправь /start"
)

_lock = asyncio.Lock()
pending_add: dict[int, list[dict]] = {}
pending_clear: set[int] = set()
pending_buy: dict[int, dict] = {}      # user_id -> {"offer": offer, "cat": str, "qty": int, "shown_usd": float}
pending_store: dict[int, list[str]] = {}  # user_id -> строки "mail | pass [| 2fa]" для добавления
offer_cache: dict[str, dict] = {}      # oid ("tun:85" / "rvn:variant_…") -> offer
catalog_page: dict[int, int] = {}      # user_id -> последняя открытая страница каталога


# ─── Работа с файлами ─────────────────────────────────────────────────────────

def _load_json(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        log.exception("Failed to load %s: %s", path, e)
        return []


def _save_json(path: Path, data: list) -> None:
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


RAW_STORES = {  # разделы со складом формата "raw"-строк
    "gpt":    (load_chatgpt, save_chatgpt),
    "capcut": (load_capcut,  save_capcut),
}


# Аккаунт через "|": "mail | password" или "mail | password | 2fa" (форматы шопа)
RE_PIPE_LINE = re.compile(
    r"^([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\s*\|\s*(\S+)(?:\s*\|\s*(\S+))?$"
)


# ─── Shop API ─────────────────────────────────────────────────────────────────

async def shop_api(method: str, path: str, payload: dict | None = None) -> dict:
    if not SHOP_API_KEY:
        return {"success": False, "error": "API-ключ не задан. Используй /setapikey КЛЮЧ"}
    headers = {"X-API-Key": SHOP_API_KEY}
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.request(
                method, f"{SHOP_API_BASE}{path}", json=payload, headers=headers
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


def english_part(text: str) -> str:
    """Описание TunVN вида «вьетнамская часть === английская часть» → английская часть."""
    for part in re.split(r"={3,}", text or ""):
        if re.search(r"[A-Za-z]", part) and not re.search(r"[àáảãạăâđêôơưọầấ]", part.lower()):
            return part
    return text or ""


def translate_desc(text: str, split: bool = True) -> str:
    """Словарный перевод частых фраз описания на RU (запасной вариант без сети)."""
    if not text:
        return ""
    chunk = english_part(text) if split else text
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


TRANSLATIONS_FILE = Path(os.getenv("TRANSLATIONS_FILE", "translations.json"))
_translations: dict[str, str] | None = None


def _mt_chunks(text: str, limit: int = 450) -> list[str]:
    """Нарезать текст на куски ≤ limit символов по строкам (лимит MyMemory — 500)."""
    chunks, cur = [], ""
    for ln in text.splitlines():
        while len(ln) > limit:
            chunks.append(ln[:limit])
            ln = ln[limit:]
        if len(cur) + len(ln) + 1 > limit:
            chunks.append(cur)
            cur = ln
        else:
            cur = f"{cur}\n{ln}" if cur else ln
    if cur:
        chunks.append(cur)
    return chunks


async def translate_ru(text: str) -> str:
    """Машинный перевод на русский (MyMemory) с кэшем в файле; при сбое/лимите — словарь."""
    global _translations
    text = (text or "").strip()
    if not text:
        return ""
    if _translations is None:
        try:
            _translations = json.loads(TRANSLATIONS_FILE.read_text(encoding="utf-8")) if TRANSLATIONS_FILE.exists() else {}
        except Exception:
            _translations = {}
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()
    if key in _translations:
        return _translations[key]
    out = []
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            for chunk in _mt_chunks(text):
                if not chunk.strip():
                    out.append(chunk)
                    continue
                async with sess.get(
                    "https://api.mymemory.translated.net/get",
                    params={"q": chunk, "langpair": "en|ru"},
                ) as resp:
                    data = await resp.json(content_type=None)
                tr = (data.get("responseData") or {}).get("translatedText") or ""
                if data.get("responseStatus") != 200 or not tr or "MYMEMORY WARNING" in tr:
                    raise RuntimeError(f"MyMemory: {data.get('responseDetails') or data.get('responseStatus')}")
                out.append(tr)
    except Exception as e:
        log.info("Machine translation unavailable, using dictionary: %s", e)
        return translate_desc(text, split=False)
    result = "\n".join(out).strip()
    _translations[key] = result
    try:
        _save_json(TRANSLATIONS_FILE, _translations)
    except Exception:
        log.exception("Failed to save translations")
    return result


def cat_filter(products: list[dict], cat: str) -> list[dict]:
    match = SHOP_CATS[cat]["match"]
    return [p for p in products if match in p.get("name", "").lower()]

def prod_short_name(name: str, cat: str) -> str:
    """Убрать название категории из имени товара для кнопки."""
    n = re.sub(r"^[^A-Za-z0-9]+", "", name)  # срезать эмодзи/символы в начале
    n = re.sub(r"(?i)^(chat\s*gpt|grok|link\s+gemini|gemini|capcut)\s*(plus|super|pro(\s+team)?)?\s*", "", n).strip(" -")
    return n or name


# ─── Roboticvn API ────────────────────────────────────────────────────────────

async def rvn_api(method: str, path: str, payload: dict | None = None, params: dict | None = None) -> dict:
    """→ {"ok": True, "data": …, "meta": …} или {"ok": False, "error": str}."""
    if not RVN_API_KEY:
        return {"ok": False, "error": "API-ключ Roboticvn не задан. Используй /setrvnkey КЛЮЧ"}
    query = {"locale": "en-US", **(params or {})}
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.request(
                method, f"{RVN_API_BASE}{path}", params=query, json=payload,
                headers={"x-api-key": RVN_API_KEY},
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status >= 400 or (isinstance(body, dict) and "error" in body):
                    err = body.get("error") if isinstance(body, dict) else None
                    msg = err.get("message") if isinstance(err, dict) else str(body)[:300]
                    return {"ok": False, "error": f"HTTP {resp.status}: {msg}"}
                if isinstance(body, dict) and "data" in body:
                    return {"ok": True, "data": body["data"], "meta": body.get("meta")}
                return {"ok": True, "data": body, "meta": None}  # delivery-ответ без обёртки data
    except Exception as e:
        return {"ok": False, "error": f"Сеть/API недоступен: {e}"}


def _rvn_seen_load() -> dict:
    d = {}
    if RVN_SEEN_FILE.exists():
        try:
            d = json.loads(RVN_SEEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            log.exception("Failed to load %s", RVN_SEEN_FILE)
    if not isinstance(d, dict):
        d = {}
    d.setdefault("products", [])
    d.setdefault("variants", {})  # variant_id -> product_id
    return d


rvn_variant_pid: dict[str, str] = dict(_rvn_seen_load()["variants"])
_rvn_list_cache: dict = {"ts": 0.0, "items": []}


def _strip_lead(s: str) -> str:
    """Срезать эмодзи/символы в начале названия («🔥 Grok» → «Grok»)."""
    return re.sub(r"^[^\w]+", "", s or "").strip() or (s or "")


def tun_offer(p: dict) -> dict:
    return {
        "shop": "tun", "oid": f"tun:{p['id']}", "pid": p["id"], "vid": None,
        "name": p.get("name", "?"), "short": p.get("name", "?"),
        "usd": float(p.get("price_usdt") or 0), "vnd": float(p.get("price_vnd") or 0),
        "stock": int(p.get("stock") or 0),
        "desc": english_part(p.get("description") or "").strip(),
    }


def rvn_offers(prod: dict) -> list[dict]:
    """Товар Roboticvn → предложения (по одному на вариант)."""
    out = []
    ptitle = _strip_lead(prod.get("title", "?"))
    for v in prod.get("variants") or []:
        prices = v.get("prices") or {}
        vtitle = (v.get("title") or "").strip()
        parts = [v.get("description"), v.get("delivery_instructions"), prod.get("description")]
        desc = "\n\n".join(x.strip() for x in parts if x and x.strip())
        out.append({
            "shop": "rvn", "oid": f"rvn:{v['id']}", "pid": prod.get("id"), "vid": v["id"],
            "name": f"{ptitle} · {vtitle}", "short": vtitle or ptitle,
            "usd": float(prices.get("usd") or 0), "vnd": float(prices.get("vnd") or 0),
            "stock": int(v.get("available_quantity") or 0) if v.get("in_stock") else 0,
            "desc": desc,
        })
    return out


def fmt_price(o: dict) -> str:
    return fmt_usdt(o["usd"]) if o["usd"] else "?"


async def rvn_list_products(force: bool = False) -> tuple[list[dict] | None, str | None]:
    """Весь список товаров (id, title), кэш 5 минут."""
    if not force and _rvn_list_cache["items"] and time.time() - _rvn_list_cache["ts"] < 300:
        return _rvn_list_cache["items"], None
    items: list[dict] = []
    offset = 0
    while True:
        r = await rvn_api("GET", "/api/v2/products", params={"limit": 100, "offset": offset})
        if not r["ok"]:
            return None, r["error"]
        batch = r["data"] or []
        items += batch
        if len(batch) < 100:
            break
        offset += 100
    _rvn_list_cache.update(ts=time.time(), items=items)
    return items, None


async def rvn_get_product(pid: str) -> tuple[dict | None, str | None]:
    """Карточка товара с вариантами; заодно обновляет кэш предложений."""
    r = await rvn_api("GET", f"/api/v2/products/{pid}")
    if not r["ok"]:
        return None, r["error"]
    prod = r["data"] or {}
    for o in rvn_offers(prod):
        offer_cache[o["oid"]] = o
        rvn_variant_pid[o["vid"]] = o["pid"]
    return prod, None


async def rvn_quote(o: dict, qty: int) -> dict | None:
    r = await rvn_api("POST", f"/api/v2/products/{o['pid']}/quote", {
        "variant_id": o["vid"], "quantity": qty, "currency_code": "usd",
    })
    return r["data"] if r["ok"] else None


def _fmt_delivery(d: dict) -> str:
    s = " | ".join(x for x in (d.get("account"), d.get("password")) if x)
    if d.get("additional_info"):
        s = f"{s}\n{d['additional_info']}" if s else d["additional_info"]
    return s or (d.get("display_title") or "?")


async def rvn_fetch_delivery(order_id: str) -> tuple[list[str] | None, str | None]:
    r = await rvn_api("GET", f"/api/v2/orders/{order_id}/delivery")
    if not r["ok"]:
        return None, r["error"]
    d = r["data"] or {}
    accs = d.get("delivered_accounts") or d.get("deliveredAccount") or []
    return [_fmt_delivery(a) for a in accs], None


async def get_offer(oid: str, fresh: bool = False) -> dict | None:
    """Предложение по oid; fresh=True — перечитать цену и наличие из магазина."""
    if not fresh and oid in offer_cache:
        return offer_cache[oid]
    shop, _, key = oid.partition(":")
    if shop == "tun":
        data = await shop_api("GET", "/api/products")
        if data.get("success"):
            for p in data.get("products", []):
                o = tun_offer(p)
                offer_cache[o["oid"]] = o
    elif shop == "rvn":
        pid = (offer_cache.get(oid) or {}).get("pid") or rvn_variant_pid.get(key)
        if pid:
            await rvn_get_product(pid)
    return offer_cache.get(oid)


async def shop_balance(shop: str) -> tuple[dict | None, str | None]:
    """Баланс магазина → {"usd": …, "vnd": …}."""
    if shop == "tun":
        b = await shop_api("GET", "/api/balance")
        if not b.get("success"):
            return None, str(b.get("error"))
        return {"usd": float(b.get("balance_usdt") or 0), "vnd": float(b.get("balance_vnd") or 0)}, None
    r = await rvn_api("GET", "/api/v2/wallet/balance")
    if not r["ok"]:
        return None, r["error"]
    d = r["data"] or {}
    return {"usd": float(d.get("usd") or 0), "vnd": float(d.get("vnd") or 0)}, None


def affordable(bal: dict, o: dict) -> tuple[str | None, int]:
    """Сколько штук хватает купить и в какой валюте (USD в приоритете)."""
    best: tuple[str | None, int] = (None, 0)
    for cur in ("usd", "vnd"):
        price = o[cur]
        if price > 0:
            n = int(bal[cur] // price + 1e-9)
            if n > best[1]:
                best = (cur, n)
    return best


async def buy_offer(o: dict, qty: int, max_usd: float | None = None) -> dict:
    """Купить qty шт. Ответ: {"ok": True, "items", "pending", "order_id", "order_no", "qty", "spent", "balance"}
    или {"ok": False, "error": код/текст, ...}. max_usd — не платить больше показанной суммы."""
    unit_usd = o["usd"]
    if o["shop"] == "rvn":
        q = await rvn_quote(o, qty)
        if q is None:
            return {"ok": False, "error": "Не удалось проверить цену и наличие в магазине."}
        if not q.get("can_purchase"):
            return {"ok": False, "error": "no_stock", "available": q.get("available_quantity")}
        unit_usd = float(q.get("unit_price") or unit_usd)
        if max_usd is not None and float(q.get("total") or 0) > max_usd * 1.01 + 0.01:
            return {"ok": False, "error": "price_changed", "total": float(q.get("total") or 0)}

    bal, err = await shop_balance(o["shop"])
    if err:
        return {"ok": False, "error": err}
    cur, n = affordable(bal, {**o, "usd": unit_usd})
    if n < qty:
        return {"ok": False, "error": "low_balance", "balance": bal, "need_usd": unit_usd * qty}

    if o["shop"] == "tun":
        res = await shop_api("POST", "/api/buy", {
            "product_id": o["pid"], "quantity": qty, "currency": "usdt" if cur == "usd" else "vnd",
        })
        if not res.get("success"):
            return {"ok": False, "error": str(res.get("error"))}
        order = res.get("order", {})
        return {
            "ok": True, "items": [str(i) for i in res.get("items", [])], "pending": False,
            "order_id": order.get("order_group"), "order_no": order.get("order_group"),
            "qty": order.get("total_items", qty), "bonus": order.get("bonus") or 0,
            "spent": f"{order.get('total_price')} {order.get('currency', '')}".strip(),
            "balance": res.get("new_balance"),
        }

    r = await rvn_api("POST", "/api/v2/orders", {
        "items": [{"variant_id": o["vid"], "quantity": qty}],
        "currency_code": cur, "payment_method": "wallet",
    })
    if not r["ok"]:
        return {"ok": False, "error": r["error"]}
    checkout = r["data"] or {}
    order_id = checkout.get("order_id")
    pay = checkout.get("payment") or {}
    items: list[str] = []
    for _ in range(4):  # выдача обычно мгновенная, но даём магазину пару секунд
        got, _err = await rvn_fetch_delivery(order_id) if order_id else (None, None)
        if got:
            items = got
            break
        await asyncio.sleep(4)
    bal_after, _ = await shop_balance("rvn")
    spent = pay.get("amount")
    return {
        "ok": True, "items": items, "pending": not items,
        "order_id": order_id, "order_no": checkout.get("order_display_id") or order_id,
        "qty": qty, "bonus": 0,
        "spent": f"{fmt_usdt(spent)}" if spent is not None and (pay.get("currency_code") or cur) == "usd"
                 else (f"{spent} {pay.get('currency_code', '')}".strip() if spent is not None else None),
        "balance": fmt_usdt(bal_after["usd"]) if bal_after else None,
    }


def load_rvn_pending() -> list[dict]:
    return _load_json(RVN_PENDING_FILE)

def save_rvn_pending(data: list[dict]) -> None:
    _save_json(RVN_PENDING_FILE, data)


async def add_rvn_pending(order_id: str, chat_id: int, name: str, cat: str | None) -> None:
    async with _lock:
        pend = load_rvn_pending()
        pend.append({"order_id": order_id, "chat_id": chat_id, "name": name, "cat": cat, "ts": time.time()})
        save_rvn_pending(pend)


async def report_purchase(send, o: dict, cat: str | None, res: dict, chat_id: int, title: str) -> None:
    """Отправить итог покупки: шапку + аккаунты (или «жду выдачу»)."""
    ce = cat_meta(cat)["ce"]
    head = (
        f"{title}\n{ce} <b>{escape(o['name'])}</b> — {SHOP_NAMES[o['shop']]}\n"
        f"Количество: <b>{res['qty']}</b>"
        + (f" (бонус +{res['bonus']})" if res.get("bonus") else "")
        + (f"\nСписано: <b>{escape(str(res['spent']))}</b>" if res.get("spent") else "")
        + (f"\nБаланс: <b>{escape(str(res['balance']))}</b>" if res.get("balance") is not None else "")
    )
    if res["pending"]:
        head += (
            f"\n\n⏳ Заказ <b>#{escape(str(res['order_no']))}</b> оплачен, магазин ещё выдаёт товар "
            f"(у некоторых позиций до 24–48 ч). Пришлю аккаунты сюда, как только будут готовы."
        )
        if res.get("order_id"):
            await add_rvn_pending(res["order_id"], chat_id, o["name"], cat)
    await send(head)
    if res["items"]:
        await send_items_chunks(send, f"{ce} <b>Аккаунты:</b>", res["items"])


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


# ─── Форматирование ───────────────────────────────────────────────────────────

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


# ─── Клавиатуры ───────────────────────────────────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    # Кастомные эмодзи на кнопках через icon_custom_emoji_id (Bot API 9.4+).
    # Текст обработчиков ловится по подстроке, эмодзи-иконка отдельно.
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Grok",    icon_custom_emoji_id=ID_GROK),
                KeyboardButton(text="Gemini",  icon_custom_emoji_id=ID_GEMINI),
            ],
            [
                KeyboardButton(text="ChatGPT", icon_custom_emoji_id=ID_GPT),
                KeyboardButton(text="CapCut",  icon_custom_emoji_id=ID_CAPCUT),
            ],
            [
                KeyboardButton(text="Список", icon_custom_emoji_id=ID_LIST),
                KeyboardButton(text="Счёт",   icon_custom_emoji_id=ID_COUNT),
            ],
            [
                KeyboardButton(text="Каталог", icon_custom_emoji_id=ID_BOX),
                KeyboardButton(text="Помощь",  icon_custom_emoji_id=ID_HELP),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

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


def is_admin(msg: Message) -> bool:
    return msg.from_user is not None and msg.from_user.id == ADMIN_ID

def is_admin_cb(cb: CallbackQuery) -> bool:
    return cb.from_user is not None and cb.from_user.id == ADMIN_ID


dp = Dispatcher()


# ─── /start, /help ────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message):
        return
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


# ─── /count, /list ────────────────────────────────────────────────────────────

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


# ─── /get, /use, /clear ───────────────────────────────────────────────────────

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


# ─── /settoken ────────────────────────────────────────────────────────────────

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
    """Задать API-ключ шопа (SHOP_API_KEY) для покупки ChatGPT."""
    if not is_admin(message):
        return
    new_key = (command.args or "").strip()
    if not new_key or len(new_key) < 16:
        await message.answer(
            f"{CE_KEY} Использование: <code>/setapikey КЛЮЧ</code>\n"
            f"Ключ шопа — команда /apikey в боте магазина.",
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
    bal = await shop_api("GET", "/api/balance")
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


@dp.message(Command("setrvnkey"))
async def cmd_setrvnkey(message: Message, command):
    """Задать API-ключ магазина Roboticvn (RVN_API_KEY)."""
    if not is_admin(message):
        return
    new_key = (command.args or "").strip()
    if not new_key.startswith("apk_") or len(new_key) < 20:
        await message.answer(
            f"{CE_KEY} Использование: <code>/setrvnkey apk_…</code>\n"
            f"Ключ выдаёт бот магазина Roboticvn.",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    try:  # в сообщении ключ — убираем его из чата
        await message.delete()
    except Exception:
        pass

    env_path = Path(__file__).parent / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        lines = [ln for ln in lines if not ln.startswith("RVN_API_KEY=")]
        lines.append(f"RVN_API_KEY={new_key}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        await message.answer(
            f"{CE_NO} Не удалось обновить .env:\n<code>{escape(str(e))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return

    global RVN_API_KEY
    RVN_API_KEY = new_key
    bal, err = await shop_balance("rvn")
    if bal:
        await message.answer(
            f"{CE_OK} Ключ {SHOP_NAMES['rvn']} сохранён и работает!\n"
            f"Баланс: <b>{fmt_usdt(bal['usd'])}</b>\n\n"
            f"{CE_BOX} Жми <b>Каталог</b> или раздел → <b>Купить</b>.",
            parse_mode="HTML", reply_markup=MK,
        )
    else:
        await message.answer(
            f"{CE_WARN} Ключ сохранён, но проверка не прошла:\n<code>{escape(str(err))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )


# ─── /pop, /Nday ──────────────────────────────────────────────────────────────

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


# ─── Шоп-разделы (Grok / Gemini / ChatGPT / CapCut) ──────────────────────────

def _cat_store_count(cat: str) -> str:
    if cat == "grok":
        return f"{len(load_accounts())} акк. | {len(load_cdk())} CDK"
    if cat == "gemini":
        return f"{len(load_gemini())} ссыл."
    load_fn, _ = RAW_STORES[cat]
    return f"{len(load_fn())} шт."


def _cat_menu_text(cat: str) -> str:
    c = SHOP_CATS[cat]
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


async def _cat_offers(cat: str) -> tuple[dict[str, list[dict]], list[str]]:
    """Предложения раздела из обоих магазинов → ({shop: [offer]}, [ошибки])."""
    by_shop: dict[str, list[dict]] = {"tun": [], "rvn": []}
    errors: list[str] = []
    data = await shop_api("GET", "/api/products")
    if data.get("success"):
        for p in cat_filter(data.get("products", []), cat):
            o = tun_offer(p)
            offer_cache[o["oid"]] = o
            by_shop["tun"].append(o)
    else:
        errors.append(f"{SHOP_NAMES['tun']}: {data.get('error')}")
    if RVN_API_KEY:
        lst, err = await rvn_list_products()
        if err:
            errors.append(f"{SHOP_NAMES['rvn']}: {err}")
        for prod in lst or []:
            if SHOP_CATS[cat]["match"] in prod.get("title", "").lower():
                full, err2 = await rvn_get_product(prod["id"])
                if full:
                    by_shop["rvn"] += rvn_offers(full)
                elif err2:
                    errors.append(f"{SHOP_NAMES['rvn']}: {err2}")
    return by_shop, errors


def _offer_button(o: dict, cat: str, icon: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=f"{o['short']} · {fmt_price(o)} · {o['stock']} шт",
        callback_data=f"of:{cat}:{o['oid']}",
        style=ButtonStyle.SUCCESS if o["stock"] > 0 else ButtonStyle.PRIMARY,
        icon_custom_emoji_id=icon,
    )


async def _balances_line() -> str:
    shops = ["tun"] + (["rvn"] if RVN_API_KEY else [])
    results = await asyncio.gather(*(shop_balance(s) for s in shops))
    parts = [
        f"{SHOP_NAMES[s]} <b>{fmt_usdt(b['usd'])}</b>" if b else f"{SHOP_NAMES[s]} —"
        for s, (b, _err) in zip(shops, results)
    ]
    return "Баланс: " + " · ".join(parts)


@dp.callback_query(F.data.startswith("shop_buy:"))
async def cb_shop_buy(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    cat = cb.data.split(":")[1]
    c = SHOP_CATS[cat]
    await cb.answer("Загружаю товары...")
    (by_shop, errors), bal_line = await asyncio.gather(_cat_offers(cat), _balances_line())

    lines = [f"{c['ce']} <b>{c['title']} — купить</b>\n{bal_line}"]
    rows = []
    for shop, offers in by_shop.items():
        if not offers:
            continue
        lines.append(f"\n<b>{SHOP_NAMES[shop]}:</b>")
        for o in offers:
            mark = CE_OK if o["stock"] > 0 else CE_EMPTY
            lines.append(f"{mark} {escape(o['short'])} — {fmt_price(o)} — <b>{o['stock']}</b> шт")
            rows.append([_offer_button(o, cat, c["icon"])])
    if not rows:
        lines.append(f"\n{CE_EMPTY} В магазинах нет {c['title']}-товаров.")
    for e in errors:
        lines.append(f"\n{CE_WARN} <i>{escape(e[:200])}</i>")
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"shop_menu:{cat}", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    await cb.message.edit_text(
        "\n".join(lines)[:4000],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("of:"))
async def cb_offer(cb: CallbackQuery):
    """Карточка предложения: цена, наличие, описание → ввод количества."""
    if not is_admin_cb(cb):
        return
    _, cat, oid = cb.data.split(":", 2)
    o = await get_offer(oid, fresh=True)
    if o is None:
        await cb.answer("Товар не найден, обнови список.", show_alert=True)
        return
    await cb.answer()
    m = cat_meta(cat)
    pending_buy[cb.from_user.id] = {"offer": o, "cat": cat}
    desc = o["desc"]
    if len(desc) > 900:  # обрезаем до перевода — экономим дневной лимит переводчика
        desc = desc[:900].rsplit("\n", 1)[0] + "\n…"
    desc = await translate_ru(desc)
    desc_block = f"\n<blockquote expandable>{escape(desc)}</blockquote>\n" if desc else ""
    back = f"clp:{o['pid']}" if cat == "cl" else f"shop_buy:{cat}"
    await cb.message.edit_text(
        f"{m['ce']} <b>{escape(o['name'])}</b>\n"
        f"Магазин: {SHOP_NAMES[o['shop']]}\n"
        f"Цена: <b>{fmt_price(o)}</b>\n"
        f"В наличии: <b>{o['stock']}</b> шт.\n"
        f"{desc_block}\n"
        f"{CE_KBD} <b>Отправь количество сообщением</b> (1-100):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data=back, style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
        ]),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("shop_prod:"))
async def cb_shop_prod_legacy(cb: CallbackQuery):
    """Старые кнопки из истории чата (до второго магазина) → новый формат."""
    _, cat, pid = cb.data.split(":")
    await cb_offer(cb.model_copy(update={"data": f"of:{cat}:tun:{pid}"}))


# ─── Каталог Roboticvn ───────────────────────────────────────────────────────

CATALOG_PAGE_SIZE = 12


async def _catalog_view(page: int) -> tuple[str, InlineKeyboardMarkup]:
    lst, err = await rvn_list_products()
    if err:
        return (
            f"{CE_NO} Каталог недоступен:\n<code>{escape(err)}</code>",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="Повторить", callback_data="clist:0", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_UP)]]),
        )
    pages = max(1, math.ceil(len(lst) / CATALOG_PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    chunk = lst[page * CATALOG_PAGE_SIZE:(page + 1) * CATALOG_PAGE_SIZE]
    bal, _ = await shop_balance("rvn")
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(chunk), 2):
        rows.append([
            InlineKeyboardButton(text=p["title"], callback_data=f"clp:{p['id']}", style=ButtonStyle.PRIMARY)
            for p in chunk[i:i + 2]
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"clist:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"clist:{page + 1}"))
    rows.append(nav)
    text = (
        f"{CE_BOX} <b>Каталог {SHOP_NAMES['rvn']}</b> — {len(lst)} товаров\n"
        f"Баланс: <b>{fmt_usdt(bal['usd']) if bal else '—'}</b>\n\n"
        f"Выбери товар:"
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(F.text == "Каталог")
async def handle_catalog_button(message: Message):
    if not is_admin(message):
        return
    if not RVN_API_KEY:
        await message.answer(
            f"{CE_KEY} Сначала задай ключ магазина: <code>/setrvnkey КЛЮЧ</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    catalog_page[message.from_user.id] = 0
    text, kb = await _catalog_view(0)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data.startswith("clist:"))
async def cb_catalog_list(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    page = int(cb.data.split(":")[1])
    catalog_page[cb.from_user.id] = page
    await cb.answer()
    text, kb = await _catalog_view(page)
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


@dp.callback_query(F.data.startswith("clp:"))
async def cb_catalog_product(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    pid = cb.data.split(":", 1)[1]
    prod, err = await rvn_get_product(pid)
    page = catalog_page.get(cb.from_user.id, 0)
    back = [InlineKeyboardButton(text="Назад", callback_data=f"clist:{page}", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)]
    if prod is None:
        await cb.answer()
        await cb.message.edit_text(
            f"{CE_NO} Не удалось открыть товар:\n<code>{escape(str(err))}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[back]), parse_mode="HTML",
        )
        return
    await cb.answer()
    offers = rvn_offers(prod)
    lines = [f"{CE_BOX} <b>{escape(prod.get('title', '?'))}</b>"]
    pdesc = await translate_ru((prod.get("description") or "")[:500])
    if pdesc:
        lines.append(f"<blockquote expandable>{escape(pdesc)}</blockquote>")
    lines.append("")
    for o in offers:
        mark = CE_OK if o["stock"] > 0 else CE_EMPTY
        lines.append(f"{mark} {escape(o['short'])} — {fmt_price(o)} — <b>{o['stock']}</b> шт")
    if not offers:
        lines.append(f"{CE_EMPTY} Нет вариантов для покупки.")
    rows = [[_offer_button(o, "cl", ID_BOX)] for o in offers]
    rows.append(back)
    await cb.message.edit_text(
        "\n".join(lines)[:4000],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
    )


def _buy_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить сейчас", callback_data="shop_now",  style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_OK)],
        [InlineKeyboardButton(text="Автопокупка (когда появится)", callback_data="shop_auto", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_PIN)],
        [InlineKeyboardButton(text="Отмена", callback_data="shop_cancelbuy", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
    ])


@dp.callback_query(F.data == "shop_now")
async def cb_shop_now(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    info = pending_buy.get(cb.from_user.id)
    if not info or "qty" not in info:
        await cb.answer("Заказ устарел — начни заново.", show_alert=True)
        return
    await cb.answer("Покупаю...")
    o, qty, cat = info["offer"], info["qty"], info.get("cat")
    await cb.message.edit_text(f"⏳ Покупаю <b>{escape(o['name'])}</b> × {qty}…", parse_mode="HTML")
    res = await buy_offer(o, qty, max_usd=info.get("shown_usd"))
    if not res["ok"]:
        err = res["error"]
        if err == "low_balance":
            msg = (
                f"{CE_WARN} <b>Недостаточно средств в {SHOP_NAMES[o['shop']]}.</b>\n"
                f"Нужно: {fmt_usdt(res['need_usd'])}\n"
                f"Баланс: {fmt_usdt(res['balance']['usd'])}"
            )
        elif err == "no_stock":
            avail = res.get("available")
            msg = f"{CE_EMPTY} Столько нет в наличии" + (f" (есть {avail} шт.)" if avail is not None else "") + "."
        elif err == "price_changed":
            msg = (
                f"{CE_WARN} <b>Цена изменилась:</b> теперь {fmt_usdt(res['total'])} "
                f"вместо {fmt_usdt(info.get('shown_usd') or 0)}. Не покупаю — открой товар заново."
            )
        else:
            msg = f"{CE_NO} Покупка не прошла:\n<code>{escape(str(err))}</code>"
        await cb.message.edit_text(
            f"{msg}\n\n{CE_TIP} Можно включить автопокупку — куплю, как только появится.",
            reply_markup=_buy_confirm_keyboard(), parse_mode="HTML",
        )
        return

    pending_buy.pop(cb.from_user.id, None)
    await cb.message.edit_text(f"{CE_OK} <b>Покупка прошла.</b>", parse_mode="HTML")
    await report_purchase(
        lambda t: cb.message.answer(t, parse_mode="HTML"),
        o, cat, res, cb.message.chat.id, f"{CE_OK} <b>Куплено!</b>",
    )


@dp.callback_query(F.data == "shop_auto")
async def cb_shop_auto(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    info = pending_buy.pop(cb.from_user.id, None)
    if not info or "qty" not in info:
        await cb.answer("Заказ устарел — начни заново.", show_alert=True)
        return
    o, qty, cat = info["offer"], info["qty"], info.get("cat")
    watch = {
        "shop": o["shop"], "name": o["name"], "cat": cat, "qty_left": qty,
        "chat_id": cb.message.chat.id, "notified_low_balance": False,
    }
    if o["shop"] == "tun":
        watch["product_id"] = o["pid"]
    else:
        watch["pid"], watch["vid"] = o["pid"], o["vid"]
    async with _lock:
        watches = load_autobuy()
        watches.append(watch)
        save_autobuy(watches)
    await cb.answer("Автопокупка создана.")
    await cb.message.edit_text(
        f"{CE_PIN} <b>Автопокупка создана:</b>\n"
        f"{cat_meta(cat)['ce']} {escape(o['name'])} × <b>{qty}</b> — {SHOP_NAMES[o['shop']]}\n\n"
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
    c = SHOP_CATS[cat]

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

    # ChatGPT / CapCut: выдать аккаунт-строку
    load_fn, save_fn = RAW_STORES[cat]
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
        ce = cat_meta(w.get("cat"))["ce"]
        shop = SHOP_NAMES.get(w.get("shop", "tun"), "?")
        lines.append(f"{i + 1}. {ce} {escape(w.get('name', '?'))} ({shop}) — ждём <b>{w.get('qty_left', 0)}</b> шт.")
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

    c = SHOP_CATS[cat]
    load_fn, save_fn = RAW_STORES[cat]
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
    await cb.message.edit_text(msg, parse_mode="HTML")


@dp.callback_query(F.data == "store_cancel")
async def cb_store_cancel(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    pending_store.pop(cb.from_user.id, None)
    await cb.answer("Отменено.")
    await cb.message.edit_text(f"{CE_NO} Добавление отменено.", parse_mode="HTML")


# ─── Grok inline callbacks ────────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("grok_d:"))
async def cb_grok_days(cb: CallbackQuery):
    if not is_admin_cb(cb):
        await cb.answer("Нет доступа.", show_alert=True)
        return
    days = int(cb.data.split(":")[1])
    await cb.answer()

    if days in CDK_ONLY:
        cdk_list = load_cdk()
        cdk_cnt = sum(1 for c in cdk_list if c.get("days") == days)
        await cb.message.edit_text(
            f"{DAYS_EMOJI[days]} <b>{days} дней — только CDK:</b>\n"
            f"{CE_KEY} CDK в наличии: {cdk_cnt} шт.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Получить CDK", callback_data=f"grok_cdk:{days}", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_KEY)],
                [InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
            ]),
            parse_mode="HTML",
        )
    elif days in CDK_SUPPORTED:
        accounts = load_accounts()
        cdk_list = load_cdk()
        acc_cnt = sum(1 for a in accounts if a.get("days", 30) == days)
        cdk_cnt = sum(1 for c in cdk_list if c.get("days") == days)
        await cb.message.edit_text(
            f"{DAYS_EMOJI[days]} <b>{days} дней — выбери тип:</b>\n"
            f"{CE_EMAIL} Аккаунты: {acc_cnt} шт.   {CE_KEY} CDK: {cdk_cnt} шт.",
            reply_markup=grok_type_keyboard(days, has_cdk=True), parse_mode="HTML",
        )
    else:
        await _cb_pop_account(cb, days)


async def _cb_pop_account(cb: CallbackQuery, days: int) -> None:
    async with _lock:
        accounts = load_accounts()
        match = next((a for a in accounts if a.get("days", 30) == days), None)
        if not match:
            await cb.answer(f"Нет аккаунтов на {days} дней.", show_alert=True)
            await cb.message.edit_reply_markup(reply_markup=None)
            return
        accounts.remove(match)
        save_accounts(accounts)
    remain = sum(1 for a in accounts if a.get("days", 30) == days)
    await cb.message.edit_text(
        f"{CE_OUT} <b>Grok [{days}д] — аккаунт:</b>\n{format_account_block(match)}\n\n"
        f"<i>Осталось {days}д: {remain} шт.</i>",
        parse_mode="HTML",
    )
    await cb.message.answer(f"{CE_UP} Выдан выше", parse_mode="HTML", reply_markup=MK)


@dp.callback_query(F.data.startswith("grok_acc:"))
async def cb_grok_acc(cb: CallbackQuery):
    if not is_admin_cb(cb):
        await cb.answer("Нет доступа.", show_alert=True)
        return
    days = int(cb.data.split(":")[1])
    await cb.answer()
    await _cb_pop_account(cb, days)


@dp.callback_query(F.data.startswith("grok_cdk:"))
async def cb_grok_cdk(cb: CallbackQuery):
    if not is_admin_cb(cb):
        await cb.answer("Нет доступа.", show_alert=True)
        return
    days = int(cb.data.split(":")[1])
    if days not in CDK_SUPPORTED:
        await cb.answer("CDK для этого типа пока не добавлены.", show_alert=True)
        return
    async with _lock:
        cdk_list = load_cdk()
        match = next((c for c in cdk_list if c.get("days", 3) == days), None)
        if not match:
            await cb.answer(f"Нет CDK на {days} дней.", show_alert=True)
            await cb.message.edit_reply_markup(reply_markup=None)
            return
        cdk_list.remove(match)
        save_cdk(cdk_list)
    remain = sum(1 for c in cdk_list if c.get("days", 3) == days)
    await cb.answer("✅ CDK выдан!")
    await cb.message.edit_text(
        f"{CE_KEY} <b>Grok CDK [{days}д]:</b>\n<code>{escape(match['code'])}</code>\n\n"
        f"<i>Осталось CDK {days}д: {remain} шт.</i>",
        parse_mode="HTML",
    )
    await cb.message.answer(f"{CE_UP} CDK выдан выше", parse_mode="HTML", reply_markup=MK)


@dp.callback_query(F.data == "grok_cancel")
async def cb_grok_cancel(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    await cb.answer("Отменено.")
    await cb.message.edit_text(f"{CE_NO} Отменено.", parse_mode="HTML")


# ─── Добавление аккаунтов (inline callback) ───────────────────────────────────

@dp.callback_query(F.data.startswith("add_days:"))
async def cb_add_days(cb: CallbackQuery):
    if not is_admin_cb(cb):
        await cb.answer("Нет доступа.", show_alert=True)
        return
    days = int(cb.data.split(":")[1])
    parsed = pending_add.pop(cb.from_user.id, None)
    if not parsed:
        await cb.answer("Сессия истекла. Пришли аккаунты снова.", show_alert=True)
        await cb.message.edit_reply_markup(reply_markup=None)
        return
    for a in parsed:
        a["days"] = days
    async with _lock:
        accounts = load_accounts()
        existing = {a["email"].lower() for a in accounts}
        added, dupes = 0, 0
        for a in parsed:
            if a["email"].lower() in existing:
                dupes += 1
            else:
                accounts.append(a)
                existing.add(a["email"].lower())
                added += 1
        save_accounts(accounts)
    em = DAYS_EMOJI.get(days, CE_PIN)
    msg = f"{CE_OK} Добавлено: <b>{added}</b> шт. {em} {days}д"
    if dupes:
        msg += f"\n{CE_WARN} Дублей пропущено: {dupes}"
    msg += f"\n<i>Всего в Grok-складе: {len(accounts)} шт.</i>"
    await cb.answer(f"Добавлено {added} шт.")
    await cb.message.edit_text(msg, parse_mode="HTML")


@dp.callback_query(F.data == "add_cancel")
async def cb_add_cancel(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    pending_add.pop(cb.from_user.id, None)
    await cb.answer("Отменено.")
    await cb.message.edit_text(f"{CE_NO} Добавление отменено.", parse_mode="HTML")


# ─── Универсальный обработчик входящего текста ────────────────────────────────

@dp.message(F.text)
async def handle_text(message: Message):
    if not is_admin(message):
        return
    text = (message.text or "").strip()

    # ── Количество для покупки из магазина ──────────────────────────────────
    uid = message.from_user.id
    if uid in pending_buy and text.isdigit():
        qty = int(text)
        if not 1 <= qty <= 100:
            await message.answer(f"{CE_WARN} Количество: от 1 до 100.", parse_mode="HTML")
            return
        info = pending_buy[uid]
        o = info["offer"]
        total, stock, note = o["usd"] * qty, o["stock"], ""
        if o["shop"] == "rvn":  # точная цена и наличие прямо сейчас
            q = await rvn_quote(o, qty)
            if q:
                total = float(q.get("total") or total)
                if q.get("available_quantity") is not None:
                    stock = q["available_quantity"]
                if not q.get("can_purchase"):
                    note = f"\n{CE_WARN} Сейчас столько купить нельзя — подойдёт автопокупка."
        info["qty"], info["shown_usd"] = qty, total
        await message.answer(
            f"{cat_meta(info.get('cat'))['ce']} <b>{escape(o['name'])}</b>\n"
            f"Магазин: {SHOP_NAMES[o['shop']]}\n"
            f"Количество: <b>{qty}</b> шт.\n"
            f"Итого: <b>{fmt_usdt(total)}</b>\n"
            f"В наличии сейчас: {stock} шт.{note}\n\n"
            f"Выбери действие:",
            reply_markup=_buy_confirm_keyboard(), parse_mode="HTML",
        )
        return

    # ── CDK: строки вида 3TG-…, bbg…-…, GGG-… ──────────────────────────────
    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    detected_cdk: list[dict] = []
    for line in raw_lines:
        for pattern, days in CDK_PATTERNS:
            if pattern.match(line):
                detected_cdk.append({"code": line, "days": days})
                break
    if detected_cdk:
        async with _lock:
            cdk_list = load_cdk()
            existing = {c["code"].upper() for c in cdk_list}
            added, dupes = 0, 0
            by_days: dict[int, int] = {}
            for c in detected_cdk:
                key = c["code"].upper()
                if key in existing:
                    dupes += 1
                else:
                    cdk_list.append({"code": c["code"], "days": c["days"]})
                    existing.add(key)
                    by_days[c["days"]] = by_days.get(c["days"], 0) + 1
                    added += 1
            save_cdk(cdk_list)
        if added:
            detail = "  ".join(
                f"{DAYS_EMOJI.get(d, CE_PIN)}{d}д: {cnt}" for d, cnt in sorted(by_days.items())
            )
            msg = f"{CE_KEY} CDK добавлено: <b>{added}</b> шт. ({detail})"
        else:
            msg = f"{CE_KEY} CDK: все коды уже были в хранилище."
        if dupes:
            msg += f"\n{CE_WARN} Дублей: {dupes}"
        msg += f"\n<i>Всего CDK: {len(cdk_list)} шт.</i>"
        await message.answer(msg, parse_mode="HTML", reply_markup=MK)
        return

    # ── Аккаунты через "|": mail | pass [| код] → спросить раздел ──────────
    detected_pipe = []
    for l in raw_lines:
        m = RE_PIPE_LINE.match(l)
        if m:
            parts = [g.strip() for g in m.groups() if g]
            detected_pipe.append(" | ".join(parts))
    if detected_pipe:
        pending_store[uid] = detected_pipe
        await message.answer(
            f"{CE_IN} Найдено <b>{len(detected_pipe)}</b> аккаунт(ов). Куда добавить?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="ChatGPT", callback_data="store_as:gpt",    style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_GPT),
                    InlineKeyboardButton(text="CapCut",  callback_data="store_as:capcut", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_CAPCUT),
                ],
                [InlineKeyboardButton(text="Grok",   callback_data="store_as:grok", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_GROK)],
                [InlineKeyboardButton(text="Отмена", callback_data="store_cancel",  style=ButtonStyle.DANGER,  icon_custom_emoji_id=ID_NO)],
            ]),
            parse_mode="HTML",
        )
        return

    # ── Gemini: ссылки serviceactivation.google.com ─────────────────────────
    gemini_urls = RE_GEMINI_URL.findall(text)
    if gemini_urls:
        async with _lock:
            gemini_lst = load_gemini()
            existing = {g["url"] for g in gemini_lst}
            added, dupes = 0, 0
            for url in gemini_urls:
                if url in existing:
                    dupes += 1
                else:
                    gemini_lst.append({"url": url})
                    existing.add(url)
                    added += 1
            save_gemini(gemini_lst)
        msg = f"{CE_GEMINI} Gemini добавлено: <b>{added}</b> шт."
        if dupes:
            msg += f"\n{CE_WARN} Дублей: {dupes}"
        msg += f"\n<i>Всего Gemini: {len(gemini_lst)} шт.</i>"
        await message.answer(msg, parse_mode="HTML", reply_markup=MK)
        return

    # ── Grok аккаунты ───────────────────────────────────────────────────────
    parsed = parse_accounts(text)
    if not parsed:
        await message.answer(
            f"Не нашёл аккаунтов, CDK или ссылок.\n{CE_HELP} /help — справка",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    if message.from_user.id in pending_add:
        await message.answer(f"{CE_WARN} Предыдущая партия заменена новой.", parse_mode="HTML")
    pending_add[message.from_user.id] = parsed
    await message.answer(
        f"{CE_IN} Найдено <b>{len(parsed)}</b> Grok-аккаунт(ов). Выбери срок подписки:",
        reply_markup=add_days_keyboard(), parse_mode="HTML",
    )


# ─── Фоновая автопокупка ──────────────────────────────────────────────────────

def load_seen_products() -> set[int]:
    data = _load_json(PRODUCTS_SEEN_FILE)
    return set(data) if isinstance(data, list) else set()

def save_seen_products(ids: set[int]) -> None:
    _save_json(PRODUCTS_SEEN_FILE, sorted(ids))

def _product_category(p: dict) -> str | None:
    name = p.get("name", "").lower()
    for cat, c in SHOP_CATS.items():
        if c["match"] in name:
            return cat
    return None


async def _check_new_products(bot: Bot, products: list[dict]) -> None:
    """Уведомить админа о новых товарах в магазине."""
    current = {p["id"] for p in products}
    if not PRODUCTS_SEEN_FILE.exists():
        save_seen_products(current)  # первый запуск — запоминаем молча
        return
    seen = load_seen_products()
    new_ids = current - seen
    if not new_ids:
        return
    for p in products:
        if p["id"] not in new_ids:
            continue
        cat = _product_category(p)
        if cat:
            c = SHOP_CATS[cat]
            where = f"{c['ce']} Уже доступен: раздел <b>{c['title']}</b> → Купить."
        else:
            where = f"{CE_WARN} Не подходит ни под один раздел — напиши, добавлю его."
        try:
            await bot.send_message(
                ADMIN_ID,
                f"{CE_PIN} <b>Новый товар в магазине!</b>\n"
                f"<b>{escape(p.get('name', '?'))}</b>\n"
                f"Цена: {fmt_usdt(p.get('price_usdt', 0))} — в наличии: <b>{p.get('stock', 0)}</b> шт.\n\n"
                f"{where}",
                parse_mode="HTML",
            )
        except Exception:
            log.exception("Failed to notify about new product %s", p.get("id"))
    save_seen_products(seen | current)


async def _watch_offer(w: dict, tun_map: dict | None, rvn_cache: dict) -> dict | None:
    """Текущее предложение для автопокупки (цена/наличие), None — нет данных."""
    if w.get("shop", "tun") == "tun":
        p = tun_map.get(w.get("product_id")) if tun_map is not None else None
        return tun_offer(p) if p else None
    pid = w.get("pid")
    if pid not in rvn_cache:
        rvn_cache[pid], _ = await rvn_get_product(pid)
    prod = rvn_cache[pid]
    return next((o for o in rvn_offers(prod) if o["vid"] == w.get("vid")), None) if prod else None


async def _autobuy_tick(bot: Bot, tun_products: list[dict] | None) -> None:
    watches = load_autobuy()
    if not watches:
        return
    tun_map = {p["id"]: p for p in tun_products} if tun_products is not None else None
    rvn_cache: dict = {}
    remaining: list[dict] = []
    changed = False

    for w in watches:
        o = await _watch_offer(w, tun_map, rvn_cache)
        if not o or o["stock"] <= 0:
            remaining.append(w)
            continue

        bal, err = await shop_balance(o["shop"])
        if err:
            remaining.append(w)
            continue
        _, can = affordable(bal, o)
        want = min(w.get("qty_left", 0), o["stock"], 100, can)  # не хватает на всё — берём сколько можем

        res = await buy_offer(o, want) if want >= 1 else {"ok": False, "error": "low_balance"}
        if not res["ok"]:
            if res["error"] == "low_balance" and not w.get("notified_low_balance"):
                w["notified_low_balance"] = True
                changed = True
                await bot.send_message(
                    w["chat_id"],
                    f"{CE_WARN} <b>Автопокупка: товар появился, но не хватает баланса!</b>\n"
                    f"{cat_meta(w.get('cat'))['ce']} {escape(w.get('name', '?'))} — в наличии {o['stock']} шт.\n"
                    f"Баланс {SHOP_NAMES[o['shop']]}: {fmt_usdt(bal['usd'])}\n"
                    f"Пополни — куплю автоматически.",
                    parse_mode="HTML",
                )
            elif res["error"] != "low_balance":
                log.warning("Autobuy failed for %s: %s", w.get("name"), res["error"])
            remaining.append(w)
            continue

        w["qty_left"] = max(0, w.get("qty_left", 0) - want)
        w["notified_low_balance"] = False
        changed = True
        title = f"{CE_PIN} <b>Автопокупка сработала!</b>"
        if w["qty_left"] > 0:
            title += f"\n<i>Осталось докупить: {w['qty_left']} шт. — продолжаю следить.</i>"
            remaining.append(w)
        else:
            title += f"\n{CE_OK} <i>Заказ выполнен полностью.</i>"

        async def _send(t, chat_id=w["chat_id"]):
            await bot.send_message(chat_id, t, parse_mode="HTML")
        await report_purchase(_send, o, w.get("cat"), res, w["chat_id"], title)

    if changed or len(remaining) != len(watches):
        async with _lock:
            save_autobuy(remaining)


async def _rvn_pending_tick(bot: Bot) -> None:
    """Дослать аккаунты по заказам Roboticvn, которые магазин выдал не сразу."""
    pend = load_rvn_pending()
    if not pend:
        return
    keep: list[dict] = []
    for p in pend:
        items, _err = await rvn_fetch_delivery(p["order_id"])
        ce = cat_meta(p.get("cat"))["ce"]
        if items:
            async def _send(t, chat_id=p["chat_id"]):
                await bot.send_message(chat_id, t, parse_mode="HTML")
            await _send(f"{CE_OK} <b>Магазин выдал заказ:</b>\n{ce} {escape(p.get('name', '?'))}")
            await send_items_chunks(_send, f"{ce} <b>Аккаунты:</b>", items)
        elif time.time() - p.get("ts", 0) > 72 * 3600:
            await bot.send_message(
                p["chat_id"],
                f"{CE_WARN} Заказ {ce} {escape(p.get('name', '?'))} не выдан за 72 ч. "
                f"Проверь его в боте {SHOP_NAMES['rvn']} или напиши в поддержку магазина.",
                parse_mode="HTML",
            )
        else:
            keep.append(p)
    if len(keep) != len(pend):
        async with _lock:
            # могли добавиться новые заказы, пока мы проверяли
            done = {p["order_id"] for p in pend} - {p["order_id"] for p in keep}
            save_rvn_pending([p for p in load_rvn_pending() if p["order_id"] not in done])


async def _rvn_scan(bot: Bot) -> None:
    """Сверить каталог Roboticvn со снапшотом и сообщить о новых товарах/вариантах."""
    lst, err = await rvn_list_products(force=True)
    if err:
        log.warning("Roboticvn scan: %s", err)
        return
    first = not RVN_SEEN_FILE.exists()
    seen = _rvn_seen_load()
    seen_products = set(seen["products"])
    new_by_product: list[tuple[dict, bool, list[dict]]] = []
    for p in lst:
        prod, _ = await rvn_get_product(p["id"])
        await asyncio.sleep(1.0)  # бережём лимит 120 запросов/мин
        if not prod:
            continue
        fresh = [o for o in rvn_offers(prod) if o["vid"] not in seen["variants"]]
        is_new = p["id"] not in seen_products
        if not first and (is_new or fresh):
            new_by_product.append((p, is_new, fresh))
    seen["products"] = sorted(seen_products | {p["id"] for p in lst})
    seen["variants"] = {**seen["variants"], **rvn_variant_pid}
    _save_json(RVN_SEEN_FILE, seen)
    if first:
        return  # первый запуск — запоминаем молча

    for p, is_new, fresh in new_by_product:
        cat = next((c for c, m in SHOP_CATS.items() if m["match"] in p["title"].lower()), None)
        where = f"раздел <b>{SHOP_CATS[cat]['title']}</b> → Купить" if cat else "<b>Каталог</b>"
        lines = [
            f"{CE_PIN} <b>{'Новый товар' if is_new else 'Новые варианты'} в {SHOP_NAMES['rvn']}!</b>",
            f"{cat_meta(cat)['ce']} <b>{escape(p['title'])}</b>",
        ]
        for o in fresh[:15]:
            lines.append(f"• {escape(o['short'])} — {fmt_price(o)} — {o['stock']} шт")
        lines.append(f"\nКупить: {where}")
        try:
            await bot.send_message(ADMIN_ID, "\n".join(lines)[:4000], parse_mode="HTML")
        except Exception:
            log.exception("Failed to notify about Roboticvn product %s", p.get("id"))


async def rvn_scan_loop(bot: Bot) -> None:
    await asyncio.sleep(20)
    while True:
        if RVN_API_KEY:
            try:
                await _rvn_scan(bot)
            except Exception:
                log.exception("Roboticvn scan failed")
        await asyncio.sleep(RVN_SCAN_INTERVAL)


async def shop_loop(bot: Bot) -> None:
    log.info("Shop loop started (interval %ss)", AUTOBUY_INTERVAL)
    while True:
        try:
            data = await shop_api("GET", "/api/products")
            tun_products = data.get("products", []) if data.get("success") else None
            if tun_products is not None:
                await _check_new_products(bot, tun_products)
            await _autobuy_tick(bot, tun_products)
            if RVN_API_KEY:
                await _rvn_pending_tick(bot)
        except Exception:
            log.exception("Shop loop tick failed")
        await asyncio.sleep(AUTOBUY_INTERVAL)


# ─── Запуск ───────────────────────────────────────────────────────────────────

async def main():
    bot = Bot(token=BOT_TOKEN)
    log.info("Bot starting. Admin ID: %s", ADMIN_ID)

    await bot.set_my_commands([
        BotCommand(command="start",    description="🏠 Главное меню"),
        BotCommand(command="list",     description="📋 Все Grok-аккаунты"),
        BotCommand(command="count",    description="📊 Статистика склада"),
        BotCommand(command="pop",      description="📦 Выдать Grok (с выбором)"),
        BotCommand(command="3day",     description="⚡ Выдать Grok 3-дневный"),
        BotCommand(command="7day",     description="📅 Выдать Grok 7-дневный"),
        BotCommand(command="14day",    description="🌟 Выдать Grok 14-дневный"),
        BotCommand(command="30day",    description="👑 Выдать Grok 30-дневный"),
        BotCommand(command="use",      description="🗑 Удалить Grok по номеру"),
        BotCommand(command="clear",    description="⚠️ Очистить Grok-склад"),
        BotCommand(command="settoken",  description="🔑 Сменить токен бота"),
        BotCommand(command="setapikey", description="🛒 Ключ шопа TunVN"),
        BotCommand(command="setrvnkey", description="🛒 Ключ шопа Roboticvn"),
        BotCommand(command="help",      description="❓ Помощь"),
    ])
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    asyncio.create_task(shop_loop(bot))
    asyncio.create_task(rvn_scan_loop(bot))
    log.info("Commands registered. Starting polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
