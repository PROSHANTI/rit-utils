"""
Tests for main.py module
"""
import re
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestMainApp:
    """Tests for main application"""

    def test_app_creation(self, app):
        """Test FastAPI application creation"""
        assert app is not None
        assert hasattr(app, 'routes')
        assert len(app.routes) > 0

    def test_app_docs_disabled(self, app):
        """Test documentation disabled"""
        assert app.docs_url is None
        assert app.redoc_url is None

    def test_static_files_mounted(self, app):
        """Test static files mounting"""
        static_routes = [route for route in app.routes if hasattr(route, 'path') and route.path.startswith('/static')]
        assert len(static_routes) > 0

    def test_exception_handler_registered(self, app):
        """Test exception handler registration"""
        assert len(app.exception_handlers) > 0


class TestMainRoutes:
    """Tests for routes in main.py"""

    def test_main_routes_exist(self, app):
        """Test main routes existence"""
        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]

        expected_routes = [
            "/",
            "/login",
            "/logout",
            "/refresh",
            "/home",
            "/send_email",
            "/gen_rit_cert",
            "/doctor_form"
        ]

        for expected_route in expected_routes:
            assert expected_route in route_paths, f"Route {expected_route} not found"

    def test_route_methods(self, app):
        """Test HTTP methods for routes"""
        routes_by_method = {}
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                path = route.path
                methods = route.methods or set()
                for method in methods:
                    if method not in routes_by_method:
                        routes_by_method[method] = set()
                    routes_by_method[method].add(path)

        post_paths = routes_by_method.get("POST", set())
        essential_post_endpoints = ["/login", "/logout", "/refresh"]
        for endpoint in essential_post_endpoints:
            assert endpoint in post_paths, f"Essential POST endpoint {endpoint} not found"

        get_paths = routes_by_method.get("GET", set())
        essential_get_endpoints = ["/"]
        for endpoint in essential_get_endpoints:
            assert endpoint in get_paths, f"Essential GET endpoint {endpoint} not found"

        total_routes = len([r for r in app.routes if hasattr(r, 'path')])
        assert total_routes >= 10, f"Expected at least 10 routes, found {total_routes}"


class TestDateVariable:
    """Tests for global date_now variable"""

    def test_date_now_format(self):
        """Test date_now variable formatting"""
        import src.main

        assert hasattr(src.main, 'date_now')
        assert isinstance(src.main.date_now, str)
        date_pattern = r'^\d{2}\.\d{2}\.\d{2}$'
        assert re.match(date_pattern, src.main.date_now), f"date_now format is incorrect: {src.main.date_now}"


class TestDependencies:
    """Tests for dependencies"""

    def test_dependencies_defined(self):
        """Test dependencies definition"""
        from src.main import dependencies

        assert dependencies is not None
        assert isinstance(dependencies, list)
        assert len(dependencies) > 0


class TestTemplateEngine:
    """Tests for template engine"""

    def test_templates_configured(self):
        """Test template engine configuration"""
        from src.main import templates

        assert templates is not None
        assert hasattr(templates, 'get_template') or hasattr(templates, 'env')
