"""
Tests for gen_cert/gen_cert_handler.py module
"""
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import FileResponse, RedirectResponse

from src.utils.gen_cert.gen_cert_handler import (
    convert_pptx_to_pdf,
    gen_cert_handler,
    get_random_number,
)


class TestRandomNumber:
    """Tests for random number generation"""

    def test_get_random_number_range(self):
        """Test random number generation in correct range"""
        number = get_random_number()

        assert isinstance(number, int)
        assert 100000 <= number <= 999999

    def test_get_random_number_uniqueness(self):
        """Test generated numbers uniqueness (probabilistic)"""
        numbers = [get_random_number() for _ in range(10)]

        assert len(set(numbers)) > 1


class TestPptxToPdfConversion:
    """Tests for PPTX to PDF conversion"""

    @patch('src.utils.gen_cert.gen_cert_handler.subprocess.run')
    def test_convert_pptx_to_pdf_success(self, mock_run, temp_file):
        """Test successful PPTX to PDF conversion"""
        pptx_path = temp_file + ".pptx"
        pdf_path = temp_file + ".pdf"

        with open(pptx_path, 'w') as f:
            f.write("fake pptx")
        with open(pdf_path, 'w') as f:
            f.write("fake pdf")

        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        try:
            convert_pptx_to_pdf(pptx_path, pdf_path)
        except Exception as e:
            pytest.fail(f"Conversion failed: {e}")
        finally:
            for path in [pptx_path, pdf_path]:
                if os.path.exists(path):
                    os.unlink(path)

    @patch('src.utils.gen_cert.gen_cert_handler.subprocess.run')
    def test_convert_pptx_to_pdf_libreoffice_not_found(self, mock_run):
        """Test LibreOffice not found error handling"""
        mock_run.side_effect = FileNotFoundError("LibreOffice not found")

        with pytest.raises(Exception, match="LibreOffice не найден"):
            convert_pptx_to_pdf("fake.pptx", "fake.pdf")

    @patch('src.utils.gen_cert.gen_cert_handler.subprocess.run')
    def test_convert_pptx_to_pdf_libreoffice_error(self, mock_run, temp_file):
        """Test LibreOffice error handling"""
        pptx_path = temp_file + ".pptx"
        pdf_path = temp_file + ".pdf"

        with open(pptx_path, 'w') as f:
            f.write("fake pptx")

        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=1, stderr="LibreOffice conversion error")
        ]

        with pytest.raises(Exception, match="LibreOffice error"):
            convert_pptx_to_pdf(pptx_path, pdf_path)

        if os.path.exists(pptx_path):
            os.unlink(pptx_path)

    @patch('src.utils.gen_cert.gen_cert_handler.subprocess.run')
    def test_convert_pptx_to_pdf_timeout(self, mock_run):
        """Test conversion timeout handling"""
        mock_run.side_effect = [
            MagicMock(returncode=0),
            TimeoutError("Timeout")
        ]

        with pytest.raises(Exception, match="Ошибка конвертации"):
            convert_pptx_to_pdf("fake.pptx", "fake.pdf")


class TestGenCertHandler:
    """Tests for certificate generation handler"""

    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    def test_gen_cert_handler_success(self, mock_convert, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test successful certificate generation"""
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
        """Test missing template handling"""
        mock_exists.return_value = False

        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price="5000"
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/gen_rit_cert"
        assert result.status_code == 303

    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    def test_gen_cert_handler_empty_values(self, mock_convert, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test certificate generation with empty values"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx

        result = gen_cert_handler(
            request=mock_request,
            name="",
            price=""
        )

        assert isinstance(result, FileResponse)
        mock_convert.assert_called_once()

    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    def test_gen_cert_handler_none_values(self, mock_convert, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test certificate generation with None values"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx

        result = gen_cert_handler(
            request=mock_request,
            name=None,
            price=None
        )

        assert isinstance(result, FileResponse)
        mock_convert.assert_called_once()

    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    def test_gen_cert_handler_presentation_error(self, mock_exists, mock_presentation, mock_request):
        """Test presentation error handling"""
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

    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    def test_gen_cert_handler_numeric_price_adds_ruble_symbol(self, mock_convert, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test that numeric price gets ₽ symbol added"""
        mock_exists.return_value = True
        
        # Настраиваем мок для проверки замены текста
        mock_run = MagicMock()
        mock_run.text = "price"  # Начальный текст содержит ключ для замены
        mock_paragraph = MagicMock()
        mock_paragraph.runs = [mock_run]
        mock_text_frame = MagicMock()
        mock_text_frame.paragraphs = [mock_paragraph]
        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_shape.text_frame = mock_text_frame
        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]
        mock_presentation_instance = MagicMock()
        mock_presentation_instance.slides = [mock_slide]
        mock_presentation.return_value = mock_presentation_instance

        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price="5000"
        )

        assert isinstance(result, FileResponse)
        # Проверяем, что текст был заменен на "5000 ₽"
        assert mock_run.text == "5000 ₽"

    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    def test_gen_cert_handler_text_price_no_ruble_symbol(self, mock_convert, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test that text price doesn't get ₽ symbol added"""
        mock_exists.return_value = True
        
        # Настраиваем мок для проверки замены текста
        mock_run = MagicMock()
        mock_run.text = "price"  # Начальный текст содержит ключ для замены
        mock_paragraph = MagicMock()
        mock_paragraph.runs = [mock_run]
        mock_text_frame = MagicMock()
        mock_text_frame.paragraphs = [mock_paragraph]
        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_shape.text_frame = mock_text_frame
        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]
        mock_presentation_instance = MagicMock()
        mock_presentation_instance.slides = [mock_slide]
        mock_presentation.return_value = mock_presentation_instance

        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price="бесплатно"
        )

        assert isinstance(result, FileResponse)
        # Проверяем, что текст был заменен на "бесплатно" без ₽
        assert mock_run.text == "бесплатно"

    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    def test_gen_cert_handler_empty_price_no_ruble_symbol(self, mock_convert, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test that empty price doesn't get ₽ symbol added"""
        mock_exists.return_value = True
        
        # Настраиваем мок для проверки замены текста
        mock_run = MagicMock()
        mock_run.text = "price"  # Начальный текст содержит ключ для замены
        mock_paragraph = MagicMock()
        mock_paragraph.runs = [mock_run]
        mock_text_frame = MagicMock()
        mock_text_frame.paragraphs = [mock_paragraph]
        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_shape.text_frame = mock_text_frame
        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]
        mock_presentation_instance = MagicMock()
        mock_presentation_instance.slides = [mock_slide]
        mock_presentation.return_value = mock_presentation_instance

        result = gen_cert_handler(
            request=mock_request,
            name="Иван Иванов",
            price=""
        )

        assert isinstance(result, FileResponse)
        # Проверяем, что текст был заменен на пустую строку без ₽
        assert mock_run.text == ""
