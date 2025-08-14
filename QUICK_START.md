# 🚀 Быстрый старт на сервере

## 📋 Подготовка сервера

### 1. Подключение к серверу
```bash
ssh root@ваш-ip-адрес
# или
ssh user@ваш-ip-адрес
```

### 2. Обновление системы
```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Установка Git (если нет)
```bash
sudo apt install -y git
```

## 🚀 Развертывание приложения

### 1. Клонирование проекта
```bash
# Замените на ваш репозиторий
git clone https://github.com/username/rit-utils.git
cd rit-utils
```

### 2. Настройка переменных окружения
```bash
# Копирование шаблона
cp .env.examples .env

# Редактирование (обязательно!)
nano .env
```

**⚠️ Обязательно настройте:**
- `LOGIN` и `PASSWORD` - для входа в приложение
- `SEND_FROM` и `EMAIL_PASS` - для отправки email
- `JWT_SECRET_KEY` - секретный ключ (сгенерируйте новый)
- `TOTP_SECRET` - для 2FA (сгенерируйте новый)

### 3. Добавление дополнительных файлов

Загрузите на сервер файлы:
```bash
# Создание директорий
mkdir -p src/utils/doctor_form/
mkdir -p src/utils/gen_cert/
mkdir -p src/utils/send_email/

# Загрузите файлы:
# src/utils/doctor_form/Бланк Врача.pptx
# src/utils/doctor_form/Бланк врача на печать.pptx  
# src/utils/gen_cert/Сертификат_шаблон.pptx
# src/utils/send_email/email_templates.py
```

### 4. Автоматическое развертывание
```bash
# Запуск скрипта развертывания
./deploy.sh
```

**Скрипт автоматически:**
- Установит Docker и Docker Compose
- Настроит nginx
- Соберет и запустит приложение
- Выведет IP адрес для доступа

### 5. Проверка работы
```bash
# Статус сервисов
docker-compose ps

# Логи приложения
docker-compose logs -f app

# Логи nginx
docker-compose logs -f nginx
```

**✅ Готово!** Приложение доступно по `http://ваш-ip-адрес`

---

## 🌐 Настройка домена (опционально)

### 1. Покупка домена на reg.ru

1. Идете на reg.ru
2. Покупаете домен (например, `myapp.ru`)
3. В панели управления доменом настраиваете DNS:

```
Тип    Имя    Значение
A      @      ваш-ip-адрес
A      www    ваш-ip-адрес
```

### 2. Ожидание распространения DNS

```bash
# Проверка DNS (может занять до 24 часов)
nslookup myapp.ru
ping myapp.ru
```

### 3. Обновление nginx конфигурации

```bash
# Редактирование конфигурации
nano nginx/conf.d/rit-utils.conf

# Замените строку:
# server_name YOUR_SERVER_IP;
# на:
# server_name myapp.ru www.myapp.ru;

# Перезапуск nginx
docker-compose restart nginx
```

**✅ Готово!** Приложение доступно по `http://myapp.ru`

---

## 🔒 Настройка HTTPS

### 1. Автоматическая настройка

```bash
# Запуск скрипта HTTPS
./setup-https.sh

# Введите ваш домен когда скрипт спросит
# Например: myapp.ru
```

### 2. Проверка SSL

```bash
# Проверка сертификата
curl -I https://myapp.ru

# Проверка в браузере
# Откройте https://myapp.ru
```

**✅ Готово!** Приложение доступно по `https://myapp.ru`

---

## 🔧 Управление приложением

### Основные команды
```bash
# Просмотр статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f

# Перезапуск
docker-compose restart

# Остановка
docker-compose down

# Запуск
docker-compose up -d
```

### Обновление приложения
```bash
# Получение обновлений
git pull

# Пересборка и перезапуск
docker-compose build --no-cache
docker-compose up -d
```

### Мониторинг
```bash
# Использование ресурсов
docker stats

# Свободное место
df -h

# Логи nginx
tail -f nginx/logs/access.log
tail -f nginx/logs/error.log
```

---

## 🐛 Устранение проблем

### Приложение не запускается
```bash
# Проверка логов
docker-compose logs app

# Проверка .env файла
cat .env | grep -v "^#"

# Перезапуск всего
docker-compose down
docker-compose up -d
```

### Nginx ошибки
```bash
# Проверка конфигурации
docker-compose exec nginx nginx -t

# Просмотр ошибок nginx
docker-compose logs nginx
```

### Проблемы с доменом
```bash
# Проверка DNS
nslookup ваш-домен.ru

# Проверка доступности
curl -I http://ваш-домен.ru
```

### SSL проблемы
```bash
# Проверка сертификата
openssl s_client -servername ваш-домен.ru -connect ваш-домен.ru:443

# Принудительное обновление
./renew-cert.sh
```

---

## 📞 Контакты для поддержки

При возникновении проблем:
1. Проверьте логи: `docker-compose logs -f`
2. Убедитесь, что все файлы загружены
3. Проверьте настройки .env файла
4. Убедитесь, что порты 80 и 443 открыты в брандмауэре
