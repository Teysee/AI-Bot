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
AUTOBUY_FILE = Path(os.getenv("AUTOBUY_FILE", "autobuy.json"))

# Shop API (покупка ChatGPT-аккаунтов)
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
    f"Нажми {CE_GROK} <b>Grok</b>, {CE_GEMINI} <b>Gemini</b> или {CE_GPT} <b>ChatGPT</b> → выбери нужный тип\n\n"
    f"{CE_GPT} <b>ChatGPT:</b> Купить — покупка через шоп (сейчас или автопокупка), "
    f"Хранилище — выдача со склада\n\n"
    f"{CE_LIST} /list — список Grok-аккаунтов\n"
    f"{CE_COUNT} /count — статистика всего склада\n"
    f"{CE_TRASH} /use N — удалить аккаунт №N\n"
    f"{CE_WARN} /clear — очистить Grok-склад\n"
    f"{CE_KEY} /settoken TOKEN — сменить токен бота\n"
    f"{CE_KEY} /setapikey КЛЮЧ — API-ключ шопа\n\n"
    f"{CE_TIP} Кнопки пропали? Отправь /start"
)

_lock = asyncio.Lock()
pending_add: dict[int, list[dict]] = {}
pending_clear: set[int] = set()
pending_buy: dict[int, dict] = {}      # user_id -> {"p": product, "qty": int}
gpt_prod_cache: dict[int, dict] = {}   # product_id -> product (снимок последнего /api/products)


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

def load_autobuy() -> list[dict]:
    return _load_json(AUTOBUY_FILE)

def save_autobuy(data: list[dict]) -> None:
    _save_json(AUTOBUY_FILE, data)


# ChatGPT-аккаунт: "mail | password | 2fa" (формат шопа, 3 части через |)
RE_CHATGPT_LINE = re.compile(
    r"^([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\s*\|\s*(\S+)\s*\|\s*(\S+)$"
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


def fmt_vnd(v) -> str:
    return f"{int(v):,}".replace(",", " ") + "₫"

def fmt_usdt(v) -> str:
    return f"{float(v):g}$"

def gpt_filter(products: list[dict]) -> list[dict]:
    return [p for p in products if "gpt" in p.get("name", "").lower()]

def gpt_short_name(name: str) -> str:
    n = re.sub(r"(?i)^chat\s*gpt\s*(plus)?\s*", "", name).strip(" -")
    return n or name


async def pick_currency(total_vnd: float, total_usdt: float) -> tuple[str | None, dict]:
    """Выбрать валюту, на которую хватает баланса. Возвращает (валюта|None, balance-ответ)."""
    bal = await shop_api("GET", "/api/balance")
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
                KeyboardButton(text="ChatGPT", icon_custom_emoji_id=ID_GPT),
            ],
            [
                KeyboardButton(text="Список", icon_custom_emoji_id=ID_LIST),
                KeyboardButton(text="Счёт",   icon_custom_emoji_id=ID_COUNT),
            ],
            [KeyboardButton(text="Помощь",    icon_custom_emoji_id=ID_HELP)],
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


