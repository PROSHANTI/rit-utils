"""
Тесты для модуля аутентификации login.py
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi import Request, Form
from fastapi.responses import RedirectResponse

from src.auth.login import (
    login_handler,
    logout_handler,
    refresh_token_handler,
    check_auth_status,
    REVOKED_TOKENS
)


class TestLoginHandler:
    """Тесты для обработчика входа"""

    def test_login_success(self, mock_request):
        """Тест успешного входа"""
        result = login_handler(mock_request, "test_admin", "test_password")

        # Проверяем, что результат - это редирект на главную страницу
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/home"
        assert result.status_code == 303

    def test_login_invalid_credentials(self, mock_request):
        """Тест входа с неверными учетными данными"""
        result = login_handler(mock_request, "wrong_user", "wrong_pass")

        assert hasattr(result, 'status_code')
        assert result.status_code == 401

    def test_login_invalid_username(self, mock_request):
        """Тест входа с неверным именем пользователя"""
        result = login_handler(mock_request, "wrong_user", "test_password")

        assert hasattr(result, 'status_code')
        assert result.status_code == 401

    def test_login_invalid_password(self, mock_request):
        """Тест входа с неверным паролем"""
        result = login_handler(mock_request, "test_admin", "wrong_pass")

        assert hasattr(result, 'status_code')
        assert result.status_code == 401


class TestLogoutHandler:
    """Тесты для обработчика выхода"""

    def test_logout_with_refresh_token(self, mock_request):
        """Тест выхода с refresh токеном"""
        test_token = "test_refresh_token"
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        result = logout_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303
        assert test_token in REVOKED_TOKENS

    def test_logout_without_refresh_token(self, mock_request):
        """Тест выхода без refresh токена"""
        mock_request.cookies = {}

        result = logout_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303


class TestRefreshTokenHandler:
    """Тесты для обработчика обновления токена"""

    def test_refresh_token_missing(self, mock_request):
        """Тест обновления токена без токена"""
        mock_request.cookies = {}

        result = refresh_token_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303

    def test_refresh_token_revoked(self, mock_request):
        """Тест обновления отозванного токена"""
        test_token = "revoked_token"
        REVOKED_TOKENS.add(test_token)
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        result = refresh_token_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303

    @patch('src.auth.login.security')
    def test_refresh_token_success(self, mock_security, mock_request):
        """Тест успешного обновления токена"""
        test_token = "valid_refresh_token"
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        # Настройка мока для декодирования токена
        mock_payload = MagicMock()
        mock_payload.sub = "1"
        mock_payload.jti = "test_jti"
        mock_security._decode_token.return_value = mock_payload
        mock_security.create_access_token.return_value = "new_access_token"

        result = refresh_token_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/home"
        assert result.status_code == 303
        mock_security.create_access_token.assert_called_once()

    @patch('src.auth.login.security')
    def test_refresh_token_invalid(self, mock_security, mock_request):
        """Тест обновления невалидного токена"""
        test_token = "invalid_token"
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        # Мок для исключения при декодировании
        mock_security._decode_token.side_effect = Exception("Invalid token")

        result = refresh_token_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303


class TestCheckAuthStatus:
    """Тесты для проверки статуса авторизации"""

    def test_check_auth_with_token(self, mock_request):
        """Тест проверки авторизации с токеном"""
        mock_request.cookies = {"JWT_ACCESS_TOKEN_COOKIE": "valid_token"}

        result = check_auth_status(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/home"
        assert result.status_code == 303

    def test_check_auth_without_token(self, mock_request):
        """Тест проверки авторизации без токена"""
        mock_request.cookies = {}

        result = check_auth_status(mock_request)

        # Должен вернуть шаблон страницы входа
        assert hasattr(result, 'status_code')


