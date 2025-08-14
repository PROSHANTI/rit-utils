#!/bin/bash

# 🔄 Скрипт обновления RIT-Utils на сервере

set -e

# Цвета для вывода
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

success() { echo -e "${GREEN}✅ $1${NC}"; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }

echo "🔄 Обновление RIT-Utils"
echo "======================"

# Проверяем что мы в правильной директории
if [ ! -f "docker-compose.yml" ] || [ ! -f "src/main.py" ]; then
    error "Запустите скрипт из корневой директории проекта rit-utils"
    exit 1
fi

# Проверяем статус git
info "Проверка статуса Git..."
if ! git status &>/dev/null; then
    error "Это не Git репозиторий или Git недоступен"
    exit 1
fi

# Показываем текущий коммит
current_commit=$(git rev-parse --short HEAD)
info "Текущий коммит: $current_commit"

# Получаем обновления
info "Получение обновлений из Git..."
git fetch origin

# Проверяем есть ли обновления
if git diff HEAD origin/main --quiet; then
    success "Код уже актуален, обновления не требуются"
    
    # Спрашиваем нужно ли перезапустить принудительно
    read -p "Перезапустить приложение принудительно? [y/N]: " force_restart
    if [[ ! $force_restart =~ ^[Yy]$ ]]; then
        info "Обновление завершено без изменений"
        exit 0
    fi
else
    info "Найдены обновления, применяем..."
    
    # Показываем что изменилось
    echo ""
    info "Изменения:"
    git log --oneline HEAD..origin/main
    echo ""
    
    # Применяем обновления
    git pull origin main
    
    new_commit=$(git rev-parse --short HEAD)
    success "Обновлено до коммита: $new_commit"
fi

# Определяем тип обновления
needs_rebuild=false

# Проверяем изменения в критических файлах
if git diff HEAD~1 --name-only | grep -E "(Dockerfile|pyproject.toml|poetry.lock)" &>/dev/null; then
    warning "Обнаружены изменения в зависимостях или Dockerfile"
    needs_rebuild=true
fi

# Показываем план действий
echo ""
info "План обновления:"
if [ "$needs_rebuild" = true ]; then
    echo "  1. 🏗️  Пересборка Docker образов (обнаружены изменения в зависимостях)"
    echo "  2. 🔄 Перезапуск сервисов"
else
    echo "  1. 🔄 Быстрый перезапуск сервисов"
fi
echo "  3. ✅ Проверка статуса"
echo ""

read -p "Продолжить обновление? [Y/n]: " confirm
if [[ $confirm =~ ^[Nn]$ ]]; then
    warning "Обновление отменено"
    exit 0
fi

# Выполняем обновление
echo ""
info "Начинаем обновление приложения..."

if [ "$needs_rebuild" = true ]; then
    info "Пересборка Docker образов..."
    docker-compose down
    docker-compose build --no-cache
    docker-compose up -d
else
    info "Быстрый перезапуск..."
    docker-compose restart
fi

# Ждем запуска
info "Ожидание запуска сервисов..."
sleep 10

# Проверяем статус
echo ""
info "Статус сервисов:"
docker-compose ps

# Проверяем логи приложения
echo ""
info "Последние логи приложения:"
docker-compose logs --tail=10 app

# Проверяем доступность
echo ""
info "Проверка доступности..."

# Определяем URL для проверки
if grep -q "listen 443" nginx/conf.d/rit-utils.conf 2>/dev/null; then
    # HTTPS конфигурация
    domain=$(grep "server_name" nginx/conf.d/rit-utils.conf | head -1 | awk '{print $2}' | sed 's/;//')
    check_url="https://$domain"
else
    # HTTP конфигурация
    check_url="http://localhost"
fi

if curl -s -f "$check_url" >/dev/null; then
    success "Приложение доступно: $check_url"
else
    warning "Приложение может быть недоступно"
    echo ""
    info "Для диагностики выполните:"
    echo "  docker-compose logs app"
    echo "  docker-compose ps"
fi

echo ""
success "🎉 Обновление завершено!"

# Показываем полезную информацию
echo ""
info "Полезные команды:"
echo "  📊 Статус:     docker-compose ps"
echo "  📋 Логи:       docker-compose logs -f"
echo "  🔄 Рестарт:    docker-compose restart"
echo "  ⏹️  Остановка:  docker-compose down"
