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


# ─── Добавление аккаунтов (inline callback) ─────────────────────────────────────

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
    uid = message.from_user.id

    # ── Ожидание эмодзи для раздела ──────────────────────────────────────
    if uid in pending_emoji:
        key = pending_emoji.pop(uid)
        cats = load_custom_cats()
        target = next((c for c in cats if c.get("key") == key), None)
        if target is None:
            await message.answer(f"{CE_WARN} Раздел не найден.", parse_mode="HTML", reply_markup=MK)
            return
        custom_ids = [e.custom_emoji_id for e in (message.entities or []) if e.type == "custom_emoji"]
        if custom_ids:
            target["emoji_id"] = custom_ids[0]
            save_custom_cats(cats)
            refresh_mk()
            await message.answer(
                f"{CE_OK} Эмодзи для раздела <b>{escape(target.get('title', '?'))}</b> установлен!\n"
                f"{CE_TIP} Нажми /start, чтобы кнопки внизу обновились.",
                parse_mode="HTML", reply_markup=MK,
            )
        elif text and len(text) <= 4:
            # обычный эмодзи — добавим в название кнопки (иконку может дать только кастомный)
            target["title"] = f"{text} {target.get('title', '').strip()}".strip()
            save_custom_cats(cats)
            refresh_mk()
            await message.answer(
                f"{CE_OK} Добавил {escape(text)} в название раздела.\n"
                f"{CE_TIP} Кастомный эмодзи из премиум-пака может стать иконкой кнопки — /setemoji.\n"
                f"Нажми /start, чтобы кнопки обновились.",
                parse_mode="HTML", reply_markup=MK,
            )
        else:
            pending_emoji[uid] = key
            await message.answer(f"{CE_WARN} Это не похоже на эмодзи. Пришли эмодзи или /skip.", parse_mode="HTML")
        return

    # ── Кнопки пользовательских разделов ────────────────────────────────────
    for key, c in all_cats().items():
        if c.get("custom") and text == c["title"]:
            await _send_cat_menu(message, key)
            return

    # ── Количество для покупки в шопе ────────────────────────────────────────
    if uid in pending_buy and text.isdigit():
        qty = int(text)
        if not 1 <= qty <= 100:
            await message.answer(f"{CE_WARN} Количество: от 1 до 100.", parse_mode="HTML")
            return
        pending_buy[uid]["qty"] = qty
        p = pending_buy[uid]["p"]
        shop = get_shop(pending_buy[uid].get("shop_id", 0)) or default_shop()
        ce = get_cat(pending_buy[uid].get("cat", "gpt"))["ce"]
        total_usdt = p.get("price_usdt", 0) * qty
        await message.answer(
            f"{ce} <b>{escape(p['name'])}</b>\n"
            f"Магазин: {escape((shop or {}).get('name', '?'))}\n"
            f"Количество: <b>{qty}</b> шт.\n"
            f"Итого: <b>{fmt_usdt(total_usdt)}</b>\n"
            f"В наличии сейчас: {p.get('stock', 0)} шт.\n\n"
            f"Выбери действие:",
            reply_markup=_buy_confirm_keyboard(shop), parse_mode="HTML",
        )
        return

    # ── CDK: строки вида 3TG-…, bbg…-…, GGG-… ──────────────────────
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
        cat_rows = [
            [
                InlineKeyboardButton(text="ChatGPT", callback_data="store_as:gpt",    style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_GPT),
                InlineKeyboardButton(text="CapCut",  callback_data="store_as:capcut", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_CAPCUT),
            ],
            [InlineKeyboardButton(text="Grok",   callback_data="store_as:grok", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_GROK)],
        ]
        for key, c in all_cats().items():
            if c.get("custom"):
                cat_rows.append([InlineKeyboardButton(
                    text=c["title"], callback_data=f"store_as:{key}",
                    style=ButtonStyle.SUCCESS, icon_custom_emoji_id=c["icon"],
                )])
        cat_rows.append([InlineKeyboardButton(text="Отмена", callback_data="store_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
        await message.answer(
            f"{CE_IN} Найдено <b>{len(detected_pipe)}</b> аккаунт(ов). Куда добавить?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=cat_rows),
            parse_mode="HTML",
        )
        return

    # ── Gemini: ссылки serviceactivation.google.com ─────────────────────
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

    # ── Grok аккаунты ─────────────────────────────────────────────────────
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


# ─── Фоновая автопокупка (по всем шопам) ───────────────────────────────────

def load_seen_products() -> dict[str, list]:
    data = _load_json_any(PRODUCTS_SEEN_FILE)
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        # старый формат (один шоп) — считаем, что это шоп №1
        return {"1": data}
    return {}

def save_seen_products(seen: dict[str, list]) -> None:
    _save_json(PRODUCTS_SEEN_FILE, seen)

def _product_category(p: dict) -> str | None:
    name = p.get("name", "").lower()
    for cat, c in all_cats().items():
        if c["match"] in name:
            return cat
    return None


async def _check_new_products(bot: Bot, shop: dict, products: list[dict]) -> None:
    """Уведомить админа о новых товарах в магазине."""
    skey = str(shop.get("id"))
    seen_all = load_seen_products()
    current = {p["id"] for p in products}
    if skey not in seen_all:
        seen_all[skey] = sorted(current)  # первый запуск для шопа — запоминаем молча
        save_seen_products(seen_all)
        return
    seen = set(seen_all[skey])
    new_ids = current - seen
    if not new_ids:
        return
    for p in products:
        if p["id"] not in new_ids:
            continue
        cat = _product_category(p)
        kb = None
        if cat:
            c = get_cat(cat)
            where = f"{c['ce']} Уже доступен: раздел <b>{c['title']}</b> → Купить."
        else:
            where = f"{CE_TIP} Раздела под него нет — можно создать в один клик, потом выберешь эмодзи."
            gpt_prod_cache[f"{shop.get('id')}:{p['id']}"] = p
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="Создать раздел", callback_data=f"newcat:{shop.get('id')}:{p['id']}",
                    style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_BOX,
                ),
            ]])
        try:
            await bot.send_message(
                ADMIN_ID,
                f"{CE_PIN} <b>Новый товар в «{escape(shop.get('name', '?'))}»!</b>\n"
                f"<b>{escape(p.get('name', '?'))}</b>\n"
                f"Цена: {fmt_usdt(p.get('price_usdt', 0))} — в наличии: <b>{p.get('stock', 0)}</b> шт.\n\n"
                f"{where}",
                parse_mode="HTML", reply_markup=kb,
            )
        except Exception:
            log.exception("Failed to notify about new product %s", p.get("id"))
    seen_all[skey] = sorted(seen | current)
    save_seen_products(seen_all)


