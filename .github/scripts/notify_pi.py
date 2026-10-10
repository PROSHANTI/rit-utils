"""Send a plain-text Pi CI notification without exposing Telegram credentials."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

MAX_MESSAGE_LENGTH = 4096
MAX_DESCRIPTION_LENGTH = 2000
MAX_RESPONSE_BYTES = 65536
REQUEST_TIMEOUT_SECONDS = 20


class NotificationError(Exception):
    """An error safe to print in public CI logs."""


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "")
    if not value:
        raise NotificationError(f"Required environment variable {name} is missing.")
    return value


def _length(text: str) -> int:
    # Telegram entity offsets use UTF-16; use that stricter length for emoji too.
    return len(text.encode("utf-16-le")) // 2


def _truncate(text: str, limit: int) -> str:
    if _length(text) <= limit:
        return text
    parts: list[str] = []
    used = 0
    for char in text:
        size = _length(char)
        if used + size > limit - 1:
            break
        parts.append(char)
        used += size
    return "".join(parts) + "…"


def _description(event_path: str) -> str:
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise NotificationError("GitHub event JSON could not be read.") from None
    if not isinstance(event, dict):
        raise NotificationError("GitHub event JSON is invalid.")
    commit = event.get("head_commit")
    if commit is None:
        return "N/A"
    if not isinstance(commit, dict):
        raise NotificationError("GitHub event commit is invalid.")
    description = commit.get("message")
    if description is None or description == "":
        return "N/A"
    if not isinstance(description, str):
        raise NotificationError("GitHub commit description is invalid.")
    try:
        return _truncate(description, MAX_DESCRIPTION_LENGTH)
    except UnicodeError:
        raise NotificationError("GitHub commit description is invalid.") from None


def build_message(environ: Mapping[str, str]) -> str:
    result = _required(environ, "PI_CI_RESULT")
    if result not in {"success", "failure"}:
        raise NotificationError("PI_CI_RESULT must be success or failure.")
    if environ.get("GITHUB_EVENT_NAME") != "push" or environ.get("GITHUB_REF") != "refs/heads/pi":
        raise NotificationError("Pi notifications require a push to the pi branch.")
    sha = _required(environ, "GITHUB_SHA")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise NotificationError("GITHUB_SHA is invalid.")
    repository = _required(environ, "GITHUB_REPOSITORY")
    if len(repository) > 200 or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise NotificationError("GITHUB_REPOSITORY is invalid.")
    run_id = _required(environ, "GITHUB_RUN_ID")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id):
        raise NotificationError("GITHUB_RUN_ID is invalid.")
    description = _description(_required(environ, "GITHUB_EVENT_PATH"))
    if result == "success":
        title = "✅ RIT-UTILS: сборка для Raspberry Pi завершена"
        details = (
            "\nARM64: тесты и проверка PDF пройдены."
            f"\nОбраз proshanti/rit-utils:pi-{sha} опубликован."
            "\nКанал pi обновлён."
            "\nRaspberry Pi проверяет обновления раз в 5 минут."
        )
    else:
        title = "❌ RIT-UTILS: сборка для Raspberry Pi не прошла"
        details = ""
    prefix = f"{title}\nВетка: pi\nКоммит: {sha}\nОписание: "
    suffix = f"{details}\nActions: https://github.com/{repository}/actions/runs/{run_id}"
    budget = min(MAX_DESCRIPTION_LENGTH, MAX_MESSAGE_LENGTH - _length(prefix + suffix))
    return prefix + _truncate(description, budget) + suffix


def send_notification(environ: Mapping[str, str] | None = None) -> None:
    if environ is None:
        environ = os.environ
    token = _required(environ, "TELEGRAM_TOKEN")
    if not re.fullmatch(r"[0-9]{1,20}:[A-Za-z0-9_-]{20,200}", token):
        raise NotificationError("TELEGRAM_TOKEN is invalid.")
    chat_id = _required(environ, "TELEGRAM_TO")
    if not re.fullmatch(r"-?[1-9][0-9]{0,19}|@[A-Za-z][A-Za-z0-9_]{4,31}", chat_id):
        raise NotificationError("TELEGRAM_TO is invalid.")
    payload = json.dumps({"chat_id": chat_id, "text": build_message(environ)}, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = response.status
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise NotificationError(f"Telegram request failed (HTTP {error.code}).") from None
    except Exception:
        # urllib errors may include the complete request URL and its bot token.
        raise NotificationError("Telegram request failed.") from None
    if status != 200:
        raise NotificationError(f"Telegram request failed (HTTP {status}).")
    if len(body) > MAX_RESPONSE_BYTES:
        raise NotificationError("Telegram response is invalid (HTTP 200).")
    try:
        result = json.loads(body)
    except (UnicodeError, ValueError):
        raise NotificationError("Telegram response is invalid (HTTP 200).") from None
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise NotificationError("Telegram rejected the notification (HTTP 200).")


def main() -> int:
    try:
        send_notification()
    except NotificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Pi CI Telegram notification sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
