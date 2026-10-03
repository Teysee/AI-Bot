def grok_type_keyboard(days: int, has_cdk: bool = True) -> InlineKeyboardMarkup:
    acc_btn = InlineKeyboardButton(
        text="Аккаунт", callback_data=f"grok_acc:{days}", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_EMAIL
    )
    cdk_btn = InlineKeyboardButton(
        text="CDK", callback_data=f"grok_cdk:{days}", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_KEY
    ) if has_cdk else InlineKeyboardButton(
        text="CDK (скоро)", callback_data="grok_cdk_soon", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_KEY
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [acc_btn, cdk_btn],
        [InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
    ])


def cat_menu_keyboard(cat: str, watch_count: int = 0) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="Купить", callback_data=f"shop_buy:{cat}", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_OUT),
    ]]
    if watch_count:
        rows.append([InlineKeyboardButton(
            text=f"Автопокупки ({watch_count})", callback_data="ab_home",
            style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_PIN,
        )])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="grok_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_days_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="3 дня",   callback_data="add_days:3",  style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_D3),
            InlineKeyboardButton(text="7 дней",  callback_data="add_days:7",  style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_D7),
        ],
        [
            InlineKeyboardButton(text="14 дней", callback_data="add_days:14", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ID_D14),
            InlineKeyboardButton(text="30 дней", callback_data="add_days:30", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_D30),
        ],
        [InlineKeyboardButton(text="Отмена", callback_data="add_cancel", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)],
    ])


def _shops_keyboard(cat: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=s.get("name", f"Шоп {s.get('id', '?')}"),
            callback_data=f"shop_sel:{cat}:{s.get('id')}",
            style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ID_BOX,
        )]
        for s in load_shops()
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"shop_menu:{cat}", style=ButtonStyle.DANGER, icon_custom_emoji_id=ID_NO)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_admin(msg: Message) -> bool:
    return msg.from_user is not None and msg.from_user.id == ADMIN_ID

def is_admin_cb(cb: CallbackQuery) -> bool:
    return cb.from_user is not None and cb.from_user.id == ADMIN_ID


dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message):
        return
    refresh_mk()
    await message.answer(HELP_TEXT, parse_mode="HTML")
    await message.answer(
        f"{CE_KBD} <b>Панель управления</b>\n"
        f"<i>Не удаляй это сообщение — оно держит кнопки внизу.</i>",
        parse_mode="HTML",
        reply_markup=MK,
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not is_admin(message):
        return
    await message.answer(HELP_TEXT, parse_mode="HTML", reply_markup=MK)


@dp.message(Command("update"))
async def cmd_update(message: Message):
    if not is_admin(message):
        return
    await message.answer(f"{CE_UP} Проверяю обновления на GitHub...", parse_mode="HTML")
    repo_dir = Path(__file__).resolve().parent
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo_dir), "pull", "--ff-only",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        result = (out_b or b"").decode("utf-8", "replace").strip()
    except Exception as e:
        await message.answer(
            f"{CE_NO} Не удалось выполнить git pull:\n<code>{escape(str(e))}</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    if "Already up to date" in result or "Already up-to-date" in result:
        await message.answer(f"{CE_OK} Уже стоит последняя версия.", parse_mode="HTML", reply_markup=MK)
        return
    if proc.returncode != 0:
        await message.answer(
            f"{CE_NO} git pull завершился с ошибкой:\n<code>{escape(result[-1500:])}</code>",
            parse_mode="HTML", reply_markup=MK,
        )
        return
    await message.answer(
        f"{CE_OK} <b>Код обновлён!</b>\n<code>{escape(result[-1000:])}</code>\n\n"
        f"{CE_UP} Перезапускаюсь...",
        parse_mode="HTML", reply_markup=MK,
    )
    try:
        subprocess.Popen(["sudo", "systemctl", "restart", "grok-bot"])
    except Exception:
        os.execv(sys.executable, [sys.executable] + sys.argv)

# continue bot_x04.py
_NEXT = Path(__file__).resolve().with_name('bot_x04.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
