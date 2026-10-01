"""
Конфигурация приложения и загрузка переменных окружения
"""

import logging
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

SENSITIVE_ENV_NAMES = (
    "JWT_SECRET_KEY",
    "EMAIL_PASS",
    "PASSWORD",
    "TOTP_SECRET",
    "LOGIN",
    "SEND_FROM",
    "ADDR_TO",
    "BCC_TO",
)


class RedactingFormatter(logging.Formatter):
    """Маскирует чувствительные настройки в сообщениях и стеке исключения."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        sensitive_values = {value for name in SENSITIVE_ENV_NAMES if (value := os.getenv(name))}
        sensitive_forms = {
            form for value in sensitive_values for form in (value, repr(value)[1:-1], repr(value.encode("utf-8"))[2:-1])
        }

        for sensitive_form in sorted(sensitive_forms, key=len, reverse=True):
            message = message.replace(sensitive_form, "[REDACTED]")

        return message


@dataclass(frozen=True, slots=True)
class LoggingConfiguration:
    level: str = "INFO"

    @classmethod
    def from_env(cls) -> "LoggingConfiguration":
        return cls(level=os.getenv("LOG_LEVEL", "INFO").upper())

    def configure(self) -> None:
        """Выводит логи в stdout, доступный через docker logs."""
        level = logging.getLevelNamesMapping().get(self.level.upper(), logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s [%(name)s.%(funcName)s] %(message)s"))
        logging.basicConfig(level=level, handlers=[handler], force=True)
        logger.info("Логирование приложения настроено")


load_dotenv()
