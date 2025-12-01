#!/bin/bash

# 🔄 Скрипт обновления RIT-Utils на сервере
# Использование: ./update.sh [branch]
# Или установите переменную: BRANCH=test ./update.sh

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

# Определение окружения и ветки
detect_environment() {
    # Если ветка указана явно как аргумент, используем её
    if [ ! -z "$1" ]; then
        echo "$1"
        return 0
    fi

    # Проверяем переменную окружения
    if [ ! -z "$ENV" ]; then
        if [ "$ENV" = "test" ] || [ "$ENV" = "prod" ]; then
            if [ "$ENV" = "test" ]; then
                echo "test"
            else
                echo "main"
            fi
            return 0
        fi
    fi

    # Определяем по домену из nginx конфига
    if [ -f "nginx/conf.d/rit-utils.conf" ]; then
        DOMAIN_FROM_CONFIG=$(grep "server_name" nginx/conf.d/rit-utils.conf | head -1 | awk '{print $2}' | sed 's/;//' | awk '{print $1}')

        if echo "$DOMAIN_FROM_CONFIG" | grep -q "test"; then
            echo "test"
            return 0
        elif echo "$DOMAIN_FROM_CONFIG" | grep -q "ritclinic-utils.ru"; then
            echo "main"
            return 0
        fi
    fi

    # Fallback: определяем по текущему домену сервера
    HOSTNAME=$(hostname -f 2>/dev/null || echo "")
    if echo "$HOSTNAME" | grep -q "test"; then
        echo "test"
        return 0
    fi

    # По умолчанию - main (prod)
    echo "main"
}

# Определяем ветку для обновления
BRANCH=$(detect_environment "$1")

if [ "$BRANCH" = "test" ]; then
    DOMAIN="ritclinic-utils-test.ru"
    ENV_LABEL="🧪 ТЕСТОВОЕ"
else
    DOMAIN="ritclinic-utils.ru"
    ENV_LABEL="🚀 ПРОДОВОЕ"
fi

echo "🔄 Обновление RIT-Utils"
echo "======================"
info "Окружение: $ENV_LABEL"
info "Целевая ветка: $BRANCH"
info "Домен: $DOMAIN"

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

# Проверяем существование ветки
if ! git rev-parse --verify origin/$BRANCH >/dev/null 2>&1; then
    error "Ветка '$BRANCH' не существует в удаленном репозитории"
    info "Доступные ветки:"
    git branch -r | grep -v HEAD | sed 's|origin/||' | sed 's|^|  |'
    exit 1
fi

# Сохраняем текущий коммит до обновления для сравнения
old_commit=$(git rev-parse HEAD)

# Проверяем текущую ветку
current_branch=$(git branch --show-current)
if [ "$current_branch" != "$BRANCH" ]; then
    warning "Текущая ветка: $current_branch, целевая ветка: $BRANCH"
    info "Переключение на ветку $BRANCH..."
    git checkout $BRANCH
    success "Переключились на ветку $BRANCH"
fi

# Проверяем есть ли обновления
if git diff HEAD origin/$BRANCH --quiet 2>/dev/null; then
    success "Код уже актуален, обновления не требуются"
    info "Перезапуск контейнеров для применения текущего кода..."
    force_restart="y"
else
    info "Найдены обновления, применяем..."

    # Показываем что изменилось
    echo ""
    info "Изменения:"
    git log --oneline HEAD..origin/$BRANCH 2>/dev/null | head -10
    echo ""

    # Применяем обновления
    git pull origin $BRANCH

    new_commit=$(git rev-parse --short HEAD)
    success "Обновлено до коммита: $new_commit"
fi

# Определяем тип обновления
needs_rebuild=false
changed_files=""

# Получаем список измененных файлов между старым и новым коммитом
if [ "$old_commit" != "$(git rev-parse HEAD)" ]; then
    # Были изменения - сравниваем старый и новый коммит
    changed_files=$(git diff --name-only $old_commit HEAD 2>/dev/null || echo "")
