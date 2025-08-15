"""
Тесты для модуля gen_cert/gen_cert_handler.py
"""
import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from fastapi.responses import FileResponse, RedirectResponse

from src.utils.gen_cert.gen_cert_handler import (
    get_random_number,
    convert_pptx_to_pdf,
    gen_cert_handler
)


class TestRandomNumber:
    """Тесты для генерации случайных номеров"""
    
    def test_get_random_number_range(self):
        """Тест генерации случайного числа в правильном диапазоне"""
        number = get_random_number()
        
        assert isinstance(number, int)
        assert 100000 <= number <= 999999
    
    def test_get_random_number_uniqueness(self):
        """Тест уникальности генерируемых чисел (вероятностный)"""
        numbers = [get_random_number() for _ in range(10)]
        
        # Маловероятно, что все 10 чисел будут одинаковыми
        assert len(set(numbers)) > 1


class TestPptxToPdfConversion:
    """Тесты для конвертации PPTX в PDF"""
    
    @patch('src.utils.gen_cert.gen_cert_handler.subprocess.run')
    def test_convert_pptx_to_pdf_success(self, mock_run, temp_file):
        """Тест успешной конвертации PPTX в PDF"""
        # Создаем временные файлы
        pptx_path = temp_file + ".pptx"
        pdf_path = temp_file + ".pdf"
        
        # Создаем фиктивные файлы
        with open(pptx_path, 'w') as f:
            f.write("fake pptx")
        with open(pdf_path, 'w') as f:
            f.write("fake pdf")
        
        # Настройка мока
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""
        
        # Тест должен пройти без исключений
        try:
            convert_pptx_to_pdf(pptx_path, pdf_path)
        except Exception as e:
            pytest.fail(f"Conversion failed: {e}")
        finally:
            # Очистка
            for path in [pptx_path, pdf_path]:
                if os.path.exists(path):
                    os.unlink(path)
    
    @patch('src.utils.gen_cert.gen_cert_handler.subprocess.run')
    def test_convert_pptx_to_pdf_libreoffice_not_found(self, mock_run):
        """Тест обработки ошибки когда LibreOffice не найден"""
        mock_run.side_effect = FileNotFoundError("LibreOffice not found")
        
        with pytest.raises(Exception, match="LibreOffice не найден"):
            convert_pptx_to_pdf("fake.pptx", "fake.pdf")
    
    @patch('src.utils.gen_cert.gen_cert_handler.subprocess.run')
    def test_convert_pptx_to_pdf_libreoffice_error(self, mock_run, temp_file):
        """Тест обработки ошибки LibreOffice"""
        pptx_path = temp_file + ".pptx"
        pdf_path = temp_file + ".pdf"
        
        # Создаем фиктивный PPTX файл
        with open(pptx_path, 'w') as f:
            f.write("fake pptx")
        
        # Первый вызов для проверки версии - успешен
        # Второй вызов для конвертации - неуспешен
        mock_run.side_effect = [
            MagicMock(returncode=0),  # Проверка версии
            MagicMock(returncode=1, stderr="LibreOffice conversion error")  # Конвертация
        ]
        
        with pytest.raises(Exception, match="LibreOffice error"):
            convert_pptx_to_pdf(pptx_path, pdf_path)
        
        # Очистка
        if os.path.exists(pptx_path):
            os.unlink(pptx_path)
    
    @patch('src.utils.gen_cert.gen_cert_handler.subprocess.run')
    def test_convert_pptx_to_pdf_timeout(self, mock_run):
        """Тест обработки таймаута конвертации"""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # Проверка версии
            TimeoutError("Timeout")  # Конвертация
        ]
        
        with pytest.raises(Exception, match="Ошибка конвертации"):
            convert_pptx_to_pdf("fake.pptx", "fake.pdf")


class TestGenCertHandler:
    """Тесты для обработчика генерации сертификатов"""
    
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    def test_gen_cert_handler_success(self, mock_exists, mock_presentation, mock_convert, mock_request, mock_pptx):
        """Тест успешной генерации сертификата"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx
        
        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price="5000"
        )
        
        assert isinstance(result, FileResponse)
        assert result.filename == "Сертификат.pdf"
        mock_convert.assert_called_once()
    
    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    def test_gen_cert_handler_template_not_found(self, mock_exists, mock_request):
        """Тест обработки отсутствующего шаблона"""
        mock_exists.return_value = False
        
        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price="5000"
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/gen_rit_cert"
        assert result.status_code == 303
    
    def test_gen_cert_handler_invalid_price_too_long(self, mock_request):
        """Тест обработки слишком длинной цены"""
        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price="1234567"  # 7 символов, больше максимума
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/gen_rit_cert"
        assert result.status_code == 303
    
    def test_gen_cert_handler_invalid_price_not_number(self, mock_request):
        """Тест обработки нечислового значения цены"""
        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price="не число"
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/gen_rit_cert"
        assert result.status_code == 303
    
    def test_gen_cert_handler_zero_price(self, mock_request):
        """Тест обработки нулевой цены"""
        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price="0"
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/gen_rit_cert"
        assert result.status_code == 303
    
    def test_gen_cert_handler_negative_price(self, mock_request):
        """Тест обработки отрицательной цены"""
        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов", 
            price="-100"
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/gen_rit_cert"
        assert result.status_code == 303
    
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    def test_gen_cert_handler_empty_values(self, mock_exists, mock_presentation, mock_convert, mock_request, mock_pptx):
        """Тест генерации сертификата с пустыми значениями"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx
        
        result = gen_cert_handler(
            request=mock_request,
            name="",
            price=""
        )
        
        assert isinstance(result, FileResponse)
        mock_convert.assert_called_once()
    
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    def test_gen_cert_handler_none_values(self, mock_exists, mock_presentation, mock_convert, mock_request, mock_pptx):
        """Тест генерации сертификата с None значениями"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx
        
        result = gen_cert_handler(
            request=mock_request,
            name=None,
            price=None
        )
        
        assert isinstance(result, FileResponse)
        mock_convert.assert_called_once()
    
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    def test_gen_cert_handler_presentation_error(self, mock_exists, mock_presentation, mock_request):
        """Тест обработки ошибки при работе с презентацией"""
        mock_exists.return_value = True
        mock_presentation.side_effect = Exception("Presentation error")
        
        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price="5000"
        )
        
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/gen_rit_cert"
        assert result.status_code == 303
