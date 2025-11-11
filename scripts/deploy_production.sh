#!/bin/bash
# =============================================================================
# Production Deployment Script for ThermoCalcBot
# =============================================================================
# Автоматизированное развёртывание с health checks и rollback возможностью
# =============================================================================

set -euo pipefail

# Конфигурация
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/backup"
LOG_FILE="$PROJECT_DIR/logs/deployment.log"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для логирования
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# Проверка prerequirements
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Проверка Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    # Проверка Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi

    # Проверка environment
    if [ "$ENVIRONMENT" != "production" ]; then
        log_error "ENVIRONMENT must be 'production'. Current: $ENVIRONMENT"
        exit 1
    fi

    # Проверка обязательных переменных окружения
    local required_vars=("TELEGRAM_BOT_TOKEN" "OPENROUTER_API_KEY")
    for var in "${required_vars[@]}"; do
        if [ -z "${!var:-}" ]; then
            log_error "Required environment variable $var is not set"
            exit 1
        fi
    done

    log_success "Prerequisites check passed"
}

# Создание backup
create_backup() {
    log_info "Creating backup..."

    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="$BACKUP_DIR/before_deployment_$timestamp"

    mkdir -p "$backup_path"

    # Backup docker images
    log_info "Backing up Docker images..."
    docker save thermo-telegram-bot:latest > "$backup_path/bot_image.tar" 2>/dev/null || true

    # Backup configuration
    log_info "Backing up configuration..."
    cp -r "$PROJECT_DIR/nginx" "$backup_path/" 2>/dev/null || true
    cp "$PROJECT_DIR/docker-compose.yml" "$backup_path/" 2>/dev/null || true
    cp "$PROJECT_DIR/.env.prod" "$backup_path/" 2>/dev/null || true

    # Backup logs
    log_info "Backing up logs..."
    cp -r "$PROJECT_DIR/logs" "$backup_path/" 2>/dev/null || true

    log_success "Backup created: $backup_path"
}

# Pull изменений
pull_changes() {
    log_info "Pulling latest changes..."

    cd "$PROJECT_DIR"

    # Проверка на незакоммиченные изменения
    if [ -n "$(git status --porcelain)" ]; then
        log_warning "You have uncommitted changes. Commit or stash them first."
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    # Pull изменений
    git pull origin main

    log_success "Changes pulled successfully"
}

# Сборка образов
build_images() {
    log_info "Building Docker images..."

    cd "$PROJECT_DIR"

    # Сборка с no-cache для production
    docker-compose build --no-cache

    log_success "Docker images built successfully"
}

# Запуск сервисов
start_services() {
    log_info "Starting services..."

    cd "$PROJECT_DIR"

    # Остановка старых сервисов
    docker-compose down

    # Запуск новых сервисов
    docker-compose up -d

    log_success "Services started"
}

# Проверка здоровья
health_check() {
    log_info "Performing health check..."

    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        log_info "Health check attempt $attempt/$max_attempts..."

        # Проверка здоровья бота
        if curl -f http://localhost/health > /dev/null 2>&1; then
            log_success "Health check passed!"
            return 0
        fi

        log_warning "Health check failed, waiting 10 seconds..."
        sleep 10
        ((attempt++))
    done

    log_error "Health check failed after $max_attempts attempts"
    return 1
}

# Rollback при неудаче
rollback() {
    log_error "Deployment failed, initiating rollback..."

    cd "$PROJECT_DIR"

    # Остановка текущих сервисов
    docker-compose down || true

    # Поиск последнего backup
    local latest_backup=$(ls -1t "$BACKUP_DIR" | head -n 1)
    if [ -n "$latest_backup" ]; then
        log_info "Rolling back to: $latest_backup"

        local backup_path="$BACKUP_DIR/$latest_backup"

        # Восстановление Docker image
        if [ -f "$backup_path/bot_image.tar" ]; then
            docker load < "$backup_path/bot_image.tar"
        fi

        # Восстановление конфигурации
        if [ -f "$backup_path/docker-compose.yml" ]; then
            cp "$backup_path/docker-compose.yml" "$PROJECT_DIR/"
        fi

        # Запуск с backup конфигурацией
        docker-compose up -d

        log_warning "Rollback completed"
    else
        log_error "No backup found for rollback"
    fi
}

# Очистка старых backup
cleanup_backups() {
    log_info "Cleaning up old backups..."

    # Удаление backup старше 7 дней
    find "$BACKUP_DIR" -name "before_deployment_*" -mtime +7 -exec rm -rf {} + 2>/dev/null || true

    log_success "Old backups cleaned up"
}

# Успешное завершение
deployment_success() {
    log_success "🎉 Production deployment completed successfully!"

    # Вывод статуса сервисов
    log_info "Service status:"
    docker-compose ps

    # Вывод информации для проверки
    log_info "Deployment information:"
    echo "  - Bot URL: https://your-domain.com"
    echo "  - Health check: https://your-domain.com/health"
    echo "  - Logs: docker-compose logs -f thermo-telegram-bot"
}

# Основная функция
main() {
    log_info "🚀 Starting ThermoCalcBot production deployment..."

    # Создание директорий
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$(dirname "$LOG_FILE")"

    # Выполнение шагов развёртывания
    check_prerequisites
    create_backup
    pull_changes
    build_images
    start_services

    # Проверка здоровья с rollback при необходимости
    if health_check; then
        cleanup_backups
        deployment_success
    else
        rollback
        exit 1
    fi
}

# Обработка сигналов
trap 'log_error "Deployment interrupted"; exit 1' INT TERM

# Запуск
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi