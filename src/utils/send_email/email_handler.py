import base64
import datetime
import logging
import os
import re
import smtplib
from contextlib import closing
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import BinaryIO

from fastapi import UploadFile
from fastapi.responses import RedirectResponse

from src.utils.send_email.email_templates import get_email_template

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentReport:
    cashless: str | None = None
    card: str | None = None
    qr: str | None = None
    cash: str | None = None

    def render(self, template: str) -> str:
        payments = (
            ("body_cashless", "Безналичная оплата", self.cashless),
            ("body_card", "На карту", self.card),
            ("body_qr", "QR-код", self.qr),
            ("body_cash", "Наличные", self.cash),
        )
        body_values = {name: f"{label}: {amount}\n" if amount else "" for name, label, amount in payments}
        return template.format(**body_values)


@dataclass(frozen=True, slots=True, kw_only=True)
class SMTPSettings:
    sender: str
    password: str = field(repr=False)
    recipient: str
    bcc: str = ""
    host: str = "smtp.yandex.ru"
    port: int = 465
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "SMTPSettings":
        return cls(
            sender=os.getenv("SEND_FROM") or "",
            password=os.getenv("EMAIL_PASS") or "",
            recipient=os.getenv("ADDR_TO") or "",
            bcc=os.getenv("BCC_TO") or "",
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class EmailService:
    settings: SMTPSettings

    def build_message(self, *, report: PaymentReport, attachment_content: bytes, date_label: str) -> MIMEMultipart:
        message = MIMEMultipart()
        message["From"] = self.settings.sender
        message["To"] = self.settings.recipient
        message["Subject"] = date_label
        message["Bcc"] = self.settings.bcc
        body = report.render(get_email_template())
        message.attach(MIMEText(self._normalize_message(body), "plain"))

        attachment_part = MIMEApplication(attachment_content, Name=f"{date_label}.xlsx")
        attachment_part["Content-Disposition"] = f'attachment; filename="{date_label}.xlsx"'
        message.attach(attachment_part)
        return message

    def send(self, *, report: PaymentReport, attachment: BinaryIO) -> str:
        logger.info("Начата отправка письма")
        sent_at = datetime.datetime.now()

        try:
            message = self.build_message(
                report=report,
                attachment_content=attachment.read(),
                date_label=sent_at.strftime("%d.%m.%y"),
            )

            with closing(smtplib.SMTP_SSL(self.settings.host, self.settings.port, timeout=self.settings.timeout)) as server:
                server.login(self.settings.sender, self.settings.password)
                server.send_message(message)
                server.quit()

        except smtplib.SMTPAuthenticationError as exc:
            logger.exception("SMTP отклонил авторизацию")
            smtp_error = exc.smtp_error
            smtp_error_text = smtp_error.decode("utf-8", errors="replace") if isinstance(smtp_error, bytes) else smtp_error

            if exc.smtp_code == 525 and "SMTP disabled" in smtp_error_text:
                return "Ошибка отправки: SMTP отключён для этого почтового ящика"

            return "Ошибка отправки: проверьте настройки доступа к почте"

        except Exception:
            logger.exception("Не удалось отправить письмо")
            return "Ошибка отправки письма. Подробности — в логах сервера"

        logger.info("Письмо успешно отправлено")
        return f"Письмо успешно отправлено в {sent_at.strftime('%H:%M')}"

    @staticmethod
    def _normalize_message(message: str) -> str:
        """Убирает пробелы и табуляцию после «(» и перед «)», сохраняя остальное форматирование сообщения."""

        logger.debug("Нормализация пробелов внутри скобок")

        def replace_spacing(match: re.Match[str]) -> str:
            before = message[match.start() - 1 : match.start()]
            after = message[match.end() : match.end() + 1]

            if before == "(" or after == ")":
                return ""

            return match.group()

        return re.sub(r"[ \t]+", replace_spacing, message)


@dataclass(frozen=True, slots=True, kw_only=True)
class EmailHandler:
    service: EmailService = field(
        default_factory=lambda: EmailService(settings=SMTPSettings.from_env()),
        repr=False,
    )

    def handle(
        self,
        *,
        attachment: UploadFile,
        qr_pay: str | None = None,
        cashless_pay: str | None = None,
        card_pay: str | None = None,
        cash_pay: str | None = None,
    ) -> RedirectResponse:
        report = PaymentReport(cashless=cashless_pay, card=card_pay, qr=qr_pay, cash=cash_pay)
        status = self.service.send(report=report, attachment=attachment.file)
        response = RedirectResponse(url="/send_email", status_code=303)
        encoded_status = base64.b64encode(status.encode("utf-8")).decode("ascii")
        response.set_cookie("email_status", encoded_status, max_age=10)
        return response
