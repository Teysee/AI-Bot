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
        f"Проверяю наличие каждые несколько секунд. "
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

    if cat == "grok":
        await cb.answer()
        text, kb = _grok_days_view()
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        return

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

# continue bot_x13.py
_NEXT = Path(__file__).resolve().with_name('bot_x13.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
