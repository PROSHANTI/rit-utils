#!/bin/bash

# 🚀 Скрипт первичного развертывания RIT-Utils
# Использование: ./deploy.sh
# Предполагается, что HTTPS уже настроен через certbot

set -e

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

# Переменные
PROJECT_DIR="/home/shanti/rit-utils"

# Определение окружения и домена
detect_environment() {
    # Проверяем переменную окружения
    if [ ! -z "$ENV" ]; then
        if [ "$ENV" = "test" ] || [ "$ENV" = "prod" ]; then
            echo "$ENV"
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
            echo "prod"
            return 0
        fi
    fi

    # Fallback: определяем по текущему домену сервера
    HOSTNAME=$(hostname -f 2>/dev/null || echo "")
    if echo "$HOSTNAME" | grep -q "test"; then
        echo "test"
        return 0
    fi

    # По умолчанию - prod
    echo "prod"
}

ENVIRONMENT=$(detect_environment)

if [ "$ENVIRONMENT" = "test" ]; then
    DOMAIN="ritclinic-utils-test.ru"
    BRANCH="test"
    ENV_LABEL="🧪 ТЕСТОВОЕ"
else
    DOMAIN="ritclinic-utils.ru"
    BRANCH="main"
    ENV_LABEL="🚀 ПРОДОВОЕ"
fi

CERTBOT_CERTS="/etc/letsencrypt/live/$DOMAIN"
PROJECT_CERTS="$PROJECT_DIR/nginx/ssl/live/$DOMAIN"

echo "🚀 Первичное развертывание RIT-Utils"
echo "===================================="
info "Окружение: $ENV_LABEL"
info "Домен: $DOMAIN"
info "Ветка Git: $BRANCH"
echo ""

# Проверка что скрипт запущен из правильной директории
if [ ! -f "docker-compose.yml" ] || [ ! -f "src/main.py" ]; then
    error "Запустите скрипт из корневой директории проекта rit-utils"
    exit 1
fi

# Функция проверки команды
check_command() {
    if command -v $1 &> /dev/null; then
        success "$1 найден"
        return 0
    else
        error "$1 не найден. Установите его перед продолжением."
        return 1
    fi
}

# Проверка системных требований
check_requirements() {
    info "Проверка системных требований..."

    if ! check_command docker; then
        exit 1
    fi

    if ! check_command docker-compose; then
        exit 1
    fi

    if ! check_command git; then
        exit 1
    fi

    success "Все системные требования выполнены"
}

