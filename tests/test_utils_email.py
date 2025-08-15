"""
Тесты для модуля send_email/email_handler.py
"""
import pytest
from unittest.mock import patch, MagicMock
import smtplib
from fastapi.responses import RedirectResponse

from src.utils.send_email.email_handler import send_email_handler
from src.utils.send_email.email_templates import get_email_template


class TestEmailTemplates:
    """Тесты для email шаблонов"""
    
    def test_get_email_template(self):
        """Тест получения шаблона email"""
        template = get_email_template()
        
        assert isinstance(template, str)
        assert "{body_cashless}" in template
        assert "{body_card}" in template
        assert "{body_qr}" in template
        assert "{body_cash}" in template
        assert "Добрый вечер!" in template
        assert "С уважением" in template


class TestEmailHandler:
    """Тесты для обработчика отправки email"""
    
    def test_send_email_handler_success(self, mock_request, mock_file_upload, mock_smtp):
        """Тест успешной отправки email"""
        result = send_email_handler(
            request=mock_request,
            qr_pay="1000",
            cashless_pay="2000", 
            card_pay="3000",
            cash_pay="4000",
            attachment=mock_file_upload
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/send_email"
        assert result.status_code == 303
        
        # Проверяем, что SMTP был вызван
        mock_smtp.login.assert_called_once()
        mock_smtp.send_message.assert_called_once()
        mock_smtp.quit.assert_called_once()
    
    def test_send_email_handler_empty_values(self, mock_request, mock_file_upload, mock_smtp):
        """Тест отправки email с пустыми значениями"""
        result = send_email_handler(
            request=mock_request,
            qr_pay=None,
            cashless_pay=None,
            card_pay=None,
            cash_pay=None,
            attachment=mock_file_upload
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/send_email"
        assert result.status_code == 303
    
    def test_send_email_handler_smtp_auth_error(self, mock_request, mock_file_upload, mock_smtp):
        """Тест обработки ошибки аутентификации SMTP"""
        mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, "Authentication failed")
        
        result = send_email_handler(
            request=mock_request,
            qr_pay="1000",
            cashless_pay="2000",
            card_pay="3000", 
            cash_pay="4000",
            attachment=mock_file_upload
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/send_email"
        assert result.status_code == 303
    
    def test_send_email_handler_general_error(self, mock_request, mock_file_upload, mock_smtp):
        """Тест обработки общей ошибки отправки"""
        mock_smtp.login.side_effect = Exception("Network error")
        
        result = send_email_handler(
            request=mock_request,
            qr_pay="1000",
            cashless_pay="2000",
            card_pay="3000",
            cash_pay="4000", 
            attachment=mock_file_upload
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/send_email"
        assert result.status_code == 303
    
    @patch('src.utils.send_email.email_handler.datetime')
    def test_send_email_handler_datetime_formatting(self, mock_datetime, mock_request, mock_file_upload, mock_smtp):
        """Тест корректного форматирования даты и времени"""
        # Настройка мока для datetime
        mock_now = MagicMock()
        mock_now.strftime.side_effect = lambda fmt: "15:30" if fmt == "%H:%M" else "01.01.23"
        mock_datetime.datetime.now.return_value = mock_now
        
        result = send_email_handler(
            request=mock_request,
            qr_pay="1000",
            cashless_pay="2000",
            card_pay="3000",
            cash_pay="4000",
            attachment=mock_file_upload
        )
        
        assert isinstance(result, RedirectResponse)
        # Проверяем, что datetime.now() был вызван
        mock_datetime.datetime.now.assert_called()
    
    def test_send_email_handler_file_processing(self, mock_request, mock_smtp):
        """Тест обработки загружаемого файла"""
        # Создаем мок файла с более подробными настройками
        mock_file = MagicMock()
        mock_file.file.read.return_value = b"Excel file content"
        mock_file.filename = "report.xlsx"
        
        result = send_email_handler(
            request=mock_request,
            qr_pay="1000",
            cashless_pay="2000",
            card_pay="3000",
            cash_pay="4000",
            attachment=mock_file
        )
        
        assert isinstance(result, RedirectResponse)
        # Проверяем, что файл был прочитан
        mock_file.file.read.assert_called_once()
    
    def test_send_email_body_formatting(self, mock_request, mock_file_upload, mock_smtp):
        """Тест форматирования тела письма"""
        with patch('src.utils.send_email.email_handler.get_email_template') as mock_template:
            mock_template.return_value = "Test: {body_cashless}{body_card}{body_qr}{body_cash}"
            
            result = send_email_handler(
                request=mock_request,
                qr_pay="1000",
                cashless_pay="2000",
                card_pay="3000",
                cash_pay="4000",
                attachment=mock_file_upload
            )
            
            assert isinstance(result, RedirectResponse)
            mock_template.assert_called_once()
