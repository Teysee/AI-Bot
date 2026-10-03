# ─── Автопокупки и история покупок ──────────────────────────────
# Кнопка «Автопокупки» внизу и /autobuys: активные автопокупки + последние покупки
# (аккаунты из покупки можно открыть повторно, товар — купить ещё раз).
# Подключается из bot_x15.py и до bot_x16.py: обработчики команд и кнопок должны
# регистрироваться раньше общего обработчика текста.

import time

HISTORY_FILE = Path(os.getenv("HISTORY_FILE", "purchases.json"))
HISTORY_KEEP = 50   # сколько покупок хранить
HISTORY_SHOW = 8    # сколько показывать на экране


def load_history() -> list[dict]:
    return _load_json(HISTORY_FILE)


def add_history(*, auto: bool, name: str, cat: str, shop_id, product_id,
                qty: int, price: str = "", items: list | None = None) -> None:
    """Записать покупку. Ошибка записи не должна ломать саму покупку — только в лог."""
    try:
        hist = load_history()
        last_id = max((h.get("id", 0) for h in hist), default=0)
        hist.insert(0, {
            "id": max(int(time.time() * 1000), last_id + 1),
            "ts": time.time(), "auto": auto, "name": name, "cat": cat,
            "shop_id": shop_id, "product_id": product_id, "qty": qty,
            "price": price, "items": [str(i) for i in (items or [])],
        })
        _save_json(HISTORY_FILE, hist[:HISTORY_KEEP])
    except Exception:
        log.exception("Failed to save purchase history")


def _fmt_ts(ts) -> str:
    return time.strftime("%d.%m %H:%M", time.localtime(ts or 0))


def _autobuys_view() -> tuple[str, InlineKeyboardMarkup]:
    watches = load_autobuy()
    hist = load_history()[:HISTORY_SHOW]
    lines = [f"{CE_PIN} <b>Автопокупки</b>\n"]
    rows: list[list[InlineKeyboardButton]] = []

    if watches:
        lines.append(f"<b>Ждут товар ({len(watches)}):</b>")
        for i, w in enumerate(watches):
            ce = get_cat(w.get("cat", "gpt"))["ce"]
            s = get_shop(w.get("shop_id", 1))
            sn = f" · {escape(s.get('name', ''))}" if s else ""
            line = f"{i + 1}. {ce} {escape(w.get('name', '?'))}{sn} — ждём <b>{w.get('qty_left', 0)}</b> шт."
            if w.get("last_error"):
                line += f"\n    {CE_WARN} <i>{escape(str(w['last_error'])[:120])}</i>"
            elif w.get("notified_low_balance"):
                line += f"\n    {CE_WARN} <i>не хватает баланса</i>"
            lines.append(line)
            rows.append([InlineKeyboardButton(
                text=f"Убрать №{i + 1}", callback_data=f"ab_unwatch:{i}",
                style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_TRASH,
            )])
    else:
        lines.append(
            "<i>Активных автопокупок нет.</i>\n"
            f"{CE_TIP} Поставить: раздел → <b>Купить</b> → товар → «Автопокупка»."
        )

    lines.append(f"\n<b>Последние покупки:</b>")
    if not hist:
        lines.append("<i>Пока пусто.</i>")
    for k, h in enumerate(hist, 1):
        ce = get_cat(h.get("cat", "gpt"))["ce"]
        s = get_shop(h.get("shop_id", 0))
        sn = f" · {escape(s.get('name', ''))}" if s else ""
        how = "авто" if h.get("auto") else "вручную"
        price = f" · {escape(str(h['price']))}" if h.get("price") else ""
        lines.append(
            f"{k}. {_fmt_ts(h.get('ts'))} {ce} {escape(h.get('name', '?'))} × <b>{h.get('qty', 0)}</b>"
            f"{sn}{price} <i>({how})</i>"
        )
        btns = []
        if h.get("items"):
            btns.append(InlineKeyboardButton(
                text=f"№{k} аккаунты", callback_data=f"ab_items:{h.get('id')}",
                style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_EMAIL,
            ))
        if h.get("product_id") is not None and get_shop(h.get("shop_id", 0)):
            btns.append(InlineKeyboardButton(
                text=f"№{k} купить ещё", callback_data=f"ab_again:{h.get('id')}",
                style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_OUT,
            ))
        if btns:
            rows.append(btns)

    rows.append([InlineKeyboardButton(text="Обновить", callback_data="ab_home", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_HOME)])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_autobuys(message: Message) -> None:
    text, kb = _autobuys_view()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.message(F.text == "Автопокупки")
async def handle_autobuys_button(message: Message):
    if not is_admin(message):
        return
    await _send_autobuys(message)


@dp.message(Command("autobuys"))
async def cmd_autobuys(message: Message):
    if not is_admin(message):
        return
    await _send_autobuys(message)


async def _ab_refresh(cb: CallbackQuery) -> None:
    text, kb = _autobuys_view()
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:  # «message is not modified» при повторном «Обновить»
        if "not modified" not in str(e):
            raise


@dp.callback_query(F.data == "ab_home")
async def cb_ab_home(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    await cb.answer()
    await _ab_refresh(cb)


@dp.callback_query(F.data.startswith("ab_unwatch:"))
async def cb_ab_unwatch(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    idx = int(cb.data.split(":")[1])
    async with _lock:
        watches = load_autobuy()
        removed = watches.pop(idx) if 0 <= idx < len(watches) else None
        save_autobuy(watches)
    await cb.answer("Убрано." if removed else "Уже нет.")
    await _ab_refresh(cb)


def _hist_entry(hid: str) -> dict | None:
    return next((h for h in load_history() if str(h.get("id")) == hid), None)


@dp.callback_query(F.data.startswith("ab_items:"))
async def cb_ab_items(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    h = _hist_entry(cb.data.split(":")[1])
    if not h or not h.get("items"):
        await cb.answer("Эта покупка уже не хранится.", show_alert=True)
        return
    await cb.answer()
    ce = get_cat(h.get("cat", "gpt"))["ce"]
    await send_items_chunks(
        lambda t: cb.message.answer(t, parse_mode="HTML"),
        f"{ce} <b>{escape(h.get('name', '?'))}</b> — {_fmt_ts(h.get('ts'))}:", h["items"],
    )


@dp.callback_query(F.data.startswith("ab_again:"))
async def cb_ab_again(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    h = _hist_entry(cb.data.split(":")[1])
    if not h or not get_shop(h.get("shop_id", 0)):
        await cb.answer("Покупка или магазин уже не найдены.", show_alert=True)
        return
    sid, pid, cat = h.get("shop_id"), h.get("product_id"), h.get("cat", "gpt")
    if cat == "mall":
        cb2 = cb.model_copy(update={"data": f"mall_prod:{sid}:{pid}"})
        await cb_mall_prod(cb2)
    else:
        cb2 = cb.model_copy(update={"data": f"shop_prod:{cat}:{sid}:{pid}"})
        await cb_shop_prod(cb2)


# ─── Количество кнопками (вместо набора числа) ──────────────────────────────

QTY_PRESETS = (1, 2, 3, 5, 10)


def qty_rows() -> list[list[InlineKeyboardButton]]:
    return [[
        InlineKeyboardButton(text=str(n), callback_data=f"buyqty:{n}", style=ButtonStyle.SUCCESS)
        for n in QTY_PRESETS
    ]]


async def ask_buy_confirm(uid: int, qty: int, reply) -> None:
    """Количество выбрано: показать итог и «Купить сейчас / Автопокупка». reply — answer или edit_text."""
    info = pending_buy[uid]
    info["qty"] = qty
    p = info["p"]
    shop = get_shop(info.get("shop_id", 0)) or default_shop()
    ce = get_cat(info.get("cat", "gpt"))["ce"]
    total_usdt = p.get("price_usdt", 0) * qty
    await reply(
        f"{ce} <b>{escape(p['name'])}</b>\n"
        f"Магазин: {escape((shop or {}).get('name', '?'))}\n"
        f"Количество: <b>{qty}</b> шт.\n"
        f"Итого: <b>{fmt_usdt(total_usdt)}</b>\n"
        f"В наличии сейчас: {p.get('stock', 0)} шт.\n\n"
        f"Выбери действие:",
        reply_markup=_buy_confirm_keyboard(shop), parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("buyqty:"))
async def cb_buyqty(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    if cb.from_user.id not in pending_buy:
        await cb.answer("Заказ устарел — выбери товар заново.", show_alert=True)
        return
    await cb.answer()
    await ask_buy_confirm(cb.from_user.id, int(cb.data.split(":")[1]), cb.message.edit_text)

# continue bot_x16.py
_NEXT = Path(__file__).resolve().with_name('bot_x16.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
