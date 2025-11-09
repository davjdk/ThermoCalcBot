#!/bin/bash
# =============================================================================
# SSL Setup Script for ThermoCalcBot
# =============================================================================
# Настройка SSL/TLS сертификатов для production окружения
# =============================================================================

set -euo pipefail

# Конфигурация
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
NGINX_SSL_DIR="$PROJECT_DIR/nginx/ssl"
DOMAIN="${DOMAIN:-your-domain.com}"
EMAIL="${EMAIL:-admin@your-domain.com}"

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

# Проверка зависимостей
check_dependencies() {
    log_info "Checking dependencies..."

    local missing_deps=()

    # Проверка OpenSSL
    if ! command -v openssl &> /dev/null; then
        missing_deps+=("openssl")
    fi

    # Проверка Certbot (для production)
    if [ "${USE_LETSENCRYPT:-true}" = "true" ] && ! command -v certbot &> /dev/null; then
        missing_deps+=("certbot")
    fi

    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "Missing dependencies: ${missing_deps[*]}"
        echo ""
        echo "For Ubuntu/Debian:"
        echo "  sudo apt-get update"
        echo "  sudo apt-get install -y openssl certbot python3-certbot-nginx"
        echo ""
        echo "For CentOS/RHEL:"
        echo "  sudo yum install -y openssl certbot python3-certbot-nginx"
        echo ""
        echo "For macOS:"
        echo "  brew install openssl certbot"
        exit 1
    fi

    log_success "Dependencies check passed"
}

# Создание самоподписанного сертификата (для разработки)
create_self_signed_certificate() {
    log_info "Creating self-signed SSL certificate..."

    mkdir -p "$NGINX_SSL_DIR"

    # Генерация приватного ключа
    openssl genrsa -out "$NGINX_SSL_DIR/key.pem" 4096

    # Создание CSR
    openssl req -new -key "$NGINX_SSL_DIR/key.pem" -out "$NGINX_SSL_DIR/cert.csr" -subj "/C=RU/ST=State/L=City/O=ThermoSystem/CN=$DOMAIN"

    # Создание самоподписанного сертификата
    openssl x509 -req -days 365 -in "$NGINX_SSL_DIR/cert.csr" -signkey "$NGINX_SSL_DIR/key.pem" -out "$NGINX_SSL_DIR/cert.pem"

    # Удаление CSR
    rm "$NGINX_SSL_DIR/cert.csr"

    # Установка прав доступа
    chmod 600 "$NGINX_SSL_DIR/key.pem"
    chmod 644 "$NGINX_SSL_DIR/cert.pem"

    log_success "Self-signed certificate created"
    log_warning "This certificate is suitable for development only!"
    log_warning "Browsers will show security warnings"
}

# Настройка Let's Encrypt сертификата
setup_letsencrypt_certificate() {
    log_info "Setting up Let's Encrypt certificate..."

    # Проверка, что домен указан
    if [ "$DOMAIN" = "your-domain.com" ]; then
        log_error "Please set your actual domain name:"
        echo "  export DOMAIN=your-real-domain.com"
        echo "  export EMAIL=your-email@domain.com"
        exit 1
    fi

    # Проверка доступности домена
    log_info "Checking domain availability..."
    if ! dig +short "$DOMAIN" > /dev/null 2>&1; then
        log_error "Domain $DOMAIN is not accessible"
        log_error "Make sure DNS is configured and the domain points to this server"
        exit 1
    fi

    # Создание директории для сертификатов
    mkdir -p "$NGINX_SSL_DIR"

    # Получение сертификата через certbot
    log_info "Obtaining Let's Encrypt certificate for $DOMAIN..."

    if certbot certonly \
        --nginx \
        --non-interactive \
        --agree-tos \
        --email "$EMAIL" \
        --domains "$DOMAIN" \
        --cert-name "$DOMAIN"; then

        # Копирование сертификатов в нашу директорию
        cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$NGINX_SSL_DIR/cert.pem"
        cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$NGINX_SSL_DIR/key.pem"

        # Установка прав доступа
        chmod 644 "$NGINX_SSL_DIR/cert.pem"
        chmod 600 "$NGINX_SSL_DIR/key.pem"

        log_success "Let's Encrypt certificate obtained and installed"
        log_info "Certificate location: $NGINX_SSL_DIR/"
        log_info "Auto-renewal: certbot automatically handles renewal"

    else
        log_error "Failed to obtain Let's Encrypt certificate"
        log_info "Falling back to self-signed certificate..."
        create_self_signed_certificate
    fi
}

# Создание Diffie-Hellman параметров
create_dh_params() {
    log_info "Creating Diffie-Hellman parameters..."

    local dh_params_file="$NGINX_SSL_DIR/dhparam.pem"

    if [ ! -f "$dh_params_file" ]; then
        openssl dhparam -out "$dh_params_file" 2048
        chmod 644 "$dh_params_file"
        log_success "DH parameters created"
    else
        log_info "DH parameters already exist"
    fi
}