async def _autobuy_tick(bot: Bot, shop: dict, products: list[dict]) -> None:
    all_watches = load_autobuy()
    if not all_watches:
        return
    sid = shop.get("id")
    stock_map = {p["id"]: p for p in products}
    remaining: list[dict] = []
    changed = False

    for w in all_watches:
        if w.get("shop_id", 1) != sid:
            remaining.append(w)
            continue
        w_ce = get_cat(w.get("cat", "gpt"))["ce"]
        p = stock_map.get(w.get("product_id"))
        stock = p.get("stock", 0) if p else 0
        if not p or stock <= 0:
            remaining.append(w)
            continue

        want = min(w.get("qty_left", 0), stock, 100)
        price_vnd, price_usdt = p.get("price_vnd", 0), p.get("price_usdt", 0)
        currency, bal = await pick_currency(shop, price_vnd * want, price_usdt * want)

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
                kb = None
                if shop.get("link"):
                    kb = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="Пополнить баланс в шопе", url=shop["link"], style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_UP),
                    ]])
                await bot.send_message(
                    w["chat_id"],
                    f"{CE_WARN} <b>Автопокупка: товар появился, но не хватает баланса!</b>\n"
                    f"{w_ce} {escape(w.get('name', '?'))} — в наличии {stock} шт. ({escape(shop.get('name', '?'))})\n"
                    f"Баланс: {fmt_usdt(bal.get('balance_usdt', 0))}\n"
                    f"Пополни — куплю автоматически.",
                    parse_mode="HTML", reply_markup=kb,
                )
            remaining.append(w)
            continue

        res = await shop_api(shop, "POST", "/api/buy", {
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

        head = (
            f"{CE_PIN} <b>Автопокупка сработала!</b>\n"
            f"{w_ce} {escape(w.get('name', '?'))} — куплено <b>{want}</b> шт. ({escape(shop.get('name', '?'))})"
        )
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
        await send_items_chunks(_send, f"{w_ce} <b>Аккаунты:</b>", items)

    if changed or len(remaining) != len(all_watches):
        async with _lock:
            save_autobuy(remaining)


async def shop_loop(bot: Bot) -> None:
    log.info("Shop loop started (interval %ss)", AUTOBUY_INTERVAL)
    while True:
        try:
            for shop in load_shops():
                data = await shop_api(shop, "GET", "/api/products")
                if data.get("success"):
                    products = data.get("products", [])
                    await _check_new_products(bot, shop, products)
                    await _autobuy_tick(bot, shop, products)
        except Exception:
            log.exception("Shop loop tick failed")
        await asyncio.sleep(AUTOBUY_INTERVAL)


# ─── Reseller API (/v1) — переходник ────────────────────────────────────────────────

def _shop_api_type(shop: dict) -> str:
    """Тип API шопа: 'legacy' (первый шоп) или 'reseller' (/v1/..., ключ rsk_...)."""
    t = shop.get("api_type")
    if t in ("legacy", "reseller"):
        return t
    return "reseller" if str(shop.get("key", "")).startswith("rsk_") else "legacy"


def _strip_html(text: str) -> str:
    """Убрать HTML-теги из описаний Reseller API."""
    from html import unescape
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def _reseller_err(data) -> str:
    if isinstance(data, dict):
        d = data.get("detail")
        if isinstance(d, str):
            return d
        if d is not None:
            return json.dumps(d, ensure_ascii=False)[:300]
    return str(data)[:300]


async def _reseller_api(shop: dict, method: str, path: str, payload: dict | None = None) -> dict:
    """Переходник Reseller API (/v1/...) -> формат ответов первого шопа."""
    base = str(shop.get("base", "")).rstrip("/")
    headers = {"Authorization": f"Bearer {shop['key']}"}

    async def call(m: str, p: str, body: dict | None = None):
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.request(m, f"{base}{p}", json=body, headers=headers) as resp:
                return resp.status, await resp.json(content_type=None)

    try:
        if method == "GET" and path == "/api/balance":
            status, data = await call("GET", "/v1/me")
            if status != 200 or not isinstance(data, dict):
                return {"success": False, "error": _reseller_err(data)}
            return {
                "success": True,
                "username": data.get("name") or data.get("telegram_username", "?"),
                "balance_usdt": float(data.get("balance") or 0),
                "balance_vnd": -1,
            }

        if method == "GET" and path == "/api/products":
            status, data = await call("GET", "/v1/products")
            if status != 200 or not isinstance(data, dict):
                return {"success": False, "error": _reseller_err(data)}
            prods = []
            for p in data.get("products", []):
                stock = p.get("stock")
                desc = _strip_html(p.get("description") or "")
                if p.get("inputs"):
                    need = ", ".join(str(i.get("name", "?")) for i in p["inputs"])
                    desc = f"{desc}\n[!] Шоп требует при заказе: {need}".strip()
                prods.append({
                    "id": p.get("id"),
                    "name": p.get("name", "?"),
                    "price_usdt": float(p.get("your_unit_price") or p.get("retail_price") or 0),
                    "price_vnd": 0,
                    "stock": 999 if stock is None else int(stock),
                    "description": desc,
                })
            return {"success": True, "products": prods}

        if method == "POST" and path == "/api/buy":
            payload = payload or {}
            status, data = await call("POST", "/v1/orders", {
                "product_id": payload.get("product_id"),
                "quantity": payload.get("quantity", 1),
            })
            if status not in (200, 201) or not isinstance(data, dict) or "order_id" not in data:
                return {"success": False, "error": _reseller_err(data)}
            items = [str(c) for c in (data.get("delivered_codes") or [])]
            if not items:
                items = [
                    f"Заказ #{data.get('order_id')} принят (статус: {data.get('status')}). "
                    f"Коды придут позже — проверь заказ в шопе."
                ]
            instr = _strip_html(data.get("delivery_instructions") or "")
            if instr:
                items.append(f"Инструкция:\n{instr}")
            nb = None
            st_me, me = await call("GET", "/v1/me")
            if st_me == 200 and isinstance(me, dict):
                nb = f"{float(me.get('balance') or 0):g}$"
            return {
                "success": True,
                "order": {
                    "product": data.get("product_name", ""),
                    "total_items": data.get("delivered_count") or data.get("quantity", 0),
                    "total_price": data.get("amount"),
                    "currency": "USD",
                },
                "items": items,
                "new_balance": nb,
            }

        status, data = await call(method, path, payload)
        return data if isinstance(data, dict) else {"success": False, "error": str(data)[:300]}
    except Exception as e:
        return {"success": False, "error": f"Сеть/API недоступен: {e}"}


_legacy_shop_api = shop_api


async def shop_api(shop: dict | None, method: str, path: str, payload: dict | None = None) -> dict:
    """Роутер: шопы с Reseller API (ключ rsk_...) идут через переходник."""
    if shop and shop.get("key") and _shop_api_type(shop) == "reseller":
        return await _reseller_api(shop, method, path, payload)
    return await _legacy_shop_api(shop, method, path, payload)


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
        BotCommand(command="shops",    description="🏪 Магазины и балансы"),
        BotCommand(command="addshop",  description="➕ Подключить шоп"),
        BotCommand(command="newcat",   description="🆕 Новый раздел товаров"),
        BotCommand(command="setemoji", description="😎 Эмодзи раздела"),
        BotCommand(command="update",   description="⬆️ Обновить бота с GitHub"),
        BotCommand(command="settoken",  description="🔑 Сменить токен бота"),
        BotCommand(command="setapikey", description="🛒 Задать API-ключ шопа"),
        BotCommand(command="help",      description="❓ Помощь"),
    ])
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    asyncio.create_task(shop_loop(bot))
    log.info("Commands registered. Starting polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
