def translate_desc(text: str) -> str:
    if not text:
        return ""
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
            ln = re.sub(rf"\b{re.escape(en)}\b", ru, ln, flags=re.IGNORECASE)
        out.append(ln)
    return "\n".join(out).strip()


def cat_filter(products: list[dict], cat: str) -> list[dict]:
    match = get_cat(cat)["match"]
    return [p for p in products if match in p.get("name", "").lower()]

def prod_short_name(name: str, cat: str) -> str:
    n = re.sub(r"^[^A-Za-z0-9]+", "", name)
    n = re.sub(r"(?i)^(chat\s*gpt|claude|perplexity|pplx|grok|link\s+gemini|gemini|capcut)\s*(plus|pro(\s+team)?|max|sonnet|opus)?\s*", "", n).strip(" -")
    return n or name


async def pick_currency(shop: dict, total_vnd: float, total_usdt: float) -> tuple[str | None, dict]:
    bal = await shop_api(shop, "GET", "/api/balance")
    if not bal.get("success"):
        return None, bal
    if bal.get("balance_vnd", 0) >= total_vnd:
        return "vnd", bal
    if bal.get("balance_usdt", 0) >= total_usdt:
        return "usdt", bal
    return None, bal


async def send_items_chunks(send_func, header: str, items: list[str]) -> None:
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


def days_label(days: int) -> str:
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


def main_keyboard() -> ReplyKeyboardMarkup:
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
    global MK
    MK = main_keyboard()


def grok_days_keyboard() -> InlineKeyboardMarkup:
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

# continue bot_x03.py
_NEXT = Path(__file__).resolve().with_name('bot_x03.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
