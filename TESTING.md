# Тестирование RIT-Utils

## 📋 Обзор

Для проекта RIT-Utils была создана комплексная система тестирования с использованием **pytest**. Тесты покрывают все основные компоненты приложения и обеспечивают высокую надежность кода.

## 🗂️ Структура тестов

```
tests/
├── __init__.py
├── conftest.py                     # Конфигурация pytest и фикстуры
├── test_auth_cookie_utils.py       # Тесты утилит для cookies
├── test_auth_login.py              # Тесты аутентификации
├── test_auth_two_factor.py         # Тесты 2FA
├── test_config.py                  # Тесты конфигурации
├── test_integration_endpoints.py   # Интеграционные тесты API
├── test_main.py                    # Тесты основного модуля
├── test_utils_doctor_form.py       # Тесты генерации форм врачей
├── test_utils_email.py             # Тесты отправки email
├── test_utils_gen_cert.py          # Тесты генерации сертификатов
└── README.md                       # Документация по тестам
```

## ✅ Покрытие тестами

### Модули аутентификации
- ✅ **Логин/логаут** (`src/auth/login.py`) - 17 тестов
- ✅ **Двухфакторная аутентификация** (`src/auth/two_factor.py`) - 18 тестов  
- ✅ **Cookie утилиты** (`src/auth/cookie_utils.py`) - 4 теста

### Утилиты
- ✅ **Отправка email** (`src/utils/send_email/`) - 8 тестов
- ✅ **Генерация сертификатов** (`src/utils/gen_cert/`) - 13 тестов
- ✅ **Генерация форм врачей** (`src/utils/doctor_form/`) - 11 тестов

### Основное приложение
- ✅ **FastAPI endpoints** (`src/main.py`) - 25 интеграционных тестов
- ✅ **Конфигурация** (`src/config.py`) - 2 теста
- ✅ **Основной модуль** - 10 тестов

**Итого: 106 тестов**

## 🚀 Запуск тестов

### Использование скрипта (рекомендуется)
```bash
# Все тесты
./run_tests.sh

# Только тесты аутентификации
./run_tests.sh auth

# Только утилиты
./run_tests.sh utils

# С анализом покрытия
./run_tests.sh coverage

# Быстрый запуск
./run_tests.sh fast

# Справка
./run_tests.sh help
```

### Прямое использование pytest
```bash
# Все тесты
poetry run pytest

# Конкретный файл
poetry run pytest tests/test_auth_login.py

# Конкретный тест
poetry run pytest tests/test_auth_login.py::TestLoginHandler::test_login_success_with_2fa_configured

# С подробным выводом
poetry run pytest -v

# Только сбор тестов (без запуска)
poetry run pytest --collect-only
```

## 🔧 Особенности реализации

### Моки и изоляция
- **SMTP сервер** - все email отправки замокированы
- **LibreOffice** - конвертация PPTX в PDF замокирована
- **Файловая система** - работа с файлами изолирована
- **Временные переменные** - тестовые значения для всех секретных данных

### Фикстуры
- `test_env` - настройка тестового окружения
- `app` - тестовое FastAPI приложение
- `client` - HTTP клиент для тестирования
- `mock_request` - мок объекта Request
- `mock_smtp` - мок SMTP сервера
- `mock_pptx` - мок для python-pptx

### Автоочистка
- Автоматическая очистка отозванных токенов между тестами
- Очистка пользовательских секретов 2FA
- Удаление временных файлов

## ⚙️ Конфигурация

### pytest.ini
```ini
[tool:pytest]
testpaths = tests
addopts = -v --tb=short --strict-markers --disable-warnings --color=yes
markers =
    slow: marks tests as slow
    integration: marks tests as integration tests  
    unit: marks tests as unit tests
```

### Тестовые переменные окружения
- `JWT_SECRET_KEY` = `test_secret_key_for_jwt_tokens_12345`
- `LOGIN` = `test_admin`
- `PASSWORD` = `test_password`
- `TOTP_SECRET` = `TESTTOTP32CHARSSECRETFORTEST123456`
- `SEND_FROM` = `test@example.com`
- `EMAIL_PASS` = `test_password`
- `ADDR_TO` = `recipient@example.com`
- `BCC_TO` = `bcc@example.com`

## 🎯 Типы тестов

### Unit тесты
- Тестируют отдельные функции и методы
- Полная изоляция от внешних зависимостей
- Быстрое выполнение

### Интеграционные тесты  
- Тестируют взаимодействие компонентов
- Проверка HTTP endpoints
- Тестирование полного flow аутентификации

### Тесты обработки ошибок
- Проверка валидации входных данных
- Обработка сетевых ошибок
- Отсутствие файлов шаблонов

## 📊 Преимущества

1. **Без запуска сервера** - тесты работают без поднятия веб-приложения
2. **Быстрое выполнение** - все внешние зависимости замокированы
3. **Полная изоляция** - тесты не влияют друг на друга
4. **Высокое покрытие** - проверены все критические пути
5. **Простота запуска** - один скрипт для всех сценариев

## 🔍 Анализ покрытия

Для анализа покрытия кода:
```bash
# Установка coverage (опционально)
poetry add pytest-cov --group test

# Запуск с покрытием
./run_tests.sh coverage

# Результат будет в htmlcov/index.html
```

## 📝 Рекомендации

1. **Запускайте тесты** перед каждым коммитом
2. **Добавляйте тесты** для новой функциональности
3. **Поддерживайте актуальность** тестовых данных
4. **Используйте понятные имена** для тестов
5. **Группируйте связанные тесты** в классы

---

✨ Тесты готовы к использованию! Они обеспечивают надежность и стабильность вашего приложения.
