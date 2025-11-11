# Развертывание ThermoCalcBot на VPS (Ubuntu)

## Требования к серверу

**Минимальная конфигурация:**
- ОС: Ubuntu 22.04 LTS или выше
- RAM: 512 MB (минимум)
- Диск: 20 GB
- CPU: 1 vCore
- Сеть: Стабильное подключение к интернету

## Подготовка VPS

### 1. Подключение к серверу

```bash
ssh root@your_vps_ip
```

### 2. Обновление системы

```bash
apt update && apt upgrade -y
```

### 3. Установка необходимых пакетов

```bash
# Установка Python 3.12+
apt install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.12 python3.12-venv python3.12-dev

# Установка дополнительных инструментов
apt install -y git curl build-essential sqlite3

# Проверка версии Python
python3.12 --version
```

### 4. Создание пользователя для бота

```bash
# Создание пользователя (рекомендуется не использовать root)
adduser thermobot

# Добавление пользователя в группу sudo (опционально)
usermod -aG sudo thermobot

# Переключение на пользователя
su - thermobot
```

## Установка проекта

### 1. Клонирование репозитория

```bash
cd ~
git clone https://github.com/davjdk/agents_for_david.git
cd agents_for_david
```

### 2. Установка UV (пакетный менеджер)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

# Добавление UV в PATH
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Проверка установки
uv --version
```

### 3. Установка зависимостей проекта

```bash
# Создание виртуального окружения и установка зависимостей
uv sync

# Проверка установки
uv run python --version
```

## Конфигурация бота

### 1. Создание .env файла

```bash
# Копирование шаблона
cp .env.example .env

# Редактирование конфигурации
nano .env
```

### 2. Настройка обязательных переменных

Отредактируйте `.env` файл и заполните следующие обязательные параметры:

```bash
# Telegram Bot Configuration (ОБЯЗАТЕЛЬНО!)
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_BOT_USERNAME=YourBotUsername

# LLM Configuration (ОБЯЗАТЕЛЬНО!)
OPENROUTER_API_KEY=your_openrouter_api_key

# Режим работы (для VPS рекомендуется polling)
TELEGRAM_MODE=polling

# База данных
DB_PATH=data/thermo_data.db

# Логирование
LOG_LEVEL=INFO
```

**Как получить токены:**

1. **TELEGRAM_BOT_TOKEN:**
   - Откройте Telegram и найдите @BotFather
   - Отправьте команду `/newbot`
   - Следуйте инструкциям и получите токен

2. **OPENROUTER_API_KEY:**
   - Зарегистрируйтесь на https://openrouter.ai/
   - Перейдите в раздел "API Keys"
   - Создайте новый ключ и скопируйте его

### 3. Проверка базы данных

```bash
# Убедитесь, что база данных существует
ls -lh data/thermo_data.db

# Проверка целостности базы данных
sqlite3 data/thermo_data.db "PRAGMA integrity_check;"
```

## Запуск бота

### Тестовый запуск

```bash
# Запуск бота в интерактивном режиме
uv run python telegram_bot.py

# Проверьте вывод:
# ✅ Конфигурация загружена
# ✅ База данных подключена
# 🤖 Бот запущен в режиме polling
# Нажмите Ctrl+C для остановки
```

Если бот успешно запустился, протестируйте его в Telegram:
- Найдите вашего бота по username
- Отправьте команду `/start`
- Попробуйте простой запрос: `H2O при 300-400K`

**После успешного теста нажмите Ctrl+C для остановки.**

## Автоматический запуск через systemd

### 1. Создание systemd service файла

```bash
sudo nano /etc/systemd/system/thermobot.service
```

### 2. Содержимое service файла

```ini
[Unit]
Description=ThermoCalcBot Telegram Bot
After=network.target

[Service]
Type=simple
User=thermobot
WorkingDirectory=/home/thermobot/agents_for_david
Environment="PATH=/home/thermobot/.cargo/bin:/usr/bin"

# Команда запуска через UV
ExecStart=/home/thermobot/.cargo/bin/uv run python telegram_bot.py

# Автоматический перезапуск при сбое
Restart=always
RestartSec=10

# Ограничение памяти (опционально, для 512MB VPS)
MemoryLimit=400M

# Логирование
StandardOutput=journal
StandardError=journal
SyslogIdentifier=thermobot

