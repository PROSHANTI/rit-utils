"""
Тесты для модуля config.py
"""
import pytest
from unittest.mock import patch
import os


class TestConfig:
    """Тесты для конфигурации приложения"""
    
    @patch.dict(os.environ, {}, clear=True)
    def test_config_import(self):
        """Тест импорта модуля config"""
        try:
            import src.config
            # Модуль должен импортироваться без ошибок
            assert True
        except Exception as e:
            pytest.fail(f"Config import failed: {e}")
    
    def test_config_module_accessible(self):
        """Тест доступности модуля config"""
        try:
            import src.config
            # Проверяем, что модуль доступен и нет ошибок
            assert src.config is not None
        except Exception as e:
            pytest.fail(f"Config module not accessible: {e}")
