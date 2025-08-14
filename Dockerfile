# Базовый образ Python 3.13
FROM python:3.13-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    libreoffice \
    fonts-liberation \
    fonts-dejavu-core \
    locales \
    && rm -rf /var/lib/apt/lists/*

# Генерация локалей
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && \
    sed -i '/ru_RU.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen

# Установка переменных окружения для локали
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

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