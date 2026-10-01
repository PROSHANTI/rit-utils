import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.routing import Mount

from src.auth import JWTDecodeError, MissingTokenError
from src.main import application


class TestMainApp:
    def test_entrypoint_exports_built_application(self, app):
        assert isinstance(app, FastAPI)
        assert app is application.app
        assert isinstance(application.routes.router, APIRouter)

    def test_documentation_pages_are_disabled(self, app):
        assert app.docs_url is None
        assert app.redoc_url is None

    def test_static_files_are_mounted_once(self, app):
        static_mounts = [route for route in app.routes if isinstance(route, Mount)]

        assert len(static_mounts) == 1
        assert static_mounts[0].path == "/static"
        assert isinstance(static_mounts[0].app, StaticFiles)

    def test_auth_exception_handlers_are_registered(self, app):
        assert app.exception_handlers[JWTDecodeError] == application.auth.handle_jwt_error
        assert app.exception_handlers[MissingTokenError] == application.auth.handle_jwt_error

    def test_router_owns_template_engine(self):
        templates = application.routes.templates

        assert isinstance(templates, Jinja2Templates)
        assert templates.env.get_template("home.html").filename is not None


class TestApplicationRoutes:
    def test_router_and_application_have_exact_routes_without_duplicates(self, app):
        router_routes = [route for route in application.routes.router.routes if isinstance(route, APIRoute)]
        application_routes = [route for route in app.routes if isinstance(route, APIRoute)]
        expected_pairs = {
            ("/", "GET"),
            ("/", "HEAD"),
            ("/login", "POST"),
            ("/logout", "POST"),
            ("/refresh", "POST"),
            ("/home", "GET"),
            ("/send_email", "GET"),
            ("/send_email", "POST"),
            ("/gen_rit_cert", "GET"),
            ("/gen_rit_cert", "POST"),
            ("/doctor_form", "GET"),
            ("/doctor_form", "POST"),
            ("/remove_bg", "GET"),
            ("/remove_bg", "POST"),
        }

        assert len(router_routes) == 13
        assert len(application_routes) == 13
        assert {(route.path, method) for route in router_routes for method in route.methods} == expected_pairs
        assert {(route.path, method) for route in application_routes for method in route.methods} == expected_pairs

    def test_endpoint_methods_are_bound_without_self_query_parameter(self):
        routes = [route for route in application.routes.router.routes if isinstance(route, APIRoute)]

        assert all(getattr(route.endpoint, "__self__", None) is application.routes for route in routes)
        assert all(parameter.name != "self" for route in routes for parameter in route.dependant.query_params)

    @pytest.mark.parametrize(
        ("path", "method", "expected_dependencies"),
        [
            pytest.param("/", "GET", 0, id="root-get-public"),
            pytest.param("/", "HEAD", 0, id="root-head-public"),
            pytest.param("/login", "POST", 0, id="login-public"),
            pytest.param("/refresh", "POST", 0, id="refresh-public"),
            pytest.param("/logout", "POST", 1, id="logout-protected"),
            pytest.param("/home", "GET", 1, id="home-protected"),
            pytest.param("/send_email", "GET", 1, id="email-get-protected"),
            pytest.param("/send_email", "POST", 1, id="email-post-protected"),
            pytest.param("/gen_rit_cert", "GET", 1, id="certificate-get-protected"),
            pytest.param("/gen_rit_cert", "POST", 1, id="certificate-post-protected"),
            pytest.param("/doctor_form", "GET", 1, id="doctor-get-protected"),
            pytest.param("/doctor_form", "POST", 1, id="doctor-post-protected"),
            pytest.param("/remove_bg", "GET", 1, id="image-get-protected"),
            pytest.param("/remove_bg", "POST", 1, id="image-post-protected"),
        ],
    )
    def test_each_route_keeps_its_auth_dependency(self, app, path, method, expected_dependencies):
        routes = [
            route for route in app.routes if isinstance(route, APIRoute) and route.path == path and method in route.methods
        ]

        assert len(routes) == 1
        dependencies = routes[0].dependant.dependencies
        assert len(dependencies) == expected_dependencies
        auth_dependency = application.routes.dependencies[0].dependency
        assert all(dependency.call is auth_dependency for dependency in dependencies)
