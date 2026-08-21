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

# continue bot_x12.py
_NEXT = Path(__file__).resolve().with_name('bot_x12.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
