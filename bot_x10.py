# ─── Шоп-разделы (Grok / Gemini / ChatGPT / CapCut / свои) ──────────────────────────────

def _cat_store_count(cat: str) -> str:
    if cat == "grok":
        return f"{len(load_accounts())} акк. | {len(load_cdk())} CDK"
    if cat == "gemini":
        return f"{len(load_gemini())} ссыл."
    load_fn, _ = store_funcs(cat)
    return f"{len(load_fn())} шт."


def _cat_menu_text(cat: str) -> str:
    c = get_cat(cat)
    txt = f"{c['ce']} <b>{c['title']}</b>\n\n{CE_OUT} <b>Купить</b> — товары раздела из магазина"
    mine = [w for w in load_autobuy() if w.get("cat") == cat]
    if mine:
        total = sum(w.get("qty_left", 0) for w in mine)
        txt += f"\n{CE_PIN} Автопокупки в разделе: <b>{len(mine)}</b> (ждём {total} шт.)"
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


@dp.message(F.text == "Claude")
async def handle_claude_button(message: Message):
    if not is_admin(message):
        return
    await _send_cat_menu(message, "claude")


@dp.message(F.text == "Perplexity")
async def handle_pplx_button(message: Message):
    if not is_admin(message):
        return
    await _send_cat_menu(message, "pplx")


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

    lines = [f"{c['ce']} <b>{c['title']} — {escape(shop.get('name', ''))}:</b>{bal_line}"]
    rows = []
    for p in prods:
        gpt_prod_cache[f"{shop.get('id')}:{p['id']}"] = p
        stock = int(p.get("stock", 0) or 0)
        price = fmt_usdt(p.get("price_usdt", 0) or p.get("price_vnd", 0))
        short = prod_short_name(p["name"], cat)
        kw = dict(
            text=f"{short} · {stock} шт · {price}",
            callback_data=f"shop_prod:{cat}:{shop.get('id')}:{p['id']}",
            icon_custom_emoji_id=ID_OK if stock > 0 else ID_NO,
        )
        if stock > 0:
            kw["style"] = ButtonStyle.SUCCESS
        rows.append([InlineKeyboardButton(**kw)])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"shop_menu:{cat}", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
    )

# continue bot_x11.py
_NEXT = Path(__file__).resolve().with_name('bot_x11.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
