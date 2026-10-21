"""Exercise Pi notifications with synthetic events and mocked Telegram calls."""

from __future__ import annotations

import io
import json
import tempfile
import traceback
import unittest
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import notify_pi


class NotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.event_path = Path(self.directory.name) / "event.json"
        self.write_event("Add a Pi notification\n\nPreserve multiline descriptions.")
        self.token = "123456:synthetic_token_never_logged_123456789"
        self.env = {
            "TELEGRAM_TOKEN": self.token,
            "TELEGRAM_TO": "-1001234567890",
            "PI_CI_RESULT": "success",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/pi",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_REPOSITORY": "PROSHANTI/rit-utils",
            "GITHUB_RUN_ID": "123456789",
            "GITHUB_EVENT_PATH": str(self.event_path),
        }

    def write_event(self, message: object) -> None:
        self.event_path.write_text(json.dumps({"head_commit": {"message": message}}, ensure_ascii=False), encoding="utf-8")

    def response(self, body: bytes = b'{"ok": true}', status: int = 200) -> MagicMock:
        response = MagicMock()
        response.status = status
        response.read.return_value = body
        response.__enter__.return_value = response
        return response

    def assert_safe_error(self, exception: Exception, body: str = "") -> None:
        with patch("notify_pi.urlopen", side_effect=exception):
            try:
                notify_pi.send_notification(self.env)
            except notify_pi.NotificationError as error:
                rendered = "".join(traceback.format_exception(type(error), error, error.__traceback__))
                self.assertNotIn(self.token, rendered)
                self.assertNotIn("api.telegram.org/bot", rendered)
                if body:
                    self.assertNotIn(body, rendered)
            else:
                self.fail("Expected a safe NotificationError")

    def test_success_sends_plain_text_with_multiline_description(self) -> None:
        self.write_event('First line\nSecond line: $(echo injected) "quotes" <b>text</b>')
        response = self.response()

        with patch("notify_pi.urlopen", return_value=response) as opener:
            notify_pi.send_notification(self.env)

        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        payload = json.loads(request.data)
        self.assertEqual(payload["chat_id"], self.env["TELEGRAM_TO"])
        self.assertNotIn("parse_mode", payload)
        self.assertNotIn(self.token, payload["text"])
        self.assertIn('First line\nSecond line: $(echo injected) "quotes" <b>text</b>', payload["text"])
        self.assertIn("ARM64: тесты и проверка PDF пройдены.", payload["text"])
        self.assertIn(f"proshanti/rit-utils:pi-{self.env['GITHUB_SHA']}", payload["text"])
        self.assertIn("Канал pi обновлён.", payload["text"])
        self.assertIn("раз в 5 минут", payload["text"])
        self.assertIn("https://github.com/PROSHANTI/rit-utils/actions/runs/123456789", payload["text"])
        self.assertEqual(opener.call_args.kwargs["timeout"], 20)
        response.read.assert_called_once_with(notify_pi.MAX_RESPONSE_BYTES + 1)

    def test_failure_has_no_claim_about_publication_or_pi(self) -> None:
        self.env["PI_CI_RESULT"] = "failure"

        message = notify_pi.build_message(self.env)

        self.assertTrue(message.startswith("❌"))
        self.assertIn("сборка для Raspberry Pi не прошла", message)
        self.assertIn(self.env["GITHUB_SHA"], message)
        self.assertIn("Preserve multiline descriptions.", message)
        self.assertIn("/actions/runs/123456789", message)
        for claim in ("опубликован", "обновлён", "пройдены", "раз в 5 минут"):
            self.assertNotIn(claim, message)

    def test_long_unicode_description_is_bounded_and_keeps_link(self) -> None:
        self.write_event("🎉" * 5000 + "\n" + "я" * 5000)

        message = notify_pi.build_message(self.env)

        self.assertLessEqual(len(message), notify_pi.MAX_MESSAGE_LENGTH)
        self.assertLessEqual(len(message.encode("utf-16-le")) // 2, notify_pi.MAX_MESSAGE_LENGTH)
        self.assertIn("…", message)
        self.assertTrue(message.endswith("/actions/runs/123456789"))
        description = message.split("Описание: ", 1)[1].split("\nARM64:", 1)[0]
        self.assertLessEqual(len(description.encode("utf-16-le")) // 2, notify_pi.MAX_DESCRIPTION_LENGTH)

    def test_http_error_does_not_expose_url_or_response_body(self) -> None:
        body = "SECRET RESPONSE BODY"
        error = HTTPError(f"https://api.telegram.org/bot{self.token}/sendMessage", 401, body, Message(), None)

        self.assert_safe_error(error, body)

    def test_http_error_reports_status_code(self) -> None:
        error = HTTPError(f"https://api.telegram.org/bot{self.token}/sendMessage", 401, "Unauthorized", Message(), None)

        with patch("notify_pi.urlopen", side_effect=error):
            with self.assertRaisesRegex(notify_pi.NotificationError, r"^Telegram request failed \(HTTP 401\)\.$"):
                notify_pi.send_notification(self.env)

    def test_network_and_timeout_errors_do_not_expose_secrets(self) -> None:
        for error in (URLError(self.token), TimeoutError(self.token), ValueError(self.token), RuntimeError(self.token)):
            with self.subTest(error=type(error).__name__):
                self.assert_safe_error(error)

    def test_invalid_responses_are_rejected_without_raw_body(self) -> None:
        bodies: tuple[bytes, ...] = (b"not JSON", b"\xff", b"[]", b'{"ok": 1}', b"{}", b"x" * (notify_pi.MAX_RESPONSE_BYTES + 1))
        bodies += (json.dumps({"ok": False, "description": self.token}).encode(),)
        for body in bodies:
            with self.subTest(body=body[:10]), patch("notify_pi.urlopen", return_value=self.response(body)):

                with self.assertRaises(notify_pi.NotificationError) as caught:
                    notify_pi.send_notification(self.env)

                self.assertNotIn(self.token, str(caught.exception))

    def test_non_200_response_is_rejected(self) -> None:
        with patch("notify_pi.urlopen", return_value=self.response(status=503)):
            with self.assertRaisesRegex(notify_pi.NotificationError, r"HTTP 503"):
                notify_pi.send_notification(self.env)

    def test_missing_required_environment_fails_before_network(self) -> None:
        for name in self.env:
            env = self.env.copy()
            del env[name]

            with self.subTest(name=name), patch("notify_pi.urlopen") as opener:
                with self.assertRaises(notify_pi.NotificationError):
                    notify_pi.send_notification(env)

                opener.assert_not_called()

    def test_invalid_environment_fails_without_echoing_values(self) -> None:
        values = {
            "TELEGRAM_TOKEN": "SECRET invalid token",
            "TELEGRAM_TO": "SECRET invalid destination",
            "PI_CI_RESULT": "SECRET invalid result",
            "GITHUB_SHA": "SECRET invalid SHA",
            "GITHUB_REPOSITORY": "SECRET invalid repository",
            "GITHUB_RUN_ID": "SECRET invalid run",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_REF": "refs/heads/main",
        }
        for name, value in values.items():
            env = self.env.copy()
            env[name] = value

            with self.subTest(name=name), patch("notify_pi.urlopen") as opener:
                with self.assertRaises(notify_pi.NotificationError) as caught:
                    notify_pi.send_notification(env)

                self.assertNotIn(value, str(caught.exception))
                opener.assert_not_called()

    def test_channel_username_is_supported(self) -> None:
        self.env["TELEGRAM_TO"] = "@synthetic_channel"

        with patch("notify_pi.urlopen", return_value=self.response()) as opener:
            notify_pi.send_notification(self.env)

        opener.assert_called_once()

    def test_invalid_event_fails_before_network(self) -> None:
        for contents in ("not JSON", "[]", '{"head_commit": []}', '{"head_commit": {"message": 123}}'):
            self.event_path.write_text(contents, encoding="utf-8")

            with self.subTest(contents=contents), patch("notify_pi.urlopen") as opener:
                with self.assertRaises(notify_pi.NotificationError):
                    notify_pi.send_notification(self.env)

                opener.assert_not_called()

    def test_missing_event_file_is_sanitized(self) -> None:
        self.env["GITHUB_EVENT_PATH"] = str(self.event_path.parent / self.token)

        with patch("notify_pi.urlopen") as opener:
            with self.assertRaises(notify_pi.NotificationError) as caught:
                notify_pi.send_notification(self.env)

            self.assertNotIn(self.token, str(caught.exception))
            opener.assert_not_called()

    def test_missing_commit_description_uses_fallback(self) -> None:
        for contents in ("{}", '{"head_commit": null}', '{"head_commit": {}}', '{"head_commit": {"message": ""}}'):
            self.event_path.write_text(contents, encoding="utf-8")

            with self.subTest(contents=contents):
                message = notify_pi.build_message(self.env)

                self.assertIn("Описание: N/A", message)

    def test_invalid_unicode_description_is_sanitized(self) -> None:
        self.event_path.write_text('{"head_commit": {"message": "\\ud800"}}', encoding="utf-8")

        with self.assertRaisesRegex(notify_pi.NotificationError, "description is invalid"):
            notify_pi.build_message(self.env)

    def test_main_reads_environment_and_logs_only_safe_errors(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()

        with (
            patch.dict("os.environ", self.env, clear=True),
            patch("notify_pi.urlopen", side_effect=URLError(self.token)),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = notify_pi.main()

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "Telegram request failed.\n")
        self.assertNotIn(self.token, stderr.getvalue())

    def test_main_success_is_generic(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()

        with (
            patch.dict("os.environ", self.env, clear=True),
            patch("notify_pi.urlopen", return_value=self.response()),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = notify_pi.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "Pi CI Telegram notification sent.\n")
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
