#!/bin/bash

# Тест исправления проблемы с локалями

echo "🔧 Тестирование исправления проблемы с локалями..."

# Остановка текущих контейнеров
echo "⏹️  Остановка текущих контейнеров..."
docker-compose down

# Пересборка образа с новым Dockerfile
echo "🏗️  Пересборка образа..."
docker-compose build --no-cache

# Запуск контейнеров
echo "🚀 Запуск контейнеров..."
docker-compose up -d

# Ожидание запуска
echo "⏰ Ожидание запуска приложения..."
sleep 10

# Проверка статуса
echo "📊 Статус контейнеров:"
docker-compose ps

# Проверка логов приложения
echo "📋 Логи приложения (последние 20 строк):"
docker-compose logs --tail=20 app

# Проверка доступности приложения
echo "🌐 Проверка доступности приложения..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000 | grep -q "200"; then
    echo "✅ Приложение успешно запущено!"
    echo "🌍 Доступно по адресу: http://localhost:8000"
else
    echo "❌ Проблемы с доступностью приложения"
    echo "📋 Подробные логи:"
    docker-compose logs app
fi

echo ""
echo "📋 Полезные команды:"
echo "   Просмотр логов:  docker-compose logs -f app"
echo "   Остановка:       docker-compose down"
echo "   Перезапуск:      docker-compose restart"
