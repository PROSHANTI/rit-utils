"""
Тесты для модуля cookie_utils.py
"""
import pytest
from unittest.mock import MagicMock

from src.auth.cookie_utils import (
    get_cookie_settings,
    set_secure_cookie,
    delete_secure_cookie
)


class TestCookieSettings:
    """Тесты для настроек cookie"""
    
    def test_get_cookie_settings(self, mock_request):
        """Тест получения настроек cookie"""
        settings = get_cookie_settings(mock_request)
        
        assert isinstance(settings, dict)
        assert settings["secure"] is True
        assert settings["samesite"] == "lax"
        assert settings["httponly"] is True


class TestSetSecureCookie:
    """Тесты для установки secure cookie"""
    
    def test_set_secure_cookie_without_max_age(self, mock_request):
        """Тест установки cookie без max_age"""
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
        """Тест установки cookie с max_age"""
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
    """Тесты для удаления secure cookie"""
    
    def test_delete_secure_cookie(self, mock_request):
        """Тест удаления cookie"""
        mock_response = MagicMock()
        
        delete_secure_cookie(mock_response, mock_request, "test_key")
        
        mock_response.delete_cookie.assert_called_once_with(
            "test_key",
            secure=True,
            samesite="lax"
        )
