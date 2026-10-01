import base64
import datetime
import locale
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
from pptx import Presentation
from pptx.presentation import Presentation as PptxPresentation

logger = logging.getLogger(__name__)

for locale_name in ("ru_RU.UTF-8", "ru_RU", "en_US.UTF-8", "C.UTF-8", "C"):
    try:
        locale.setlocale(locale.LC_ALL, locale_name)
        break
    except locale.Error:
        if locale_name == "C":
            raise


@dataclass(frozen=True, slots=True)
class DoctorFormRequest:
    doctors: tuple[str | None, ...] = (None, None, None, None)
    patients: tuple[str | None, ...] = (None, None, None, None)
    date: str | None = None


class DoctorFormGenerator:
    def __init__(self, *, template_path: Path | None = None) -> None:
        self.template_path = template_path or Path(__file__).with_name("Бланк Врача.pptx")

    def generate(self, data: DoctorFormRequest) -> FileResponse | RedirectResponse:
        logger.info("Начата обработка запроса на создание бланка врача")
        output_path: str | None = None

        try:
            replacements = self._get_replacements(data)

            if not self.template_path.exists():
                logger.error("Файл шаблона не найден")
                raise FileNotFoundError(f"Файл шаблона не найден: {self.template_path}")

            presentation = Presentation(f"{self.template_path}")
            self._replace_text(presentation, replacements)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx") as output_file:
                output_path = output_file.name

            presentation.save(output_path)
            background_tasks = BackgroundTasks()
            background_tasks.add_task(self._cleanup, output_path)
            logger.info("Бланк врача создан и подготовлен к отправке")
            return FileResponse(
                path=output_path,
                filename="Бланк Врача на печать.pptx",
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                background=background_tasks,
            )

        except Exception as exc:
            logger.exception("Не удалось создать бланк врача")

            if output_path is not None:
                self._cleanup(output_path)

            status = f"Ошибка обработки файла: {exc}"
            response = RedirectResponse(url="/doctor_form", status_code=303)
            encoded_status = base64.b64encode(status.encode("utf-8")).decode("ascii")
            response.set_cookie("doctor_form_status", encoded_status, max_age=10)
            return response

    def _get_replacements(self, data: DoctorFormRequest) -> dict[str, str]:
        day, month, year = self._get_current_date()

        if data.date and data.date.strip() and data.date.isdigit():
            day = int(data.date)

        replacements: dict[str, str] = {}

        for slot, doctor in enumerate(data.doctors, start=1):
            placeholder = f"Doctor_{slot}"
            replacements[placeholder] = f"ВРАЧ: {doctor}" if doctor else placeholder

        for slot, patient in enumerate(data.patients, start=1):
            placeholder = f"Patient_{slot}"
            replacements[placeholder] = f"ПАЦИЕНТ: {patient.upper()}" if patient else placeholder

        replacements["Дата"] = f"«{day}» {month} {year} г."
        return replacements

    @staticmethod
    def _get_current_date() -> tuple[int, str, int]:
        logger.debug("Получение текущей даты")
        now = datetime.datetime.now()

        try:
            month_name = now.strftime("%B")

        except (OSError, ValueError):
            month_mapping = {
                "January": "января",
                "February": "февраля",
                "March": "марта",
                "April": "апреля",
                "May": "мая",
                "June": "июня",
                "July": "июля",
                "August": "августа",
                "September": "сентября",
                "October": "октября",
                "November": "ноября",
                "December": "декабря",
            }
            month_name = now.strftime("%B")
            month_name = month_mapping.get(month_name, month_name)

        logger.debug("Текущая дата получена")
        return now.day, month_name, now.year

    @staticmethod
    def _replace_text(presentation: PptxPresentation, replacements: dict[str, str]) -> None:
        for slide in presentation.slides:
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue

                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        for placeholder, value in replacements.items():
                            if placeholder in run.text:
                                run.text = run.text.replace(placeholder, value)

    @staticmethod
    def _cleanup(output_path: str) -> None:
        logger.debug("Начата очистка временного файла бланка врача")

        try:
            Path(output_path).unlink()

        except OSError:
            logger.warning("Не удалось удалить временный файл бланка врача")
        else:
            logger.debug("Временный файл бланка врача удалён")
