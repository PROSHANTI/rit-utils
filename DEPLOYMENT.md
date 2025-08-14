# 🚀 Руководство по развертыванию на Ubuntu сервере

## 📋 Требования

- **Ubuntu 22.04 LTS** (рекомендуется)
- **2 GB RAM** (минимум)
- **20 GB** свободного места на диске
- **Публичный IP адрес**
- **Открытые порты**: 80 (HTTP), 443 (HTTPS), 22 (SSH)

## 🛠️ Автоматическое развертывание

### 1. Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Клонирование репозитория
git clone <your-repo-url>
cd rit-utils
```

### 2. Настройка проекта

```bash
# Копирование конфигурации
cp .env.examples .env

# Редактирование переменных окружения
nano .env
```

**Обязательно настройте:**
- `LOGIN` и `PASSWORD` - учетные данные для входа
- `SEND_FROM` и `EMAIL_PASS` - настройки почты  
- `JWT_SECRET_KEY` - секретный ключ для JWT
- `TOTP_SECRET` - секрет для 2FA (сгенерируйте новый)

### 3. Добавление дополнительных файлов

Добавьте требуемые файлы в соответствующие директории:
- `src/utils/doctor_form/Бланк Врача.pptx`
- `src/utils/doctor_form/Бланк врача на печать.pptx`
- `src/utils/gen_cert/Сертификат_шаблон.pptx`
- `src/utils/send_email/email_templates.py`

### 4. Запуск развертывания

```bash
# Запуск автоматического развертывания
./deploy.sh
```

Скрипт автоматически:
- Установит Docker и Docker Compose
- Настроит nginx конфигурацию
- Соберет и запустит приложение
- Настроит reverse proxy

### 5. Настройка HTTPS (опционально)

Если у вас есть домен:

```bash
# Настройка HTTPS с Let's Encrypt
./setup-https.sh
```

## ⚙️ Ручное развертывание

### 1. Установка Docker

```bash
# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перезагрузка или выход/вход для применения группы docker
```

### 2. Настройка nginx

```bash
# Редактирование конфигурации nginx
nano nginx/conf.d/rit-utils.conf

# Замените YOUR_SERVER_IP на ваш публичный IP
```

### 3. Сборка и запуск

```bash
# Сборка образов
docker-compose build

# Запуск сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps
```

## 📊 Управление приложением

### Основные команды

```bash
# Просмотр логов
docker-compose logs -f

# Просмотр логов конкретного сервиса
docker-compose logs -f app
docker-compose logs -f nginx

# Перезапуск сервисов
docker-compose restart

# Остановка
docker-compose down

# Обновление приложения
git pull
docker-compose build --no-cache
docker-compose up -d
```

### Мониторинг

```bash
# Статус контейнеров
docker-compose ps

# Использование ресурсов
docker stats

# Размер образов
docker images

# Логи nginx
tail -f nginx/logs/access.log
tail -f nginx/logs/error.log
```

## 🔒 Безопасность

### Брандмауэр (UFW)

```bash
# Базовая настройка UFW
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

### Обновления

```bash
# Автоматические обновления безопасности
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### SSL/TLS

- Используйте HTTPS в продакшене
- Настройте автообновление SSL сертификатов
- Проверяйте сертификаты регулярно

## 🐛 Устранение неполадок

### Приложение не запускается

```bash
# Проверка логов
docker-compose logs app

# Проверка переменных окружения
docker-compose exec app env | grep -E "(LOGIN|TOTP_SECRET|JWT_SECRET_KEY)"

# Проверка сети
docker network ls
docker network inspect rit-utils_rit-utils-network
```

### Nginx ошибки

```bash
# Проверка конфигурации nginx
docker-compose exec nginx nginx -t

# Перезагрузка nginx
docker-compose restart nginx

# Проверка портов
sudo netstat -tlnp | grep -E "(80|443)"
```

### Проблемы с SSL

```bash
# Проверка сертификата
openssl x509 -in nginx/ssl/live/yourdomain.com/cert.pem -text -noout

# Проверка срока действия
echo | openssl s_client -servername yourdomain.com -connect yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates

# Принудительное обновление
./renew-cert.sh
```

### Очистка системы

```bash
# Очистка неиспользуемых контейнеров и образов
docker system prune -a

# Очистка логов Docker
sudo truncate -s 0 /var/lib/docker/containers/*/*-json.log
```

## 📈 Производительность

### Оптимизация

```bash
# Увеличение лимитов файлов
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# Оптимизация сети
echo "net.core.somaxconn = 65536" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Мониторинг ресурсов

```bash
# Использование диска
df -h
du -sh /var/lib/docker

# Память
free -h
docker stats --no-stream

# Сеть
sudo iftop
sudo nethogs
```

## 🔄 Резервное копирование

### Создание резервной копии

```bash
# Скрипт резервного копирования
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/rit-utils"

mkdir -p $BACKUP_DIR

# Остановка сервисов
docker-compose down

# Копирование данных
tar -czf $BACKUP_DIR/rit-utils-$DATE.tar.gz \
    .env \
    src/utils/ \
    nginx/ \
    docker-compose.yml

# Запуск сервисов
docker-compose up -d

echo "Резервная копия создана: $BACKUP_DIR/rit-utils-$DATE.tar.gz"
```

### Восстановление

```bash
# Остановка сервисов
docker-compose down

# Восстановление из архива
tar -xzf /backup/rit-utils/rit-utils-YYYYMMDD_HHMMSS.tar.gz

# Запуск сервисов
docker-compose up -d
```
