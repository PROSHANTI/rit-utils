#!/bin/bash

# 🚀 Универсальный скрипт развертывания RIT-Utils
# Поддерживает HTTP и HTTPS развертывание

set -e

echo "🚀 Универсальное развертывание RIT-Utils"
echo "========================================"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции вывода
success() { echo -e "${GREEN}✅ $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

# Функция проверки команды
check_command() {
    if command -v $1 &> /dev/null; then
        success "$1 найден"
        return 0
    else
        error "$1 не найден"
        return 1
    fi
}

# Проверка системных требований
check_requirements() {
    info "Проверка системных требований..."

    # Проверка Docker
    if ! check_command docker; then
        warning "Установка Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $USER
        rm get-docker.sh
        success "Docker установлен"
        warning "Для применения прав Docker необходим перезапуск сессии"
        warning "Запустите: newgrp docker && ./deploy.sh"
        exit 0
    fi

    # Проверка Docker Compose
    if ! check_command docker-compose; then
        warning "Установка Docker Compose..."
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        success "Docker Compose установлен"
    fi

    # Проверка git
    if ! check_command git; then
        warning "Установка Git..."
        sudo apt update
        sudo apt install -y git
        success "Git установлен"
    fi

    # Проверка curl и openssl для HTTPS
    sudo apt update
    sudo apt install -y curl openssl
}

# Получение настроек от пользователя
get_user_settings() {
    echo ""
    info "Настройка проекта"
    echo "=================="

    # Домен или IP
    echo ""
    echo -e "${BLUE}Введите ваш домен или оставьте пустым для использования только IP:${NC}"
    echo "Примеры:"
    echo "  - myapp.ru (для HTTPS)"
    echo "  - оставить пустым (только HTTP по IP)"
    read -p "Домен: " DOMAIN

    if [ -z "$DOMAIN" ]; then
        USE_HTTPS=false
        info "Будет настроен HTTP по IP адресу"
    else
        USE_HTTPS=true
        info "Будет настроен HTTPS для домена: $DOMAIN"

        # Email для Let's Encrypt
        echo -e "${BLUE}Введите email для Let's Encrypt:${NC}"
        read -p "Email: " SSL_EMAIL
        if [ -z "$SSL_EMAIL" ]; then
            SSL_EMAIL="admin@$DOMAIN"
        fi
    fi

    # Получение IP адреса сервера
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ipinfo.io/ip 2>/dev/null || echo "YOUR_SERVER_IP")
    if [ "$SERVER_IP" = "YOUR_SERVER_IP" ]; then
        warning "Не удалось определить IP сервера автоматически"
        read -p "Введите IP сервера: " SERVER_IP
    else
        info "Обнаружен IP сервера: $SERVER_IP"
    fi
}

