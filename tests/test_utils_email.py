"""
Tests for send_email/email_handler.py module
"""

import base64
import logging
import smtplib
from email.message import Message
from http.cookies import SimpleCookie
from typing import TypedDict
from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse

from src.utils.send_email.email_handler import EmailHandler, EmailService, PaymentReport, SMTPSettings
from src.utils.send_email.email_templates import get_email_template
from src.utils.send_email.email_templates_examples import get_email_template as get_example_email_template


class PaymentArguments(TypedDict, total=False):
    cashless_pay: str | None
    card_pay: str | None
    qr_pay: str | None
    cash_pay: str | None


def get_email_status(response: RedirectResponse) -> str:
    cookies = SimpleCookie()
    cookies.load(response.headers["set-cookie"])
    return base64.b64decode(cookies["email_status"].value).decode("utf-8")


def assert_logged_exception(caplog: pytest.LogCaptureFixture, message: str, exception: Exception) -> None:
    error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    error_record = error_records[0]
    assert error_record.name == "src.utils.send_email.email_handler"
    assert error_record.getMessage() == message
    assert error_record.exc_info is not None
    assert error_record.exc_info[0] is type(exception)
    assert error_record.exc_info[1] is exception
    assert error_record.exc_info[2] is not None


class TestEmailTemplates:
    """Tests for email templates"""

    def test_get_email_template(self):
        """Test getting email template"""
        template = get_email_template()

        assert isinstance(template, str)
        assert "{body_cashless}" in template
        assert "{body_card}" in template
        assert "{body_qr}" in template
        assert "{body_cash}" in template
        assert "Добрый вечер!" in template
        assert "С уважением" in template


class TestSMTPSettings:
    def test_from_env_reads_settings_without_exposing_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        expected_password = "smtp-test-password"
        monkeypatch.setenv("SEND_FROM", "sender@example.com")
        monkeypatch.setenv("EMAIL_PASS", expected_password)
        monkeypatch.setenv("ADDR_TO", "recipient@example.com")
        monkeypatch.setenv("BCC_TO", "copy@example.com")

        settings = SMTPSettings.from_env()

        assert settings.sender == "sender@example.com"
        assert settings.password == expected_password
        assert settings.recipient == "recipient@example.com"
        assert settings.bcc == "copy@example.com"
        assert expected_password not in repr(settings)
        assert expected_password not in repr(EmailService(settings=settings))
        assert expected_password not in repr(EmailHandler(service=EmailService(settings=settings)))

    @pytest.mark.parametrize(
        ("variable_name", "field_name"),
        [
            pytest.param("SEND_FROM", "sender", id="missing-sender"),
            pytest.param("EMAIL_PASS", "password", id="missing-password"),
            pytest.param("ADDR_TO", "recipient", id="missing-recipient"),
            pytest.param("BCC_TO", "bcc", id="missing-bcc"),
        ],
    )
    def test_from_env_defaults_missing_values_to_empty_strings(
        self, monkeypatch: pytest.MonkeyPatch, variable_name: str, field_name: str
    ) -> None:
        monkeypatch.delenv(variable_name, raising=False)

        settings = SMTPSettings.from_env()

        assert getattr(settings, field_name) == ""


class TestPaymentReport:
    @pytest.mark.parametrize(
        ("report", "expected_body"),
        [
            pytest.param(PaymentReport(), "", id="missing-payments"),
            pytest.param(PaymentReport(cashless="", card="", qr="", cash=""), "", id="empty-payments"),
            pytest.param(
                PaymentReport(cashless="39.000", card=None, qr="22.300", cash=""),
                "Безналичная оплата: 39.000\nQR-код: 22.300\n",
                id="omits-missing-and-empty-payments",
            ),
            pytest.param(PaymentReport(card="0"), "На карту: 0\n", id="preserves-zero-payment"),
        ],
    )
    def test_render_formats_only_present_payments(self, report: PaymentReport, expected_body: str) -> None:
        template = "{body_cashless}{body_card}{body_qr}{body_cash}"

        body = report.render(template)

        assert body == expected_body


class TestEmailService:
    def test_build_message_preserves_headers_and_attachment(self) -> None:
        service = EmailService(
            settings=SMTPSettings(sender="sender@example.com", password="test-password", recipient="recipient@example.com")
        )
        attachment_content = b"attachment bytes"

        message = service.build_message(
            report=PaymentReport(card="0"), attachment_content=attachment_content, date_label="01.01.26"
        )

        assert message["From"] == "sender@example.com"
        assert message["To"] == "recipient@example.com"
        assert message["Subject"] == "01.01.26"
        attachment_part = message.get_payload(1)
        assert isinstance(attachment_part, Message)
        assert attachment_part.get_filename() == "01.01.26.xlsx"
        assert attachment_part.get_payload(decode=True) == attachment_content

    def test_send_uses_configured_smtp_timeout(self, mock_file_upload: MagicMock, mock_smtp: MagicMock) -> None:
        service = EmailService(
            settings=SMTPSettings(
                sender="sender@example.com",
                password="test-password",
                recipient="recipient@example.com",
                host="mail.example.com",
                port=2465,
                timeout=12.0,
            )
        )

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp) as mock_transport:
            service.send(report=PaymentReport(card="0"), attachment=mock_file_upload.file)

        mock_transport.assert_called_once_with("mail.example.com", 2465, timeout=12.0)
        mock_smtp.send_message.assert_called_once()
        mock_smtp.quit.assert_called_once()
        mock_smtp.close.assert_called_once()

    @pytest.mark.parametrize(
        "failing_operation",
        [pytest.param("send_message", id="send-failure"), pytest.param("quit", id="quit-failure")],
    )
    def test_send_closes_connection_after_smtp_failure(
        self,
        mock_file_upload: MagicMock,
        mock_smtp: MagicMock,
        caplog: pytest.LogCaptureFixture,
        failing_operation: str,
    ) -> None:
        service = EmailService(settings=SMTPSettings.from_env())
        smtp_exception = smtplib.SMTPException("SMTP operation failed")
        getattr(mock_smtp, failing_operation).side_effect = smtp_exception

        status = service.send(report=PaymentReport(card="0"), attachment=mock_file_upload.file)

        assert status == "Ошибка отправки письма. Подробности — в логах сервера"
        assert_logged_exception(caplog, "Не удалось отправить письмо", smtp_exception)
        mock_smtp.close.assert_called_once()


@pytest.mark.parametrize(
    ("message", "expected_message"),
    [
        pytest.param("( долг)", "(долг)", id="space-after-opening-parenthesis"),
        pytest.param("(долг )", "(долг)", id="space-before-closing-parenthesis"),
        pytest.param("(   долг   )", "(долг)", id="multiple-spaces"),
        pytest.param("(\t долг \t)", "(долг)", id="tabs-and-spaces"),
        pytest.param("( ( долг ) )", "((долг))", id="nested-parentheses"),
        pytest.param(
            "  На карту: 35.500  ( долг  за крем )  ",
            "  На карту: 35.500  (долг  за крем)  ",
            id="preserves-other-spaces",
        ),
        pytest.param("( \nдолг\n )", "(\nдолг\n)", id="preserves-line-breaks"),
        pytest.param("(\r\nдолг\r\n)", "(\r\nдолг\r\n)", id="preserves-crlf-line-breaks"),
        pytest.param("( )", "()", id="empty-parentheses"),
        pytest.param("", "", id="empty-message"),
        pytest.param("На карту: 35.500 (долг)", "На карту: 35.500 (долг)", id="already-formatted"),
        pytest.param("Добрый вечер!\n\nНаличные: 22.600", "Добрый вечер!\n\nНаличные: 22.600", id="without-parentheses"),
        pytest.param("( долг ) и ( за крем )", "(долг) и (за крем)", id="multiple-parenthesis-groups"),
        pytest.param("( долг )( за крем )", "(долг)(за крем)", id="adjacent-parenthesis-groups"),
        pytest.param(
            "\tНа карту:\t35.500\t( долг )\t",
            "\tНа карту:\t35.500\t(долг)\t",
            id="preserves-tabs-outside-parentheses",
        ),
        pytest.param(" \t  \t ", " \t  \t ", id="preserves-whitespace-only-message"),
        pytest.param(
            "Добрый вечер!\n\n"
            "Безналичная оплата: 39.000\n"
            "На карту: 35.500 ( долг )\n"
            "QR-код: 22.300\n"
            "Наличные: 22.600 ( за крем )\n\n"
            "С уважением,\n"
            "Администратор",
            "Добрый вечер!\n\n"
            "Безналичная оплата: 39.000\n"
            "На карту: 35.500 (долг)\n"
            "QR-код: 22.300\n"
            "Наличные: 22.600 (за крем)\n\n"
            "С уважением,\n"
            "Администратор",
            id="full-report-preserves-blank-lines",
        ),
    ],
)
def test_normalize_message_removes_only_inside_padding(message: str, expected_message: str) -> None:
    normalized_message = EmailService._normalize_message(message)
    renormalized_message = EmailService._normalize_message(normalized_message)

    assert normalized_message == expected_message
    assert renormalized_message == expected_message


