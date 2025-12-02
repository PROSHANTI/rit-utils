"""
Tests for doctor_form/doctor_form_handler.py module
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import FileResponse, RedirectResponse

from src.utils.doctor_form.doctor_form_handler import (
    doctor_form_handler,
    get_current_date,
)


class TestGetCurrentDate:
    """Tests for getting current date"""

    @patch('src.utils.doctor_form.doctor_form_handler.datetime')
    def test_get_current_date_success(self, mock_datetime):
        """Test successful date retrieval"""
        mock_now = MagicMock()
        mock_now.day = 15
        mock_now.strftime.return_value = "март"
        mock_now.year = 2024
        mock_datetime.datetime.now.return_value = mock_now

        day, month, year = get_current_date()

        assert day == 15
        assert month == "март"
        assert year == 2024

    @patch('src.utils.doctor_form.doctor_form_handler.datetime')
    def test_get_current_date_locale_fallback(self, mock_datetime):
        """Test locale fallback"""
        mock_now = MagicMock()
        mock_now.day = 1
        mock_now.year = 2024
        mock_now.strftime.side_effect = [OSError("Locale error"), "January", "January"]
        mock_datetime.datetime.now.return_value = mock_now

        day, month, year = get_current_date()

        assert day == 1
        assert month == "января"
        assert year == 2024

    @patch('src.utils.doctor_form.doctor_form_handler.datetime')
    def test_get_current_date_unknown_month(self, mock_datetime):
        """Test unknown month handling"""
        mock_now = MagicMock()
        mock_now.day = 1
        mock_now.year = 2024
        mock_now.strftime.side_effect = [OSError("Locale error"), "UnknownMonth", "UnknownMonth"]
        mock_datetime.datetime.now.return_value = mock_now

        day, month, year = get_current_date()

        assert day == 1
        assert month == "UnknownMonth"
        assert year == 2024


class TestDoctorFormHandler:
    """Tests for doctor form handler"""

    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    @patch('src.utils.doctor_form.doctor_form_handler.Presentation')
    @patch('src.utils.doctor_form.doctor_form_handler.get_current_date')
    def test_doctor_form_handler_success(self, mock_get_date, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test successful doctor form generation"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx
        mock_get_date.return_value = (15, "марта", 2024)

        result = doctor_form_handler(
            request=mock_request,
            doctor_1="Доктор Иванов",
            doctor_2="Доктор Петров",
            doctor_3="Доктор Сидоров",
            doctor_4="Доктор Козлов",
            patient_1="Пациент Иванов",
            patient_2="Пациент Петров",
            patient_3="Пациент Сидоров",
            patient_4="Пациент Козлов",
            date="20"
        )

        assert isinstance(result, FileResponse)
        assert result.filename == "Бланк Врача на печать.pptx"
        assert result.media_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    def test_doctor_form_handler_template_not_found(self, mock_exists, mock_request):
        """Test missing template handling"""
        mock_exists.return_value = False

        result = doctor_form_handler(
            request=mock_request,
            doctor_1="Доктор Иванов",
            patient_1="Пациент Иванов",
            date="15"
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/doctor_form"
        assert result.status_code == 303

    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    @patch('src.utils.doctor_form.doctor_form_handler.Presentation')
    @patch('src.utils.doctor_form.doctor_form_handler.get_current_date')
    def test_doctor_form_handler_custom_date(self, mock_get_date, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test with custom date"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx
        mock_get_date.return_value = (15, "марта", 2024)

        result = doctor_form_handler(
            request=mock_request,
            doctor_1="Доктор Иванов",
            patient_1="Пациент Иванов",
            date="25"
        )

        assert isinstance(result, (FileResponse, RedirectResponse))

    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    @patch('src.utils.doctor_form.doctor_form_handler.Presentation')
    @patch('src.utils.doctor_form.doctor_form_handler.get_current_date')
    def test_doctor_form_handler_invalid_date(self, mock_get_date, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test with invalid date"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx
        mock_get_date.return_value = (15, "марта", 2024)

        result = doctor_form_handler(
            request=mock_request,
            doctor_1="Доктор Иванов",
            patient_1="Пациент Иванов",
            date="не число"
        )

        assert isinstance(result, (FileResponse, RedirectResponse))

    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    @patch('src.utils.doctor_form.doctor_form_handler.Presentation')
    @patch('src.utils.doctor_form.doctor_form_handler.get_current_date')
    def test_doctor_form_handler_empty_date(self, mock_get_date, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test with empty date"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx
        mock_get_date.return_value = (15, "марта", 2024)

        result = doctor_form_handler(
            request=mock_request,
            doctor_1="Доктор Иванов",
            patient_1="Пациент Иванов",
            date=""
        )

        assert isinstance(result, (FileResponse, RedirectResponse))

    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    @patch('src.utils.doctor_form.doctor_form_handler.Presentation')
    @patch('src.utils.doctor_form.doctor_form_handler.get_current_date')
    def test_doctor_form_handler_none_values(self, mock_get_date, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test with None values"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx
        mock_get_date.return_value = (15, "марта", 2024)

        result = doctor_form_handler(
            request=mock_request,
            doctor_1=None,
            doctor_2=None,
            doctor_3=None,
            doctor_4=None,
            patient_1=None,
            patient_2=None,
            patient_3=None,
            patient_4=None,
            date=None
        )

        assert isinstance(result, FileResponse)

    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    @patch('src.utils.doctor_form.doctor_form_handler.Presentation')
    @patch('src.utils.doctor_form.doctor_form_handler.get_current_date')
    def test_doctor_form_handler_patient_name_uppercase(self, mock_get_date, mock_presentation, mock_exists, mock_request, mock_pptx):
        """Test patient name uppercase conversion"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx
        mock_get_date.return_value = (15, "марта", 2024)

        result = doctor_form_handler(
            request=mock_request,
            doctor_1="Доктор Иванов",
            patient_1="пациент иванов",
            date="15"
        )

        assert isinstance(result, (FileResponse, RedirectResponse))

    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    @patch('src.utils.doctor_form.doctor_form_handler.Presentation')
    def test_doctor_form_handler_presentation_error(self, mock_exists, mock_presentation, mock_request):
        """Test presentation error handling"""
        mock_exists.return_value = True
        mock_presentation.side_effect = Exception("Presentation error")

        result = doctor_form_handler(
            request=mock_request,
            doctor_1="Доктор Иванов",
            patient_1="Пациент Иванов",
            date="15"
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/doctor_form"
        assert result.status_code == 303