# Настройка проекта
setup_project() {
    info "Настройка файлов проекта..."

    # Создание необходимых директорий
    mkdir -p nginx/logs nginx/ssl nginx/conf.d

    # Проверка .env файла
    if [ ! -f .env ]; then
        if [ -f .env.examples ]; then
            warning "Копирование .env.examples в .env..."
            cp .env.examples .env
            echo ""
            warning "ВАЖНО: Отредактируйте файл .env с вашими данными!"
            echo -e "${YELLOW}Основные настройки для изменения:${NC}"
            echo "  - LOGIN и PASSWORD (логин для входа в приложение)"
            echo "  - SEND_FROM и EMAIL_PASS (настройки почты)"
            echo "  - JWT_SECRET_KEY (секретный ключ)"
            echo ""
            read -p "Нажмите Enter когда отредактируете .env или Enter для продолжения с примерами..."
        else
            error "Файл .env.examples не найден!"
            exit 1
        fi
    else
        success "Файл .env найден"
    fi

    # Проверка дополнительных файлов
    info "Проверка дополнительных файлов..."
    missing_files=()

    if [ ! -f "src/utils/doctor_form/Бланк Врача.pptx" ]; then
        missing_files+=("src/utils/doctor_form/Бланк Врача.pptx")
    fi

    if [ ! -f "src/utils/gen_cert/Сертификат_шаблон.pptx" ]; then
        missing_files+=("src/utils/gen_cert/Сертификат_шаблон.pptx")
    fi

    if [ ! -f "src/utils/send_email/email_templates.py" ]; then
        missing_files+=("src/utils/send_email/email_templates.py")
    fi

    if [ ${#missing_files[@]} -gt 0 ]; then
        warning "Отсутствуют файлы шаблонов:"
        for file in "${missing_files[@]}"; do
            echo "   - $file"
        done
        echo ""
        warning "Добавьте эти файлы для полной функциональности"
        read -p "Продолжить без них? [y/N]: " continue_without_files
        if [[ ! $continue_without_files =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        success "Все дополнительные файлы найдены"
    fi
}

# Настройка nginx конфигурации
setup_nginx() {
    info "Настройка nginx..."

    if [ "$USE_HTTPS" = true ]; then
        # HTTPS конфигурация
        cat > nginx/conf.d/rit-utils.conf << EOF
# Upstream для FastAPI приложения
upstream fastapi_backend {
    server app:8000;
}

# Перенаправление HTTP на HTTPS
server {
    listen 80;
    server_name $DOMAIN;

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
    }

    # Перенаправление всего остального на HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS сервер
server {
    listen 443 ssl;
    http2 on;
    server_name $DOMAIN;

    # SSL сертификаты
    ssl_certificate /etc/nginx/ssl/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/live/$DOMAIN/privkey.pem;

    # SSL настройки
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Безопасность
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Лимиты
    client_max_body_size 20M;
    client_body_timeout 60s;
    client_header_timeout 60s;

    # Основные локации
    location / {
        proxy_pass http://fastapi_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Server \$host;

        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Для WebSocket поддержки
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Статические файлы
    location /static/ {
        proxy_pass http://fastapi_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Server \$host;

        # Кэширование статики
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Системные файлы
    location = /favicon.ico {
        access_log off;
        log_not_found off;
        return 204;
    }

    location = /robots.txt {
        access_log off;
        log_not_found off;
        return 200 "User-agent: *\nDisallow: /\n";
        add_header Content-Type text/plain;
    }

    # Блокировка доступа к служебным файлам
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
EOF
    else
        # HTTP конфигурация
        cat > nginx/conf.d/rit-utils.conf << EOF
# Upstream для FastAPI приложения
upstream fastapi_backend {
    server app:8000;
}

# HTTP сервер
server {
    listen 80;
    server_name $SERVER_IP;

    # Лимиты
    client_max_body_size 20M;
    client_body_timeout 60s;
    client_header_timeout 60s;

    # Основные локации
    location / {
        proxy_pass http://fastapi_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Server \$host;

        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Для WebSocket поддержки
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Статические файлы
    location /static/ {
        proxy_pass http://fastapi_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Server \$host;

        # Кэширование статики
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Системные файлы
    location = /favicon.ico {
        access_log off;
        log_not_found off;
        return 204;
    }

    location = /robots.txt {
        access_log off;
        log_not_found off;
        return 200 "User-agent: *\nDisallow: /\n";
        add_header Content-Type text/plain;
    }

    # Блокировка доступа к служебным файлам
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
EOF
    fi

    success "Nginx конфигурация создана"
}

# Получение SSL сертификата
setup_ssl() {
    if [ "$USE_HTTPS" != true ]; then
        return 0
    fi

    info "Настройка SSL сертификата..."

    # Проверка DNS
    info "Проверка DNS для $DOMAIN..."
    if ! nslookup $DOMAIN > /dev/null 2>&1; then
        error "DNS для $DOMAIN не настроен или еще не распространился"
        warning "Настройте A-запись: $DOMAIN → $SERVER_IP"
        warning "Подождите 1-24 часа после настройки DNS"

        read -p "Продолжить без HTTPS? [y/N]: " continue_without_ssl
        if [[ $continue_without_ssl =~ ^[Yy]$ ]]; then
            warning "Переключение на HTTP конфигурацию..."
            USE_HTTPS=false
            setup_nginx
            return 0
        else
            exit 1
        fi
    fi

    # Остановка nginx для освобождения порта 80
    info "Временная остановка nginx..."
    sudo docker-compose stop nginx 2>/dev/null || true

    # Остановка системного nginx если есть
    sudo systemctl stop nginx 2>/dev/null || true
    sudo pkill -f nginx 2>/dev/null || true

    # Проверка что порт 80 свободен
    if ss -tlnp | grep -q ":80 "; then
        error "Порт 80 занят. Остановите процессы использующие порт 80"
        ss -tlnp | grep ":80"
        exit 1
    fi

    # Создание webroot директории
    mkdir -p ./nginx/ssl

    # Получение сертификата
    info "Получение SSL сертификата от Let's Encrypt..."
    sudo docker run --rm \
        -p 80:80 \
        -v $(pwd)/nginx/ssl:/etc/letsencrypt \
        certbot/certbot \
        certonly \
        --standalone \
        --email $SSL_EMAIL \
        --agree-tos \
        --no-eff-email \
        --force-renewal \
        -d $DOMAIN

    # Проверка что сертификат создался
    if ! sudo test -f "./nginx/ssl/live/$DOMAIN/fullchain.pem"; then
        error "Сертификат не был создан"
        warning "Переключение на HTTP конфигурацию..."
        USE_HTTPS=false
        setup_nginx
        return 0
    fi

    success "SSL сертификат успешно получен"

    # Создание скрипта автообновления
    info "Настройка автообновления SSL сертификата..."
    sudo rm -f renew-cert.sh
    cat > renew-cert.sh << 'EOF'
#!/bin/bash
echo "🔄 Обновление SSL сертификата..."

# Остановка nginx
sudo docker-compose stop nginx

# Обновление сертификата
sudo docker run --rm \
    -p 80:80 \
    -v $(pwd)/nginx/ssl:/etc/letsencrypt \
    certbot/certbot renew

# Запуск nginx
sudo docker-compose start nginx

echo "✅ Сертификат обновлен"
EOF

    chmod +x renew-cert.sh

    # Добавление в crontab
    (crontab -l 2>/dev/null; echo "0 12 * * * $(pwd)/renew-cert.sh >> $(pwd)/certbot.log 2>&1") | crontab -

    success "Автообновление SSL настроено (ежедневно в 12:00)"
}

# Развертывание приложения
deploy_app() {
    info "Развертывание приложения..."

    # Остановка существующих контейнеров
    sudo docker-compose down 2>/dev/null || true

    # Сборка образов
    info "Сборка Docker образов..."
    sudo docker-compose build --no-cache

    # Запуск сервисов
    info "Запуск сервисов..."
    sudo docker-compose up -d

    # Ожидание запуска
    sleep 10

    # Проверка статуса
    info "Проверка статуса сервисов..."
    sudo docker-compose ps

    # Проверка логов
    info "Проверка логов приложения:"
    sudo docker-compose logs --tail=10 app

    success "Приложение развернуто"
}

# Финальная информация
show_final_info() {
    echo ""
    success "🎉 Развертывание завершено!"
    echo ""

    if [ "$USE_HTTPS" = true ]; then
        info "Приложение доступно по адресу:"
        echo "   🌐 HTTPS: https://$DOMAIN"
        echo "   🔄 HTTP автоматически перенаправляется на HTTPS"
        echo ""
        info "SSL сертификат:"
        echo "   📅 Автообновление: Включено (ежедневно в 12:00)"
        echo "   📋 Скрипт обновления: ./renew-cert.sh"
    else
        info "Приложение доступно по адресу:"
        echo "   🌐 HTTP: http://$SERVER_IP"
    fi

    echo ""
    info "Управление приложением:"
    echo "   📊 Статус:          sudo docker-compose ps"
    echo "   📋 Логи:            sudo docker-compose logs -f"
    echo "   🔄 Перезапуск:      sudo docker-compose restart"
    echo "   ⏹️  Остановка:       sudo docker-compose down"
    echo "   🔧 Обновление:      git pull && sudo docker-compose restart"
    echo ""

    if [ ${#missing_files[@]} -gt 0 ]; then
        warning "Не забудьте добавить файлы шаблонов для полной функциональности:"
        for file in "${missing_files[@]}"; do
            echo "   - $file"
        done
        echo ""
    fi
}

# Основная функция
main() {
    check_requirements
    get_user_settings
    setup_project
    setup_nginx
    setup_ssl
    deploy_app
    show_final_info
}

# Запуск
main "$@"
