"""
Tests for config.py module
"""

import logging
import os
import smtplib
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import RedactingFormatter


def run_logging_probe(probe_script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", probe_script],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )


@pytest.mark.parametrize(
    ("log_level", "expected_messages"),
    [
        pytest.param("INFO", ["info-event"], id="info-level"),
        pytest.param("debug", ["debug-event", "info-event"], id="debug-level"),
        pytest.param("unknown", ["info-event"], id="invalid-level-falls-back-to-info"),
    ],
)
def test_logging_writes_module_and_function_to_stdout(
    log_level: str, expected_messages: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", log_level)
    probe_script = (
        "import logging\n"
        "from src.config import LoggingConfiguration\n"
        "LoggingConfiguration.from_env().configure()\n"
        "logger = logging.getLogger('src.logging_probe')\n"
        "def run_probe():\n"
        "    logger.debug('debug-event')\n"
        "    logger.info('info-event')\n"
        "run_probe()\n"
    )

    result = run_logging_probe(probe_script)

    probe_lines = [line for line in result.stdout.splitlines() if "[src.logging_probe.run_probe]" in line]
    assert [line.partition("] ")[2] for line in probe_lines] == expected_messages
    assert result.stderr == ""


def test_uvicorn_app_import_configures_logging_once_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    probe_script = (
        "import logging\n"
        "import os\n"
        "import smtplib\n"
        "import sys\n"
        "from types import ModuleType\n"
        "from uvicorn import Config\n"
        "os.environ['EMAIL_PASS'] = 'fake-email-password-for-uvicorn-log-test'\n"
        "email_templates = ModuleType('src.utils.send_email.email_templates')\n"
        "email_templates.get_email_template = lambda: ''\n"
        "sys.modules[email_templates.__name__] = email_templates\n"
        "Config('src.main:app').load()\n"
        "try:\n"
        "    raise smtplib.SMTPAuthenticationError(535, b'fake-email-password-for-uvicorn-log-test')\n"
        "except smtplib.SMTPAuthenticationError:\n"
        "    logging.getLogger('src.utils.send_email.email_handler').exception('SMTP отклонил авторизацию')\n"
    )

    result = run_logging_probe(probe_script)

    assert "[src.config.configure] Логирование приложения настроено" in result.stdout
    assert "[src.application.__init__] Приложение RIT Utils подготовлено к запуску" in result.stdout
    assert result.stdout.count("Логирование приложения настроено") == 1
    assert "[src.utils.send_email.email_handler.<module>] SMTP отклонил авторизацию" in result.stdout
    assert "Traceback" in result.stdout
    assert "SMTPAuthenticationError: (535, b'[REDACTED]')" in result.stdout
    assert "fake-email-password-for-uvicorn-log-test" not in result.stdout
    assert result.stderr == ""


def test_log_formatter_redacts_sensitive_settings_in_message_and_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_value = "fake-secret-for-log-test"
    monkeypatch.setenv("EMAIL_PASS", secret_value)
    formatter = RedactingFormatter("%(levelname)s %(message)s")

    try:
        raise ValueError(secret_value)

    except ValueError:
        record = logging.LogRecord(
            "src.logging_probe", logging.ERROR, __file__, 0, "Ошибка: %s", (secret_value,), sys.exc_info()
        )

    formatted_message = formatter.format(record)

    assert secret_value not in formatted_message
    assert "ERROR Ошибка: [REDACTED]" in formatted_message
    assert "Traceback" in formatted_message
    assert "ValueError: [REDACTED]" in formatted_message


@pytest.mark.parametrize(
    "secret_value",
    [
        pytest.param("fake\\secret-for-log-test", id="backslash"),
        pytest.param("fake-секрет-for-log-test", id="unicode"),
        pytest.param("fake'\"secret-for-log-test", id="quotes"),
    ],
)
def test_log_formatter_redacts_secret_in_smtp_bytes_traceback(secret_value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PASS", secret_value)
    formatter = RedactingFormatter("%(levelname)s %(message)s")

    try:
        raise smtplib.SMTPAuthenticationError(535, secret_value.encode("utf-8"))

    except smtplib.SMTPAuthenticationError:
        record = logging.LogRecord(
            "src.logging_probe", logging.ERROR, __file__, 0, "SMTP отклонил авторизацию", (), sys.exc_info()
        )

    formatted_message = formatter.format(record)

    assert secret_value not in formatted_message
    assert repr(secret_value.encode("utf-8")) not in formatted_message
    assert "SMTPAuthenticationError: (535, b'[REDACTED]')" in formatted_message or (
        'SMTPAuthenticationError: (535, b"[REDACTED]")' in formatted_message
    )


class TestConfig:
    """Tests for application configuration"""

    @patch.dict(os.environ, {}, clear=True)
    def test_config_import(self):
        """Test config module import"""
        try:
            config_module = import_module("src.config")
            assert config_module.__name__ == "src.config"
        except Exception as e:
            pytest.fail(f"Config import failed: {e}")

    def test_config_module_accessible(self):
        """Test config module accessibility"""
        try:
            import src.config

            assert src.config is not None
        except Exception as e:
            pytest.fail(f"Config module not accessible: {e}")
