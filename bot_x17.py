def load_seen_products() -> dict[str, list]:
    data = _load_json_any(PRODUCTS_SEEN_FILE)
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
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
    skey = str(shop.get("id"))
    seen_all = load_seen_products()
    current = {p["id"] for p in products}
    if skey not in seen_all:
        seen_all[skey] = sorted(current)
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

# continue bot_x18.py
_NEXT = Path(__file__).resolve().with_name('bot_x18.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
