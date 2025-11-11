# Стадия 6: Конфигурация и развёртывание

**Статус:** Ready for implementation
**Версия:** 1.0
**Дата:** 9 ноября 2025

---

## 📋 Обзор

Этот документ определяет требования к конфигурации окружения, развёртыванию и управлению Telegram ботом ThermoSystem в различных средах (development, staging, production).

## ⚙️ 1. Конфигурация

### 1.1. Переменные окружения

**Обязательные переменные (.env):**
```bash
# ==================== Telegram Bot Configuration ====================
TELEGRAM_BOT_TOKEN=8556976404:AAH_Zxj-yWY9DRSWQVcn5FOq03_mgIim80o
TELEGRAM_BOT_USERNAME=ThermoCalcBot
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook/telegram
TELEGRAM_MODE=polling  # polling или webhook

# ==================== Performance Configuration ====================
MAX_CONCURRENT_USERS=20  # Консервативное значение для начального запуска
REQUEST_TIMEOUT_SECONDS=60
MESSAGE_MAX_LENGTH=4000
RATE_LIMIT_REQUESTS_PER_MINUTE=30

# ==================== File Handling Configuration ====================
ENABLE_FILE_DOWNLOADS=true
AUTO_FILE_THRESHOLD=3000  # Символов для автоматической отправки файла
FILE_CLEANUP_HOURS=24
MAX_FILE_SIZE_MB=20  # Лимит Telegram Bot API
TEMP_FILE_DIR=temp/telegram_files

# ==================== Admin Configuration ====================
TELEGRAM_ADMIN_USER_ID=123456789
LOG_BOT_ERRORS=true

# ==================== Feature Flags ====================
ENABLE_USER_AUTH=false
ENABLE_ANALYTICS=true
ENABLE_PROGRESS_INDICATORS=true

# ==================== Logging Configuration ====================
LOG_LEVEL=INFO
LOG_REQUESTS=true
LOG_RESPONSES=true

# ==================== Database Configuration ====================
DB_PATH=data/thermo_data.db
STATIC_DATA_DIR=data/static_compounds

# ==================== LLM Configuration ====================
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=openai/gpt-4o
```

### 1.2. Класс конфигурации

**Централизованная конфигурация:**
```python
# src/thermo_agents/telegram_bot/config.py
import os
from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path

@dataclass
class TelegramBotConfig:
    """Конфигурация Telegram бота"""

    # Telegram API
    bot_token: str
    bot_username: str
    webhook_url: Optional[str] = None
    mode: str = "polling"  # polling или webhook

    # Performance limits
    max_concurrent_users: int = 20
    request_timeout_seconds: int = 60
    message_max_length: int = 4000
    rate_limit_per_minute: int = 30

    # File handling
    enable_file_downloads: bool = True
    auto_file_threshold: int = 3000
    file_cleanup_hours: int = 24
    max_file_size_mb: int = 20
    temp_file_dir: str = "temp/telegram_files"

    # Admin settings
    admin_user_id: Optional[int] = None
    log_errors_to_admin: bool = True

    # Feature flags
    enable_user_auth: bool = False
    enable_analytics: bool = True
    enable_progress_indicators: bool = True

    # Logging
    log_level: str = "INFO"
    log_requests: bool = True
    log_responses: bool = True

    # Database
    db_path: str = "data/thermo_data.db"
    static_data_dir: str = "data/static_compounds"

    @classmethod
    def from_env(cls) -> 'TelegramBotConfig':
        """Создание конфигурации из переменных окружения"""
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "ThermoCalcBot"),
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL"),
            mode=os.getenv("TELEGRAM_MODE", "polling"),

            max_concurrent_users=int(os.getenv("MAX_CONCURRENT_USERS", "20")),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
            message_max_length=int(os.getenv("MESSAGE_MAX_LENGTH", "4000")),
            rate_limit_per_minute=int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "30")),

            enable_file_downloads=os.getenv("ENABLE_FILE_DOWNLOADS", "true").lower() == "true",
            auto_file_threshold=int(os.getenv("AUTO_FILE_THRESHOLD", "3000")),
            file_cleanup_hours=int(os.getenv("FILE_CLEANUP_HOURS", "24")),
            max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "20")),
            temp_file_dir=os.getenv("TEMP_FILE_DIR", "temp/telegram_files"),

            admin_user_id=int(os.getenv("TELEGRAM_ADMIN_USER_ID", "0")) if os.getenv("TELEGRAM_ADMIN_USER_ID") else None,
            log_errors_to_admin=os.getenv("LOG_BOT_ERRORS", "true").lower() == "true",

            enable_user_auth=os.getenv("ENABLE_USER_AUTH", "false").lower() == "true",
            enable_analytics=os.getenv("ENABLE_ANALYTICS", "true").lower() == "true",
            enable_progress_indicators=os.getenv("ENABLE_PROGRESS_INDICATORS", "true").lower() == "true",

            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_requests=os.getenv("LOG_REQUESTS", "true").lower() == "true",
            log_responses=os.getenv("LOG_RESPONSES", "true").lower() == "true",

            db_path=os.getenv("DB_PATH", "data/thermo_data.db"),
            static_data_dir=os.getenv("STATIC_DATA_DIR", "data/static_compounds")
        )

    def validate(self) -> List[str]:
        """Валидация конфигурации"""
        errors = []

        # Обязательные поля
        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")

        if not self.bot_username:
            errors.append("TELEGRAM_BOT_USERNAME is required")

        # Валидация режима работы
        if self.mode not in ["polling", "webhook"]:
            errors.append("TELEGRAM_MODE must be 'polling' or 'webhook'")

        # Валидация webhook
        if self.mode == "webhook" and not self.webhook_url:
            errors.append("TELEGRAM_WEBHOOK_URL is required for webhook mode")

        # Валидация лимитов
        if self.max_concurrent_users <= 0:
            errors.append("MAX_CONCURRENT_USERS must be positive")

        if self.request_timeout_seconds <= 0:
            errors.append("REQUEST_TIMEOUT_SECONDS must be positive")

        if self.message_max_length <= 0:
            errors.append("MESSAGE_MAX_LENGTH must be positive")

        # Валидация файлов
        if self.auto_file_threshold <= 0:
            errors.append("AUTO_FILE_THRESHOLD must be positive")

        if self.max_file_size_mb <= 0:
            errors.append("MAX_FILE_SIZE_MB must be positive")

        # Проверка путей
        if not Path(self.db_path).exists():
            errors.append(f"Database file not found: {self.db_path}")

        return errors

    def is_production(self) -> bool:
        """Проверка production окружения"""
        return (
            self.mode == "webhook" and
            self.log_level == "INFO" and
            self.max_concurrent_users >= 50
        )

    def is_development(self) -> bool:
        """Проверка development окружения"""
        return (
            self.mode == "polling" and
            self.log_level in ["DEBUG", "INFO"]
        )
```

