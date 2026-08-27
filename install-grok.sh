#!/usr/bin/env bash
# Установщик AI-Bot (Grok Bot) для Ubuntu/Debian.
# Ставит код ИЗ ЭТОГО репозитория (git clone/pull), а не свою копию bot.py.
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

REPO_URL="${REPO_URL:-https://github.com/Teysee/AI-Bot.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/grok-bot}"
SERVICE_NAME="grok-bot"
RUN_USER="$(id -un)"

echo -e "${CYAN}${BOLD}"
echo "=========================================="
echo "            AI-Bot installer"
echo "  Склад подписок: Grok / GPT / Gemini /"
echo "       CapCut / Claude / Perplexity"
echo "=========================================="
echo -e "${NC}"

if ! command -v apt-get >/dev/null 2>&1; then
    echo -e "${RED}[x] Поддерживается только Ubuntu/Debian${NC}"
    exit 1
fi

echo -e "${YELLOW}[>] Устанавливаю системные пакеты...${NC}"
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip git

echo -e "${YELLOW}[>] Папка установки: ${INSTALL_DIR}${NC}"
if [ -d "${INSTALL_DIR}/.git" ]; then
    echo -e "${YELLOW}[>] Репозиторий уже есть — обновляю до origin/${REPO_BRANCH}...${NC}"
    git -C "${INSTALL_DIR}" fetch --depth 1 origin "${REPO_BRANCH}"
    git -C "${INSTALL_DIR}" checkout -q "${REPO_BRANCH}" 2>/dev/null || git -C "${INSTALL_DIR}" checkout -q -b "${REPO_BRANCH}" "origin/${REPO_BRANCH}"
    git -C "${INSTALL_DIR}" reset --hard "origin/${REPO_BRANCH}"
elif [ -e "${INSTALL_DIR}" ] && [ -n "$(ls -A "${INSTALL_DIR}" 2>/dev/null || true)" ]; then
    echo -e "${RED}[x] Папка ${INSTALL_DIR} не пустая и не является git-репозиторием.${NC}"
    echo -e "    Удалите её или укажите другую:"
    echo -e "    ${CYAN}INSTALL_DIR=\$HOME/ai-bot bash install-grok.sh${NC}"
    exit 1
else
    git clone --depth 1 --branch "${REPO_BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"
echo -e "${GREEN}[v] Код на месте: $(git rev-parse --short HEAD)${NC}"

echo -e "${YELLOW}[>] Проверяю синтаксис Python-файлов...${NC}"
if ! python3 -m py_compile bot.py bot_x*.py bot_part3.py; then
    echo -e "${RED}[x] В коде синтаксическая ошибка (см. вывод выше). Установка остановлена.${NC}"
    exit 1
fi
echo -e "${GREEN}[v] Синтаксис в порядке${NC}"

echo -e "${YELLOW}[>] Виртуальное окружение и зависимости...${NC}"
if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

# Боту обязательно нужен aiogram >= 3.28: раньше не было ButtonStyle
# и полей style / icon_custom_emoji_id у кнопок.
if ! .venv/bin/python -c "from aiogram.enums import ButtonStyle" >/dev/null 2>&1; then
    echo -e "${YELLOW}[>] Обновляю aiogram до версии с поддержкой ButtonStyle...${NC}"
    .venv/bin/pip install -q --upgrade "aiogram>=3.28,<4"
fi
if ! .venv/bin/python -c "from aiogram.enums import ButtonStyle" >/dev/null 2>&1; then
    echo -e "${RED}[x] Установленная версия aiogram не поддерживает ButtonStyle.${NC}"
    echo -e "    Проверьте: ${CYAN}.venv/bin/pip show aiogram${NC}"
    exit 1
fi
echo -e "${GREEN}[v] Зависимости установлены: aiogram $(.venv/bin/python -c 'import aiogram; print(aiogram.__version__)')${NC}"

echo ""
echo -e "${CYAN}${BOLD}------------------------------------------${NC}"
echo -e "${BOLD}  Настройка бота${NC}"
echo -e "${CYAN}------------------------------------------${NC}"

if [ -f ".env" ]; then
    echo -e "${GREEN}[v] .env уже существует — пропускаю${NC}"
else
    read -rp "  Telegram токен бота (BOT_TOKEN): " NEW_BOT_TOKEN
    read -rp "  Ваш Telegram ID     (ADMIN_ID):  " NEW_ADMIN_ID
    read -rp "  API-ключ магазина   (SHOP_API_KEY, можно пусто): " NEW_SHOP_KEY
    printf 'BOT_TOKEN=%s\nADMIN_ID=%s\n' "${NEW_BOT_TOKEN}" "${NEW_ADMIN_ID}" > .env
    if [ -n "${NEW_SHOP_KEY}" ]; then
        printf 'SHOP_API_KEY=%s\n' "${NEW_SHOP_KEY}" >> .env
    fi
    chmod 600 .env
    echo -e "${GREEN}[v] .env создан${NC}"
fi

echo -e "${YELLOW}[>] Создаю systemd-сервис ${SERVICE_NAME}...${NC}"
sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" > /dev/null << EOF
[Unit]
Description=AI-Bot (Grok Bot) - склад подписок
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/python -u bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=${INSTALL_DIR}/.env

[Install]
WantedBy=multi-user.target
EOF

# Чтобы команда /update в боте могла перезапустить сервис без пароля.
sudo tee "/etc/sudoers.d/${SERVICE_NAME}" > /dev/null << EOF
${RUN_USER} ALL=(root) NOPASSWD: /bin/systemctl restart ${SERVICE_NAME}, /usr/bin/systemctl restart ${SERVICE_NAME}
EOF
sudo chmod 440 "/etc/sudoers.d/${SERVICE_NAME}"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1
sudo systemctl restart "${SERVICE_NAME}"

sleep 3
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo ""
    echo -e "${GREEN}${BOLD}==========================================${NC}"
    echo -e "${GREEN}${BOLD}   Готово! Бот запущен.${NC}"
    echo -e "${GREEN}${BOLD}==========================================${NC}"
else
    echo ""
    echo -e "${RED}[x] Сервис не поднялся. Последние логи:${NC}"
    sudo journalctl -u "${SERVICE_NAME}" -n 30 --no-pager || true
    exit 1
fi

echo ""
echo -e "Управление:"
echo -e "  ${CYAN}sudo systemctl status ${SERVICE_NAME}${NC}    — состояние"
echo -e "  ${CYAN}sudo systemctl restart ${SERVICE_NAME}${NC}   — перезапуск"
echo -e "  ${CYAN}sudo systemctl stop ${SERVICE_NAME}${NC}      — остановить"
echo -e "  ${CYAN}journalctl -u ${SERVICE_NAME} -f${NC}          — логи в реальном времени"
echo -e "Обновление кода: команда ${CYAN}/update${NC} в боте или повторный запуск этого скрипта."
