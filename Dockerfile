# Базовый образ Python 3.13
FROM python:3.13-slim

# Установка Poetry
RUN pip install poetry

# Создание и настройка рабочей директории
WORKDIR /app
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Копирование файлов зависимостей
COPY pyproject.toml poetry.lock ./

# Установка зависимостей
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# Копирование исходного кода
COPY . .

# Порт для FastAPI
EXPOSE 8000

# Команда запуска
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]