### 1.3. Конфигурации для разных сред

**Development (.env.dev):**
```bash
# Development configuration
TELEGRAM_MODE=polling
LOG_LEVEL=DEBUG
MAX_CONCURRENT_USERS=10
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Debug features
ENABLE_USER_AUTH=false
ENABLE_ANALYTICS=true
ENABLE_PROGRESS_INDICATORS=true

# Relaxed limits for testing
REQUEST_TIMEOUT_SECONDS=120
AUTO_FILE_THRESHOLD=2000

# Database
DB_PATH=data/thermo_data_dev.db
```

**Staging (.env.staging):**
```bash
# Staging configuration
TELEGRAM_MODE=webhook
TELEGRAM_WEBHOOK_URL=https://staging.your-domain.com/webhook/telegram
LOG_LEVEL=INFO
MAX_CONCURRENT_USERS=50
RATE_LIMIT_REQUESTS_PER_MINUTE=30

# Production-like features
ENABLE_USER_AUTH=true
ENABLE_ANALYTICS=true
ENABLE_PROGRESS_INDICATORS=true

# Production limits
REQUEST_TIMEOUT_SECONDS=60
AUTO_FILE_THRESHOLD=3000
MAX_FILE_SIZE_MB=20
```

**Production (.env.prod):**
```bash
# Production configuration
TELEGRAM_MODE=webhook
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook/telegram
LOG_LEVEL=INFO
MAX_CONCURRENT_USERS=100
RATE_LIMIT_REQUESTS_PER_MINUTE=30

# Security features
ENABLE_USER_AUTH=true
ENABLE_ANALYTICS=true
ENABLE_PROGRESS_INDICATORS=false  # Reduce noise in production

# Strict limits
REQUEST_TIMEOUT_SECONDS=45
AUTO_FILE_THRESHOLD=3000
MAX_FILE_SIZE_MB=20
FILE_CLEANUP_HOURS=12  # More aggressive cleanup
```

## 🐳 2. Развёртывание

### 2.1. Локальное развёртывание (Development)

**Шаги для локального запуска:**
```bash
# 1. Установка зависимостей
uv sync --group telegram

# 2. Настройка окружения
cp .env.example .env.dev
# Заполнить .env.dev с вашим токеном

# 3. Создание необходимых директорий
mkdir -p logs/telegram_sessions
mkdir -p temp/telegram_files

# 4. Запуск бота в development режиме
uv run python -m src.thermo_agents.telegram_bot.bot --dev

# 5. Тестирование бота
uv run python -m pytest tests/telegram_bot/ -v
```

