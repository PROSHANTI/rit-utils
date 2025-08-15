"""
Тесты для модуля двухфакторной аутентификации two_factor.py
"""
import pytest
from unittest.mock import patch, MagicMock
import pyotp
from fastapi.responses import RedirectResponse

from src.auth.two_factor import (
    generate_totp_secret,
    get_user_secret,
    get_totp_uri,
    generate_qr_code,
    verify_totp,
    two_factor_handler,
    show_two_factor_page,
    is_2fa_verified,
    clear_2fa_verification,
    USER_SECRETS
)


class TestTotpSecrets:
    """Тесты для генерации и управления TOTP секретами"""
    
    def test_generate_totp_secret(self):
        """Тест генерации TOTP секрета"""
        secret = generate_totp_secret()
        
        assert isinstance(secret, str)
        assert len(secret) == 32  # Base32 секрет должен быть 32 символа
        assert secret.isalnum()  # Только буквы и цифры
    
    def test_get_user_secret_new_user(self):
        """Тест получения секрета для нового пользователя"""
        username = "new_user"
        secret = get_user_secret(username)
        
        assert isinstance(secret, str)
        assert username in USER_SECRETS
        assert USER_SECRETS[username] == secret
    
    def test_get_user_secret_existing_user(self):
        """Тест получения секрета для существующего пользователя"""
        username = "existing_user"
        original_secret = "EXISTING32CHARACTERSECRETTEST123"
        USER_SECRETS[username] = original_secret
        
        secret = get_user_secret(username)
        
        assert secret == original_secret
    
    def test_get_user_secret_no_generation(self):
        """Тест получения секрета без генерации"""
        username = "no_gen_user"
        secret = get_user_secret(username, generate_if_missing=False)
        
        # Должен вернуть базовый TOTP_SECRET или пустую строку
        assert isinstance(secret, str)
        assert username not in USER_SECRETS
    
    def test_get_totp_uri(self):
        """Тест генерации URI для QR-кода"""
        username = "test_user"
        secret = "TEST32CHARACTERSECRETFORQRCODE12"
        
        uri = get_totp_uri(username, secret)
        
        assert isinstance(uri, str)
        assert "otpauth://totp/" in uri
        assert username in uri
        assert "RIT-UTILS" in uri
        assert secret in uri
    
    def test_get_totp_uri_auto_secret(self):
        """Тест генерации URI с автоматическим получением секрета"""
        username = "auto_secret_user"
        
        uri = get_totp_uri(username)
        
        assert isinstance(uri, str)
        assert "otpauth://totp/" in uri
        assert username in uri


class TestQrCodeGeneration:
    """Тесты для генерации QR-кодов"""
    
    @patch('src.auth.two_factor.qrcode.QRCode')
    def test_generate_qr_code_success(self, mock_qr_code):
        """Тест успешной генерации QR-кода"""
        # Настройка мока
        mock_qr = MagicMock()
        mock_img = MagicMock()
        mock_qr_code.return_value = mock_qr
        mock_qr.make_image.return_value = mock_img
        
        # Мок для BytesIO
        with patch('src.auth.two_factor.BytesIO') as mock_bytesio:
            mock_buffer = MagicMock()
            mock_bytesio.return_value = mock_buffer
            mock_buffer.getvalue.return_value = b"fake_image_data"
            
            # Мок для base64
            with patch('src.auth.two_factor.base64.b64encode') as mock_b64:
                mock_b64.return_value = b"ZmFrZV9pbWFnZV9kYXRh"
                
                uri = "otpauth://totp/test"
                result = generate_qr_code(uri)
                
                assert result == "ZmFrZV9pbWFnZV9kYXRh"
                mock_qr.add_data.assert_called_once_with(uri)
                mock_qr.make.assert_called_once()
    
    @patch('src.auth.two_factor.qrcode.QRCode')
    def test_generate_qr_code_error(self, mock_qr_code):
        """Тест обработки ошибки при генерации QR-кода"""
        mock_qr_code.side_effect = Exception("QR code error")
        
        uri = "otpauth://totp/test"
        result = generate_qr_code(uri)
        
        assert result == ""


