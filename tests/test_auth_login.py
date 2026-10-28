"""
Tests for login.py authentication module
"""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse

from src.auth.login import AuthenticationService, Credentials, LoginThrottle, auth_service


class TestCredentials:
    @pytest.mark.parametrize(
        ("configured", "password", "expected"),
        [
            ("secret", "secret", True),
            ("secret", "wrong", False),
            ("Пароль с пробелом", "Пароль с пробелом", True),
            (" secret ", "secret", False),
            (None, "", False),
            ("", "", False),
            ("secret", "x" * 1025, False),
        ],
    )
    def test_credentials_match_only_configured_nonempty_password(
        self, configured: str | None, password: str, expected: bool
    ) -> None:
        credentials = Credentials(password=configured)

        result = credentials.matches(password)

        assert result is expected

    def test_credentials_repr_hides_password(self) -> None:
        credentials = Credentials(password="private-password")

        representation = repr(credentials)

        assert "private-password" not in representation

    def test_password_is_compared_in_constant_time(self) -> None:
        credentials = Credentials(password="секрет")

        with patch("src.auth.login.hmac.compare_digest", return_value=True) as compare:
            result = credentials.matches("секрет")

        assert result is True
        compare.assert_called_once_with("секрет".encode(), "секрет".encode())


class TestLoginThrottle:
    def test_tenth_failure_starts_five_minute_cooldown(self):
        throttle = LoginThrottle(clock=lambda: 1000.0)
        verify = MagicMock(return_value=False)

        results = [throttle.attempt(verify) for _ in range(10)]

        assert [result.remaining_attempts for result in results] == list(range(9, -1, -1))
        assert [result.retry_after for result in results] == [0] * 9 + [300]
        assert all(not result.accepted for result in results)
        assert throttle.retry_after() == 300
        assert verify.call_count == 10

    def test_blocked_attempts_do_not_check_password_or_extend_cooldown(self):
        clock = MagicMock(return_value=1000.0)
        throttle = LoginThrottle(clock=clock)
        for _ in range(10):
            throttle.attempt(lambda: False)
        verify = MagicMock(return_value=True)
        clock.return_value = 1200.0

        blocked = throttle.attempt(verify)
        clock.return_value = 1300.0
        accepted = throttle.attempt(verify)

        assert not blocked.accepted and blocked.retry_after == 100
        assert accepted.accepted and throttle.retry_after() == 0
        verify.assert_called_once_with()

    def test_last_fraction_of_cooldown_is_still_blocked(self):
        clock = MagicMock(return_value=1000.0)
        throttle = LoginThrottle(clock=clock)
        for _ in range(10):
            throttle.attempt(lambda: False)
        clock.return_value = 1299.999

        result = throttle.attempt(lambda: True)

        assert result.retry_after == 1 and not result.accepted

    def test_success_resets_consecutive_failures(self):
        throttle = LoginThrottle(clock=lambda: 1000.0)
        for _ in range(9):
            throttle.attempt(lambda: False)

        accepted = throttle.attempt(lambda: True)
        rejected = throttle.attempt(lambda: False)

        assert accepted.accepted
        assert not rejected.accepted and rejected.remaining_attempts == 9
        assert rejected.retry_after == 0

    def test_cooldown_expiry_gives_ten_new_attempts(self):
        clock = MagicMock(return_value=1000.0)
        throttle = LoginThrottle(clock=clock)
        for _ in range(10):
            throttle.attempt(lambda: False)
        clock.return_value = 1300.0

        result = throttle.attempt(lambda: False)

        assert not result.accepted and result.remaining_attempts == 9 and result.retry_after == 0

    def test_parallel_requests_share_the_same_ten_attempts(self):
        throttle = LoginThrottle(clock=lambda: 1000.0)
        verify = MagicMock(return_value=False)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: throttle.attempt(verify), range(64)))

        assert verify.call_count == 10
        assert sum(result.retry_after == 0 for result in results) == 9
        assert sum(result.retry_after == 300 for result in results) == 55
        assert all(not result.accepted for result in results)


class TestAuthenticationService:
    def test_from_env_does_not_require_login(self, monkeypatch) -> None:
        monkeypatch.delenv("LOGIN", raising=False)
        monkeypatch.setenv("PASSWORD", "password-only-fixture")

        service = AuthenticationService.from_env()

        assert service.credentials.matches("password-only-fixture")

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
        result = auth_service.login(mock_request, "test_password")

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/home"
        assert result.status_code == 303

    def test_login_invalid_password(self, mock_request):
        """Test login with invalid password"""
        result = auth_service.login(mock_request, "wrong_pass")

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