**Development скрипт:**
```python
# scripts/run_dev.py
import os
import asyncio
from pathlib import Path

def setup_dev_environment():
    """Настройка development окружения"""

    # Установка development окружения
    os.environ["ENVIRONMENT"] = "development"

    # Создание директорий
    Path("logs/telegram_sessions").mkdir(parents=True, exist_ok=True)
    Path("temp/telegram_files").mkdir(parents=True, exist_ok=True)

    # Загрузка .env.dev
    from dotenv import load_dotenv
    load_dotenv(".env.dev")

    print("✅ Development environment configured")

async def run_dev_bot():
    """Запуск бота в development режиме"""

    setup_dev_environment()

    from src.thermo_agents.telegram_bot.config import TelegramBotConfig
    from src.thermo_agents.telegram_bot.bot import ThermoSystemTelegramBot

    # Загрузка конфигурации
    config = TelegramBotConfig.from_env()

    # Валидация
    errors = config.validate()
    if errors:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        return

    print(f"🤖 Starting ThermoCalcBot in development mode...")
    print(f"   Mode: {config.mode}")
    print(f"   Username: {config.bot_username}")
    print(f"   Max users: {config.max_concurrent_users}")

    # Создание и запуск бота
    bot = ThermoSystemTelegramBot(config)

    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot error: {e}")
    finally:
        await bot.shutdown()

if __name__ == "__main__":
    asyncio.run(run_dev_bot())
```

### 2.2. Docker контейнеризация

**Dockerfile:**
```dockerfile
# Dockerfile
FROM python:3.12-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование файлов проекта
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Установка uv и зависимостей
RUN pip install uv && \
    uv sync --frozen --group telegram

# Создание необходимых директорий
RUN mkdir -p logs/telegram_sessions temp/telegram_files

# Переменные окружения
ENV PYTHONPATH=/app/src
ENV ENVIRONMENT=docker

# Порт для webhook
EXPOSE 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD uv run python -c "import requests; requests.get('http://localhost:8443/health', timeout=5)"

# Запуск бота
CMD ["uv", "run", "python", "-m", "src.thermo_agents.telegram_bot.bot"]
```

**Docker Compose:**
```yaml
# docker-compose.yml
version: '3.8'

services:
  thermo-telegram-bot:
    build: .
    container_name: thermo-telegram-bot
    restart: unless-stopped

    environment:
      # Environment
      - ENVIRONMENT=production

      # Telegram Configuration
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_BOT_USERNAME=${TELEGRAM_BOT_USERNAME}
      - TELEGRAM_MODE=webhook
      - TELEGRAM_WEBHOOK_URL=${TELEGRAM_WEBHOOK_URL}

      # Performance
      - MAX_CONCURRENT_USERS=100
      - REQUEST_TIMEOUT_SECONDS=45
      - RATE_LIMIT_REQUESTS_PER_MINUTE=30

      # Features
      - ENABLE_FILE_DOWNLOADS=true
      - ENABLE_ANALYTICS=true
      - ENABLE_USER_AUTH=true

      # Logging
      - LOG_LEVEL=INFO

      # Admin
      - TELEGRAM_ADMIN_USER_ID=${TELEGRAM_ADMIN_USER_ID}

      # Database
      - DB_PATH=/app/data/thermo_data.db

    volumes:
      # Данные
      - ./data:/app/data:ro
      - ./logs:/app/logs
      - ./temp:/app/temp

    ports:
      - "8443:8443"

    networks:
      - thermo-bot-network

    healthcheck:
      test: ["CMD", "uv", "run", "python", "-c", "import requests; requests.get('http://localhost:8443/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  nginx:
    image: nginx:alpine
    container_name: thermo-nginx
    restart: unless-stopped

    ports:
      - "80:80"
      - "443:443"

    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro

    depends_on:
      - thermo-telegram-bot

    networks:
      - thermo-bot-network

networks:
  thermo-bot-network:
    driver: bridge

volumes:
  logs:
  temp:
```

### 2.3. Nginx конфигурация

**Nginx reverse proxy:**
```nginx
# nginx/nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream telegram_bot {
        server thermo-telegram-bot:8443;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=telegram_limit:10m rate=30r/m;

    server {
        listen 80;
        server_name your-domain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name your-domain.com;

        # SSL конфигурация
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
        ssl_prefer_server_ciphers off;

        # Webhook endpoint
        location /webhook/telegram {
            limit_req zone=telegram_limit burst=10 nodelay;

            proxy_pass http://telegram_bot;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # Timeouts
            proxy_connect_timeout 30s;
            proxy_send_timeout 30s;
            proxy_read_timeout 30s;

            # Size limits
            client_max_body_size 20M;
        }

        # Health check endpoint
        location /health {
            proxy_pass http://telegram_bot;
            access_log off;
        }

        # Static files (if needed)
        location /static/ {
            alias /var/www/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

### 2.4. SSL/TLS настройка

**Let's Encrypt сертификаты:**
```bash
# Установка certbot
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com