# Обновление конфигурации Nginx для SSL
update_nginx_config() {
    log_info "Updating Nginx configuration..."

    local nginx_config="$PROJECT_DIR/nginx/nginx.conf"

    # Замена placeholder домена
    if [ "$DOMAIN" != "your-domain.com" ]; then
        sed -i "s/your-domain.com/$DOMAIN/g" "$nginx_config"
        log_success "Updated domain in Nginx configuration"
    fi

    log_info "Nginx configuration updated"
    log_info "Reload Nginx to apply changes: docker-compose restart nginx"
}

# Создание тестовой конфигурации Nginx
create_test_nginx_config() {
    log_info "Creating test Nginx configuration..."

    local test_config_dir="$NGINX_SSL_DIR/test_config"
    mkdir -p "$test_config_dir"

    cat > "$test_config_dir/test_nginx.conf" << EOF
# Test Nginx Configuration for SSL Testing
events {
    worker_connections 1024;
}

http {
    server {
        listen 8443 ssl;
        server_name $DOMAIN;

        ssl_certificate $NGINX_SSL_DIR/cert.pem;
        ssl_certificate_key $NGINX_SSL_DIR/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        location / {
            return 200 "SSL Configuration Test - Success!";
            add_header Content-Type text/plain;
        }
    }
}
EOF

    log_success "Test Nginx configuration created"
    log_info "Test with: nginx -t -c $test_config_dir/test_nginx.conf"
}

# Проверка сертификата
verify_certificate() {
    log_info "Verifying SSL certificate..."

    if [ -f "$NGINX_SSL_DIR/cert.pem" ]; then
        # Проверка срока действия
        local expiry_date=$(openssl x509 -in "$NGINX_SSL_DIR/cert.pem" -noout -enddate | cut -d= -f2)
        log_info "Certificate expires: $expiry_date"

        # Проверка валидности сертификата
        if openssl x509 -in "$NGINX_SSL_DIR/cert.pem" -noout -text > /dev/null 2>&1; then
            log_success "Certificate is valid"
        else
            log_error "Certificate is invalid"
            return 1
        fi

        # Проверка приватного ключа
        if [ -f "$NGINX_SSL_DIR/key.pem" ]; then
            if openssl rsa -in "$NGINX_SSL_DIR/key.pem" -check > /dev/null 2>&1; then
                log_success "Private key is valid"
            else
                log_error "Private key is invalid"
                return 1
            fi

            # Проверка соответствия ключа и сертификата
            local cert_modulus=$(openssl x509 -noout -modulus -in "$NGINX_SSL_DIR/cert.pem" | openssl md5)
            local key_modulus=$(openssl rsa -noout -modulus -in "$NGINX_SSL_DIR/key.pem" | openssl md5)

            if [ "$cert_modulus" = "$key_modulus" ]; then
                log_success "Certificate and private key match"
            else
                log_error "Certificate and private key do not match"
                return 1
            fi
        fi
    else
        log_error "Certificate file not found"
        return 1
    fi

    return 0
}

# Вывод инструкций по настройке
print_instructions() {
    log_info "SSL setup completed!"
    echo ""
    echo "📋 Next Steps:"
    echo ""
    echo "1. Update your domain DNS to point to this server"
    echo "2. Update Nginx configuration:"
    echo "   - Edit nginx/nginx.conf"
    echo "   - Replace 'your-domain.com' with your actual domain"
    echo "3. Restart services:"
    echo "   docker-compose down"
    echo "   docker-compose up -d"
    echo ""
    echo "🔒 SSL Certificate Information:"
    echo "   Certificate: $NGINX_SSL_DIR/cert.pem"
    echo "   Private Key: $NGINX_SSL_DIR/key.pem"
    echo "   DH Params: $NGINX_SSL_DIR/dhparam.pem"
    echo ""
    if [ "${USE_LETSENCRYPT:-true}" = "true" ]; then
        echo "🔄 Let's Encrypt Auto-renewal:"
        echo "   Certbot automatically handles renewal"
        echo "   Check renewal: certbot certificates"
    fi
    echo ""
    echo "🧪 Test SSL configuration:"
    echo "   curl -v https://$DOMAIN/health"
    echo "   openssl s_client -connect $DOMAIN:443"
}

# Основная функция
main() {
    local ssl_type="${1:-letsencrypt}"

    log_info "🔐 Starting SSL setup for ThermoCalcBot..."

    # Проверка зависимостей
    check_dependencies

    # Создание самоподписанного сертификата для разработки
    if [ "$ssl_type" = "self-signed" ]; then
        create_self_signed_certificate
    elif [ "$ssl_type" = "letsencrypt" ]; then
        setup_letsencrypt_certificate
    else
        log_error "Unknown SSL type: $ssl_type"
        echo "Usage: $0 [letsencrypt|self-signed]"
        exit 1
    fi

    # Создание DH параметров
    create_dh_params

    # Обновление конфигурации Nginx
    update_nginx_config

    # Создание тестовой конфигурации
    create_test_nginx_config

    # Проверка сертификата
    if verify_certificate; then
        # Вывод инструкций
        print_instructions
        log_success "🎉 SSL setup completed successfully!"
    else
        log_error "❌ SSL verification failed"
        exit 1
    fi
}

# Обработка сигналов
trap 'log_error "SSL setup interrupted"; exit 1' INT TERM

# Запуск
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi