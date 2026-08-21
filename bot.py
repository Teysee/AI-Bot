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

SHOP_API_BASE = os.getenv("SHOP_API_BASE", "https://tunvnmmo.duckdns.org").rstrip("/")
SHOP_API_KEY  = os.getenv("SHOP_API_KEY", "").strip()
AUTOBUY_INTERVAL = int(os.getenv("AUTOBUY_INTERVAL", "30"))

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN env var is required")
if not ADMIN_ID:
    raise SystemExit("ADMIN_ID env var is required")


def _e(eid: str, fb: str) -> str:
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

ID_GROK   = "5319288443153445517"
ID_GEMINI = "5321197740800120767"
ID_GPT    = "5310259124817134249"
ID_CAPCUT = "5474521476197536994"
ID_CLAUDE = "5310259124817134249"
ID_PPLX   = "5321199630585732877"
ID_LIST   = "5251308525426075254"
ID_COUNT  = "5251579679596372458"
ID_HELP   = "5251588462804491181"
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
ID_D3   = "5251356470145996194"
ID_D7   = "5251521246566307049"
ID_D14  = "5251307915540716107"
ID_D30  = "5251443675161976035"
ID_D60  = "5249101449106840434"

CE_GROK   = _e(ID_GROK,   "🤖")
CE_GEMINI = _e(ID_GEMINI, "💎")
CE_GPT    = _e(ID_GPT,    "💬")
CE_CAPCUT = _e(ID_CAPCUT, "✂️")
CE_CLAUDE = _e(ID_CLAUDE, "🤖")
CE_PPLX   = _e(ID_PPLX,   "🔍")
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
CE_DAY  = _e("5307843983102204243", "📋")

SHOP_CATS = {
    "grok":   {"title": "Grok",    "icon": ID_GROK,   "ce": CE_GROK,   "match": "grok"},
    "gemini": {"title": "Gemini",  "icon": ID_GEMINI, "ce": CE_GEMINI, "match": "gemini"},
    "gpt":    {"title": "ChatGPT", "icon": ID_GPT,    "ce": CE_GPT,    "match": "gpt"},
    "capcut": {"title": "CapCut",  "icon": ID_CAPCUT, "ce": CE_CAPCUT, "match": "capcut"},
    "claude": {"title": "Claude",  "icon": ID_CLAUDE, "ce": CE_CLAUDE, "match": "claude"},
    "pplx":   {"title": "Perplexity", "icon": ID_PPLX, "ce": CE_PPLX, "match": "perplex"},
}

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
DAYS_EMOJI = {3: CE_D3, 7: CE_D7, 14: CE_D14, 30: CE_D30, 60: CE_D60}
DAYS_EMOJI_P = {3: "⚡", 7: "📅", 14: "🌟", 30: "👑", 60: "🔥"}
CDK_SUPPORTED = {3, 30, 60}
CDK_ONLY = {60}
CDK_PATTERNS = [
    (re.compile(r"^3TG-[A-Z0-9]+$",   re.IGNORECASE), 3),
    (re.compile(r"^bbg[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                                       re.IGNORECASE), 30),
    (re.compile(r"^GGG-[A-Z0-9]+$",   re.IGNORECASE), 60),
]

HELP_TEXT = (
    f"{CE_BOX} <b>Склад подписок</b>\n\n"
    f"{CE_OUT} <b>Как выдавать:</b>\n"
    f"Нажми {CE_GROK} <b>Grok</b>, {CE_GEMINI} <b>Gemini</b>, {CE_GPT} <b>ChatGPT</b>, "
    f"{CE_CAPCUT} <b>CapCut</b>, {CE_CLAUDE} <b>Claude</b> "
    f"или {CE_PPLX} <b>Perplexity</b> → выбери раздел\n\n"
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
pending_buy: dict[int, dict] = {}
pending_store: dict[int, list[str]] = {}
pending_emoji: dict[int, str] = {}
gpt_prod_cache: dict[str, dict] = {}

# continue bot_x01.py
_NEXT = Path(__file__).resolve().with_name('bot_x01.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
