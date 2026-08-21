@dp.message(F.text.in_({"Gemini", "💎 Gemini"}))
async def handle_gemini_button(message: Message):
    if not is_admin(message):
        return
    await _send_cat_menu(message, "gemini")


@dp.message(F.text.in_({"Список", "📋 Список"}))
async def handle_list_button(message: Message):
    if not is_admin(message): return
    await _send_list(message)

@dp.message(F.text.in_({"Счёт", "📊 Счёт"}))
async def handle_count_button(message: Message):
    if not is_admin(message): return
    await _send_count(message)

@dp.message(F.text.in_({"Помощь", "❓ Помощь"}))
async def handle_help_button(message: Message):
    if not is_admin(message): return
    await message.answer(HELP_TEXT, parse_mode="HTML", reply_markup=MK)

# continue bot_x10.py
_NEXT = Path(__file__).resolve().with_name('bot_x10.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
