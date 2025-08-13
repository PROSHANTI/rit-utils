# rit-utils

![Python](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116.1-green)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)

Веб-приложение на FastAPI + Jinja для автоматизации рабочих процессов

## 📝 Описание

Проект предоставляет набор утилит для автоматизации рабочих процессов, включая:
- Генерацию сертификатов
- Обработку форм (например, формы врача)
- Отправку email-уведомлений

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
   # Файл .env уже добавлен в .gitignore
   ```

## 🐳 Docker

### Сборка образа
```bash
docker build -t rit-utils .
```

### Запуск контейнера
```bash
docker run -p 8000:8000 --env-file .env rit-utils
```

Приложение будет доступно по адресу: [http://localhost:8000](http://localhost:8000)

### Запуск
```bash
poetry run uvicorn backend.main:app --reload
```

Приложение будет доступно по адресу: [http://localhost:8000](http://localhost:8000)

## 📚 Документация

После запуска приложения доступна автоматически сгенерированная документация API:
- Swagger UI: [/docs](http://localhost:8000/docs)
- ReDoc: [/redoc](http://localhost:8000/redoc)

### Скриншоты приложения

1. Авторизация:
![Авторизация](https://github.com/PROSHANTI/rit-utils/blob/63a9b00d33c991f64075a2adc291ae2f92ee2568/screenshots/auth.png)

2. Главный экран:
![Главный экран](https://github.com/PROSHANTI/rit-utils/blob/63a9b00d33c991f64075a2adc291ae2f92ee2568/screenshots/home.png)

3. Отправка письма:
![Отправка письма](https://github.com/PROSHANTI/rit-utils/blob/63a9b00d33c991f64075a2adc291ae2f92ee2568/screenshots/send_email.png)

4. Генерация сертификата:
![Генерация сертификата](https://github.com/PROSHANTI/rit-utils/blob/63a9b00d33c991f64075a2adc291ae2f92ee2568/screenshots/gen_cert.png)

5. Создание карточек:
![Создание карточек](https://github.com/PROSHANTI/rit-utils/blob/63a9b00d33c991f64075a2adc291ae2f92ee2568/screenshots/doctor_form.png)

## 🏗️ Структура проекта
```
rit-utils/
├── backend/               # Backend на FastAPI
│   ├── main.py            # Основное приложение
│   ├── schema.py          # Схемы данных
│   └── email_templates.py # Шаблоны email сообщений
├── frontend/              # Frontend шаблоны
│   └── templates/         # Jinja2 шаблоны
│       ├── css/           # Стили
│       └── *.html         # HTML страницы
├── pyproject.toml         # Конфигурация Poetry
└── README.md              # Этот файл
```

## 📦 Зависимости
Основные зависимости:
- FastAPI (^0.116.1)
- Uvicorn (^0.35.0)
- Python-multipart (^0.0.20)
- Python-dotenv (^1.1.1)
- AuthX (^1.4.3)

Полный список зависимостей можно найти в [pyproject.toml](./pyproject.toml)

## ⚙️ Конфигурация

### Переменные окружения
Файл `.env.example` содержит шаблонные значения переменных окружения. Для работы приложения:
1. Создайте `.env` на основе примера
2. Замените значения на реальные
3. Не коммитьте `.env` в репозиторий (файл уже в .gitignore)

### Шаблоны писем
Файл `email_templates.py` содержит шаблоны email сообщений. Основные особенности:
- Хранит текст писем с правильным форматированием
- Позволяет легко редактировать шаблоны
- Использует Python-строки для удобства работы

## 📄 Лицензия
Проект распространяется под лицензией Apache 2.0. Подробнее см. [LICENSE](./LICENSE)
