#!/bin/bash

# Скрипт настройки HTTPS с Let's Encrypt для RIT-Utils

set -e

echo "🔒 Настройка HTTPS с Let's Encrypt..."

# Проверка домена
read -p "Введите ваш домен (например, example.com): " DOMAIN

if [ -z "$DOMAIN" ]; then
    echo "❌ Домен не указан!"
    exit 1
fi

echo "🌐 Домен: $DOMAIN"

# Проверка Certbot
check_certbot() {
    echo "📋 Проверка Certbot..."
    
    if ! command -v certbot &> /dev/null; then
        echo "❌ Certbot не найден. Установка..."
        sudo apt update
        sudo apt install -y certbot python3-certbot-nginx
        echo "✅ Certbot установлен"
    else
        echo "✅ Certbot найден"
    fi
}

# Создание HTTPS конфигурации nginx
create_https_config() {
    echo "📝 Создание HTTPS конфигурации..."
    
    cat > nginx/conf.d/rit-utils-https.conf << EOF
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
    }
    
    # Перенаправление всего остального на HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS сервер
server {
    listen 443 ssl http2;
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

    echo "✅ HTTPS конфигурация создана"
}

# Получение SSL сертификата
get_certificate() {
    echo "🔒 Получение SSL сертификата..."
    
    # Создание директории для webroot
    sudo mkdir -p /var/www/certbot
    
    # Временная остановка nginx в контейнере
    docker-compose stop nginx
    
    # Получение сертификата
    sudo certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email admin@$DOMAIN \
        --agree-tos \
        --no-eff-email \
        -d $DOMAIN
    
    # Копирование сертификатов в nginx директорию
    sudo cp -R /etc/letsencrypt/live/$DOMAIN nginx/ssl/live/
    sudo cp -R /etc/letsencrypt/archive/$DOMAIN nginx/ssl/archive/
    
    # Установка прав
    sudo chown -R $USER:$USER nginx/ssl/
    
    echo "✅ SSL сертификат получен"
}

# Обновление Docker Compose для HTTPS
update_docker_compose() {
    echo "🐳 Обновление Docker Compose конфигурации..."
    
    # Добавление volume для certbot
    if ! grep -q "certbot" docker-compose.yml; then
        cat >> docker-compose.yml << EOF

  # Certbot для обновления сертификатов
  certbot:
    image: certbot/certbot
    container_name: rit-utils-certbot
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt
      - /var/www/certbot:/var/www/certbot
    command: sleep infinity
EOF
    fi
    
    echo "✅ Docker Compose обновлен"
}

# Настройка автообновления сертификата
setup_auto_renewal() {
    echo "🔄 Настройка автообновления сертификата..."
    
    # Создание скрипта обновления
    cat > renew-cert.sh << 'EOF'
#!/bin/bash
# Скрипт автообновления SSL сертификата

echo "🔄 Обновление SSL сертификата..."

# Обновление сертификата
docker-compose run --rm certbot renew

# Копирование обновленных сертификатов
if [ -d "/etc/letsencrypt/live" ]; then
    sudo cp -R /etc/letsencrypt/live/* nginx/ssl/live/
    sudo chown -R $USER:$USER nginx/ssl/
    
    # Перезапуск nginx
    docker-compose restart nginx
    
    echo "✅ Сертификат обновлен"
else
    echo "❌ Сертификаты не найдены"
fi
EOF

    chmod +x renew-cert.sh
    
    # Добавление в crontab
    (crontab -l 2>/dev/null; echo "0 12 * * * $(pwd)/renew-cert.sh >> $(pwd)/certbot.log 2>&1") | crontab -
    
    echo "✅ Автообновление настроено (каждый день в 12:00)"
}

# Переключение на HTTPS конфигурацию
switch_to_https() {
    echo "🔄 Переключение на HTTPS..."
    
    # Резервная копия текущей конфигурации
    cp nginx/conf.d/rit-utils.conf nginx/conf.d/rit-utils.conf.backup
    
    # Замена конфигурации
    mv nginx/conf.d/rit-utils.conf nginx/conf.d/rit-utils-http.conf.disabled
    mv nginx/conf.d/rit-utils-https.conf nginx/conf.d/rit-utils.conf
    
    # Перезапуск сервисов
    docker-compose up -d
    
    echo "✅ Переключение на HTTPS завершено"
}

# Информация после настройки
post_setup_info() {
    echo ""
    echo "🎉 HTTPS успешно настроен!"
    echo ""
    echo "🌐 Ваше приложение доступно по адресу:"
    echo "   https://$DOMAIN"
    echo ""
    echo "📋 Информация о сертификате:"
    echo "   Домен: $DOMAIN"
    echo "   Автообновление: Включено (ежедневно в 12:00)"
    echo ""
    echo "📋 Полезные команды:"
    echo "   Проверка сертификата: ./renew-cert.sh"
    echo "   Просмотр логов certbot: cat certbot.log"
    echo "   Статус SSL: curl -I https://$DOMAIN"
    echo ""
}

# Основная функция
main() {
    check_certbot
    create_https_config
    get_certificate
    update_docker_compose
    setup_auto_renewal
    switch_to_https
    post_setup_info
}

# Запуск
main "$@"
