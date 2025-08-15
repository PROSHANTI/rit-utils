"""
Конфигурация pytest для тестов rit-utils
"""
import os
import pytest
import tempfile
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import Request

# Устанавливаем тестовые переменные окружения сразу при импорте
os.environ.update({
    'JWT_SECRET_KEY': 'test_secret_key_for_jwt_tokens_12345',
    'LOGIN': 'test_admin',
    'PASSWORD': 'test_password',
    'TOTP_SECRET': 'TESTTOTP32CHARSSECRETFORTEST123456',
    'SEND_FROM': 'test@example.com',
    'EMAIL_PASS': 'test_password',
    'ADDR_TO': 'recipient@example.com',
    'BCC_TO': 'bcc@example.com'
})


@pytest.fixture(scope="session")
def test_env():
    """Настройка тестового окружения"""
    # Переменные уже установлены при импорте модуля
    yield


@pytest.fixture
def app(test_env):
    """Создание тестового FastAPI приложения"""
    # Импортируем приложение после установки переменных окружения
    from src.main import app
    return app


@pytest.fixture
def client(app):
    """Тестовый клиент FastAPI"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_request():
    """Мок объекта Request для FastAPI"""
    request = MagicMock(spec=Request)
    request.cookies = {}
    request.headers = {}
    return request


@pytest.fixture
def temp_file():
    """Временный файл для тестов"""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        yield tmp.name
    try:
        os.unlink(tmp.name)
    except FileNotFoundError:
        pass


@pytest.fixture
def mock_smtp():
    """Мок для SMTP сервера"""
    with patch('smtplib.SMTP_SSL') as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        yield mock_server


@pytest.fixture
def mock_subprocess():
    """Мок для subprocess (LibreOffice)"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""
        yield mock_run


@pytest.fixture
def mock_pptx():
    """Мок для python-pptx"""
    with patch('pptx.Presentation') as mock_prs:
        mock_presentation = MagicMock()
        mock_slide = MagicMock()
        mock_shape = MagicMock()
        mock_text_frame = MagicMock()
        mock_paragraph = MagicMock()
        mock_run = MagicMock()
        
        # Настройка цепочки моков
        mock_presentation.slides = [mock_slide]
        mock_slide.shapes = [mock_shape]
        mock_shape.has_text_frame = True
        mock_shape.text_frame = mock_text_frame
        mock_text_frame.paragraphs = [mock_paragraph]
        mock_paragraph.runs = [mock_run]
        mock_run.text = "placeholder_text"
        
        mock_prs.return_value = mock_presentation
        yield mock_presentation


@pytest.fixture
def mock_file_upload():
    """Мок для загружаемого файла"""
    mock_file = MagicMock()
    mock_file.file.read.return_value = b"test file content"
    mock_file.filename = "test.xlsx"
    return mock_file


@pytest.fixture(autouse=True)
def reset_revoked_tokens():
    """Очистка отозванных токенов перед каждым тестом"""
    from src.auth.login import REVOKED_TOKENS
    REVOKED_TOKENS.clear()
    yield
    REVOKED_TOKENS.clear()


@pytest.fixture(autouse=True) 
def reset_user_secrets():
    """Очистка пользовательских секретов перед каждым тестом"""
    from src.auth.two_factor import USER_SECRETS
    USER_SECRETS.clear()
    yield
    USER_SECRETS.clear()


# Настройка pytest-asyncio
pytest_plugins = ('pytest_asyncio',)
