@dp.message(F.text == "Магазины")
async def handle_mall_button(message: Message):
    if not is_admin(message):
        return
    if not load_shops():
        await message.answer(
            f"{CE_WARN} Нет подключённых шопов.\n"
            f"Добавь: <code>/addshop Название | https://url | КЛЮЧ | ссылка_на_шоп</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    text, kb = _mall_shops_view()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "mall_home")
async def cb_mall_home(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    await cb.answer()
    text, kb = _mall_shops_view()
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


MALL_PAGE_SIZE = 20          # Telegram: не больше 100 кнопок в сообщении
mall_page: dict[int, int] = {}  # user_id -> открытая страница ассортимента


@dp.callback_query(F.data.startswith("mall_sel:"))
async def cb_mall_sel(cb: CallbackQuery):
    """mall_sel:<shop_id>[:<page>] — ассортимент шопа постранично."""
    if not is_admin_cb(cb):
        return
    parts = cb.data.split(":")
    shop = get_shop(int(parts[1]))
    if not shop:
        await cb.answer("Шоп не найден.", show_alert=True)
        return
    page = int(parts[2]) if len(parts) > 2 else 0
    mall_page[cb.from_user.id] = page
    await cb.answer("Загружаю ассортимент...")
    await _mall_show_products(cb, shop, page)


@dp.callback_query(F.data == "mall_noop")
async def cb_mall_noop(cb: CallbackQuery):
    await cb.answer()


async def _mall_show_products(cb: CallbackQuery, shop: dict, page: int = 0) -> None:
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="mall_home", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
    ])
    data = await shop_api(shop, "GET", "/api/products")
    if not data.get("success"):
        await cb.message.edit_text(
            f"{CE_NO} Ошибка API ({escape(shop.get('name', '?'))}):\n<code>{escape(str(data.get('error')))}</code>",
            reply_markup=back_kb, parse_mode="HTML",
        )
        return
    prods = data.get("products", [])
    if not prods:
        await cb.message.edit_text(
            f"{CE_EMPTY} В шопе «{escape(shop.get('name', '?'))}» пока нет товаров.",
            reply_markup=back_kb, parse_mode="HTML",
        )
        return
    bal = await shop_api(shop, "GET", "/api/balance")
    bal_line = ""
    if bal.get("success"):
        bal_line = f"\nБаланс: <b>{fmt_usdt(bal.get('balance_usdt', 0))}</b>"

    sid = shop.get("id")
    pages = max(1, -(-len(prods) // MALL_PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    lines = [f"{CE_MALL} <b>{escape(shop.get('name', ''))} — весь ассортимент:</b>{bal_line}"]
    if pages > 1:
        lines.append(f"Позиций: <b>{len(prods)}</b> · страница {page + 1}/{pages}")
    rows = []
    for p in prods:  # кэш — для всех, кнопки — только для текущей страницы
        gpt_prod_cache[f"{sid}:{p['id']}"] = p
    for p in prods[page * MALL_PAGE_SIZE:(page + 1) * MALL_PAGE_SIZE]:
        stock = int(p.get("stock", 0) or 0)
        price = fmt_usdt(p.get("price_usdt", 0) or p.get("price_vnd", 0))
        name = (p.get("name") or "?")[:40]
        kw = dict(
            text=f"{name} · {stock} шт · {price}",
            callback_data=f"mall_prod:{sid}:{p['id']}",
            icon_custom_emoji_id=ID_OK if stock > 0 else ID_NO,
        )
        if stock > 0:
            kw["style"] = ButtonStyle.SUCCESS
        rows.append([InlineKeyboardButton(**kw)])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀", callback_data=f"mall_sel:{sid}:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="mall_noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="▶", callback_data=f"mall_sel:{sid}:{page + 1}"))
        rows.append(nav)
    if shop.get("link"):
        rows.append([InlineKeyboardButton(text="Пополнить баланс в шопе", url=shop["link"], style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_UP)])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="mall_home", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n…"
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("mall_prod:"))
async def cb_mall_prod(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    _, sid_s, pid_s = cb.data.split(":")
    sid, pid = int(sid_s), int(pid_s)
    shop = get_shop(sid)
    if not shop:
        await cb.answer("Шоп не найден.", show_alert=True)
        return
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
    pending_buy[cb.from_user.id] = {"p": p, "cat": "mall", "shop_id": sid}
    desc = translate_desc(p.get("description", ""))
    desc_block = f"\n<blockquote>{escape(desc)}</blockquote>\n" if desc else ""
    back_page = mall_page.get(cb.from_user.id, 0)
    rows = [[InlineKeyboardButton(text="Назад", callback_data=f"mall_sel:{sid}:{back_page}", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)]]
    if shop.get("link"):
        rows.insert(0, [InlineKeyboardButton(text="Пополнить баланс в шопе", url=shop["link"], style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_UP)])
    await cb.message.edit_text(
        f"{CE_MALL} <b>{escape(p['name'])}</b>\n"
        f"Магазин: {escape(shop.get('name', '?'))}\n"
        f"Цена: {fmt_usdt(p.get('price_usdt', 0))}\n"
        f"В наличии: <b>{p.get('stock', 0)}</b> шт.\n"
        f"{desc_block}\n"
        f"{CE_KBD} <b>Отправь количество сообщением</b> (1-100):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


# ─── Универсальный обработчик входящего текста ──────────────────────────────

# continue bot_x16.py
_NEXT = Path(__file__).resolve().with_name('bot_x16.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
