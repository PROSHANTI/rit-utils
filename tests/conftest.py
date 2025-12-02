import os
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import Request

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

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

# Mock для отсутствующего модуля email_templates
# Создаем фиктивный модуль до импорта email_handler
if 'src.utils.send_email.email_templates' not in sys.modules:
    from types import ModuleType

    def get_email_template():
        """Mock function for email template"""
        return (
            'Добрый вечер!\n'
            '\n'
            '{body_cashless}'
            '{body_card}'
            '{body_qr}'
            '{body_cash}'
            '\n'
            'С уважением'
        )

    email_templates_module = ModuleType('src.utils.send_email.email_templates')
    setattr(email_templates_module, 'get_email_template', get_email_template)
    sys.modules['src.utils.send_email.email_templates'] = email_templates_module


@pytest.fixture(scope="session")
def test_env():
    """Настройка тестового окружения"""
    yield


@pytest.fixture
def app(test_env):
    """Создание тестового FastAPI приложения"""
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

pytest_plugins = ('pytest_asyncio',)