else
    # Изменений не было, но нужно перезапустить - проверяем текущие файлы
    changed_files=$(git diff --name-only HEAD origin/$BRANCH 2>/dev/null || echo "")
fi

if [ ! -z "$changed_files" ]; then
    info "Измененные файлы:"
    echo "$changed_files" | sed 's/^/  - /'
    echo ""

    # Проверяем изменения в критических файлах
    if echo "$changed_files" | grep -E "(Dockerfile|pyproject.toml|poetry.lock|requirements\.txt)" &>/dev/null; then
        warning "Обнаружены изменения в зависимостях или Dockerfile"
        needs_rebuild=true
    fi

    # Проверяем изменения в исходном коде Python
    if echo "$changed_files" | grep -E "\.(py|pyx)$" &>/dev/null; then
        info "Обнаружены изменения в исходном коде Python"
    fi

    # Проверяем изменения в конфигурации nginx
    if echo "$changed_files" | grep -E "nginx/.*\.conf" &>/dev/null; then
        warning "Обнаружены изменения в конфигурации nginx"
        needs_rebuild=true
    fi
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
echo "  2. ✅ Проверка статуса и доступности"
echo ""

# Выполняем обновление
echo ""
info "Начинаем обновление приложения..."

if [ "$needs_rebuild" = true ]; then
    info "Пересборка Docker образов..."
    docker-compose down
    docker-compose build --no-cache
    docker-compose up -d
else
    info "Быстрый перезапуск контейнеров..."
    # Перезапускаем только app контейнер, nginx обычно не требует перезапуска
    docker-compose restart app
    # Если были изменения в nginx конфиге, перезапускаем и nginx
    if [ ! -z "$changed_files" ] && echo "$changed_files" | grep -E "nginx/.*\.conf" &>/dev/null; then
        info "Перезапуск nginx из-за изменений в конфигурации..."
        docker-compose restart nginx
    fi
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

# Определяем URL для проверки (используем определенный домен)
if grep -q "listen 443" nginx/conf.d/rit-utils.conf 2>/dev/null; then
    # HTTPS конфигурация
    check_url="https://$DOMAIN"
else
    # HTTP конфигурация
    check_url="http://localhost"
fi

# Проверка доступности с учетом HTTPS
info "Проверка доступности: $check_url"
if grep -q "listen 443" nginx/conf.d/rit-utils.conf 2>/dev/null; then
    # HTTPS конфигурация - используем -k для игнорирования проблем с сертификатами при проверке
    # Даем больше времени на запуск
    sleep 5

    if curl -s -f -k --max-time 10 "$check_url" >/dev/null 2>&1; then
        success "✅ Приложение доступно: $check_url"
    else
        warning "⚠️  Приложение может быть недоступно по HTTPS"
        info "Проверка через HTTP..."
        http_url="http://$domain"
        if curl -s -f --max-time 10 "$http_url" >/dev/null 2>&1; then
            warning "HTTP работает, но HTTPS может иметь проблемы"
        else
            echo ""
            info "Для диагностики выполните:"
            echo "  docker-compose logs -f app"
            echo "  docker-compose logs -f nginx"
            echo "  docker-compose ps"
        fi
    fi
else
    # HTTP конфигурация
    sleep 5
    if curl -s -f --max-time 10 "$check_url" >/dev/null 2>&1; then
        success "✅ Приложение доступно: $check_url"
    else
        warning "⚠️  Приложение может быть недоступно"
        echo ""
        info "Для диагностики выполните:"
        echo "  docker-compose logs -f app"
        echo "  docker-compose logs -f nginx"
        echo "  docker-compose ps"
    fi
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
echo ""
info "Обновление:"
echo "  🧪 Тестовый сервер: ./update.sh (автоматически определит ветку test)"
echo "  🚀 Продовый сервер: ./update.sh (автоматически определит ветку main)"
echo "  📝 Принудительно:   ./update.sh test  или  ./update.sh main"
echo ""
info "Примечание: Скрипт автоматически определяет окружение по домену в nginx конфиге"
