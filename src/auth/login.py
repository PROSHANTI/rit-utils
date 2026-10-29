import datetime
import hmac
import logging
import math
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from threading import Lock

from authx import AuthX, AuthXConfig
from authx.exceptions import AuthXException, JWTDecodeError, MissingTokenError
from authx.schema import TokenPayload
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
        return Depends(self.require_session)

    async def require_session(self, request: Request) -> None:
        try:
            await self.security.access_token_required(request)
            return
        except MissingTokenError:
            pass
        except AuthXException as exc:
            if not isinstance(exc, JWTDecodeError) or "expired" not in str(exc).lower():
                raise JWTDecodeError("Invalid access token") from exc

        payload = await self._refresh_payload(request)
        request.state.renewed_access_token = self.security.create_access_token(uid=payload.sub, jti=str(uuid.uuid4()))

    async def persist_session(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        token = getattr(request.state, "renewed_access_token", None)
        if token and request.url.path != "/logout":
            self.cookies.set(response, self.config.JWT_ACCESS_COOKIE_NAME, token)
            response.headers["Cache-Control"] = "no-store"
            logger.info("Сессия автоматически продлена при обработке запроса")
        return response

    async def _refresh_payload(self, request: Request) -> TokenPayload:
        token = request.cookies.get(self.config.JWT_REFRESH_COOKIE_NAME)
        if not token:
            raise MissingTokenError("Refresh token missing")
        if token in self.revoked_tokens:
            raise JWTDecodeError("Refresh token revoked")
        try:
            payload = await self.security.refresh_token_required(request)
        except AuthXException as exc:
            raise JWTDecodeError("Invalid refresh token") from exc
        if payload.sub != "1" or not payload.jti or payload.exp is None:
            raise JWTDecodeError("Invalid refresh session")
        return payload

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

    async def refresh(self, request: Request) -> Response:
        logger.info("Начато обновление токена доступа")
        try:
            payload = await self._refresh_payload(request)
            new_access_token = self.security.create_access_token(uid=payload.sub, jti=f"{uuid.uuid4()}")
            response = (
                JSONResponse({"detail": "Сессия продлена."})
                if self._wants_json(request)
                else RedirectResponse(url="/home", status_code=303)
            )
            self.cookies.set(response, self.config.JWT_ACCESS_COOKIE_NAME, new_access_token)
            response.headers["Cache-Control"] = "no-store"
            logger.info("Токен доступа обновлён")
            return response
        except (JWTDecodeError, MissingTokenError):
            logger.warning("Обновление токена отклонено: не удалось проверить токен")
            return self._clear_session(request)

    async def handle_jwt_error(self, request: Request, exc: Exception) -> Response:
        logger.warning("Запрос отклонён: ошибка проверки JWT")

        return self._clear_session(request)

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

    @staticmethod
    def _wants_json(request: Request) -> bool:
        return "application/json" in request.headers.get("accept", "").lower()

    def _clear_session(self, request: Request) -> Response:
        response = (
            JSONResponse(status_code=401, content={"detail": "Сессия завершена. Войдите снова."})
            if self._wants_json(request)
            else RedirectResponse(url="/", status_code=303)
        )
        self.cookies.delete(response, self.config.JWT_ACCESS_COOKIE_NAME)
        self.cookies.delete(response, self.config.JWT_REFRESH_COOKIE_NAME)
        response.headers["Cache-Control"] = "no-store"
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