[Install]
WantedBy=multi-user.target
```

**Важно:** Замените `thermobot` на имя вашего пользователя, если оно отличается.

### 3. Активация и запуск сервиса

```bash
# Перезагрузка конфигурации systemd
sudo systemctl daemon-reload

# Включение автозапуска при загрузке системы
sudo systemctl enable thermobot

# Запуск сервиса
sudo systemctl start thermobot

# Проверка статуса
sudo systemctl status thermobot
```

### 4. Управление сервисом

```bash
# Остановка бота
sudo systemctl stop thermobot

# Перезапуск бота
sudo systemctl restart thermobot

# Просмотр логов
sudo journalctl -u thermobot -f

# Просмотр последних 100 строк логов
sudo journalctl -u thermobot -n 100

# Просмотр логов с определенного времени
sudo journalctl -u thermobot --since "1 hour ago"
```

## Мониторинг и обслуживание

### Проверка работоспособности

```bash
# Статус сервиса
sudo systemctl status thermobot

# Использование памяти
ps aux | grep telegram_bot

# Проверка логов на ошибки
sudo journalctl -u thermobot -p err -n 50

# Проверка доступности бота в Telegram
# Отправьте команду /start вашему боту
```

### Мониторинг ресурсов

```bash
# Установка htop для мониторинга
sudo apt install -y htop

# Запуск htop
htop

# Мониторинг использования диска
df -h

# Проверка свободной памяти
free -m
```

### Ротация логов

Создайте конфигурацию logrotate для управления размером логов:

```bash
sudo nano /etc/logrotate.d/thermobot
```

Содержимое:

```
/var/log/thermobot/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 thermobot thermobot
}
```

### Очистка временных файлов

```bash
# Создайте cron задачу для очистки старых временных файлов
crontab -e

# Добавьте строку (очистка файлов старше 24 часов каждый день в 3:00)
0 3 * * * find /home/thermobot/agents_for_david/temp/telegram_files -type f -mtime +1 -delete
```

## Обновление бота

### 1. Остановка сервиса

```bash
sudo systemctl stop thermobot
```

### 2. Обновление кода

```bash
cd ~/agents_for_david

# Сохранение текущих изменений (если есть)
git stash

# Получение последних изменений
git pull origin main

# Восстановление локальных изменений (если нужно)
git stash pop
```

### 3. Обновление зависимостей

```bash
# Обновление зависимостей проекта
uv sync
```

### 4. Запуск обновленного бота

```bash
# Запуск сервиса
sudo systemctl start thermobot

# Проверка статуса
sudo systemctl status thermobot
```

## Резервное копирование

### Создание бэкапа

```bash
# Создайте директорию для бэкапов
mkdir -p ~/backups

# Скрипт бэкапа
cat > ~/backup_thermobot.sh << 'EOF'
#!/bin/bash

BACKUP_DIR=~/backups
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="thermobot_backup_$DATE.tar.gz"

# Остановка бота
sudo systemctl stop thermobot

# Создание архива
tar -czf "$BACKUP_DIR/$BACKUP_NAME" \
    ~/agents_for_david/data/ \
    ~/agents_for_david/logs/ \
    ~/agents_for_david/.env

# Запуск бота
sudo systemctl start thermobot

# Удаление старых бэкапов (старше 30 дней)
find "$BACKUP_DIR" -name "thermobot_backup_*.tar.gz" -mtime +30 -delete

echo "Бэкап создан: $BACKUP_NAME"
EOF

# Добавление прав на выполнение
chmod +x ~/backup_thermobot.sh

# Запуск бэкапа
~/backup_thermobot.sh
```

### Автоматическое резервное копирование

```bash
# Добавьте в crontab (каждый день в 2:00)
crontab -e

# Добавьте строку:
0 2 * * * /home/thermobot/backup_thermobot.sh >> /home/thermobot/backup.log 2>&1
```

### Восстановление из бэкапа

```bash
# Остановка бота
sudo systemctl stop thermobot

# Восстановление из архива
tar -xzf ~/backups/thermobot_backup_YYYYMMDD_HHMMSS.tar.gz -C ~/

# Запуск бота
sudo systemctl start thermobot
```

## Решение проблем

### Бот не запускается

```bash
# Проверьте логи systemd
sudo journalctl -u thermobot -n 100

# Проверьте конфигурацию
uv run python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('Token:', os.getenv('TELEGRAM_BOT_TOKEN')[:10] + '...')"

