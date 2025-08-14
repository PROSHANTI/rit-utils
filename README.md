# rit-utils

![Python](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116.1-green)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![2FA](https://img.shields.io/badge/2FA-TOTP-orange)

Веб-приложение на FastAPI для автоматизации рабочих процессов.

## 📝 Описание

Проект предоставляет набор утилит для автоматизации рабочих процессов, включая:
- 🔐 Двухфакторная аутентификация (2FA) через TOTP (Google Authenticator, Authy и др.)
- 📄 Генерацию сертификатов
- 🏥 Обработку форм
- 📧 Отправку email-уведомлений с вложениями
- 🛡️ JWT-авторизацию с refresh токенами

## 🔐 Безопасность

Приложение защищено многоуровневой системой аутентификации:
- **Логин/пароль** - первый уровень защиты
- **2FA TOTP** - второй уровень через приложения аутентификации
- **JWT токены** - защищенные сессии с автоматическим обновлением
- **Secure cookies** - защита от XSS и CSRF атак

## 🚀 Быстрый старт

### Требования
- Python 3.13
- Poetry (для управления зависимостями)

### Установка
1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/your-repo/rit-utils.git
   cd rit-utils
   ```

2. Установите зависимости:
   ```bash
   poetry install
   ```

3. Настройте переменные окружения:
   ```bash
   cp .env.example .env
   # Отредактируйте .env, указав реальные значения
   ```

4. Настройте 2FA:
   - При первом входе система предложит настроить 2FA
   - Отсканируйте QR-код или введите секрет вручную в приложение аутентификации
   - 2FA настраивается один раз и сохраняется навсегда

### Запуск

**Способ 1: Из папки src (рекомендуется)**
```bash
cd src
poetry run python main.py
```

**Способ 2: Как модуль**
```bash
poetry run python -m src.main
```

**Способ 3: Через uvicorn**
```bash
poetry run uvicorn src.main:app --reload
```

Приложение будет доступно по адресу: [http://localhost:8000](http://localhost:8000)

## 🐳 Docker

### Сборка образа
```bash
docker build -t rit-utils .
```

### Запуск контейнера
```bash
docker run -p 8000:8000 --env-file .env rit-utils
```

## ⚙️ Конфигурация

### Переменные окружения (.env)
```bash
# Email настройки
SEND_FROM=your_email@yandex.ru
EMAIL_PASS=your_password
ADDR_TO=recipient@example.com
BCC_TO=bcc@example.com
EMAIL_TEMPLATE=default

# 2FA/TOTP настройки
TOTP_SECRET=JBSWY3DPEHPK3PXP  # Base32 секрет для TOTP

# JWT настройки
JWT_SECRET_KEY=your-super-secret-jwt-key-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Учетные данные админа
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-admin-password

# Дополнительно
USERNAME=admin  # Имя пользователя для 2FA (опционально)
```

### Генерация TOTP секрета
Для генерации нового TOTP секрета:
```bash
python -c "import pyotp; print(pyotp.random_base32())"
```

## 📚 Документация

После запуска приложения доступна автоматически сгенерированная документация API:
- Swagger UI: [/docs](http://localhost:8000/docs)
- ReDoc: [/redoc](http://localhost:8000/redoc)

## 🔐 Процесс аутентификации

1. **Вход** → Введите логин/пароль
2. **Настройка 2FA** (только при первом входе):
   - Отсканируйте QR-код в приложении аутентификации
   - Или введите секрет вручную
   - Настройка сохраняется навсегда
3. **Ввод 2FA кода** → Введите 6-значный код из приложения
4. **Доступ к приложению** → Получение JWT токенов и доступ к функциям

### Поддерживаемые приложения 2FA
- Google Authenticator
- Яндекс.Ключ
- Microsoft Authenticator
- Authy
- 1Password
- Любое приложение с поддержкой TOTP

## 📸 Скриншоты приложения

**Авторизация:**

![Авторизация](screenshots/auth.png)

**Настройка 2FA:**

![Авторизация](screenshots/2fa_setup.png)

**Ввод пароля 2FA:**

![Авторизация](screenshots/2fa.png)

**Главный экран:**

![Главный экран](screenshots/home.png)

**Отправка письма:**

![Отправка письма](screenshots/send_email.png)

**Генерация сертификата:**

![Генерация сертификата](screenshots/gen_cert.png)

**Создание карточек:**

![Создание карточек](screenshots/doctor_form.png)

## 🏗️ Структура проекта
```
rit-utils/
├── src/                       # Исходный код приложения
│   ├── main.py               # Основное FastAPI приложение
│   ├── email_templates.py    # Шаблоны email сообщений
│   ├── auth/                 # Модуль аутентификации
│   │   ├── __init__.py       # Экспорт функций авторизации
│   │   ├── login.py          # JWT авторизация и сессии
│   │   └── two_factor.py     # 2FA TOTP функциональность
│   └── utils/                # Утилиты
│       ├── __init__.py       # Экспорт утилит
│       └── email_handler.py  # Обработка отправки email
├── templates/                # Jinja2 шаблоны
│   ├── css/                  # Стили CSS
│   │   ├── style_home.css    # Стили главной страницы
│   │   ├── style_login.css   # Стили страниц входа
│   │   └── style_utils.css   # Стили утилит
│   ├── login.html            # Страница входа
│   ├── two_factor.html       # Страница ввода 2FA кода
│   ├── setup_2fa.html        # Страница настройки 2FA
│   ├── home.html             # Главная страница
│   ├── send_email.html       # Отправка email
│   ├── gen_rit_cert.html     # Генерация сертификатов
│   ├── doctor_form.html      # Форма врача
│   ├── footer.html           # Подвал страниц
│   └── token-refresh.js      # Обновление JWT токенов
├── screenshots/              # Скриншоты приложения
├── pyproject.toml           # Конфигурация Poetry
├── Dockerfile               # Docker образ
├── .env.example             # Пример переменных окружения
└── README.md                # Документация проекта
```

## 📦 Зависимости

### Основные зависимости:
- **FastAPI** (^0.116.1) - веб-фреймворк
- **Uvicorn** (^0.35.0) - ASGI сервер
- **AuthX** (^1.4.3) - JWT аутентификация
- **PyOTP** (^2.9.0) - TOTP двухфакторная аутентификация
- **QRCode** (^8.0) - генерация QR-кодов для 2FA
- **Python-multipart** (^0.0.20) - обработка форм и файлов
- **Python-dotenv** (^1.1.1) - работа с переменными окружения
- **Jinja2** (^3.1.4) - шаблонизатор HTML

Полный список зависимостей можно найти в [pyproject.toml](./pyproject.toml)

## 🛡️ Безопасность

### Рекомендации по безопасности:
1. **Используйте сильные пароли** для всех учетных записей
2. **Регулярно обновляйте JWT_SECRET_KEY** в production
3. **Настройте HTTPS** в production окружении
4. **Включите файрволл** и ограничьте доступ к порту 8000
5. **Регулярно обновляйте зависимости** через `poetry update`
6. **Не коммитьте .env файл** в репозиторий

### Настройки безопасности:
- JWT токены истекают через 15 минут (настраивается)
- Refresh токены истекают через 7 дней
- 2FA настройка сохраняется навсегда
- Все cookies защищены флагами `httponly`, `secure`, `samesite`


## 📄 Лицензия
Проект распространяется под лицензией Apache 2.0. Подробнее см. [LICENSE](./LICENSE)