class TestEmailHandler:
    """Tests for email handler"""

    def test_send_email_handler_success(
        self,
        mock_file_upload: MagicMock,
        mock_smtp: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test successful email sending"""
        caplog.set_level(logging.INFO, logger="src.utils.send_email.email_handler")

        result = EmailHandler().handle(
            qr_pay="1000",
            cashless_pay="2000",
            card_pay="3000",
            cash_pay="4000",
            attachment=mock_file_upload,
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/send_email"
        assert result.status_code == 303

        mock_smtp.login.assert_called_once()
        mock_smtp.send_message.assert_called_once()
        mock_smtp.quit.assert_called_once()
        mock_smtp.close.assert_called_once()
        email_records = [record for record in caplog.records if record.name == "src.utils.send_email.email_handler"]
        assert [(record.name, record.levelno, record.getMessage()) for record in email_records] == [
            ("src.utils.send_email.email_handler", logging.INFO, "Начата отправка письма"),
            ("src.utils.send_email.email_handler", logging.INFO, "Письмо успешно отправлено"),
        ]

    @pytest.mark.parametrize(
        ("payment_arguments", "expected_body"),
        [
            pytest.param({}, "Отчёт:\nКонец", id="default-optional-payments"),
            pytest.param(
                {"cashless_pay": "", "card_pay": "", "qr_pay": "", "cash_pay": ""},
                "Отчёт:\nКонец",
                id="empty-payments",
            ),
            pytest.param(
                {"cashless_pay": "39.000", "card_pay": None, "qr_pay": "22.300", "cash_pay": ""},
                "Отчёт:\nБезналичная оплата: 39.000\nQR-код: 22.300\nКонец",
                id="partially-filled-report",
            ),
        ],
    )
    def test_send_email_handler_omits_missing_payments(
        self,
        mock_file_upload: MagicMock,
        mock_smtp: MagicMock,
        payment_arguments: PaymentArguments,
        expected_body: str,
    ) -> None:
        """Test email sending with empty values"""
        template = "Отчёт:\n{body_cashless}{body_card}{body_qr}{body_cash}Конец"

        with patch("src.utils.send_email.email_handler.get_email_template", return_value=template):
            result = EmailHandler().handle(
                attachment=mock_file_upload,
                **payment_arguments,
            )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/send_email"
        assert result.status_code == 303
        mock_smtp.send_message.assert_called_once()
        message = mock_smtp.send_message.call_args.args[0]
        text_part = message.get_payload(0)
        assert text_part.get_payload(decode=True).decode("utf-8") == expected_body

    @pytest.mark.parametrize(
        ("smtp_code", "smtp_error", "expected_status"),
        [
            pytest.param(
                535,
                b"Authentication failed",
                "Ошибка отправки: проверьте настройки доступа к почте",
                id="invalid-credentials",
            ),
            pytest.param(
                525,
                b"5.7.0 SMTP disabled for this mailbox",
                "Ошибка отправки: SMTP отключён для этого почтового ящика",
                id="smtp-disabled-bytes",
            ),
            pytest.param(
                525,
                "5.7.0 SMTP disabled for this mailbox",
                "Ошибка отправки: SMTP отключён для этого почтового ящика",
                id="smtp-disabled-string",
            ),
            pytest.param(
                525,
                b"Another authentication error",
                "Ошибка отправки: проверьте настройки доступа к почте",
                id="other-525-error",
            ),
        ],
    )
    def test_send_email_handler_smtp_auth_error(
        self,
        mock_file_upload: MagicMock,
        mock_smtp: MagicMock,
        caplog: pytest.LogCaptureFixture,
        smtp_code: int,
        smtp_error: bytes | str,
        expected_status: str,
    ) -> None:
        """Test SMTP authentication error handling"""
        smtp_exception = smtplib.SMTPAuthenticationError(smtp_code, smtp_error)
        mock_smtp.login.side_effect = smtp_exception

        result = EmailHandler().handle(
            qr_pay="1000",
            cashless_pay="2000",
            card_pay="3000",
            cash_pay="4000",
            attachment=mock_file_upload,
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/send_email"
        assert result.status_code == 303
        assert get_email_status(result) == expected_status
        assert_logged_exception(caplog, "SMTP отклонил авторизацию", smtp_exception)
        mock_smtp.send_message.assert_not_called()
        mock_smtp.close.assert_called_once()

    def test_send_email_handler_general_error(
        self,
        mock_file_upload: MagicMock,
        mock_smtp: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test general error handling"""
        smtp_exception = Exception("Network error")
        mock_smtp.login.side_effect = smtp_exception

        result = EmailHandler().handle(
            qr_pay="1000",
            cashless_pay="2000",
            card_pay="3000",
            cash_pay="4000",
            attachment=mock_file_upload,
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/send_email"
        assert result.status_code == 303
        assert get_email_status(result) == "Ошибка отправки письма. Подробности — в логах сервера"
        assert_logged_exception(caplog, "Не удалось отправить письмо", smtp_exception)
        mock_smtp.send_message.assert_not_called()
        mock_smtp.close.assert_called_once()

    @patch("src.utils.send_email.email_handler.datetime")
    def test_send_email_handler_datetime_formatting(self, mock_datetime, mock_file_upload, mock_smtp):
        """Test correct date and time formatting"""
        mock_now = MagicMock()
        mock_now.strftime.side_effect = lambda fmt: "15:30" if fmt == "%H:%M" else "01.01.23"
        mock_datetime.datetime.now.return_value = mock_now

        result = EmailHandler().handle(
            qr_pay="1000",
            cashless_pay="2000",
            card_pay="3000",
            cash_pay="4000",
            attachment=mock_file_upload,
        )

        assert isinstance(result, RedirectResponse)
        mock_datetime.datetime.now.assert_called()

    def test_send_email_handler_file_processing(self, mock_smtp):
        """Test uploaded file processing"""
        mock_file = MagicMock()
        mock_file.file.read.return_value = b"Excel file content"
        mock_file.filename = "report.xlsx"

        result = EmailHandler().handle(
            qr_pay="1000", cashless_pay="2000", card_pay="3000", cash_pay="4000", attachment=mock_file
        )

        assert isinstance(result, RedirectResponse)
        mock_file.file.read.assert_called_once()

    def test_send_email_body_formatting(self, mock_file_upload: MagicMock, mock_smtp: MagicMock) -> None:
        expected_body = """Добрый вечер!

Безналичная оплата: 39.000
На карту: 35.500 (долг Орел)
QR-код: 22.300
Наличные: 22.600 (Захцер за крем)

С уважением, Анастасия
Администратор
ReInTa Clinic
ООО "ФЭМИЛИС"
Москва, Новолесной переулок 5
тел.: +7(499)110-37-77"""

        with patch("src.utils.send_email.email_handler.get_email_template", return_value=get_example_email_template()):
            result = EmailHandler().handle(
                qr_pay="22.300",
                cashless_pay="39.000",
                card_pay="35.500 ( долг Орел)",
                cash_pay="22.600 ( Захцер за крем)",
                attachment=mock_file_upload,
            )

        assert isinstance(result, RedirectResponse)
        mock_smtp.send_message.assert_called_once()
        message = mock_smtp.send_message.call_args.args[0]
        text_part = message.get_payload(0)
        assert text_part.get_content_type() == "text/plain"
        assert text_part.get_payload(decode=True).decode("utf-8") == expected_body

    @pytest.mark.parametrize(
        ("card_payment", "expected_card_payment"),
        [
            pytest.param("35.500 ( долг )", "35.500 (долг)", id="normalizes-padding"),
            pytest.param("35.500 (долг)", "35.500 (долг)", id="preserves-formatted-body"),
        ],
    )
    def test_send_email_sends_normalized_mime_body(
        self,
        mock_file_upload: MagicMock,
        mock_smtp: MagicMock,
        card_payment: str,
        expected_card_payment: str,
    ) -> None:
        template = "Добрый вечер!\n\n{body_cashless}{body_card}{body_qr}{body_cash}\nС уважением"
        expected_body = (
            "Добрый вечер!\n\n"
            "Безналичная оплата: 39.000\n"
            f"На карту: {expected_card_payment}\n"
            "QR-код: 22.300\n"
            "Наличные: 22.600\n"
            "\nС уважением"
        )

        with patch("src.utils.send_email.email_handler.get_email_template", return_value=template):
            result = EmailHandler().handle(
                qr_pay="22.300",
                cashless_pay="39.000",
                card_pay=card_payment,
                cash_pay="22.600",
                attachment=mock_file_upload,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        mock_smtp.send_message.assert_called_once()
        sent_message = mock_smtp.send_message.call_args.args[0]
        body_part = sent_message.get_payload(0)
        sent_body = body_part.get_payload(decode=True).decode(body_part.get_content_charset())
        assert body_part.get_content_type() == "text/plain"
        assert sent_body == expected_body
