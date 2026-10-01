import base64
import logging
import random
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
from pptx import Presentation
from pptx.presentation import Presentation as PptxPresentation

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CertificateRequest:
    name: str | None = None
    price: str | None = None


class LibreOfficeConverter:
    def convert(self, pptx_path: str, pdf_path: str) -> None:
        logger.info("Начата конвертация сертификата в PDF")

        try:
            executable = self._find_executable()
            output_directory = Path(pdf_path).parent
            command = [executable, "--headless", "--convert-to", "pdf", "--outdir", f"{output_directory}", pptx_path]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                raise Exception(f"LibreOffice error: {result.stderr}")

            generated_pdf = output_directory / f"{Path(pptx_path).stem}.pdf"

            if not generated_pdf.exists():
                raise Exception("PDF файл не был создан")

            if generated_pdf != Path(pdf_path):
                generated_pdf.rename(pdf_path)

            logger.info("Конвертация сертификата в PDF завершена")

        except subprocess.TimeoutExpired:
            logger.exception("Превышено время ожидания конвертации сертификата")
            raise Exception("Превышено время ожидания конвертации")

        except Exception as exc:
            logger.exception("Не удалось конвертировать сертификат в PDF")
            raise Exception(f"Ошибка конвертации: {exc}")

    @staticmethod
    def _find_executable() -> str:
        candidates = (
            "libreoffice",
            "/usr/bin/libreoffice",
            "/usr/local/bin/libreoffice",
            "/snap/bin/libreoffice",
            "/opt/libreoffice/program/soffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        )

        for executable in candidates:
            try:
                version_result = subprocess.run([executable, "--version"], capture_output=True, timeout=5)

                if version_result.returncode == 0:
                    return executable

            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        raise Exception(
            "LibreOffice не найден. Установите LibreOffice:\n"
            "Ubuntu/Debian: sudo apt-get install libreoffice\n"
            "CentOS/RHEL: sudo yum install libreoffice\n"
            "macOS: brew install --cask libreoffice"
        )


class CertificateGenerator:
    def __init__(self, *, template_path: Path | None = None, converter: LibreOfficeConverter | None = None) -> None:
        self.template_path = template_path or Path(__file__).with_name("Сертификат_шаблон.pptx")
        self.converter = converter or LibreOfficeConverter()

    def generate(self, data: CertificateRequest) -> FileResponse | RedirectResponse:
        logger.info("Начата обработка запроса на создание сертификата")
        temporary_paths: list[str] = []

        try:
            if not self.template_path.exists():
                raise FileNotFoundError(f"Файл шаблона не найден: {self.template_path}")

            replacements = self._get_replacements(data)
            presentation = Presentation(f"{self.template_path}")
            self._replace_text(presentation, replacements)
            pptx_path = self._create_temporary_file(".pptx", temporary_paths)
            pdf_path = self._create_temporary_file(".pdf", temporary_paths)
            presentation.save(pptx_path)
            self.converter.convert(pptx_path, pdf_path)

            background_tasks = BackgroundTasks()
            background_tasks.add_task(self._cleanup, temporary_paths)
            logger.info("Сертификат создан и подготовлен к отправке")
            return FileResponse(
                path=pdf_path, filename="Сертификат.pdf", media_type="application/pdf", background=background_tasks
            )

        except Exception as exc:
            logger.exception("Не удалось создать сертификат")
            self._cleanup(temporary_paths)
            status = f"Ошибка генерации сертификата: {exc}"
            response = RedirectResponse(url="/gen_rit_cert", status_code=303)
            encoded_status = base64.b64encode(status.encode("utf-8")).decode("ascii")
            response.set_cookie("gen_cert_status", encoded_status, max_age=10)
            return response

    def _get_replacements(self, data: CertificateRequest) -> dict[str, str]:
        name = data.name.strip() if data.name else ""
        price = data.price.strip() if data.price else ""
        return {
            "price": f"{price} ₽" if price and price.isdigit() else price,
            "name": name,
            "serial": f"{self._get_random_number()}",
        }

    @staticmethod
    def _get_random_number() -> int:
        logger.debug("Генерация номера сертификата")
        return random.randint(100000, 999999)

    @staticmethod
    def _replace_text(presentation: PptxPresentation, replacements: dict[str, str]) -> None:
        for shape in presentation.slides[0].shapes:
            if not shape.has_text_frame:
                continue

            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    for placeholder, value in replacements.items():
                        if placeholder in run.text:
                            run.text = run.text.replace(placeholder, value)

    @staticmethod
    def _create_temporary_file(suffix: str, temporary_paths: list[str]) -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary_file:
            temporary_paths.append(temporary_file.name)
            return temporary_file.name

    @staticmethod
    def _cleanup(temporary_paths: list[str]) -> None:
        logger.debug("Начата очистка временных файлов сертификата")

        for temporary_path in temporary_paths:
            try:
                Path(temporary_path).unlink()

            except OSError:
                logger.warning("Не удалось удалить временный файл сертификата")

        logger.debug("Очистка временных файлов сертификата завершена")
