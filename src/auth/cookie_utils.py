"""Настройки защищённых cookies."""

import logging
from dataclasses import dataclass
from typing import Literal

from fastapi.responses import Response

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CookiePolicy:
    secure: bool = True
    samesite: Literal["lax", "strict", "none"] = "lax"
    httponly: bool = True

    def set(self, response: Response, key: str, value: str, *, max_age: int | None = None) -> None:
        logger.debug("Установка защищённой cookie")
        response.set_cookie(
            key=key, value=value, max_age=max_age, secure=self.secure, samesite=self.samesite, httponly=self.httponly
        )

    def delete(self, response: Response, key: str) -> None:
        logger.debug("Удаление защищённой cookie")
        response.delete_cookie(key, secure=self.secure, samesite=self.samesite)
