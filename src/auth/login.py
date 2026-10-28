import datetime
import hmac
import logging
import math
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock

from authx import AuthX, AuthXConfig
from authx.exceptions import JWTDecodeError
from dotenv import load_dotenv
from fastapi import Request
from fastapi.params import Depends
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .cookie_utils import CookiePolicy

logger = logging.getLogger(__name__)
load_dotenv()


@dataclass(frozen=True, slots=True)
class Credentials:
    password: str | None = field(repr=False)

    def matches(self, password: str) -> bool:
        if not self.password or len(password) > 1024:
            return False
        return hmac.compare_digest(password.encode("utf-8"), self.password.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class LoginAttempt:
    accepted: bool
    remaining_attempts: int
    retry_after: int = 0


class LoginThrottle:
    """Общий лимит для единственной учётной записи в одном процессе приложения."""

    max_attempts = 10
    cooldown_seconds = 5 * 60

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = Lock()
        self._failures = 0
        self._blocked_until = 0.0

    def attempt(self, verify_password: Callable[[], bool]) -> LoginAttempt:
        with self._lock:
            now = self._clock()
            retry_after = max(0, math.ceil(self._blocked_until - now))
            if retry_after:
                return LoginAttempt(False, 0, retry_after)

            if self._blocked_until:
                self._failures = 0
                self._blocked_until = 0.0

            if verify_password():
                self._failures = 0
                return LoginAttempt(True, self.max_attempts)

            self._failures += 1
            if self._failures >= self.max_attempts:
                self._blocked_until = now + self.cooldown_seconds
                return LoginAttempt(False, 0, self.cooldown_seconds)

            return LoginAttempt(False, self.max_attempts - self._failures)

    def retry_after(self) -> int:
        with self._lock:
            return max(0, math.ceil(self._blocked_until - self._clock()))


class AuthenticationService:
    def __init__(
        self,
        credentials: Credentials,
        security: AuthX,
        *,
        templates: Jinja2Templates | None = None,
        login_throttle: LoginThrottle | None = None,
    ) -> None:
        self.credentials = credentials
        self.security = security
        self.config = security.config
        self.templates = templates or Jinja2Templates(directory="templates")
        self.cookies = CookiePolicy()
        self.revoked_tokens: set[str] = set()
        self.login_throttle = login_throttle or LoginThrottle()

    @classmethod
    def from_env(cls) -> "AuthenticationService":
        return cls(Credentials(os.getenv("PASSWORD")), cls._create_security())

    def dependency(self) -> Depends:
        logger.debug("Подготовка проверки токена доступа")
        return Depends(self.security.access_token_required)

    def login(self, request: Request, password: str) -> Response:
        logger.info("Начата авторизация")

        attempt = self.login_throttle.attempt(lambda: self.credentials.matches(password))
        if not attempt.accepted:
            logger.warning(
                "Авторизация отклонена: осталось попыток %s, ожидание %s с",
                attempt.remaining_attempts,
                attempt.retry_after,
            )
            return self._login_page(
                request,
                error=f"Неверный пароль. Осталось попыток: {attempt.remaining_attempts}.",
                retry_after=attempt.retry_after,
                status_code=401,
            )

        response = RedirectResponse(url="/home", status_code=303)
        access_token = self.security.create_access_token(uid="1", jti=f"{uuid.uuid4()}")
        refresh_token = self.security.create_refresh_token(uid="1", jti=f"{uuid.uuid4()}")
        self.cookies.set(response, self.config.JWT_ACCESS_COOKIE_NAME, access_token)
        self.cookies.set(response, self.config.JWT_REFRESH_COOKIE_NAME, refresh_token, max_age=7 * 24 * 60 * 60)
        logger.info("Авторизация выполнена")
        return response

    def logout(self, request: Request) -> RedirectResponse:
        logger.info("Начат выход из системы")

        if refresh_token := request.cookies.get(self.config.JWT_REFRESH_COOKIE_NAME):
            self.revoked_tokens.add(refresh_token)

        response = RedirectResponse(url="/", status_code=303)

        for key in (self.config.JWT_ACCESS_COOKIE_NAME, self.config.JWT_REFRESH_COOKIE_NAME):
            response.delete_cookie(key=key, path="/", domain=None, secure=True, httponly=True, samesite="strict")

        logger.info("Выход из системы выполнен")
        return response

    def refresh(self, request: Request) -> RedirectResponse:
        logger.info("Начато обновление токена доступа")
        refresh_token = request.cookies.get(self.config.JWT_REFRESH_COOKIE_NAME)

        if not refresh_token:
            logger.warning("Обновление токена отклонено: токен обновления отсутствует")
            return RedirectResponse(url="/", status_code=303)

        if refresh_token in self.revoked_tokens:
            logger.warning("Обновление токена отклонено: токен обновления отозван")
            return self._clear_session()

        try:
            payload = self.security._decode_token(refresh_token)

            if not hasattr(payload, "jti"):
                raise ValueError("Invalid token format")

            new_access_token = self.security.create_access_token(uid=payload.sub, jti=f"{uuid.uuid4()}")
            response = RedirectResponse(url="/home", status_code=303)
            response.set_cookie(
                key=self.config.JWT_ACCESS_COOKIE_NAME, value=new_access_token, httponly=True, secure=True, samesite="strict"
            )
            logger.info("Токен доступа обновлён")
            return response

        except Exception:
            logger.warning("Обновление токена отклонено: не удалось проверить токен")
            return self._clear_session()

    async def handle_jwt_error(self, request: Request, exc: Exception) -> Response:
        logger.warning("Запрос отклонён: ошибка проверки JWT")

        if isinstance(exc, JWTDecodeError) and "expired" in f"{exc}".lower():

            if request.headers.get("accept") == "application/json":
                return JSONResponse(status_code=401, content={"detail": "Token expired"})

            return self._clear_session(refresh=False)

        return self._clear_session()

    def check_status(self, request: Request) -> Response:
        logger.debug("Проверка наличия авторизации")

        if request.cookies.get(self.config.JWT_ACCESS_COOKIE_NAME):
            return RedirectResponse(url="/home", status_code=303)

        return self._login_page(request)

    def _login_page(
        self, request: Request, *, error: str | None = None, retry_after: int | None = None, status_code: int = 200
    ) -> Response:
        wait = self.login_throttle.retry_after() if retry_after is None else retry_after
        headers = {"Cache-Control": "no-store"}
        if wait:
            error = "Слишком много неверных попыток. Повторить через"
            status_code = 429
            headers["Retry-After"] = str(wait)

        return self.templates.TemplateResponse(
            request,
            "login.html",
            {"error": error, "retry_after": wait, "retry_display": f"{wait // 60:02d}:{wait % 60:02d}"},
            status_code=status_code,
            headers=headers,
        )

    def _clear_session(self, *, refresh: bool = True) -> RedirectResponse:
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(self.config.JWT_ACCESS_COOKIE_NAME, secure=True, samesite="strict")

        if refresh:
            response.delete_cookie(self.config.JWT_REFRESH_COOKIE_NAME, secure=True, samesite="strict")

        return response

    @staticmethod
    def _create_security() -> AuthX:
        config = AuthXConfig()
        config.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
        config.JWT_ACCESS_COOKIE_NAME = "JWT_ACCESS_TOKEN_COOKIE"
        config.JWT_REFRESH_COOKIE_NAME = "JWT_REFRESH_TOKEN_COOKIE"
        config.JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(minutes=15)
        config.JWT_REFRESH_TOKEN_EXPIRES = datetime.timedelta(days=7)
        config.JWT_TOKEN_LOCATION = ["cookies"]
        config.JWT_COOKIE_CSRF_PROTECT = False
        config.JWT_COOKIE_SECURE = True
        config.JWT_COOKIE_SAMESITE = "strict"
        return AuthX(config=config)


auth_service = AuthenticationService.from_env()
