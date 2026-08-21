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


# ─── Добавление аккаунтов "mail | pass [| код]" — выбор раздела ──────────────────────────────

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
    await cb.message.edit_text(msg, parse_mode="HTML")


@dp.callback_query(F.data == "store_cancel")
async def cb_store_cancel(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    pending_store.pop(cb.from_user.id, None)
    await cb.answer("Отменено.")
    await cb.message.edit_text(f"{CE_NO} Добавление отменено.", parse_mode="HTML")


# ─── Grok inline callbacks ──────────────────────────────

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

# continue bot_x14.py
_NEXT = Path(__file__).resolve().with_name('bot_x14.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
