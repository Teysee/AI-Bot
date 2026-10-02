# AI-Bot (Grok Bot)

Telegram-бот — личный склад аккаунтов и подписок (Grok, ChatGPT, Gemini, CapCut, Claude,
Perplexity) с покупкой товаров и автопокупкой через API подключённых магазинов.
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
| `DATA_FILE` | нет | `accounts.json` | склад Grok-аккаунтов |
| `CDK_FILE` | нет | `cdk.json` | склад CDK-ключей |
| `GEMINI_FILE` / `CHATGPT_FILE` / `CAPCUT_FILE` | нет | `*.json` | склады по категориям |
| `SHOPS_FILE` | нет | `shops.json` | подключённые магазины |
| `CATS_FILE` | нет | `custom_cats.json` | пользовательские категории |
| `AUTOBUY_FILE` | нет | `autobuy.json` | правила автопокупки |
| `PRODUCTS_SEEN_FILE` | нет | `products_seen.json` | уже виденные товары |

Токен и ключ API можно задать и из чата: `/settoken` и `/setapikey` — они пишут в `.env`.

## Команды

- Склад: `/list`, `/count`, `/get N`, `/pop`, `/use N…`, `/clear` (+ `/yes`, `/no`), `/getchar`
- Быстрая выдача: `/3day`, `/7day`, `/14day`, `/30day`
- Магазины: `/shops`, `/addshop`, `/renameshop`, `/delshop`, `/shoplink`
  - Поддерживаемые API (тип определяется по префиксу ключа): legacy (`X-API-Key`),
    Reseller (`rsk_…`), Buyer (`tgb_…`), Dorin (`dk_…`), Roboticvn (`apk_…`, `/api/v2`).
  - Roboticvn: `/addshop apk_… roboticvn`. Каждый вариант товара — отдельная позиция;
    каталог (~60 карточек) кэшируется на 2 минуты из‑за лимита 120 запросов/мин.
- Категории: `/newcat`, `/delcat`, `/setemoji`, `/skip`
- Прочее: `/start`, `/help`, `/update`, `/settoken`, `/setapikey`

Добавление аккаунтов: просто отправь боту текст вида `Email : … / Password : …` —
дальше он предложит выбрать срок подписки кнопками.

## Структура кода

Бот разбит на части, которые подключаются цепочкой через `exec` в общем пространстве имён:

```
bot.py -> bot_x01.py -> bot_x02.py -> ... -> bot_x18.py -> bot_part3.py
```

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