class TestTotpVerification:
    """Тесты для верификации TOTP токенов"""
    
    @patch('src.auth.two_factor.pyotp.TOTP')
    def test_verify_totp_success(self, mock_totp_class):
        """Тест успешной верификации TOTP"""
        mock_totp = MagicMock()
        mock_totp_class.return_value = mock_totp
        mock_totp.verify.return_value = True
        
        result = verify_totp("123456", "test_user", "TEST_SECRET")
        
        assert result is True
        mock_totp.verify.assert_called_once_with("123456", valid_window=40)
    
    @patch('src.auth.two_factor.pyotp.TOTP')
    @patch('time.time')
    def test_verify_totp_timezone_fallback(self, mock_time, mock_totp_class):
        """Тест верификации TOTP с проверкой часовых поясов"""
        mock_totp = MagicMock()
        mock_totp_class.return_value = mock_totp
        mock_totp.verify.return_value = False
        mock_totp.at.side_effect = lambda t: "123456" if t == 3600 else "000000"
        mock_time.return_value = 0
        
        result = verify_totp("123456", "test_user", "TEST_SECRET")
        
        assert result is True
    
    @patch('src.auth.two_factor.pyotp.TOTP')
    def test_verify_totp_failure(self, mock_totp_class):
        """Тест неуспешной верификации TOTP"""
        mock_totp = MagicMock()
        mock_totp_class.return_value = mock_totp
        mock_totp.verify.return_value = False
        mock_totp.at.return_value = "000000"  # Неправильный код
        
        result = verify_totp("123456", "test_user", "TEST_SECRET")
        
        assert result is False
    
    @patch('src.auth.two_factor.pyotp.TOTP')
    def test_verify_totp_exception(self, mock_totp_class):
        """Тест обработки исключения при верификации"""
        mock_totp_class.side_effect = Exception("TOTP error")
        
        result = verify_totp("123456", "test_user", "TEST_SECRET")
        
        assert result is False


class TestTwoFactorHandler:
    """Тесты для обработчика двухфакторной аутентификации"""
    
    @patch('src.auth.two_factor.pyotp.TOTP')
    def test_two_factor_handler_success(self, mock_totp_class, mock_request):
        """Тест успешной обработки 2FA"""
        mock_totp = MagicMock()
        mock_totp_class.return_value = mock_totp
        mock_totp.verify.return_value = True
        
        result = two_factor_handler(mock_request, "123456")
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/setup-session"
        assert result.status_code == 303
    
    @patch('src.auth.two_factor.pyotp.TOTP')
    def test_two_factor_handler_invalid_token(self, mock_totp_class, mock_request):
        """Тест обработки 2FA с невалидным токеном"""
        mock_totp = MagicMock()
        mock_totp_class.return_value = mock_totp
        mock_totp.verify.return_value = False
        mock_totp.at.return_value = "000000"  # Неправильный код
        
        result = two_factor_handler(mock_request, "123456")
        
        assert hasattr(result, 'status_code')
        assert result.status_code == 401
    
    @patch('src.auth.two_factor.pyotp.TOTP')
    @patch('time.time')
    def test_two_factor_handler_timezone_success(self, mock_time, mock_totp_class, mock_request):
        """Тест успешной 2FA с проверкой часовых поясов"""
        mock_totp = MagicMock()
        mock_totp_class.return_value = mock_totp
        mock_totp.verify.return_value = False
        mock_totp.at.side_effect = lambda t: "123456" if t == 3600 else "000000"
        mock_time.return_value = 0
        
        result = two_factor_handler(mock_request, "123456")
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/setup-session"
        assert result.status_code == 303


class TestTwoFactorPages:
    """Тесты для страниц двухфакторной аутентификации"""
    
    def test_show_two_factor_page(self, mock_request):
        """Тест отображения страницы 2FA"""
        result = show_two_factor_page(mock_request)
        
        # Проверяем, что возвращается TemplateResponse
        assert hasattr(result, 'status_code')
    
    def test_is_2fa_verified_true(self, mock_request):
        """Тест проверки верификации 2FA (успешная)"""
        mock_request.cookies = {"2fa_verified": "true"}
        
        result = is_2fa_verified(mock_request)
        
        assert result is True
    
    def test_is_2fa_verified_false(self, mock_request):
        """Тест проверки верификации 2FA (неуспешная)"""
        mock_request.cookies = {"2fa_verified": "false"}
        
        result = is_2fa_verified(mock_request)
        
        assert result is False
    
    def test_is_2fa_verified_missing(self, mock_request):
        """Тест проверки верификации 2FA (отсутствует cookie)"""
        mock_request.cookies = {}
        
        result = is_2fa_verified(mock_request)
        
        assert result is False
    
    def test_clear_2fa_verification(self, mock_request):
        """Тест очистки верификации 2FA"""
        result = clear_2fa_verification(mock_request)
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/"
        assert result.status_code == 303