# Проверьте доступ к базе данных
sqlite3 ~/agents_for_david/data/thermo_data.db "SELECT COUNT(*) FROM sqlite_master;"
```

### Бот не отвечает на сообщения

```bash
# Проверьте подключение к Telegram API
curl -s https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe

# Проверьте подключение к OpenRouter
curl -s -H "Authorization: Bearer ${OPENROUTER_API_KEY}" https://openrouter.ai/api/v1/models
```

### Ошибки памяти

```bash
# Проверьте использование памяти
free -m

# Увеличьте ограничение swap (если нужно)
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### База данных заблокирована

```bash
# Проверьте процессы, использующие базу данных
lsof ~/agents_for_david/data/thermo_data.db

# Перезапустите бота
sudo systemctl restart thermobot
```

## Безопасность

### Базовая защита

```bash
# Настройка firewall (UFW)
sudo apt install -y ufw

# Разрешить SSH
sudo ufw allow ssh

# Включить firewall
sudo ufw enable

# Проверка статуса
sudo ufw status
```

### Защита .env файла

```bash
# Установите правильные права доступа
chmod 600 ~/agents_for_david/.env

# Проверьте права
ls -l ~/agents_for_david/.env
```

### Регулярные обновления системы

```bash
# Создайте скрипт автоматического обновления
cat > ~/update_system.sh << 'EOF'
#!/bin/bash
apt update
apt upgrade -y
apt autoremove -y
EOF

chmod +x ~/update_system.sh

# Добавьте в crontab (каждое воскресенье в 4:00)
sudo crontab -e
# Добавьте:
0 4 * * 0 /home/thermobot/update_system.sh >> /var/log/system_updates.log 2>&1
```

## Оптимизация для VPS с 512MB RAM

### 1. Настройка параметров бота

В файле `.env` установите следующие параметры:

```bash
# Уменьшение одновременных пользователей
MAX_CONCURRENT_USERS=5

# Уменьшение таймаута
REQUEST_TIMEOUT_SECONDS=30

# Отключение файловых операций (экономия памяти)
ENABLE_FILE_DOWNLOADS=false

# Агрессивная очистка временных файлов
FILE_CLEANUP_HOURS=1
```

### 2. Настройка Python для экономии памяти

Отредактируйте service файл:

```bash
sudo nano /etc/systemd/system/thermobot.service
```

Добавьте переменные окружения для оптимизации:

```ini
[Service]
# ... существующие настройки ...

# Оптимизация Python для низкого потребления памяти
Environment="PYTHONOPTIMIZE=1"
Environment="PYTHONDONTWRITEBYTECODE=1"
Environment="MALLOC_TRIM_THRESHOLD_=100000"

# Ограничение памяти
MemoryLimit=400M
MemoryMax=450M
```

### 3. Мониторинг использования памяти

Создайте скрипт мониторинга:

```bash
cat > ~/monitor_memory.sh << 'EOF'
#!/bin/bash

MEMORY_USAGE=$(ps aux | grep telegram_bot.py | grep -v grep | awk '{print $4}')
THRESHOLD=80

if (( $(echo "$MEMORY_USAGE > $THRESHOLD" | bc -l) )); then
    echo "$(date): Высокое использование памяти: ${MEMORY_USAGE}%" >> ~/memory_alerts.log
    sudo systemctl restart thermobot
fi
EOF

chmod +x ~/monitor_memory.sh

# Запуск проверки каждые 15 минут
crontab -e
# Добавьте:
*/15 * * * * /home/thermobot/monitor_memory.sh
```

## Поддержка и помощь

### Полезные команды

```bash
# Быстрая диагностика
echo "=== Статус бота ===" && sudo systemctl status thermobot --no-pager
echo "=== Использование памяти ===" && free -m
echo "=== Последние логи ===" && sudo journalctl -u thermobot -n 20 --no-pager
echo "=== Использование диска ===" && df -h
```

### Контакты и документация

- **Основная документация:** `docs/ARCHITECTURE.md`
- **Архитектура бота:** `docs/TELEGRAM_BOT_ARCHITECTURE.md`
- **Руководство пользователя:** `docs/user_guide.md`
- **GitHub репозиторий:** https://github.com/davjdk/agents_for_david

---

**Дата создания:** 11 ноября 2025  
**Версия:** 1.0  
**Статус:** Production Ready для VPS с минимальной конфигурацией
