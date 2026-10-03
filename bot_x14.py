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


# ─── Раздел «Магазины» — все шопы и весь ассортимент ──────────────────────────────

ID_MALL = "5373052667671093676"
CE_MALL = _e(ID_MALL, "🏪")

_orig_main_keyboard = main_keyboard

def main_keyboard() -> ReplyKeyboardMarkup:
    cat_btns = [
        KeyboardButton(text=c["title"], icon_custom_emoji_id=c["icon"])
        for c in all_cats().values()
    ]
    rows = [[KeyboardButton(text="Магазины", icon_custom_emoji_id=ID_MALL)]]
    rows += [cat_btns[i:i + 2] for i in range(0, len(cat_btns), 2)]
    rows.append([
        KeyboardButton(text="Автопокупки", icon_custom_emoji_id=ID_PIN),
        KeyboardButton(text="Помощь", icon_custom_emoji_id=ID_HELP),
    ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)

refresh_mk()

_orig_get_cat = get_cat

def get_cat(cat: str) -> dict:
    if cat == "mall":
        return {"title": "Магазины", "icon": ID_MALL, "ce": CE_MALL, "match": "", "custom": True}
    return _orig_get_cat(cat)


def _mall_shops_view() -> tuple[str, InlineKeyboardMarkup]:
    shops = load_shops()
    rows = [
        [InlineKeyboardButton(
            text=s.get("name", f"Шоп {s.get('id', '?')}"),
            callback_data=f"mall_sel:{s.get('id')}",
            style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_MALL,
        )]
        for s in shops
    ]
    text = (
        f"{CE_MALL} <b>Магазины</b>\n\n"
        f"{CE_BOX} Подключено: <b>{len(shops)}</b>\n"
        f"Выбери магазин — покажу весь ассортимент:"
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


# Хендлер кнопки «Магазины» объявлен и зарегистрирован в bot_x15.py

# continue bot_x15.py
_NEXT = Path(__file__).resolve().with_name('bot_x15.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