# Автоматическое обновление
sudo crontab -e
# Добавить строку:
# 0 12 * * * /usr/bin/certbot renew --quiet
```

**Для разработки (самоподписанные сертификаты):**
```bash
# Создание директории для сертификатов
mkdir -p nginx/ssl

# Генерация самоподписанного сертификата
openssl req -x509 -newkey rsa:4096 -keyout nginx/ssl/key.pem \
    -out nginx/ssl/cert.pem -days 365 -nodes \
    -subj "/C=RU/ST=State/L=City/O=Organization/CN=localhost"
```

## 🚀 3. Production развертывание

### 3.1. Подготовка production окружения

**Проверочный лист:**
- [ ] SSL сертификаты настроены
- [ ] Firewall правила configured
- [ ] Monitoring настроен
- [ ] Backup procedures implemented
- [ ] Log rotation настроен
- [ ] Rate limiting протестирован
- [ ] Health checks работают
- [ ] Error alerts настроены

### 3.2. Развертывание на VPS/Dedicated сервер

**Скрипт развертывания:**
```bash
#!/bin/bash
# scripts/deploy_production.sh

set -e

echo "🚀 Deploying ThermoCalcBot to production..."

# 1. Проверка окружения
if [ "$ENVIRONMENT" != "production" ]; then
    echo "❌ ENVIRONMENT must be 'production'"
    exit 1
fi

# 2. Backup текущей версии
echo "📦 Creating backup..."
docker-compose down
docker save thermo-telegram-bot:latest > backup/bot_$(date +%Y%m%d_%H%M%S).tar

# 3. Pull изменений
git pull origin main

# 4. Сборка нового образа
echo "🏗️ Building new image..."
docker-compose build --no-cache

# 5. Запуск с health check
echo "🚀 Starting services..."
docker-compose up -d

# 6. Проверка здоровья
echo "🏥 Checking health..."
sleep 30

if curl -f http://localhost/health > /dev/null 2>&1; then
    echo "✅ Deployment successful!"
else
    echo "❌ Health check failed, rolling back..."
    docker-compose down
    # Восстановление из backup
    docker load < backup/bot_latest.tar
    docker-compose up -d
    exit 1
fi

echo "🎉 Production deployment completed!"
```

### 3.3. Monitoring и backup

**Automated backup script:**
```bash
#!/bin/bash
# scripts/backup.sh

BACKUP_DIR="/backup/thermo-bot"
DATE=$(date +%Y%m%d_%H%M%S)

# Создание директории
mkdir -p $BACKUP_DIR

# Backup базы данных
echo "📦 Backing up database..."
cp data/thermo_data.db $BACKUP_DIR/thermo_data_$DATE.db

# Backup логов
echo "📝 Backing up logs..."
tar -czf $BACKUP_DIR/logs_$DATE.tar.gz logs/

# Backup конфигурации
echo "⚙️ Backing up configuration..."
cp .env.prod $BACKUP_DIR/env_$DATE.prod

# Очистка старых бэкапов (оставляем последние 7 дней)
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
find $BACKUP_DIR -name "env_*" -mtime +7 -delete

echo "✅ Backup completed: $BACKUP_DIR"
```

### 3.4. CI/CD pipeline

**GitHub Actions workflow:**
```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python 3.12
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install uv
        uses: astral-sh/setup-uv@v1
      - name: Install dependencies
        run: uv sync --group telegram
      - name: Run tests
        run: uv run pytest tests/ -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v3
      - name: Deploy to production
        uses: appleboy/ssh-action@v0.1.7
        with:
          host: ${{ secrets.HOST }}
          username: ${{ secrets.USERNAME }}
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /opt/thermo-bot
            git pull origin main
            ./scripts/deploy_production.sh
```

---

## 📝 Резюме

**Ключевые требования к конфигурации и развёртыванию:**

1. **Конфигурация:**
   - Централизованная конфигурация через переменные окружения
   - Separate configs для dev/staging/production
   - Валидация конфигурации при запуске
   - Feature flags для управления функциональностью

2. **Развёртывание:**
   - Docker контейнеризация
   - Docker Compose для orchestration
   - Nginx reverse proxy с SSL
   - Automated deployment scripts

3. **Production:**
   - SSL/TLS сертификаты через Let's Encrypt
   - Health checks и monitoring
   - Automated backup procedures
   - CI/CD pipeline с GitHub Actions

4. **Безопасность:**
   - Rate limiting через Nginx
   - Firewall правила
   - Environment variable management
   - SSL termination на Nginx

**Следующий этап:** [07_testing_strategy.md](07_testing_strategy.md) - Стратегия тестирования.