"""
Tests for cookie_utils.py module
"""
from unittest.mock import MagicMock

import pytest

from src.auth.cookie_utils import (
    delete_secure_cookie,
    get_cookie_settings,
    set_secure_cookie,
)


class TestCookieSettings:
    """Tests for cookie settings"""

    def test_get_cookie_settings(self, mock_request):
        """Test getting cookie settings"""
        settings = get_cookie_settings(mock_request)

        assert isinstance(settings, dict)
        assert settings["secure"] is True
        assert settings["samesite"] == "lax"
        assert settings["httponly"] is True


class TestSetSecureCookie:
    """Tests for setting secure cookie"""

    def test_set_secure_cookie_without_max_age(self, mock_request):
        """Test setting cookie without max_age"""
        mock_response = MagicMock()

        set_secure_cookie(mock_response, mock_request, "test_key", "test_value")

        mock_response.set_cookie.assert_called_once_with(
            key="test_key",
            value="test_value",
            max_age=None,
            secure=True,
            samesite="lax",
            httponly=True
        )

    def test_set_secure_cookie_with_max_age(self, mock_request):
        """Test setting cookie with max_age"""
        mock_response = MagicMock()

        set_secure_cookie(mock_response, mock_request, "test_key", "test_value", max_age=3600)

        mock_response.set_cookie.assert_called_once_with(
            key="test_key",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="lax",
            httponly=True
        )


class TestDeleteSecureCookie:
    """Tests for deleting secure cookie"""

    def test_delete_secure_cookie(self, mock_request):
        """Test deleting cookie"""
        mock_response = MagicMock()

        delete_secure_cookie(mock_response, mock_request, "test_key")

        mock_response.delete_cookie.assert_called_once_with(
            "test_key",
            secure=True,
            samesite="lax"
        )
