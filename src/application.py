import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.auth import AuthenticationService, JWTDecodeError, MissingTokenError
from src.config import LoggingConfiguration
from src.routers import ApplicationRouter

logger = logging.getLogger(__name__)


class WebApplication:
    def __init__(self, auth: AuthenticationService) -> None:
        LoggingConfiguration.from_env().configure()
        self.auth = auth
        self.routes = ApplicationRouter(auth)
        self.app = FastAPI(docs_url=None, redoc_url=None)
        self.app.mount("/static", StaticFiles(directory="templates"), name="static")
        self.app.add_exception_handler(JWTDecodeError, auth.handle_jwt_error)
        self.app.add_exception_handler(MissingTokenError, auth.handle_jwt_error)
        self.app.include_router(self.routes.router)
        logger.info("Приложение RIT Utils подготовлено к запуску")
