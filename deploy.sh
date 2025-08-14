#!/bin/bash

# Скрипт развертывания RIT-Utils на Ubuntu сервере

set -e

echo "🚀 Начало развертывания RIT-Utils..."

# Проверка требований
check_requirements() {
    echo "📋 Проверка системных требований..."
    
    # Проверка Docker
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker не найден. Установка Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $USER
        rm get-docker.sh
        echo "✅ Docker установлен"
    else
        echo "✅ Docker найден"
    fi

    # Проверка Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        echo "❌ Docker Compose не найден. Установка..."
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        echo "✅ Docker Compose установлен"
    else
        echo "✅ Docker Compose найден"
    fi

    # Проверка git
    if ! command -v git &> /dev/null; then
        echo "❌ Git не найден. Установка..."
        sudo apt update
        sudo apt install -y git
        echo "✅ Git установлен"
    else
        echo "✅ Git найден"
    fi
}

# Настройка проекта
setup_project() {
    echo "📁 Настройка проекта..."
    
    # Создание директорий
    mkdir -p nginx/logs
    mkdir -p nginx/ssl
    
    # Проверка .env файла
    if [ ! -f .env ]; then
        echo "⚠️  Файл .env не найден!"
        if [ -f .env.examples ]; then
            echo "📋 Копирование .env.examples в .env..."
            cp .env.examples .env
            echo "🔧 ВАЖНО: Отредактируйте файл .env с реальными данными!"
            echo "nano .env"
            read -p "Нажмите Enter когда отредактируете .env..."
        else
            echo "❌ Файл .env.examples не найден!"
            exit 1
        fi
    else
        echo "✅ Файл .env найден"
    fi
    
    # Проверка дополнительных файлов
    echo "📋 Проверка дополнительных файлов..."
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
        echo "⚠️  Отсутствуют обязательные файлы:"
        for file in "${missing_files[@]}"; do
            echo "   - $file"
        done
        echo "🔧 Добавьте эти файлы и запустите скрипт снова"
        exit 1
    else
        echo "✅ Все дополнительные файлы найдены"
    fi
}

# Настройка nginx
setup_nginx() {
    echo "🌐 Настройка nginx..."
    
    # Получение IP адреса сервера
    SERVER_IP=$(curl -s ifconfig.me || curl -s ipinfo.io/ip || echo "YOUR_SERVER_IP")
    
    if [ "$SERVER_IP" != "YOUR_SERVER_IP" ]; then
        echo "🌍 Обнаружен IP сервера: $SERVER_IP"
        sed -i "s/YOUR_SERVER_IP/$SERVER_IP/g" nginx/conf.d/rit-utils.conf
        echo "✅ IP адрес настроен в nginx конфигурации"
    else
        echo "⚠️  Не удалось определить IP сервера"
        echo "🔧 Отредактируйте nginx/conf.d/rit-utils.conf вручную"
    fi
}

# Сборка и запуск
deploy() {
    echo "🏗️  Сборка и запуск приложения..."
    
    # Остановка существующих контейнеров
    docker-compose down 2>/dev/null || true
    
    # Сборка образов
    echo "📦 Сборка Docker образов..."
    docker-compose build --no-cache
    
    # Запуск сервисов
    echo "🚀 Запуск сервисов..."
    docker-compose up -d
    
    # Проверка статуса
    sleep 10
    echo "📊 Статус сервисов:"
    docker-compose ps
    
    # Проверка логов
    echo "📋 Последние логи приложения:"
    docker-compose logs --tail=20 app
    
    echo "📋 Последние логи nginx:"
    docker-compose logs --tail=10 nginx
}

# Информация после развертывания
post_deploy_info() {
    echo ""
    echo "🎉 Развертывание завершено!"
    echo ""
    echo "📍 Приложение доступно по адресу:"
    
    SERVER_IP=$(curl -s ifconfig.me || curl -s ipinfo.io/ip || echo "YOUR_SERVER_IP")
    if [ "$SERVER_IP" != "YOUR_SERVER_IP" ]; then
        echo "   http://$SERVER_IP"
    else
        echo "   http://YOUR_SERVER_IP (замените на ваш IP)"
    fi
    
    echo ""
    echo "📋 Полезные команды:"
    echo "   Просмотр логов:      docker-compose logs -f"
    echo "   Остановка:           docker-compose down"
    echo "   Перезапуск:          docker-compose restart"
    echo "   Статус:              docker-compose ps"
    echo ""
    echo "🔐 Для настройки HTTPS запустите:"
    echo "   ./setup-https.sh"
    echo ""
    echo "⚠️  Убедитесь, что порты 80 и 443 открыты в брандмауэре!"
}

# Основная функция
main() {
    check_requirements
    setup_project
    setup_nginx
    deploy
    post_deploy_info
}

# Запуск
main "$@"
