#!/bin/bash

# Отладочный скрипт для диагностики проблем с HTTPS

set -e

DOMAIN="ritclinic-utils.ru"

echo "🔍 Диагностика проблем с HTTPS для $DOMAIN..."

# Проверка DNS
echo "🌐 Проверка DNS..."
echo "nslookup результат:"
nslookup $DOMAIN || echo "❌ DNS проблема"

echo "dig результат:"
dig $DOMAIN A +short || echo "❌ dig проблема"

# Проверка доступности по HTTP
echo "🌍 Проверка доступности по HTTP..."
if curl -I "http://$DOMAIN" > /dev/null 2>&1; then
    echo "✅ HTTP доступен"
    curl -I "http://$DOMAIN"
else
    echo "❌ HTTP недоступен"
fi

# Проверка webroot директории
echo "📁 Проверка webroot директории..."
mkdir -p ./certbot-webroot/.well-known/acme-challenge
echo "test-content" > ./certbot-webroot/.well-known/acme-challenge/test-file

# Проверка доступности webroot через nginx
echo "🧪 Проверка webroot через nginx..."
if curl -f "http://$DOMAIN/.well-known/acme-challenge/test-file" 2>/dev/null | grep -q "test-content"; then
    echo "✅ Webroot доступен через nginx"
else
    echo "❌ Webroot недоступен через nginx"
    echo "📋 Проверим что nginx запущен:"
    docker-compose ps nginx
    
    echo "📋 Логи nginx:"
    docker-compose logs --tail=10 nginx
    
    echo "📋 Тестируем напрямую:"
    if [ -f "./certbot-webroot/.well-known/acme-challenge/test-file" ]; then
        echo "✅ Файл существует локально"
        cat ./certbot-webroot/.well-known/acme-challenge/test-file
    else
        echo "❌ Файл не существует локально"
    fi
fi

# Очистка тестового файла
rm -f ./certbot-webroot/.well-known/acme-challenge/test-file

# Проверка брандмауэра и портов
echo "🔥 Проверка портов..."
if command -v ss >/dev/null 2>&1; then
    echo "Открытые порты:"
    ss -tlnp | grep -E ":80|:443" || echo "Порты 80/443 не открыты"
elif command -v netstat >/dev/null 2>&1; then
    echo "Открытые порты:"
    netstat -tlnp | grep -E ":80|:443" || echo "Порты 80/443 не открыты"
fi

# Проверка конфигурации nginx
echo "⚙️ Проверка конфигурации nginx..."
if docker-compose exec nginx nginx -t 2>/dev/null; then
    echo "✅ Конфигурация nginx корректна"
else
    echo "❌ Ошибки в конфигурации nginx"
    docker-compose exec nginx nginx -t
fi

# Проверка volume монтирования
echo "💾 Проверка volume монтирования..."
docker-compose exec nginx ls -la /var/www/certbot/.well-known/ 2>/dev/null || echo "❌ /var/www/certbot недоступен в nginx"

echo ""
echo "📋 Рекомендации:"
echo "1. Если webroot недоступен - используйте standalone метод: ./fix-https.sh"
echo "2. Если DNS проблемы - подождите 1-24 часа"
echo "3. Если порты закрыты - откройте 80 и 443 в брандмауэре"
echo "4. Если nginx проблемы - перезапустите: docker-compose restart nginx"
