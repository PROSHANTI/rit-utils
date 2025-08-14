#!/bin/bash

# Улучшенный скрипт настройки HTTPS с полной остановкой сервисов

set -e

DOMAIN="ritclinic-utils.ru"

echo "🔒 Исправление настройки HTTPS для $DOMAIN..."

# Функция проверки порта
check_port_80() {
    if ss -tlnp | grep -q ":80 "; then
        echo "⚠️  Порт 80 занят:"
        ss -tlnp | grep ":80 "
        return 1
    else
        echo "✅ Порт 80 свободен"
        return 0
    fi
}

# Полная остановка всех сервисов
echo "⏹️  Полная остановка всех сервисов..."
docker-compose down --remove-orphans

# Остановка всех nginx контейнеров (если есть)
echo "🛑 Остановка всех nginx контейнеров..."
docker stop $(docker ps -q --filter "ancestor=nginx:alpine") 2>/dev/null || true
docker stop $(docker ps -q --filter "name=nginx") 2>/dev/null || true

# Проверка что порт 80 свободен
echo "🔍 Проверка порта 80..."
sleep 3
if ! check_port_80; then
    echo "❌ Порт 80 всё еще занят. Проверим кто его использует..."
    
    # Показываем кто использует порт 80
    echo "Процессы на порту 80:"
    sudo ss -tlnp | grep ":80 " || true
    sudo lsof -i :80 || true
    
    # Пытаемся освободить порт
    echo "🔧 Попытка освободить порт 80..."
    sudo pkill -f nginx || true
    sudo systemctl stop nginx || true
    sleep 2
    
    if ! check_port_80; then
        echo "❌ Не удалось освободить порт 80. Перезапустите сервер или остановите процесс вручную."
        exit 1
    fi
fi

# Проверка DNS
echo "🌐 Проверка DNS для $DOMAIN..."
if ! nslookup $DOMAIN > /dev/null 2>&1; then
    echo "❌ DNS для $DOMAIN не настроен или еще не распространился"
    echo "⏰ Подождите 1-24 часа после настройки DNS"
    exit 1
fi

# Создание директории для сертификатов
echo "📁 Создание директории для сертификатов..."
mkdir -p ./nginx/ssl

# Получение сертификата через standalone режим
echo "🔒 Получение SSL сертификата через standalone..."
docker run --rm \
    -p 80:80 \
    -v $(pwd)/nginx/ssl:/etc/letsencrypt \
    certbot/certbot \
    certonly \
    --standalone \
    --email admin@$DOMAIN \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d $DOMAIN

# Проверка что сертификат создался
if [ ! -f "./nginx/ssl/live/$DOMAIN/fullchain.pem" ]; then
    echo "❌ Сертификат не был создан"
    exit 1
fi

echo "✅ Сертификат успешно получен"

# Обновление server_name в nginx конфигурации для домена
echo "📝 Обновление nginx конфигурации для домена..."
sed -i "s/server_name 51.250.123.52;/server_name $DOMAIN;/" nginx/conf.d/rit-utils.conf

# Создание HTTPS конфигурации nginx
echo "📝 Создание HTTPS конфигурации..."
cat > nginx/conf.d/rit-utils-https.conf << EOF
# Upstream для FastAPI приложения
upstream fastapi_backend_https {
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

    # Let's Encrypt ACME challenge (для обновлений)
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri \$uri/ =404;
    }

    # Основные локации
    location / {
        proxy_pass http://fastapi_backend_https;
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
        proxy_pass http://fastapi_backend_https;
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

# Переключение на HTTPS конфигурацию
echo "🔄 Переключение на HTTPS..."
if [ -f "nginx/conf.d/rit-utils.conf" ]; then
    mv nginx/conf.d/rit-utils.conf nginx/conf.d/rit-utils-http.conf.backup
fi
mv nginx/conf.d/rit-utils-https.conf nginx/conf.d/rit-utils.conf

# Перезапуск с HTTPS
echo "🚀 Запуск с HTTPS..."
docker-compose up -d

# Ожидание запуска
echo "⏰ Ожидание запуска сервисов..."
sleep 15

# Проверка статуса сервисов
echo "📊 Статус сервисов:"
docker-compose ps

# Проверка логов nginx
echo "📋 Логи nginx:"
docker-compose logs --tail=10 nginx

# Проверка HTTP редиректа
echo "📍 Проверка HTTP редиректа..."
if curl -I "http://$DOMAIN" 2>/dev/null | grep -q "301\|302"; then
    echo "✅ HTTP редирект на HTTPS работает"
else
    echo "⚠️  HTTP редирект может не работать"
fi

# Проверка HTTPS
echo "📍 Проверка HTTPS..."
if curl -I "https://$DOMAIN" 2>/dev/null | grep -q "200"; then
    echo "✅ HTTPS работает!"
    echo "🌐 Ваше приложение доступно: https://$DOMAIN"
else
    echo "⚠️  HTTPS настроен, но возможны проблемы с доступностью"
    echo "📋 Проверьте логи: docker-compose logs nginx"
fi

# Проверка SSL сертификата
echo "🔒 Проверка SSL сертификата..."
echo "Сертификат выдан для:"
openssl x509 -in "./nginx/ssl/live/$DOMAIN/cert.pem" -noout -subject 2>/dev/null || echo "Не удалось прочитать сертификат"

echo "Сертификат действителен до:"
openssl x509 -in "./nginx/ssl/live/$DOMAIN/cert.pem" -noout -enddate 2>/dev/null || echo "Не удалось прочитать дату"

# Настройка автообновления
echo "🔄 Настройка автообновления сертификата..."
cat > renew-cert.sh << 'EOF'
#!/bin/bash
echo "🔄 Обновление SSL сертификата..."

# Остановка nginx
docker-compose stop nginx

# Обновление сертификата
docker run --rm \
    -p 80:80 \
    -v $(pwd)/nginx/ssl:/etc/letsencrypt \
    certbot/certbot renew

# Запуск nginx
docker-compose start nginx

echo "✅ Сертификат обновлен"
EOF

chmod +x renew-cert.sh

# Добавление в crontab
(crontab -l 2>/dev/null; echo "0 12 * * * $(pwd)/renew-cert.sh >> $(pwd)/certbot.log 2>&1") | crontab -

echo ""
echo "🎉 HTTPS успешно настроен!"
echo "🌐 Приложение доступно: https://$DOMAIN"
echo "🔄 Автообновление: Включено (ежедневно в 12:00)"
echo "📋 Файл автообновления: ./renew-cert.sh"
echo ""
echo "📍 Проверьте приложение:"
echo "   HTTP:  http://$DOMAIN (должен перенаправлять на HTTPS)"
echo "   HTTPS: https://$DOMAIN"
