@dp.message(Command("shops"))
async def cmd_shops(message: Message):
    if not is_admin(message):
        return
    shops = load_shops()
    if not shops:
        await message.answer(
            f"{CE_EMPTY} Шопы не подключены.\n"
            f"Добавь: <code>/addshop Название | https://api-url | КЛЮЧ | ссылка_для_пополнения</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    lines = [f"{CE_BOX} <b>Подключённые шопы:</b>\n"]
    for s in shops:
        bal = await shop_api(s, "GET", "/api/balance")
        if bal.get("success"):
            bal_s = fmt_usdt(bal.get("balance_usdt", 0))
        else:
            bal_s = f"{CE_NO} нет связи"
        link = s.get("link") or "—"
        lines.append(
            f"<b>{s.get('id', '?')}. {escape(s.get('name', '?'))}</b>\n"
            f"  Баланс: {bal_s}\n"
            f"  Пополнение: {escape(link)}"
        )
    lines.append(
        f"\n{CE_TIP} <code>/addshop Название | URL | КЛЮЧ | ссылка</code>\n"
        f"/renameshop N имя — переименовать\n"
        f"/shoplink N ссылка — кнопка пополнения\n"
        f"/delshop N — убрать шоп"
    )
    await message.answer("\n\n".join(lines), parse_mode="HTML", reply_markup=MK)


def _guess_shop(raw: str) -> tuple[str, str, str, str] | None:
    presets = [
        (("canboso",), "Canboso", "https://canboso.com"),
        (("dorin", "mydorin"), "MyDorinAI", "https://mydorinai.online"),
        (("cgpt", "active.pro"), "CGPT Active", "https://cgpt-active.pro/telegram/api"),
        (("testflight", "flighty"), "TestFlighty", "https://api-tgbot.testflighty.com"),
        (("roboticvn", "robotic"), "Roboticvn", "https://api.roboticvn.com"),
    ]
    if "|" in raw:
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) >= 3 and parts[0] and parts[1].startswith("http") and len(parts[2]) >= 8:
            return parts[0], parts[1].rstrip("/"), parts[2], (parts[3] if len(parts) > 3 else "")
        return None
    bits = raw.split()
    if not bits:
        return None
    key = next((b for b in bits if b.startswith(("tgb_", "rsk_", "dk_", "apk_")) or len(b) >= 16), "")
    hint = " ".join(b for b in bits if b != key).lower()
    if not key:
        return None
    for keys, name, base in presets:
        # только подсказка и сам ключ: base пресета всегда содержит его же слово
        if any(k in hint or k in key.lower() for k in keys):
            return name, base, key, ""
    if key.startswith("apk_"):
        return hint.title() or "Roboticvn", "https://api.roboticvn.com", key, ""
    if key.startswith("dk_"):
        return hint.title() or "MyDorinAI", "https://mydorinai.online", key, ""
    if key.startswith("rsk_"):
        return hint.title() or "Reseller", "https://cgpt-active.pro/telegram/api", key, ""
    if key.startswith("tgb_"):  # как раньше: tgb_ без подсказки — Canboso
        return "Canboso", "https://canboso.com", key, ""
    return None


@dp.message(Command("addshop"))
async def cmd_addshop(message: Message, command):
    if not is_admin(message):
        return
    raw = (command.args or "").strip()
    parsed = _guess_shop(raw)
    if not parsed:
        await message.answer(
            f"{CE_KEY} Использование:\n"
            f"<code>/addshop Название | https://api-url | API_КЛЮЧ | ссылка</code>\n"
            f"или коротко: <code>/addshop tgb_… canboso</code>\n"
            f"<code>/addshop dk_… mydorinai</code>\n"
            f"<code>/addshop apk_… roboticvn</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    name, base, key, link = parsed
    shops = load_shops()
    new_id = max((s.get("id", 0) for s in shops), default=0) + 1
    shop = {"id": new_id, "name": name, "base": base, "key": key, "link": link}
    bal = await shop_api(shop, "GET", "/api/balance")
    shops.append(shop)
    save_shops(shops)
    if bal.get("success"):
        await message.answer(
            f"{CE_OK} <b>Шоп «{escape(name)}» подключён!</b>\n"
            f"Аккаунт: <b>{escape(str(bal.get('username', '?')))}</b>\n"
            f"Баланс: <b>{fmt_usdt(bal.get('balance_usdt', 0))}</b>",
            parse_mode="HTML", reply_markup=MK,
        )
    else:
        await message.answer(
            f"{CE_WARN} Шоп «{escape(name)}» сохранён, но проверка не прошла:\n"
            f"<code>{escape(str(bal.get('error')))}</code>\n"
            f"{CE_TIP} Проверь URL и ключ — можно удалить (/delshop {new_id}) и добавить заново.",
            parse_mode="HTML", reply_markup=MK,
        )


@dp.message(Command("renameshop"))
async def cmd_renameshop(message: Message, command):
    if not is_admin(message):
        return
    raw = (command.args or "").strip()
    parts = raw.split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].strip():
        await message.answer(
            f"{CE_PIN} Использование: <code>/renameshop N Новое имя</code>\n"
            f"Номер — из /shops. Например: <code>/renameshop 1 Tunvnmmo</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    sid, new_name = int(parts[0]), parts[1].strip()
    shops = load_shops()
    shop = next((s for s in shops if s.get("id") == sid), None)
    if not shop:
        await message.answer(f"Нет шопа №{sid}.", reply_markup=MK)
        return
    old = shop.get("name", "?")
    shop["name"] = new_name
    save_shops(shops)
    await message.answer(
        f"{CE_OK} Шоп №{sid}: <b>{escape(old)}</b> → <b>{escape(new_name)}</b>",
        parse_mode="HTML", reply_markup=MK,
    )

# continue bot_x07.py
_NEXT = Path(__file__).resolve().with_name('bot_x07.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