def chatgpt_menu_keyboard(watch_count: int = 0) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="Купить",    callback_data="gpt_buy",   style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_OUT),
        InlineKeyboardButton(text="Хранилище", callback_data="gpt_store", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_BOX),
    ]]
    if watch_count:
        rows.append([InlineKeyboardButton(
            text=f"Автопокупки ({watch_count})", callback_data="gpt_watch",
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
            f"Баланс: <b>{fmt_vnd(bal.get('balance_vnd', 0))}</b> / <b>{fmt_usdt(bal.get('balance_usdt', 0))}</b>",
            parse_mode="HTML", reply_markup=MK,
        )
    else:
        await message.answer(
            f"{CE_WARN} Ключ сохранён, но проверка не прошла:\n"
            f"<code>{escape(str(bal.get('error')))}</code>",
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

@dp.message(F.text.in_({"Grok", "🤖 Grok"}))
async def handle_grok_button(message: Message):
    if not is_admin(message):
        return
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
    await message.answer(
        f"{CE_GROK} <b>Grok — выбери срок подписки:</b>\n" + "\n".join(lines),
        reply_markup=grok_days_keyboard(), parse_mode="HTML",
    )


@dp.message(F.text.in_({"Gemini", "💎 Gemini"}))
async def handle_gemini_button(message: Message):
    if not is_admin(message):
        return
    async with _lock:
        gemini_lst = load_gemini()
        if not gemini_lst:
            await message.answer(
                f"{CE_EMPTY} Нет Gemini-ссылок в хранилище.",
                parse_mode="HTML", reply_markup=MK,
            )
            return
        item = gemini_lst.pop(0)
        save_gemini(gemini_lst)
    url = item.get("url", "")
    await message.answer(
        f"{CE_GEMINI} <b>Gemini:</b>\n{url}\n\n"
        f"<i>Осталось: {len(gemini_lst)} шт.</i>",
        parse_mode="HTML", reply_markup=MK,
    )


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


# ─── ChatGPT: меню, покупка, хранилище ───────────────────────────────────────

def _gpt_menu_text() -> str:
    store = load_chatgpt()
    watches = load_autobuy()
    txt = (
        f"{CE_GPT} <b>ChatGPT</b>\n\n"
        f"{CE_BOX} На складе: <b>{len(store)}</b> шт."
    )
    if watches:
        total = sum(w.get("qty_left", 0) for w in watches)
        txt += f"\n{CE_PIN} Автопокупки: <b>{len(watches)}</b> (ждём {total} шт.)"
    return txt


@dp.message(F.text == "ChatGPT")
async def handle_chatgpt_button(message: Message):
    if not is_admin(message):
        return
    await message.answer(
        _gpt_menu_text(),
        reply_markup=chatgpt_menu_keyboard(len(load_autobuy())),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "gpt_menu")
async def cb_gpt_menu(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    await cb.answer()
    await cb.message.edit_text(
        _gpt_menu_text(),
        reply_markup=chatgpt_menu_keyboard(len(load_autobuy())),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "gpt_buy")
async def cb_gpt_buy(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    await cb.answer("Загружаю товары...")
    data = await shop_api("GET", "/api/products")
    if not data.get("success"):
        await cb.message.edit_text(
            f"{CE_NO} Ошибка API:\n<code>{escape(str(data.get('error')))}</code>",
            reply_markup=chatgpt_menu_keyboard(len(load_autobuy())), parse_mode="HTML",
        )
        return
    prods = gpt_filter(data.get("products", []))
    if not prods:
        await cb.message.edit_text(
            f"{CE_EMPTY} В шопе нет ChatGPT-товаров.",
            reply_markup=chatgpt_menu_keyboard(len(load_autobuy())), parse_mode="HTML",
        )
        return
    bal = await shop_api("GET", "/api/balance")
    bal_line = ""
    if bal.get("success"):
        bal_line = f"\nБаланс: <b>{fmt_vnd(bal.get('balance_vnd', 0))}</b> | <b>{fmt_usdt(bal.get('balance_usdt', 0))}</b>"

    lines = [f"{CE_GPT} <b>ChatGPT — купить:</b>{bal_line}\n"]
    rows = []
    for p in prods:
        gpt_prod_cache[p["id"]] = p
        stock = p.get("stock", 0)
        mark = CE_OK if stock > 0 else CE_EMPTY
        lines.append(
            f"{mark} <b>{escape(p['name'])}</b>\n"
            f"      {fmt_vnd(p.get('price_vnd', 0))} / {fmt_usdt(p.get('price_usdt', 0))} — в наличии: <b>{stock}</b>"
        )
        rows.append([InlineKeyboardButton(
            text=f"{gpt_short_name(p['name'])} · {stock} шт",
            callback_data=f"gpt_prod:{p['id']}",
            style=ButtonStyle.SUCCESS if stock > 0 else ButtonStyle.PRIMARY,
            icon_custom_emoji_id=ID_GPT,
        )])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="gpt_menu", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("gpt_prod:"))
async def cb_gpt_prod(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    pid = int(cb.data.split(":")[1])
    p = gpt_prod_cache.get(pid)
    if p is None:
        data = await shop_api("GET", "/api/products")
        for x in data.get("products", []):
            gpt_prod_cache[x["id"]] = x
        p = gpt_prod_cache.get(pid)
    if p is None:
        await cb.answer("Товар не найден, обнови список.", show_alert=True)
        return
    await cb.answer()
    pending_buy[cb.from_user.id] = {"p": p}
    await cb.message.edit_text(
        f"{CE_GPT} <b>{escape(p['name'])}</b>\n"
        f"Цена: {fmt_vnd(p.get('price_vnd', 0))} / {fmt_usdt(p.get('price_usdt', 0))}\n"
        f"В наличии: <b>{p.get('stock', 0)}</b> шт.\n\n"
        f"{CE_KBD} <b>Отправь количество сообщением</b> (1-100):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="gpt_buy", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
        ]),
        parse_mode="HTML",
    )


def _buy_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить сейчас", callback_data="gpt_now",  style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_OK)],
        [InlineKeyboardButton(text="Автопокупка (когда появится)", callback_data="gpt_auto", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_PIN)],
        [InlineKeyboardButton(text="Отмена", callback_data="gpt_cancelbuy", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
    ])


@dp.callback_query(F.data == "gpt_now")
async def cb_gpt_now(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    info = pending_buy.get(cb.from_user.id)
    if not info or "qty" not in info:
        await cb.answer("Заказ устарел — начни заново.", show_alert=True)
        return
    await cb.answer("Покупаю...")
    p, qty = info["p"], info["qty"]
    total_vnd  = p.get("price_vnd", 0) * qty
    total_usdt = p.get("price_usdt", 0) * qty
    currency, bal = await pick_currency(total_vnd, total_usdt)
    if currency is None:
        err = bal.get("error")
        if err:
            msg = f"{CE_NO} Ошибка API:\n<code>{escape(str(err))}</code>"
        else:
            msg = (
                f"{CE_WARN} <b>Недостаточно средств.</b>\n"
                f"Нужно: {fmt_vnd(total_vnd)} / {fmt_usdt(total_usdt)}\n"
                f"Баланс: {fmt_vnd(bal.get('balance_vnd', 0))} / {fmt_usdt(bal.get('balance_usdt', 0))}"
            )
        await cb.message.edit_text(msg, reply_markup=_buy_confirm_keyboard(), parse_mode="HTML")
        return

    res = await shop_api("POST", "/api/buy", {
        "product_id": p["id"], "quantity": qty, "currency": currency,
    })
    if not res.get("success"):
        await cb.message.edit_text(
            f"{CE_NO} Покупка не прошла:\n<code>{escape(str(res.get('error')))}</code>\n\n"
            f"{CE_TIP} Можно включить автопокупку — куплю, как только появится.",
            reply_markup=_buy_confirm_keyboard(), parse_mode="HTML",
        )
        return

    pending_buy.pop(cb.from_user.id, None)
    order = res.get("order", {})
    items = res.get("items", [])
    nb = res.get("new_balance")
    head = (
        f"{CE_OK} <b>Куплено: {escape(str(order.get('product', p['name'])))}</b>\n"
        f"Количество: <b>{order.get('total_items', len(items))}</b>"
        + (f" (бонус +{order.get('bonus')})" if order.get("bonus") else "")
        + f"\nЦена: <b>{order.get('total_price')}</b> {order.get('currency', currency.upper())}"
        + (f"\nНовый баланс: <b>{nb}</b>" if nb is not None else "")
    )
    await cb.message.edit_text(head, parse_mode="HTML")
    await send_items_chunks(
        lambda t: cb.message.answer(t, parse_mode="HTML"),
        f"{CE_GPT} <b>Аккаунты:</b>", items,
    )


@dp.callback_query(F.data == "gpt_auto")
async def cb_gpt_auto(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    info = pending_buy.pop(cb.from_user.id, None)
    if not info or "qty" not in info:
        await cb.answer("Заказ устарел — начни заново.", show_alert=True)
        return
    p, qty = info["p"], info["qty"]
    async with _lock:
        watches = load_autobuy()
        watches.append({
            "product_id": p["id"],
            "name": p["name"],
            "qty_left": qty,
            "chat_id": cb.message.chat.id,
            "notified_low_balance": False,
        })
        save_autobuy(watches)
    await cb.answer("Автопокупка создана.")
    await cb.message.edit_text(
        f"{CE_PIN} <b>Автопокупка создана:</b>\n"
        f"{CE_GPT} {escape(p['name'])} × <b>{qty}</b>\n\n"
        f"Проверяю наличие каждые {AUTOBUY_INTERVAL} сек. "
        f"Как только появится — куплю и пришлю сюда.",
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "gpt_cancelbuy")
async def cb_gpt_cancelbuy(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    pending_buy.pop(cb.from_user.id, None)
    await cb.answer("Отменено.")
    await cb.message.edit_text(f"{CE_NO} Покупка отменена.", parse_mode="HTML")


@dp.callback_query(F.data == "gpt_store")
async def cb_gpt_store(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    async with _lock:
        store = load_chatgpt()
        if not store:
            await cb.answer()
            await cb.message.edit_text(
                f"{CE_EMPTY} ChatGPT-склад пустой.\n\n"
                f"{CE_TIP} Кинь аккаунты в чат в формате:\n"
                f"<code>mail | password | 2fa</code>",
                reply_markup=chatgpt_menu_keyboard(len(load_autobuy())), parse_mode="HTML",
            )
            return
        item = store.pop(0)
        save_chatgpt(store)
    await cb.answer()
    await cb.message.edit_text(
        f"{CE_OUT} <b>ChatGPT аккаунт:</b>\n"
        f"<code>{escape(item.get('raw', ''))}</code>\n\n"
        f"<i>Осталось: {len(store)} шт.</i>",
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "gpt_watch")
async def cb_gpt_watch(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    await cb.answer()
    watches = load_autobuy()
    if not watches:
        await cb.message.edit_text(
            _gpt_menu_text(),
            reply_markup=chatgpt_menu_keyboard(0), parse_mode="HTML",
        )
        return
    lines = [f"{CE_PIN} <b>Активные автопокупки:</b>\n"]
    rows = []
    for i, w in enumerate(watches):
        lines.append(f"{i + 1}. {escape(w.get('name', '?'))} — ждём <b>{w.get('qty_left', 0)}</b> шт.")
        rows.append([InlineKeyboardButton(
            text=f"Убрать №{i + 1}", callback_data=f"gpt_unwatch:{i}",
            style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_TRASH,
        )])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="gpt_menu", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_HOME)])
    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("gpt_unwatch:"))
async def cb_gpt_unwatch(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    idx = int(cb.data.split(":")[1])
    async with _lock:
        watches = load_autobuy()
        removed = watches.pop(idx) if 0 <= idx < len(watches) else None
        save_autobuy(watches)
    await cb.answer("Убрано." if removed else "Уже нет.")
    watches = load_autobuy()
    if watches:
        await cb_gpt_watch(cb)
    else:
        await cb.message.edit_text(
            _gpt_menu_text(),
            reply_markup=chatgpt_menu_keyboard(0), parse_mode="HTML",
        )


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

    # ── Количество для покупки ChatGPT ──────────────────────────────────────
    uid = message.from_user.id
    if uid in pending_buy and text.isdigit():
        qty = int(text)
        if not 1 <= qty <= 100:
            await message.answer(f"{CE_WARN} Количество: от 1 до 100.", parse_mode="HTML")
            return
        pending_buy[uid]["qty"] = qty
        p = pending_buy[uid]["p"]
        total_vnd  = p.get("price_vnd", 0) * qty
        total_usdt = p.get("price_usdt", 0) * qty
        await message.answer(
            f"{CE_GPT} <b>{escape(p['name'])}</b>\n"
            f"Количество: <b>{qty}</b> шт.\n"
            f"Итого: <b>{fmt_vnd(total_vnd)}</b> / <b>{fmt_usdt(total_usdt)}</b>\n"
            f"В наличии сейчас: {p.get('stock', 0)} шт.\n\n"
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

    # ── ChatGPT: строки "mail | password | 2fa" ────────────────────────────
    detected_gpt = [m.group(0) for l in raw_lines if (m := RE_CHATGPT_LINE.match(l))]
    if detected_gpt:
        async with _lock:
            store = load_chatgpt()
            existing = {a.get("raw", "").lower() for a in store}
            added, dupes = 0, 0
            for raw in detected_gpt:
                norm = " | ".join(s.strip() for s in raw.split("|"))
                if norm.lower() in existing:
                    dupes += 1
                else:
                    store.append({"raw": norm})
                    existing.add(norm.lower())
                    added += 1
            save_chatgpt(store)
        msg = f"{CE_GPT} ChatGPT добавлено: <b>{added}</b> шт."
        if dupes:
            msg += f"\n{CE_WARN} Дублей: {dupes}"
        msg += f"\n<i>Всего ChatGPT: {len(store)} шт.</i>"
        await message.answer(msg, parse_mode="HTML", reply_markup=MK)
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

async def _autobuy_tick(bot: Bot) -> None:
    watches = load_autobuy()
    if not watches:
        return
    data = await shop_api("GET", "/api/products")
    if not data.get("success"):
        return
    stock_map = {p["id"]: p for p in data.get("products", [])}
    remaining: list[dict] = []
    changed = False

    for w in watches:
        p = stock_map.get(w.get("product_id"))
        stock = p.get("stock", 0) if p else 0
        if not p or stock <= 0:
            remaining.append(w)
            continue

        want = min(w.get("qty_left", 0), stock, 100)
        price_vnd, price_usdt = p.get("price_vnd", 0), p.get("price_usdt", 0)
        currency, bal = await pick_currency(price_vnd * want, price_usdt * want)

        if currency is None and not bal.get("error"):
            # На полный объём не хватает — берём сколько можем
            afford_vnd  = int(bal.get("balance_vnd", 0) // price_vnd) if price_vnd else 0
            afford_usdt = int(bal.get("balance_usdt", 0) // price_usdt) if price_usdt else 0
            if afford_vnd >= afford_usdt and afford_vnd >= 1:
                currency, want = "vnd", min(want, afford_vnd)
            elif afford_usdt >= 1:
                currency, want = "usdt", min(want, afford_usdt)

        if currency is None:
            if not w.get("notified_low_balance"):
                w["notified_low_balance"] = True
                changed = True
                await bot.send_message(
                    w["chat_id"],
                    f"{CE_WARN} <b>Автопокупка: товар появился, но не хватает баланса!</b>\n"
                    f"{CE_GPT} {escape(w.get('name', '?'))} — в наличии {stock} шт.\n"
                    f"Баланс: {fmt_vnd(bal.get('balance_vnd', 0))} / {fmt_usdt(bal.get('balance_usdt', 0))}\n"
                    f"Пополни — куплю автоматически.",
                    parse_mode="HTML",
                )
            remaining.append(w)
            continue

        res = await shop_api("POST", "/api/buy", {
            "product_id": w["product_id"], "quantity": want, "currency": currency,
        })
        if not res.get("success"):
            log.warning("Autobuy failed for %s: %s", w.get("name"), res.get("error"))
            remaining.append(w)
            continue

        items = res.get("items", [])
        w["qty_left"] = max(0, w.get("qty_left", 0) - want)
        w["notified_low_balance"] = False
        changed = True

        head = f"{CE_PIN} <b>Автопокупка сработала!</b>\n{CE_GPT} {escape(w.get('name', '?'))} — куплено <b>{want}</b> шт."
        if w["qty_left"] > 0:
            head += f"\n<i>Осталось докупить: {w['qty_left']} шт. — продолжаю следить.</i>"
            remaining.append(w)
        else:
            head += f"\n{CE_OK} <i>Заказ выполнен полностью.</i>"
        nb = res.get("new_balance")
        if nb is not None:
            head += f"\nНовый баланс: <b>{nb}</b>"

        async def _send(t, chat_id=w["chat_id"]):
            await bot.send_message(chat_id, t, parse_mode="HTML")
        await _send(head)
        await send_items_chunks(_send, f"{CE_GPT} <b>Аккаунты:</b>", items)

    if changed or len(remaining) != len(watches):
        async with _lock:
            save_autobuy(remaining)


async def autobuy_loop(bot: Bot) -> None:
    log.info("Autobuy loop started (interval %ss)", AUTOBUY_INTERVAL)
    while True:
        try:
            await _autobuy_tick(bot)
        except Exception:
            log.exception("Autobuy tick failed")
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
        BotCommand(command="setapikey", description="🛒 Задать API-ключ шопа"),
        BotCommand(command="help",      description="❓ Помощь"),
    ])
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    asyncio.create_task(autobuy_loop(bot))
    log.info("Commands registered. Starting polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
