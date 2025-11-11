#!/bin/bash
# =============================================================================
# Backup Script for ThermoCalcBot
# =============================================================================
# Создание резервных копий данных, конфигурации и логов
# =============================================================================

set -euo pipefail

# Конфигурация
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-/backup/thermo-bot}"
DATE=$(date +%Y%m%d_%H%M%S)

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для логирования
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Создание директории для backup
create_backup_directory() {
    local backup_path="$BACKUP_DIR/backup_$DATE"
    mkdir -p "$backup_path"
    echo "$backup_path"
}

# Backup базы данных
backup_database() {
    local backup_path="$1"
    log_info "Backing up database..."

    local db_file="$PROJECT_DIR/data/thermo_data.db"
    if [ -f "$db_file" ]; then
        cp "$db_file" "$backup_path/thermo_data_$DATE.db"
        log_success "Database backed up"
    else
        log_warning "Database file not found: $db_file"
    fi
}

# Backup логов
backup_logs() {
    local backup_path="$1"
    log_info "Backing up logs..."

    if [ -d "$PROJECT_DIR/logs" ]; then
        tar -czf "$backup_path/logs_$DATE.tar.gz" -C "$PROJECT_DIR" logs/
        log_success "Logs backed up"
    else
        log_warning "Logs directory not found"
    fi
}

# Backup конфигурации
backup_configuration() {
    local backup_path="$1"
    log_info "Backing up configuration..."

    # Backup .env файлов
    for env_file in .env .env.prod .env.staging .env.dev; do
        if [ -f "$PROJECT_DIR/$env_file" ]; then
            cp "$PROJECT_DIR/$env_file" "$backup_path/env_$env_file_$DATE"
        fi
    done

    # Backup Docker конфигурации
    if [ -f "$PROJECT_DIR/docker-compose.yml" ]; then
        cp "$PROJECT_DIR/docker-compose.yml" "$backup_path/docker-compose_$DATE.yml"
    fi

    # Backup Nginx конфигурации
    if [ -d "$PROJECT_DIR/nginx" ]; then
        tar -czf "$backup_path/nginx_$DATE.tar.gz" -C "$PROJECT_DIR" nginx/
    fi

    # Backup SSL сертификатов
    if [ -d "$PROJECT_DIR/nginx/ssl" ]; then
        tar -czf "$backup_path/ssl_$DATE.tar.gz" -C "$PROJECT_DIR/nginx" ssl/
        log_warning "SSL certificates backed up - ensure secure storage!"
    fi

    log_success "Configuration backed up"
}

# Backup Docker volumes
backup_docker_volumes() {
    local backup_path="$1"
    log_info "Backing up Docker volumes..."

    cd "$PROJECT_DIR"

    # Backup Redis данных
    if docker-compose ps redis | grep -q "Up"; then
        docker exec thermo-redis redis-cli BGSAVE
        sleep 5
        docker cp thermo-redis:/data/dump.rdb "$backup_path/redis_dump_$DATE.rdb" 2>/dev/null || true
        log_success "Redis data backed up"
    fi

    # Backup временных файлов
    if [ -d "$PROJECT_DIR/temp" ]; then
        tar -czf "$backup_path/temp_files_$DATE.tar.gz" -C "$PROJECT_DIR" temp/ --exclude='telegram_files'
        log_success "Temp files backed up"
    fi
}

# Backup runtime данных
backup_runtime_data() {
    local backup_path="$1"
    log_info "Backing up runtime data..."

    # Backup сессий пользователей
    if [ -d "$PROJECT_DIR/logs/telegram_sessions" ]; then
        tar -czf "$backup_path/sessions_$DATE.tar.gz" -C "$PROJECT_DIR/logs" telegram_sessions/
        log_success "User sessions backed up"
    fi

    # Backup метрик если есть
    if [ -d "$PROJECT_DIR/logs/metrics" ]; then
        tar -czf "$backup_path/metrics_$DATE.tar.gz" -C "$PROJECT_DIR/logs" metrics/
        log_success "Metrics backed up"
    fi
}

# Создание информации о backup
create_backup_info() {
    local backup_path="$1"
    local info_file="$backup_path/backup_info.txt"

    cat > "$info_file" << EOF
ThermoCalcBot Backup Information
================================

Backup Date: $(date)
Backup Type: Manual/Automated
Hostname: $(hostname)
User: $(whoami)
Git Commit: $(git rev-parse HEAD 2>/dev/null || echo "N/A")
Git Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "N/A")

