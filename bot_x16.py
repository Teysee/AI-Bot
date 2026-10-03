@dp.message(F.text)
async def handle_text(message: Message):
    if not is_admin(message):
        return
    text = (message.text or "").strip()
    uid = message.from_user.id

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

    for key, c in all_cats().items():
        if c.get("custom") and text == c["title"]:
            await _send_cat_menu(message, key)
            return

    if uid in pending_buy and text.isdigit():
        qty = int(text)
        if not 1 <= qty <= 100:
            await message.answer(f"{CE_WARN} Количество: от 1 до 100.", parse_mode="HTML")
            return
        await ask_buy_confirm(uid, qty, message.answer)
        return

    await message.answer(
        f"{CE_TIP} Выбери раздел кнопками внизу.\n"
        f"Нет кнопок или они старые — отправь /start. Справка — /help",
        parse_mode="HTML", reply_markup=MK,
    )


# ─── Фоновая автопокупка (по всем шопам) ──────────────────────────────

# continue bot_x17.py
_NEXT = Path(__file__).resolve().with_name('bot_x17.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
