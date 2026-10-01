"""
Tests for login.py authentication module
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse

from src.auth.login import AuthenticationService, Credentials, auth_service


class TestCredentials:
    @pytest.mark.parametrize(
        ("username", "password", "expected"),
        [("admin", "secret", True), ("wrong", "secret", False), ("admin", "wrong", False)],
    )
    def test_credentials_match_only_both_correct_values(self, username: str, password: str, expected: bool) -> None:
        credentials = Credentials(username="admin", password="secret")

        result = credentials.matches(username, password)

        assert result is expected

    def test_credentials_repr_hides_username_and_password(self) -> None:
        credentials = Credentials(username="private-login", password="private-password")

        representation = repr(credentials)

        assert "private-login" not in representation
        assert "private-password" not in representation


class TestAuthenticationService:
    def test_revoking_token_does_not_affect_another_service(self, mock_request: MagicMock) -> None:
        other_service = AuthenticationService(auth_service.credentials, auth_service.security)
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": "revoked-token"}

        auth_service.logout(mock_request)

        assert "revoked-token" in auth_service.revoked_tokens
        assert "revoked-token" not in other_service.revoked_tokens


class TestLoginHandler:
    """Tests for login handler"""

    def test_login_success(self, mock_request):
        """Test successful login"""
        result = auth_service.login(mock_request, "test_admin", "test_password")

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/home"
        assert result.status_code == 303

    def test_login_invalid_credentials(self, mock_request):
        """Test login with invalid credentials"""
        result = auth_service.login(mock_request, "wrong_user", "wrong_pass")

        assert hasattr(result, "status_code")
        assert result.status_code == 401

    def test_login_invalid_username(self, mock_request):
        """Test login with invalid username"""
        result = auth_service.login(mock_request, "wrong_user", "test_password")

        assert hasattr(result, "status_code")
        assert result.status_code == 401

    def test_login_invalid_password(self, mock_request):
        """Test login with invalid password"""
        result = auth_service.login(mock_request, "test_admin", "wrong_pass")

        assert hasattr(result, "status_code")
        assert result.status_code == 401


class TestLogoutHandler:
    """Tests for logout handler"""

    def test_logout_with_refresh_token(self, mock_request):
        """Test logout with refresh token"""
        test_token = "test_refresh_token"
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        result = auth_service.logout(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303
        assert test_token in auth_service.revoked_tokens

    def test_logout_without_refresh_token(self, mock_request):
        """Test logout without refresh token"""
        mock_request.cookies = {}

        result = auth_service.logout(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303


class TestRefreshTokenHandler:
    """Tests for token refresh handler"""

    def test_refresh_token_missing(self, mock_request):
        """Test token refresh without token"""
        mock_request.cookies = {}

        result = auth_service.refresh(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303

    def test_refresh_token_revoked(self, mock_request):
        """Test refresh of revoked token"""
        test_token = "revoked_token"
        auth_service.revoked_tokens.add(test_token)
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        result = auth_service.refresh(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303

    @patch.object(auth_service, "security")
    def test_refresh_token_success(self, mock_security, mock_request):
        """Test successful token refresh"""
        test_token = "valid_refresh_token"
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        mock_payload = MagicMock()
        mock_payload.sub = "1"
        mock_payload.jti = "test_jti"
        mock_security._decode_token.return_value = mock_payload
        mock_security.create_access_token.return_value = "new_access_token"

        result = auth_service.refresh(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/home"
        assert result.status_code == 303
        mock_security.create_access_token.assert_called_once()

    @patch.object(auth_service, "security")
    def test_refresh_token_invalid(self, mock_security, mock_request):
        """Test refresh of invalid token"""
        test_token = "invalid_token"
        mock_request.cookies = {"JWT_REFRESH_TOKEN_COOKIE": test_token}

        mock_security._decode_token.side_effect = Exception("Invalid token")

        result = auth_service.refresh(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303


class TestCheckAuthStatus:
    """Tests for authentication status check"""

    def test_check_auth_with_token(self, mock_request):
        """Test auth check with token"""
        mock_request.cookies = {"JWT_ACCESS_TOKEN_COOKIE": "valid_token"}

        result = auth_service.check_status(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/home"
        assert result.status_code == 303

    def test_check_auth_without_token(self, mock_request):
        """Test auth check without token"""
        mock_request.cookies = {}

        result = auth_service.check_status(mock_request)

        assert hasattr(result, "status_code")