# Проверка и настройка SSL сертификатов
setup_ssl_certs() {
    info "Проверка SSL сертификатов..."

    # Проверяем наличие сертификатов в проекте (включая символические ссылки)
    # Используем -L для проверки файла по символической ссылке
    if [ -L "$PROJECT_CERTS/fullchain.pem" ] || [ -f "$PROJECT_CERTS/fullchain.pem" ]; then
        if [ -L "$PROJECT_CERTS/privkey.pem" ] || [ -f "$PROJECT_CERTS/privkey.pem" ]; then
            success "Сертификаты найдены в проекте: $PROJECT_CERTS"

            # Проверяем права доступа (Docker контейнер должен иметь доступ)
            # Проверяем, что файлы читаемы (даже если они принадлежат root)
            if [ ! -r "$PROJECT_CERTS/fullchain.pem" ] || [ ! -r "$PROJECT_CERTS/privkey.pem" ]; then
                warning "Проблемы с правами доступа к сертификатам"
                info "Попытка исправить права доступа..."

                # Проверяем, можем ли мы прочитать через sudo
                if sudo test -r "$PROJECT_CERTS/fullchain.pem" && sudo test -r "$PROJECT_CERTS/privkey.pem"; then
                    # Делаем файлы читаемыми для всех (безопасно, так как они в read-only volume)
                    sudo chmod 644 "$PROJECT_CERTS/fullchain.pem" 2>/dev/null || true
                    sudo chmod 644 "$PROJECT_CERTS/privkey.pem" 2>/dev/null || true
                    # Также проверяем архивную директорию
                    sudo chmod -R 755 "$PROJECT_DIR/nginx/ssl/archive" 2>/dev/null || true
                    success "Права доступа исправлены"
                else
                    warning "Не удалось исправить права доступа, но Docker может иметь доступ через volume"
                fi
            fi

            # Проверяем, что символические ссылки указывают на существующие файлы
            if [ -L "$PROJECT_CERTS/fullchain.pem" ]; then
                target=$(readlink -f "$PROJECT_CERTS/fullchain.pem" 2>/dev/null || readlink "$PROJECT_CERTS/fullchain.pem")
                if [ ! -f "$target" ]; then
                    error "Символическая ссылка fullchain.pem указывает на несуществующий файл: $target"
                    exit 1
                fi
            fi

            if [ -L "$PROJECT_CERTS/privkey.pem" ]; then
                target=$(readlink -f "$PROJECT_CERTS/privkey.pem" 2>/dev/null || readlink "$PROJECT_CERTS/privkey.pem")
                if [ ! -f "$target" ]; then
                    error "Символическая ссылка privkey.pem указывает на несуществующий файл: $target"
                    exit 1
                fi
            fi

            return 0
        fi
    fi

    # Если нет в проекте, проверяем certbot
    if [ -d "$CERTBOT_CERTS" ]; then
        if [ -f "$CERTBOT_CERTS/fullchain.pem" ] && [ -f "$CERTBOT_CERTS/privkey.pem" ]; then
            warning "Сертификаты найдены в certbot, копируем в проект..."

            # Создаем директории
            mkdir -p "$PROJECT_DIR/nginx/ssl/live/$DOMAIN"
            mkdir -p "$PROJECT_DIR/nginx/ssl/archive/$DOMAIN"

            # Копируем сертификаты (может потребоваться sudo)
            if sudo test -r "$CERTBOT_CERTS/fullchain.pem" && sudo test -r "$CERTBOT_CERTS/privkey.pem"; then
                # Копируем файлы в архив
                sudo cp "$CERTBOT_CERTS/fullchain.pem" "$PROJECT_DIR/nginx/ssl/archive/$DOMAIN/fullchain.pem"
                sudo cp "$CERTBOT_CERTS/privkey.pem" "$PROJECT_DIR/nginx/ssl/archive/$DOMAIN/privkey.pem"
                sudo cp "$CERTBOT_CERTS/chain.pem" "$PROJECT_DIR/nginx/ssl/archive/$DOMAIN/chain.pem" 2>/dev/null || true
                sudo cp "$CERTBOT_CERTS/cert.pem" "$PROJECT_DIR/nginx/ssl/archive/$DOMAIN/cert.pem" 2>/dev/null || true

                # Создаем символические ссылки
                cd "$PROJECT_DIR/nginx/ssl/live/$DOMAIN"
                sudo ln -sf "../../archive/$DOMAIN/fullchain.pem" fullchain.pem
                sudo ln -sf "../../archive/$DOMAIN/privkey.pem" privkey.pem
                sudo ln -sf "../../archive/$DOMAIN/chain.pem" chain.pem 2>/dev/null || true
                sudo ln -sf "../../archive/$DOMAIN/cert.pem" cert.pem 2>/dev/null || true

                # Устанавливаем права доступа
                sudo chmod -R 755 "$PROJECT_DIR/nginx/ssl/archive"
                sudo chmod 644 "$PROJECT_DIR/nginx/ssl/archive/$DOMAIN"/*.pem
                sudo chmod 755 "$PROJECT_DIR/nginx/ssl/live/$DOMAIN"

                success "Сертификаты скопированы в проект"
                return 0
            else
                error "Не удалось прочитать сертификаты из $CERTBOT_CERTS"
                error "Проверьте права доступа или скопируйте сертификаты вручную"
                exit 1
            fi
        fi
    fi

    error "SSL сертификаты не найдены!"
    error "Ожидаемые пути:"
    echo "  - В проекте: $PROJECT_CERTS/fullchain.pem"
    echo "  - В certbot: $CERTBOT_CERTS/fullchain.pem"
    echo ""
    warning "Если сертификаты в другом месте, скопируйте их вручную:"
    echo "  mkdir -p $PROJECT_DIR/nginx/ssl/live/$DOMAIN"
    echo "  cp <путь_к_fullchain.pem> $PROJECT_CERTS/fullchain.pem"
    echo "  cp <путь_к_privkey.pem> $PROJECT_CERTS/privkey.pem"
    exit 1
}

# Проверка и переключение на нужную ветку Git
check_git_branch() {
    info "Проверка Git репозитория..."

    if ! git status &>/dev/null; then
        error "Это не Git репозиторий или Git недоступен"
        exit 1
    fi

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

    # Проверяем текущую ветку
    current_branch=$(git branch --show-current)
    if [ "$current_branch" != "$BRANCH" ]; then
        warning "Текущая ветка: $current_branch, переключаемся на: $BRANCH"
        git checkout $BRANCH
        success "Переключились на ветку $BRANCH"
    else
        info "Уже на ветке $BRANCH"
    fi

    # Обновляем до последней версии
    info "Обновление до последней версии ветки $BRANCH..."
    git pull origin $BRANCH

    success "Git репозиторий готов"
}

# Проверка необходимых файлов
check_project_files() {
    info "Проверка файлов проекта..."

    if [ ! -f ".env" ]; then
        error "Файл .env не найден!"
        warning "Создайте файл .env с необходимыми переменными окружения"
        exit 1
    fi
    success "Файл .env найден"

    # Проверка директорий
    mkdir -p nginx/logs nginx/ssl nginx/conf.d certbot-webroot
    success "Директории созданы/проверены"

    # Проверка конфигурации nginx
    if [ ! -f "nginx/conf.d/rit-utils.conf" ]; then
        error "Файл nginx/conf.d/rit-utils.conf не найден!"
        exit 1
    fi
    success "Конфигурация nginx найдена"

    # Проверка что директория ssl существует и доступна
    if [ ! -d "nginx/ssl" ]; then
        error "Директория nginx/ssl не найдена!"
        exit 1
    fi

    # Убеждаемся, что директория ssl имеет правильные права для Docker
    # Docker контейнер должен иметь возможность читать файлы
    # Проверяем через sudo, так как файлы могут принадлежать root
    if [ -d "nginx/ssl/archive" ]; then
        # Делаем директорию archive читаемой (безопасно, так как volume read-only)
        # Проверяем через sudo, если нужно
        if sudo test -d nginx/ssl/archive 2>/dev/null; then
            sudo chmod -R 755 nginx/ssl/archive 2>/dev/null || true
            sudo find nginx/ssl/archive -type f -name "*.pem" -exec chmod 644 {} \; 2>/dev/null || true
        else
            chmod -R 755 nginx/ssl/archive 2>/dev/null || true
            find nginx/ssl/archive -type f -name "*.pem" -exec chmod 644 {} \; 2>/dev/null || true
        fi
    fi

    if [ -d "nginx/ssl/live" ]; then
        if sudo test -d nginx/ssl/live 2>/dev/null; then
            sudo chmod -R 755 nginx/ssl/live 2>/dev/null || true
        else
            chmod -R 755 nginx/ssl/live 2>/dev/null || true
        fi
    fi

    info "Права доступа к SSL директории проверены"
}

# Остановка системного nginx если он запущен
stop_system_nginx() {
    info "Проверка системного nginx..."

    if systemctl is-active --quiet nginx 2>/dev/null; then
        warning "Системный nginx запущен, останавливаем..."
        sudo systemctl stop nginx 2>/dev/null || true
        success "Системный nginx остановлен"
    else
        info "Системный nginx не запущен"
    fi
}

# Развертывание приложения
deploy_app() {
    info "Развертывание приложения..."

    # Остановка существующих контейнеров
    info "Остановка существующих контейнеров..."
    docker-compose down 2>/dev/null || true

    # Сборка образов
    info "Сборка Docker образов..."
    docker-compose build --no-cache

    # Запуск сервисов
    info "Запуск сервисов..."
    docker-compose up -d

    # Ожидание запуска
    info "Ожидание запуска сервисов..."
    sleep 10

    # Проверка статуса
    info "Проверка статуса сервисов..."
    docker-compose ps

    # Проверка логов
    info "Проверка логов приложения:"
    docker-compose logs --tail=20 app

    success "Приложение развернуто"
}

# Проверка доступности
check_availability() {
    info "Проверка доступности приложения..."

    # Ждем еще немного для полного запуска
    sleep 5

    if curl -s -f -k "https://$DOMAIN" >/dev/null 2>&1; then
        success "Приложение доступно по адресу: https://$DOMAIN"
    elif curl -s -f "http://$DOMAIN" >/dev/null 2>&1; then
        warning "Приложение доступно по HTTP, но HTTPS не работает"
        warning "Проверьте конфигурацию SSL сертификатов"
    else
        warning "Приложение может быть недоступно"
        info "Проверьте логи: docker-compose logs -f"
    fi
}

# Финальная информация
show_final_info() {
    echo ""
    success "🎉 Развертывание завершено!"
    echo ""

    info "Приложение доступно по адресу:"
    echo "   🌐 HTTPS: https://$DOMAIN"
    echo ""

    info "Управление приложением:"
    echo "   📊 Статус:          docker-compose ps"
    echo "   📋 Логи:            docker-compose logs -f"
    echo "   🔄 Перезапуск:      docker-compose restart"
    echo "   ⏹️  Остановка:       docker-compose down"
    echo "   🔧 Обновление:      ./update.sh"
    echo ""

    info "Для обновления приложения используйте:"
    echo "   ./update.sh"
    echo ""
}

# Основная функция
main() {
    check_requirements
    check_git_branch
    check_project_files
    setup_ssl_certs
    stop_system_nginx
    deploy_app
    check_availability
    show_final_info
}

# Запуск
main "$@"
