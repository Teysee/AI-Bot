# AI-Bot (Grok Bot)

Telegram-бот для покупки подписок (Grok, ChatGPT, Gemini, CapCut, Claude, Perplexity)
и автопокупки через API подключённых магазинов. Главное меню: «Магазины» сверху, разделы
(в каждом — «Купить»), внизу «Автопокупки» (что ждём + последние покупки) и «Помощь».
Весь доступ только у одного администратора (`ADMIN_ID`).

## Установка (Ubuntu/Debian)

```bash
curl -fsSL https://raw.githubusercontent.com/Teysee/AI-Bot/main/install-grok.sh -o install-grok.sh
bash install-grok.sh
```

Скрипт склонирует репозиторий в `~/grok-bot`, создаст venv, поставит зависимости,
спросит `BOT_TOKEN` / `ADMIN_ID`, создаст systemd-сервис `grok-bot` и запустит бота.
Повторный запуск скрипта обновляет код и перезапускает сервис.

Требования: Python 3.10+, aiogram >= 3.28 (в более старых версиях нет `ButtonStyle`
и полей `style` / `icon_custom_emoji_id` у кнопок).

## Переменные окружения (`.env` рядом с `bot.py`)

| Переменная | Обязательна | По умолчанию | Назначение |
| --- | --- | --- | --- |
| `BOT_TOKEN` | да | — | токен бота от @BotFather |
| `ADMIN_ID` | да | — | Telegram ID единственного администратора |
| `SHOP_API_KEY` | нет | — | ключ API магазина по умолчанию |
| `SHOP_API_BASE` | нет | `https://tunvnmmo.duckdns.org` | адрес API магазина по умолчанию |
| `AUTOBUY_INTERVAL` | нет | `30` | период проверки новых товаров, сек |
| `AUTOBUY_FAST` | нет | `1.5` | самый частый опрос магазина под автопокупкой, сек. Roboticvn: раз в max(1.5, 1 с × число отслеживаемых товаров) — не больше 60 из 120 запросов/мин |
| `AUTOBUY_OTHER` | нет | `5` | опрос остальных магазинов под автопокупкой, сек (весь список одним запросом) |
| `HISTORY_FILE` | нет | `purchases.json` | последние 50 покупок (с выданными аккаунтами) |
| `DATA_FILE` / `CDK_FILE` / `GEMINI_FILE` / `CHATGPT_FILE` / `CAPCUT_FILE` | нет | `*.json` | старый склад: из меню убран, файлы не удаляются |
| `SHOPS_FILE` | нет | `shops.json` | подключённые магазины |
| `CATS_FILE` | нет | `custom_cats.json` | пользовательские категории |
| `AUTOBUY_FILE` | нет | `autobuy.json` | правила автопокупки |
| `PRODUCTS_SEEN_FILE` | нет | `products_seen.json` | уже виденные товары |

Токен и ключ API можно задать и из чата: `/settoken` и `/setapikey` — они пишут в `.env`.

## Команды

- Автопокупки: `/autobuys` (то же, что кнопка «Автопокупки»), `/autostatus`
- Магазины: `/shops`, `/addshop`, `/renameshop`, `/delshop`, `/shoplink`
  - Поддерживаемые API (тип определяется по префиксу ключа): legacy (`X-API-Key`),
    Reseller (`rsk_…`), Buyer (`tgb_…`), Dorin (`dk_…`), Roboticvn (`apk_…`, `/api/v2`).
  - Roboticvn: `/addshop apk_… roboticvn`. Каждый вариант товара — отдельная позиция;
    каталог (~60 карточек) кэшируется на 2 минуты из‑за лимита 120 запросов/мин.
- Категории: `/newcat`, `/delcat`, `/setemoji`, `/skip`
- Прочее: `/start`, `/help`, `/update`, `/settoken`, `/setapikey`

Склад убран: кнопок «Список», «Счёт», «Хранилище» больше нет, присланные в чат аккаунты
не сохраняются. Старые команды склада (`/list`, `/count`, `/pop`, …) скрыты из меню.

## Структура кода

Бот разбит на части, которые подключаются цепочкой через `exec` в общем пространстве имён:

```
bot.py -> bot_x01.py -> ... -> bot_x15.py -> bot_x19.py -> bot_x16.py -> bot_x17.py -> bot_x18.py -> bot_part3.py
```

`bot_x19.py` (автопокупки, история, кнопки количества) стоит между `bot_x15.py` и `bot_x16.py`:
его команды и кнопки должны регистрироваться раньше общего обработчика текста из `bot_x16.py`.

Каждый файл заканчивается блоком:

```python
# continue bot_xNN.py
_NEXT = Path(__file__).resolve().with_name('bot_xNN.py')
exec(compile(_NEXT.read_text(encoding='utf-8'), str(_NEXT), 'exec'))
```

Важно: любая синтаксическая ошибка в любой части ломает запуск бота целиком,
а объявление и его декоратор нельзя разрывать между файлами. Перед коммитом:

```bash
python3 -m py_compile bot.py bot_x*.py bot_part3.py
```

`bot_part2.py` — старая монолитная версия, в цепочке не участвует и не используется.

## Логи и обслуживание

```bash
journalctl -u grok-bot -f          # логи
sudo systemctl restart grok-bot    # перезапуск
```
