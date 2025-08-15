"""
Тесты для основного модуля main.py
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestMainApp:
    """Тесты для основного приложения"""
    
    def test_app_creation(self, app):
        """Тест создания FastAPI приложения"""
        assert app is not None
        assert hasattr(app, 'routes')
        assert len(app.routes) > 0
    
    def test_app_docs_disabled(self, app):
        """Тест отключения документации"""
        # Проверяем, что docs_url и redoc_url отключены
        assert app.docs_url is None
        assert app.redoc_url is None
    
    def test_static_files_mounted(self, app):
        """Тест подключения статических файлов"""
        # Проверяем наличие маршрута для статических файлов
        static_routes = [route for route in app.routes if hasattr(route, 'path') and route.path.startswith('/static')]
        assert len(static_routes) > 0
    
    def test_exception_handler_registered(self, app):
        """Тест регистрации обработчика исключений"""
        # Проверяем, что обработчик исключений зарегистрирован
        assert len(app.exception_handlers) > 0


class TestMainRoutes:
    """Тесты для маршрутов в main.py"""
    
    def test_main_routes_exist(self, app):
        """Тест существования основных маршрутов"""
        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        
        expected_routes = [
            "/",
            "/login", 
            "/logout",
            "/refresh",
            "/home",
            "/send_email",
            "/gen_rit_cert",
            "/doctor_form",
            "/2fa",
            "/setup-session",
            "/setup-2fa",
            "/configure-2fa"
        ]
        
        for expected_route in expected_routes:
            assert expected_route in route_paths, f"Route {expected_route} not found"
    
    def test_route_methods(self, app):
        """Тест HTTP методов для маршрутов"""
        # Собираем все маршруты по методам
        routes_by_method = {}
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                path = route.path
                methods = route.methods or set()
                for method in methods:
                    if method not in routes_by_method:
                        routes_by_method[method] = set()
                    routes_by_method[method].add(path)
        
        # Проверяем наличие основных POST эндпоинтов
        post_paths = routes_by_method.get("POST", set())
        essential_post_endpoints = ["/login", "/logout", "/refresh"]
        for endpoint in essential_post_endpoints:
            assert endpoint in post_paths, f"Essential POST endpoint {endpoint} not found"
        
        # Проверяем наличие основных GET эндпоинтов
        get_paths = routes_by_method.get("GET", set())
        essential_get_endpoints = ["/", "/2fa"]
        for endpoint in essential_get_endpoints:
            assert endpoint in get_paths, f"Essential GET endpoint {endpoint} not found"
        
        # Проверяем, что есть хотя бы несколько маршрутов
        total_routes = len([r for r in app.routes if hasattr(r, 'path')])
        assert total_routes >= 10, f"Expected at least 10 routes, found {total_routes}"


class TestDateVariable:
    """Тесты для глобальной переменной date_now"""
    
    def test_date_now_format(self):
        """Тест форматирования переменной date_now"""
        import src.main
        
        # Проверяем, что date_now установлена и имеет правильный формат
        assert hasattr(src.main, 'date_now')
        assert isinstance(src.main.date_now, str)
        # Проверяем формат даты (должен быть DD.MM.YY)
        import re
        date_pattern = r'^\d{2}\.\d{2}\.\d{2}$'
        assert re.match(date_pattern, src.main.date_now), f"date_now format is incorrect: {src.main.date_now}"


class TestDependencies:
    """Тесты для зависимостей"""
    
    def test_dependencies_defined(self):
        """Тест определения зависимостей"""
        from src.main import dependencies
        
        assert dependencies is not None
        assert isinstance(dependencies, list)
        assert len(dependencies) > 0


class TestTemplateEngine:
    """Тесты для шаблонизатора"""
    
    def test_templates_configured(self):
        """Тест конфигурации шаблонизатора"""
        from src.main import templates
        
        assert templates is not None
        # Проверяем, что это Jinja2Templates объект
        assert hasattr(templates, 'get_template') or hasattr(templates, 'env')