Docker Information:
- Docker Version: $(docker --version 2>/dev/null || echo "N/A")
- Docker Compose Version: $(docker-compose --version 2>/dev/null || echo "N/A")
- Running Containers: $(docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null || echo "N/A")

System Information:
- OS: $(uname -a)
- Disk Usage: $(df -h "$backup_path" | tail -n 1)
- Memory Usage: $(free -h 2>/dev/null || echo "N/A")

Files Included:
- Database: thermo_data.db
- Configuration: .env files, docker-compose.yml, nginx config
- Logs: All application logs
- Runtime Data: User sessions, metrics
- Docker Volumes: Redis data, temp files

Restore Instructions:
1. Stop services: docker-compose down
2. Restore database: cp thermo_data_*.db data/thermo_data.db
3. Restore configuration: cp env_* .env
4. Restore Docker volumes: docker cp redis_dump_*.rdb container:/data/dump.rdb
5. Start services: docker-compose up -d
EOF

    log_success "Backup information created"
}

# Компрессия backup
compress_backup() {
    local backup_path="$1"
    local compressed_file="$BACKUP_DIR/thermobot_backup_$DATE.tar.gz"

    log_info "Compressing backup..."
    tar -czf "$compressed_file" -C "$(dirname "$backup_path")" "$(basename "$backup_path")"

    # Удаление несжатой директории
    rm -rf "$backup_path"

    log_success "Backup compressed: $compressed_file"
}

# Проверка целостности backup
verify_backup() {
    local backup_file="$1"
    log_info "Verifying backup integrity..."

    if tar -tzf "$backup_file" > /dev/null 2>&1; then
        log_success "Backup integrity verified"
        return 0
    else
        log_error "Backup integrity check failed"
        return 1
    fi
}

# Очистка старых backup
cleanup_old_backups() {
    local retention_days="${BACKUP_RETENTION_DAYS:-7}"
    log_info "Cleaning up backups older than $retention_days days..."

    find "$BACKUP_DIR" -name "thermobot_backup_*.tar.gz" -mtime +$retention_days -delete
    find "$BACKUP_DIR" -name "backup_*" -mtime +1 -exec rm -rf {} + 2>/dev/null || true

    log_success "Old backups cleaned up"
}

# Отправка уведомления (опционально)
send_notification() {
    local backup_file="$1"
    local backup_size=$(du -h "$backup_file" | cut -f1)

    if [ -n "${BACKUP_WEBHOOK_URL:-}" ]; then
        log_info "Sending backup notification..."

        curl -X POST "$BACKUP_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{\"text\":\"✅ ThermoCalcBot backup completed successfully\n\nFile: $backup_file\nSize: $backup_size\nDate: $(date)\"}" \
            2>/dev/null || true

        log_success "Notification sent"
    fi
}

# Основная функция
main() {
    local backup_type="${1:-full}"

    log_info "🔄 Starting ThermoCalcBot backup..."
    log_info "Backup type: $backup_type"

    # Создание директории для backup
    mkdir -p "$BACKUP_DIR"
    local backup_path=$(create_backup_directory)

    # Выполнение backup в зависимости от типа
    case "$backup_type" in
        "database")
            backup_database "$backup_path"
            ;;
        "config")
            backup_configuration "$backup_path"
            ;;
        "logs")
            backup_logs "$backup_path"
            ;;
        "full"|"")
            backup_database "$backup_path"
            backup_configuration "$backup_path"
            backup_logs "$backup_path"
            backup_docker_volumes "$backup_path"
            backup_runtime_data "$backup_path"
            ;;
        *)
            log_error "Unknown backup type: $backup_type"
            echo "Usage: $0 [full|database|config|logs]"
            exit 1
            ;;
    esac

    # Создание информации о backup
    create_backup_info "$backup_path"

    # Компрессия backup
    local compressed_file="$BACKUP_DIR/thermobot_backup_$DATE.tar.gz"
    compress_backup "$backup_path"

    # Проверка целостности
    if verify_backup "$compressed_file"; then
        # Очистка старых backup
        cleanup_old_backups

        # Отправка уведомления
        send_notification "$compressed_file"

        log_success "🎉 Backup completed successfully!"
        log_info "Backup file: $compressed_file"
        log_info "Backup size: $(du -h "$compressed_file" | cut -f1)"
    else
        log_error "❌ Backup failed integrity check"
        exit 1
    fi
}

# Обработка сигналов
trap 'log_error "Backup interrupted"; exit 1' INT TERM

# Запуск
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi