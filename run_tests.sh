#!/bin/bash

# Скрипт для запуска тестов RIT-Utils
# Использование: ./run_tests.sh [опции]

echo "🧪 Запуск тестов для RIT-Utils"
echo "==============================="

# Проверяем, что poetry доступен
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry не найден. Установите Poetry для запуска тестов."
    exit 1
fi

# Проверяем параметры командной строки
case "${1:-all}" in
    "all")
        echo "📋 Запуск всех тестов..."
        poetry run pytest tests/ -v --tb=short
        ;;
    "unit")
        echo "🔬 Запуск unit тестов..."
        poetry run pytest tests/test_auth_* tests/test_utils_* tests/test_config.py tests/test_main.py -v
        ;;
    "integration") 
        echo "🔗 Запуск интеграционных тестов..."
        poetry run pytest tests/test_integration_* -v
        ;;
    "auth")
        echo "🔐 Запуск тестов аутентификации..."
        poetry run pytest tests/test_auth_* -v
        ;;
    "utils")
        echo "🛠️ Запуск тестов утилит..."
        poetry run pytest tests/test_utils_* -v
        ;;
    "fast")
        echo "⚡ Запуск быстрых тестов..."
        poetry run pytest tests/ -v --tb=short -x -q
        ;;
    "coverage")
        echo "📊 Запуск тестов с покрытием..."
        poetry run pytest tests/ --cov=src --cov-report=term-missing --cov-report=html
        ;;
    "collect")
        echo "📝 Сбор информации о тестах..."
        poetry run pytest tests/ --collect-only
        ;;
    "help")
        echo "Доступные команды:"
        echo "  all         - Запустить все тесты (по умолчанию)"
        echo "  unit        - Запустить только unit тесты"
        echo "  integration - Запустить только интеграционные тесты"
        echo "  auth        - Запустить тесты аутентификации"
        echo "  utils       - Запустить тесты утилит"
        echo "  fast        - Быстрый запуск (останавливается на первой ошибке)"
        echo "  coverage    - Запуск с анализом покрытия кода"
        echo "  collect     - Показать список всех тестов"
        echo "  help        - Показать эту справку"
        ;;
    *)
        echo "❓ Неизвестная команда: $1"
        echo "Используйте './run_tests.sh help' для справки"
        exit 1
        ;;
esac

echo ""
echo "✅ Готово!"
