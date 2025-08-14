#!/bin/bash

# Исправленный скрипт настройки HTTPS с Let's Encrypt

set -e

DOMAIN="ritclinic-utils.ru"  # Ваш домен

echo "🔒 Исправление настройки HTTPS для $DOMAIN..."

# Создание webroot директории
echo "📁 Создание webroot директории..."
mkdir -p ./certbot-webroot/.well-known/acme-challenge

# Остановка nginx для освобождения портов
echo "⏹️  Временная остановка nginx..."
docker-compose stop nginx

# Проверка доступности домена
echo "🌐 Проверка DNS для $DOMAIN..."
if ! nslookup $DOMAIN > /dev/null 2>&1; then
    echo "❌ DNS для $DOMAIN не настроен или еще не распространился"
    echo "⏰ Подождите 1-24 часа после настройки DNS"
    exit 1
fi

# Тест простого HTTP сервера для отладки
echo "🧪 Запуск тестового сервера для проверки..."
docker run --rm -d \
    --name nginx-test \
    -p 80:80 \
    -v $(pwd)/certbot-webroot:/var/www/certbot \
    nginx:alpine

# Создание тестового файла
echo "test-file" > ./certbot-webroot/.well-known/acme-challenge/test

# Проверка доступности
sleep 3
if curl -f "http://$DOMAIN/.well-known/acme-challenge/test" > /dev/null 2>&1; then
    echo "✅ Webroot доступен через $DOMAIN"
else
    echo "❌ Webroot недоступен. Проверьте DNS и брандмауэр"
    docker stop nginx-test
    exit 1
fi

# Остановка тестового сервера
docker stop nginx-test
rm ./certbot-webroot/.well-known/acme-challenge/test

# Получение сертификата через standalone режим (проще)
echo "🔒 Получение SSL сертификата..."
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

# Создание HTTPS конфигурации nginx
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

# Переключение на HTTPS конфигурацию
echo "🔄 Переключение на HTTPS..."
mv nginx/conf.d/rit-utils.conf nginx/conf.d/rit-utils-http.conf.backup
mv nginx/conf.d/rit-utils-https.conf nginx/conf.d/rit-utils.conf

# Перезапуск с HTTPS
echo "🚀 Запуск с HTTPS..."
docker-compose up -d

# Проверка
sleep 10
echo "📊 Проверка SSL сертификата..."
if curl -I "https://$DOMAIN" > /dev/null 2>&1; then
    echo "✅ HTTPS работает!"
    echo "🌐 Ваше приложение доступно: https://$DOMAIN"
else
    echo "⚠️  HTTPS настроен, но возможны проблемы с доступностью"
    echo "📋 Проверьте логи: docker-compose logs nginx"
fi

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
echo ""
