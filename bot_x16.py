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
            [
                InlineKeyboardButton(text="Claude", callback_data="store_as:claude", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_CLAUDE),
                InlineKeyboardButton(text="Perplexity", callback_data="store_as:pplx", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_PPLX),
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


# ─── Фоновая автопокупка (по всем шопам) ──────────────────────────────

# continue bot_x17.py
_NEXT = Path(__file__).resolve().with_name('bot_x17.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
