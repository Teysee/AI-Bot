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

# continue bot_x09.py
_NEXT = Path(__file__).resolve().with_name('bot_x09.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
