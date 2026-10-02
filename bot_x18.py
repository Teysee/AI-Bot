async def shop_loop(bot: Bot) -> None:
    """Новинки в магазинах (раз в AUTOBUY_INTERVAL). Автопокупка — в autobuy_loop."""
    log.info("Shop loop started (interval %ss)", AUTOBUY_INTERVAL)
    while True:
        try:
            for shop in load_shops():
                data = await shop_api(shop, "GET", "/api/products")
                if data.get("success"):
                    await _check_new_products(bot, shop, data.get("products", []))
        except Exception:
            log.exception("Shop loop tick failed")
        await asyncio.sleep(AUTOBUY_INTERVAL)


# Магазины не присылают уведомлений о поступлении (у Roboticvn в API нет вебхуков),
# поэтому «мгновенно» = частый опрос. Темп ограничен лимитами магазинов.
AUTOBUY_FAST  = float(os.getenv("AUTOBUY_FAST", "1.5"))   # самый частый опрос одного шопа, сек
AUTOBUY_OTHER = float(os.getenv("AUTOBUY_OTHER", "5"))    # обычные шопы (весь список одним запросом)
AUTOBUY_RVN_PER_ITEM = 1.0  # Roboticvn: 1 запрос на товар раз в N·1 с → ≤60/мин из лимита 120


async def _autobuy_pass(bot: Bot, next_at: dict) -> None:
    """Один проход: магазины с активными автопокупками, у каждого — свой темп опроса."""
    watches = load_autobuy()
    for shop in load_shops() if watches else []:
        sid = shop.get("id")
        ids = sorted({w.get("product_id") for w in watches if w.get("shop_id", 1) == sid})
        now = time.time()
        if not ids or now < next_at.get(sid, 0):
            continue
        if _shop_api_type(shop) == "roboticvn":
            # остальные ~60 запросов/мин остаются каталогу и экранам бота — без блокировки 429
            next_at[sid] = now + max(AUTOBUY_FAST, AUTOBUY_RVN_PER_ITEM * len(ids))
            data = await shop_api(shop, "GET", "/api/products/fresh", {"ids": ids})
        else:
            next_at[sid] = now + max(AUTOBUY_FAST, AUTOBUY_OTHER)
            data = await shop_api(shop, "GET", "/api/products")
        if data.get("success"):
            await _autobuy_tick(bot, shop, data.get("products", []))


async def autobuy_loop(bot: Bot) -> None:
    """Автопокупка: часто проверяем только товары под автопокупкой, чтобы купить, как только
    они появятся. Единственное место, где автопокупки покупаются."""
    log.info("Autobuy loop started (every %ss)", AUTOBUY_FAST)
    next_at: dict = {}
    while True:
        try:
            await _autobuy_pass(bot, next_at)
        except Exception:
            log.exception("Autobuy loop tick failed")
        await asyncio.sleep(0.5)  # темп каждого шопа задаёт next_at, тут — только «пульс»


# ─── Адаптеры API магазинов (Reseller /v1, Buyer tgb_) — в bot_part3.py ──────────────────────────────

_PART3 = Path(__file__).resolve().with_name("bot_part3.py")
exec(compile(_PART3.read_text(encoding="utf-8"), str(_PART3), "exec"))


# ─── Запуск ──────────────────────────────

async def main():
    bot = Bot(token=BOT_TOKEN)
    log.info("Bot starting. Admin ID: %s", ADMIN_ID)

    await bot.set_my_commands([
        BotCommand(command="start",    description="🏠 Главное меню"),
        BotCommand(command="list",     description="📋 Все Grok-аккаунты"),
        BotCommand(command="count",    description="📊 Статистика склада"),
        BotCommand(command="pop",      description="📦 Выдать Grok (с выбором)"),
        BotCommand(command="3day",     description="⚡ Выдать Grok 3-дневный"),
        BotCommand(command="7day",     description="📅 Выдать Grok 7-дневный"),
        BotCommand(command="14day",    description="🌟 Выдать Grok 14-дневный"),
        BotCommand(command="30day",    description="👑 Выдать Grok 30-дневный"),
        BotCommand(command="use",      description="🗑 Удалить Grok по номеру"),
        BotCommand(command="clear",    description="⚠️ Очистить Grok-склад"),
        BotCommand(command="shops",    description="🏪 Магазины и балансы"),
        BotCommand(command="addshop",  description="➕ Подключить шоп"),
        BotCommand(command="renameshop", description="📝 Переименовать шоп"),
        BotCommand(command="newcat",   description="🆕 Новый раздел товаров"),
        BotCommand(command="setemoji", description="😎 Эмодзи раздела"),
        BotCommand(command="update",   description="⬆️ Обновить бота с GitHub"),
        BotCommand(command="settoken",  description="🔑 Сменить токен бота"),
        BotCommand(command="setapikey", description="🛒 Задать API-ключ шопа"),
        BotCommand(command="help",      description="❓ Помощь"),
    ])
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    asyncio.create_task(shop_loop(bot))
    asyncio.create_task(autobuy_loop(bot))
    log.info("Commands registered. Starting polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
