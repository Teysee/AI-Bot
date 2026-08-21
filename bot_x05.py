@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    if not is_admin(message):
        return
    pending_clear.add(message.from_user.id)
    await message.answer(
        f"{CE_WARN} <b>Точно очистить ВСЁ Grok-хранилище?</b>\n/yes — подтвердить  |  /no — отмена",
        parse_mode="HTML", reply_markup=MK,
    )

@dp.message(Command("yes"))
async def cmd_yes(message: Message):
    if not is_admin(message):
        return
    if message.from_user.id in pending_clear:
        pending_clear.discard(message.from_user.id)
        async with _lock:
            save_accounts([])
        await message.answer(f"{CE_OK} Grok-хранилище очищено.", parse_mode="HTML", reply_markup=MK)

@dp.message(Command("no"))
async def cmd_no(message: Message):
    if not is_admin(message):
        return
    if message.from_user.id in pending_clear:
        pending_clear.discard(message.from_user.id)
        await message.answer(f"{CE_NO} Отменено.", parse_mode="HTML", reply_markup=MK)


@dp.message(Command("getchar"))
async def cmd_getchar(message: Message):
    if not is_admin(message):
        return
    target = message.reply_to_message or message
    entities = target.entities or []
    custom = [e for e in entities if e.type == "custom_emoji"]
    if not custom:
        await message.answer(
            "Не нашёл кастомных эмодзи.\n"
            "Отправь сообщение с кастомным эмодзи из пака, затем ответь на него /getchar",
            reply_markup=MK,
        )
        return
    txt = target.text or ""
    lines = ["<b>Символы кастомных эмодзи:</b>\n"]
    for ent in custom:
        char = txt[ent.offset : ent.offset + ent.length]
        codepoints = " ".join(f"U+{ord(c):04X}" for c in char)
        py_repr = repr(char)
        lines.append(
            f"ID: <code>{ent.custom_emoji_id}</code>\n"
            f"Символ: {char}\n"
            f"Python repr: <code>{escape(py_repr)}</code>\n"
            f"Codepoints: <code>{codepoints}</code>\n"
        )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=MK)


@dp.message(Command("settoken"))
async def cmd_settoken(message: Message, command):
    if not is_admin(message):
        return
    new_token = (command.args or "").strip()
    if not new_token or ":" not in new_token:
        await message.answer(
            f"{CE_KEY} Использование: <code>/settoken НОВ_ТОКЕН</code>\nПолучи у @BotFather.",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    env_path = Path(__file__).parent / ".env"
    try:
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
            new_lines, replaced = [], False
            for line in lines:
                if line.startswith("BOT_TOKEN="):
                    new_lines.append(f"BOT_TOKEN={new_token}")
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append(f"BOT_TOKEN={new_token}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            env_path.write_text(f"BOT_TOKEN={new_token}\nADMIN_ID={ADMIN_ID}\n", encoding="utf-8")
    except Exception as e:
        await message.answer(
            f"{CE_NO} Не удалось обновить .env:\n<code>{escape(str(e))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    await message.answer(f"{CE_OK} Токен обновлён. Перезапускаю...", parse_mode="HTML", reply_markup=MK)
    try:
        subprocess.Popen(["sudo", "systemctl", "restart", "grok-bot"])
    except Exception:
        os.execv(sys.executable, [sys.executable] + sys.argv)


@dp.message(Command("setapikey"))
async def cmd_setapikey(message: Message, command):
    if not is_admin(message):
        return
    new_key = (command.args or "").strip()
    if not new_key or len(new_key) < 16:
        await message.answer(
            f"{CE_KEY} Использование: <code>/setapikey КЛЮЧ</code>\n"
            f"Ключ шопа — команда /apikey в боте магазина.\n"
            f"{CE_TIP} Другие магазины: /addshop",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    env_path = Path(__file__).parent / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        new_lines, replaced = [], False
        for line in lines:
            if line.startswith("SHOP_API_KEY="):
                new_lines.append(f"SHOP_API_KEY={new_key}")
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(f"SHOP_API_KEY={new_key}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as e:
        await message.answer(
            f"{CE_NO} Не удалось обновить .env:\n<code>{escape(str(e))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    global SHOP_API_KEY
    SHOP_API_KEY = new_key
    shops = load_shops()
    if shops:
        shops[0]["key"] = new_key
        save_shops(shops)
        shop = shops[0]
    else:
        shop = {"id": 1, "name": "Основной шоп", "base": SHOP_API_BASE, "key": new_key, "link": ""}
        save_shops([shop])
    bal = await shop_api(shop, "GET", "/api/balance")
    if bal.get("success"):
        await message.answer(
            f"{CE_OK} API-ключ сохранён и работает!\n"
            f"Аккаунт: <b>{escape(str(bal.get('username', '?')))}</b>\n"
            f"Баланс: <b>{fmt_usdt(bal.get('balance_usdt', 0))}</b>",
            parse_mode="HTML", reply_markup=MK,
        )
    else:
        await message.answer(
            f"{CE_WARN} Ключ сохранён, но проверка не прошла:\n"
            f"<code>{escape(str(bal.get('error')))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )

# continue bot_x06.py
_NEXT = Path(__file__).resolve().with_name('bot_x06.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
