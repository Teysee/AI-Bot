@dp.message(Command("count"))
async def cmd_count(message: Message):
    if not is_admin(message):
        return
    await _send_count(message)


@dp.message(Command("list"))
async def cmd_list(message: Message):
    if not is_admin(message):
        return
    await _send_list(message)


async def _send_count(message: Message) -> None:
    accounts   = load_accounts()
    cdk_list   = load_cdk()
    gemini_lst = load_gemini()

    lines = [f"{CE_COUNT} <b>Склад подписок</b>\n"]
    lines.append(f"{CE_GROK} <b>Grok аккаунты:</b>")
    if accounts:
        bd: dict[int, int] = {}
        for a in accounts:
            d = a.get("days", 30)
            bd[d] = bd.get(d, 0) + 1
        for d in VALID_DAYS:
            if d in CDK_ONLY:
                continue
            lines.append(f"  {DAYS_EMOJI.get(d, CE_PIN)} {d}д: <b>{bd.get(d, 0)}</b> шт.")
        lines.append(f"  Итого: <b>{len(accounts)}</b> шт.")
    else:
        lines.append("  <i>пусто</i>")

    lines.append(f"\n{CE_KEY} <b>CDK коды:</b>")
    if cdk_list:
        cbd: dict[int, int] = {}
        for c in cdk_list:
            d = c.get("days", 3)
            cbd[d] = cbd.get(d, 0) + 1
        for d, cnt in sorted(cbd.items()):
            lines.append(f"  {DAYS_EMOJI.get(d, CE_PIN)} {d}д: <b>{cnt}</b> шт.")
        lines.append(f"  Итого: <b>{len(cdk_list)}</b> шт.")
    else:
        lines.append("  <i>пусто</i>")

    lines.append(f"\n{CE_GEMINI} <b>Gemini ссылки:</b> <b>{len(gemini_lst)}</b> шт.")
    if not gemini_lst:
        lines.append("  <i>пусто</i>")

    gpt_store = load_chatgpt()
    lines.append(f"\n{CE_GPT} <b>ChatGPT аккаунты:</b> <b>{len(gpt_store)}</b> шт.")
    if not gpt_store:
        lines.append("  <i>пусто</i>")

    cc_store = load_capcut()
    lines.append(f"\n{CE_CAPCUT} <b>CapCut аккаунты:</b> <b>{len(cc_store)}</b> шт.")
    if not cc_store:
        lines.append("  <i>пусто</i>")

    for key, ce, title in (("claude", CE_CLAUDE, "Claude"), ("pplx", CE_PPLX, "Perplexity")):
        load_fn, _ = store_funcs(key)
        n = len(load_fn())
        lines.append(f"\n{ce} <b>{title} аккаунты:</b> <b>{n}</b> шт.")
        if not n:
            lines.append("  <i>пусто</i>")

    for key, c in all_cats().items():
        if not c.get("custom"):
            continue
        load_fn, _ = store_funcs(key)
        lines.append(f"\n{c['ce']} <b>{escape(c['title'])} аккаунты:</b> <b>{len(load_fn())}</b> шт.")

    watches = load_autobuy()
    if watches:
        total = sum(w.get("qty_left", 0) for w in watches)
        lines.append(f"  {CE_PIN} Автопокупок активно: <b>{len(watches)}</b> (ждём {total} шт.)")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=MK)


async def _send_list(message: Message) -> None:
    accounts = load_accounts()
    if not accounts:
        await message.answer(f"{CE_EMPTY} Grok-склад пустой.", parse_mode="HTML", reply_markup=MK)
        return
    full = f"{CE_LIST} <b>Grok аккаунты — {len(accounts)} шт.</b>\n" + format_grok_list(accounts)
    for chunk_start in range(0, len(full), 3800):
        chunk = full[chunk_start:chunk_start + 3800]
        if chunk_start + 3800 >= len(full):
            await message.answer(chunk, parse_mode="HTML", reply_markup=MK)
        else:
            await message.answer(chunk, parse_mode="HTML")


@dp.message(Command("get"))
async def cmd_get(message: Message, command):
    if not is_admin(message):
        return
    args = (command.args or "").strip().split()
    if len(args) != 1 or not args[0].isdigit():
        await message.answer("Использование: /get N", reply_markup=MK)
        return
    n = int(args[0])
    accounts = load_accounts()
    if n < 1 or n > len(accounts):
        await message.answer(f"Нет аккаунта №{n}. Всего: {len(accounts)}.", reply_markup=MK)
        return
    a = accounts[n - 1]
    await message.answer(
        f"#{n} {days_label(a.get('days', 30))}\n{format_account_block(a)}",
        parse_mode="HTML", reply_markup=MK,
    )


@dp.message(Command("use"))
async def cmd_use(message: Message, command):
    if not is_admin(message):
        return
    args = (command.args or "").strip().split()
    if not args or not all(x.isdigit() for x in args):
        await message.answer("Использование: /use N  или  /use N1 N2 N3 ...", reply_markup=MK)
        return
    indexes = sorted({int(x) for x in args}, reverse=True)
    async with _lock:
        accounts = load_accounts()
        removed, skipped = [], []
        for n in indexes:
            if 1 <= n <= len(accounts):
                removed.append((n, accounts.pop(n - 1)))
            else:
                skipped.append(n)
        save_accounts(accounts)
    parts = []
    if removed:
        lines = [f"  №{n}: {escape(a['email'])} {days_label(a.get('days',30))}" for n, a in sorted(removed)]
        parts.append(f"{CE_TRASH} <b>Удалены:</b>\n" + "\n".join(lines))
    if skipped:
        parts.append(f"{CE_WARN} Не найдены: " + ", ".join(f"№{n}" for n in skipped))
    parts.append(f"<i>Осталось: {len(accounts)} шт.</i>")
    await message.answer("\n\n".join(parts), parse_mode="HTML", reply_markup=MK)

# continue bot_x05.py
_NEXT = Path(__file__).resolve().with_name('bot_x05.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
