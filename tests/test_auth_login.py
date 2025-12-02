"""
Tests for login.py authentication module
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Form, Request
from fastapi.responses import RedirectResponse

from src.auth.login import (
    REVOKED_TOKENS,
    check_auth_status,
    login_handler,
    logout_handler,
    refresh_token_handler,
)


class TestLoginHandler:
    """Tests for login handler"""

    def test_login_success(self, mock_request):
        """Test successful login"""
        result = login_handler(mock_request, "test_admin", "test_password")

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/home"
        assert result.status_code == 303

    def test_login_invalid_credentials(self, mock_request):
        """Test login with invalid credentials"""
        result = login_handler(mock_request, "wrong_user", "wrong_pass")

        assert hasattr(result, 'status_code')
        assert result.status_code == 401

    def test_login_invalid_username(self, mock_request):
        """Test login with invalid username"""
        result = login_handler(mock_request, "wrong_user", "test_password")

        assert hasattr(result, 'status_code')
        assert result.status_code == 401

    def test_login_invalid_password(self, mock_request):
        """Test login with invalid password"""
        result = login_handler(mock_request, "test_admin", "wrong_pass")

        assert hasattr(result, 'status_code')
        assert result.status_code == 401


class TestLogoutHandler:
    """Tests for logout handler"""

    def test_logout_with_refresh_token(self, mock_request):
        """Test logout with refresh token"""
        test_token = "test_refresh_token"
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        result = logout_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303
        assert test_token in REVOKED_TOKENS

    def test_logout_without_refresh_token(self, mock_request):
        """Test logout without refresh token"""
        mock_request.cookies = {}

        result = logout_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303


class TestRefreshTokenHandler:
    """Tests for token refresh handler"""

    def test_refresh_token_missing(self, mock_request):
        """Test token refresh without token"""
        mock_request.cookies = {}

        result = refresh_token_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303

    def test_refresh_token_revoked(self, mock_request):
        """Test refresh of revoked token"""
        test_token = "revoked_token"
        REVOKED_TOKENS.add(test_token)
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        result = refresh_token_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303

    @patch('src.auth.login.security')
    def test_refresh_token_success(self, mock_security, mock_request):
        """Test successful token refresh"""
        test_token = "valid_refresh_token"
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

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
        """Test refresh of invalid token"""
        test_token = "invalid_token"
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        mock_security._decode_token.side_effect = Exception("Invalid token")

        result = refresh_token_handler(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303


class TestCheckAuthStatus:
    """Tests for authentication status check"""

    def test_check_auth_with_token(self, mock_request):
        """Test auth check with token"""
        mock_request.cookies = {"JWT_ACCESS_TOKEN_COOKIE": "valid_token"}

        result = check_auth_status(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/home"
        assert result.status_code == 303

    def test_check_auth_without_token(self, mock_request):
        """Test auth check without token"""
        mock_request.cookies = {}

        result = check_auth_status(mock_request)

        assert hasattr(result, 'status_code')
