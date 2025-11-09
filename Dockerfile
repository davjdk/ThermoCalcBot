# =============================================================================
# Dockerfile for ThermoCalcBot - Telegram Bot for ThermoSystem
# =============================================================================
# Multi-stage build for optimized production image
# =============================================================================
FROM python:3.12-slim as base

# Установка меток для сервиса
LABEL maintainer="ThermoSystem Team"
LABEL description="ThermoCalcBot - Telegram Bot for Thermodynamic Calculations"
LABEL version="1.1.0"

# =============================================================================
# Stage 1: Dependencies and build
# =============================================================================
FROM base as builder

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Установка uv
RUN pip install uv==0.4.10

# Копирование файлов зависимостей
COPY pyproject.toml uv.lock ./

# Установка зависимостей с frozen lockfile
RUN uv sync --frozen --group telegram --no-dev

# =============================================================================
# Stage 2: Runtime image
# =============================================================================
FROM base as runtime

# Создание пользователя для безопасности
RUN groupadd -r thermobot && useradd -r -g thermobot thermobot

# Установка только необходимых runtime зависимостей
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Установка рабочей директории
WORKDIR /app

# Копирование виртуального окружения из builder stage
COPY --from=builder /root/.local /root/.local

# Копирование приложения
COPY src/ ./src/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY .env.example ./

# Создание необходимых директорий
RUN mkdir -p logs/telegram_sessions \
    && mkdir -p temp/telegram_files \
    && mkdir -p backup \
    && mkdir -p /app/ssl

# Настройка прав доступа
RUN chown -R thermobot:thermobot /app \
    && chmod +x scripts/*.py scripts/*.sh

# Переменные окружения
ENV PYTHONPATH=/app/src
ENV PATH="/root/.local/bin:$PATH"
ENV ENVIRONMENT=docker

# Порт для webhook
EXPOSE 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8443/health > /dev/null 2>&1 || exit 1

# Переключение на непривилегированного пользователя
USER thermobot

# Запуск бота
CMD ["python", "-m", "src.thermo_agents.telegram_bot.bot"]

# =============================================================================
# Development variant (for development and testing)
# =============================================================================
FROM runtime as development

# Переключение обратно на root для установки dev зависимостей
USER root

# Установка зависимостей для разработки
COPY --from=builder /root/.local /root/.local
RUN uv sync --frozen --group telegram --dev

# Установка дополнительных инструментов
RUN apt-get update && apt-get install -y \
    vim \
    htop \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Переключение на пользователя
USER thermobot

# Команда для разработки (с hot reload)
CMD ["uv", "run", "python", "-m", "src.thermo_agents.telegram_bot.bot", "--dev"]