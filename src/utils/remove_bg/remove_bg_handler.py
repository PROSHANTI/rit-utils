import base64
import logging
import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from src.utils.remove_bg.remove_bg_document import BackgroundRemovalOptions, BackgroundRemover

logger = logging.getLogger(__name__)


class RemoveBackgroundHandler:
    ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif")

    def handle(
        self, *, background_tasks: BackgroundTasks, file: UploadFile, color: str | None = None
    ) -> FileResponse | RedirectResponse:
        logger.info("Начата обработка запроса на удаление фона изображения")
        temporary_paths: list[Path] = []

        try:
            if not file.filename:
                raise ValueError("Файл не был загружен")

            file_extension = self._validate_extension(file.filename)
            text_color = self._parse_color(color)

            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_input:
                temp_input_path = temp_input.name
                temporary_paths.append(Path(temp_input_path))
                temp_input.write(file.file.read())

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_output:
                temp_output_path = temp_output.name
                temporary_paths.append(Path(temp_output_path))

            options = BackgroundRemovalOptions(text_color=text_color)
            BackgroundRemover(options).remove(input_path=temp_input_path, output_path=temp_output_path)
            output_filename = f"{Path(file.filename).stem}_no_bg.png"
            background_tasks.add_task(self._cleanup_temp_files, *temporary_paths)

            logger.info("Изображение обработано и подготовлено к отправке")
            return FileResponse(
                path=temp_output_path, filename=output_filename, media_type="image/png", background=background_tasks
            )

        except Exception as exc:
            logger.exception("Не удалось обработать изображение")
            self._cleanup_temp_files(*temporary_paths)
            status = f"Ошибка обработки изображения: {exc}"
            response = RedirectResponse(url="/remove_bg", status_code=303)
            encoded_status = base64.b64encode(status.encode("utf-8")).decode("ascii")
            response.set_cookie("remove_bg_status", encoded_status, max_age=10)
            return response

    def _validate_extension(self, filename: str) -> str:
        file_extension = Path(filename).suffix.lower()

        if file_extension not in self.ALLOWED_EXTENSIONS:
            raise ValueError(f"Неподдерживаемый формат файла. Поддерживаемые форматы: {', '.join(self.ALLOWED_EXTENSIONS)}")

        return file_extension

    @staticmethod
    def _parse_color(color: str | None) -> tuple[int, int, int]:
        if not color:
            return 0, 0, 0

        try:
            return BackgroundRemover.parse_color(color)

        except ValueError as exc:
            raise ValueError(f"Неверный формат цвета: {exc}. Используйте формат 'R,G,B' (например, '255,0,0')") from exc

    @staticmethod
    def _cleanup_temp_files(*paths: Path) -> None:
        logger.debug("Начата очистка временных файлов изображения")

        for path in paths:
            try:
                path.unlink(missing_ok=True)

            except OSError:
                logger.warning("Не удалось удалить временный файл изображения", exc_info=True)

        logger.debug("Очистка временных файлов изображения завершена")
