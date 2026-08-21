@dp.message(Command("delshop"))
async def cmd_delshop(message: Message, command):
    if not is_admin(message):
        return
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Использование: /delshop N (номер из /shops)", reply_markup=MK)
        return
    sid = int(arg)
    shops = load_shops()
    shop = next((s for s in shops if s.get("id") == sid), None)
    if not shop:
        await message.answer(f"Нет шопа №{sid}.", reply_markup=MK)
        return
    shops = [s for s in shops if s.get("id") != sid]
    save_shops(shops)
    await message.answer(
        f"{CE_TRASH} Шоп «{escape(shop.get('name', '?'))}» удалён.",
        parse_mode="HTML", reply_markup=MK,
    )


@dp.message(Command("shoplink"))
async def cmd_shoplink(message: Message, command):
    if not is_admin(message):
        return
    args = (command.args or "").strip().split(maxsplit=1)
    if len(args) != 2 or not args[0].isdigit() or not args[1].startswith("http"):
        await message.answer(
            "Использование: /shoplink N https://t.me/шоп_бот\n"
            "Эта ссылка будет на кнопке «Пополнить баланс».",
            reply_markup=MK,
        )
        return
    sid, link = int(args[0]), args[1]
    shops = load_shops()
    shop = next((s for s in shops if s.get("id") == sid), None)
    if not shop:
        await message.answer(f"Нет шопа №{sid}.", reply_markup=MK)
        return
    shop["link"] = link
    save_shops(shops)
    await message.answer(
        f"{CE_OK} Ссылка для «{escape(shop.get('name', '?'))}» сохранена — появится кнопка пополнения.",
        parse_mode="HTML", reply_markup=MK,
    )


def _make_cat_key(title: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "", title.lower())[:16]
    return key or f"cat{len(load_custom_cats()) + 1}"


async def _create_custom_cat(message: Message, title: str) -> None:
    key = _make_cat_key(title)
    cats = load_custom_cats()
    if any(c.get("key") == key for c in cats) or key in SHOP_CATS:
        await message.answer(f"{CE_WARN} Раздел «{escape(title)}» уже есть.", parse_mode="HTML", reply_markup=MK)
        return
    cats.append({"key": key, "title": title.capitalize(), "match": title.lower(), "emoji_id": None})
    save_custom_cats(cats)
    refresh_mk()
    pending_emoji[ADMIN_ID] = key
    await message.answer(
        f"{CE_OK} <b>Раздел «{escape(title.capitalize())}» создан!</b>\n"
        f"Товары со словом «{escape(title.lower())}» в названии попадут в него.\n\n"
        f"{CE_TIP} Теперь пришли <b>эмодзи</b> для кнопки раздела:\n"
        f"кастомный из премиум-пака станет иконкой, обычный добавится в название.\n"
        f"Или /skip — оставить стандартную иконку.",
        parse_mode="HTML", reply_markup=MK,
    )


@dp.message(Command("newcat"))
async def cmd_newcat(message: Message, command):
    if not is_admin(message):
        return
    title = (command.args or "").strip()
    if not title:
        await message.answer("Использование: /newcat Название (например: /newcat Netflix)", reply_markup=MK)
        return
    await _create_custom_cat(message, title)


@dp.message(Command("delcat"))
async def cmd_delcat(message: Message):
    if not is_admin(message):
        return
    cats = load_custom_cats()
    if not cats:
        await message.answer("Пользовательских разделов нет. Создай: /newcat Название", reply_markup=MK)
        return
    rows = [[InlineKeyboardButton(
        text=c.get("title", c.get("key", "?")), callback_data=f"delcat:{c.get('key')}",
        style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_TRASH,
    )] for c in cats]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_NO)])
    await message.answer(
        f"{CE_TRASH} <b>Какой раздел удалить?</b>\n<i>(склад раздела при этом не стирается)</i>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(F.data.startswith("delcat:"))
async def cb_delcat(cb: CallbackQuery):
    if not is_admin_cb(cb):
        return
    key = cb.data.split(":")[1]
    cats = [c for c in load_custom_cats() if c.get("key") != key]
    save_custom_cats(cats)
    refresh_mk()
    await cb.answer("Удалено.")
    await cb.message.edit_text(
        f"{CE_OK} Раздел удалён. Нажми /start, чтобы кнопки внизу обновились.",
        parse_mode="HTML",
    )


@dp.message(Command("setemoji"))
async def cmd_setemoji(message: Message):
    if not is_admin(message):
        return
    cats = load_custom_cats()
    if not cats:
        await message.answer("Пользовательских разделов нет. Создай: /newcat Название", reply_markup=MK)
        return
    rows = [[InlineKeyboardButton(
        text=c.get("title", "?"), callback_data=f"setemoji:{c.get('key')}",
        style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_TIP,
    )] for c in cats]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    await message.answer(
        f"{CE_TIP} <b>Какому разделу сменить эмодзи?</b>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )

# continue bot_x08.py
_NEXT = Path(__file__).resolve().with_name('bot_x08.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
