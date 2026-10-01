import base64
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import FileResponse, RedirectResponse

from src.utils.doctor_form.doctor_form_handler import DoctorFormGenerator, DoctorFormRequest


class TestDoctorFormGenerator:
    @patch("src.utils.doctor_form.doctor_form_handler.datetime")
    def test_current_date_uses_system_locale(self, mock_datetime):
        mock_now = mock_datetime.datetime.now.return_value
        mock_now.day = 15
        mock_now.year = 2024
        mock_now.strftime.return_value = "марта"

        result = DoctorFormGenerator._get_current_date()

        assert result == (15, "марта", 2024)

    @pytest.mark.parametrize(
        ("locale_error", "month_name", "expected_month"),
        [
            pytest.param(OSError("Locale error"), "January", "января", id="known-month"),
            pytest.param(ValueError("Locale error"), "UnknownMonth", "UnknownMonth", id="unknown-month"),
        ],
    )
    @patch("src.utils.doctor_form.doctor_form_handler.datetime")
    def test_current_date_falls_back_when_locale_fails(self, mock_datetime, locale_error, month_name, expected_month):
        mock_now = mock_datetime.datetime.now.return_value
        mock_now.day = 1
        mock_now.year = 2024
        mock_now.strftime.side_effect = [locale_error, month_name]

        result = DoctorFormGenerator._get_current_date()

        assert result == (1, expected_month, 2024)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("date", "expected_date"),
        [
            pytest.param("25", "«25» марта 2024 г.", id="custom-date"),
            pytest.param("не число", "«15» марта 2024 г.", id="invalid-date"),
            pytest.param("", "«15» марта 2024 г.", id="empty-date"),
            pytest.param(None, "«15» марта 2024 г.", id="missing-date"),
            pytest.param(" 25 ", "«15» марта 2024 г.", id="date-with-spaces"),
        ],
    )
    @patch.object(Path, "exists", return_value=True)
    @patch("src.utils.doctor_form.doctor_form_handler.Presentation")
    @patch.object(DoctorFormGenerator, "_get_current_date", return_value=(15, "марта", 2024))
    async def test_generate_preserves_date_rules_and_cleans_download(
        self, mock_date, mock_presentation, mock_exists, mock_pptx, date, expected_date
    ):
        mock_presentation.return_value = mock_pptx
        date_run = mock_pptx.slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
        date_run.text = "Дата"

        response = DoctorFormGenerator().generate(DoctorFormRequest(date=date))

        assert isinstance(response, FileResponse)
        assert response.filename == "Бланк Врача на печать.pptx"
        assert response.media_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        assert date_run.text == expected_date
        assert response.background is not None
        await response.background()
        assert not Path(response.path).is_file()

    @pytest.mark.asyncio
    @patch.object(Path, "exists", return_value=True)
    @patch("src.utils.doctor_form.doctor_form_handler.Presentation")
    @patch.object(DoctorFormGenerator, "_get_current_date", return_value=(15, "марта", 2024))
    async def test_generate_replaces_all_slots_on_every_slide(self, mock_date, mock_presentation, mock_exists, mock_pptx):
        mock_presentation.return_value = mock_pptx
        first_paragraph = mock_pptx.slides[0].shapes[0].text_frame.paragraphs[0]
        placeholders = ("Doctor_1", "Doctor_2", "Doctor_3", "Doctor_4", "Patient_1", "Patient_2", "Patient_3", "Patient_4")
        runs = [MagicMock(text=placeholder) for placeholder in placeholders]
        first_paragraph.runs = runs
        second_run = MagicMock(text="Doctor_1")
        second_slide = MagicMock()
        second_slide.shapes = [MagicMock(has_text_frame=True)]
        second_slide.shapes[0].text_frame.paragraphs = [MagicMock(runs=[second_run])]
        mock_pptx.slides.append(second_slide)
        data = DoctorFormRequest(
            doctors=("doctor 1", "doctor 2", "doctor 3", "doctor 4"),
            patients=("patient 1", "patient 2", "patient 3", "patient 4"),
        )

        response = DoctorFormGenerator().generate(data)

        assert isinstance(response, FileResponse)
        assert [run.text for run in runs] == [
            "ВРАЧ: doctor 1",
            "ВРАЧ: doctor 2",
            "ВРАЧ: doctor 3",
            "ВРАЧ: doctor 4",
            "ПАЦИЕНТ: PATIENT 1",
            "ПАЦИЕНТ: PATIENT 2",
            "ПАЦИЕНТ: PATIENT 3",
            "ПАЦИЕНТ: PATIENT 4",
        ]
        assert second_run.text == "ВРАЧ: doctor 1"
        assert response.background is not None
        await response.background()

    @patch.object(Path, "exists", return_value=False)
    @patch.object(DoctorFormGenerator, "_get_current_date", return_value=(15, "марта", 2024))
    def test_generate_missing_template_returns_status_cookie(self, mock_date, mock_exists):
        response = DoctorFormGenerator().generate(DoctorFormRequest())

        assert isinstance(response, RedirectResponse)
        assert response.status_code == 303
        assert response.headers["location"] == "/doctor_form"
        cookie = SimpleCookie(response.headers["set-cookie"])["doctor_form_status"]
        status = base64.b64decode(cookie.value).decode("utf-8")
        assert status.startswith("Ошибка обработки файла: Файл шаблона не найден:")
        assert cookie["max-age"] == "10"

    @patch.object(Path, "exists", return_value=True)
    @patch("src.utils.doctor_form.doctor_form_handler.Presentation")
    @patch.object(DoctorFormGenerator, "_get_current_date", return_value=(15, "марта", 2024))
    def test_generate_save_failure_cleans_temporary_file(self, mock_date, mock_presentation, mock_exists, mock_pptx):
        mock_presentation.return_value = mock_pptx
        mock_pptx.save.side_effect = ValueError("Presentation error")

        response = DoctorFormGenerator().generate(DoctorFormRequest())

        assert isinstance(response, RedirectResponse)
        assert response.status_code == 303
        assert response.headers["location"] == "/doctor_form"
        cookie = SimpleCookie(response.headers["set-cookie"])["doctor_form_status"]
        assert base64.b64decode(cookie.value).decode("utf-8") == "Ошибка обработки файла: Presentation error"
        saved_path = Path(mock_pptx.save.call_args.args[0])
        assert not saved_path.is_file()
