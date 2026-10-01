"""Проверки обработки изображений и HTTP-ответов удаления фона."""

import base64
import logging
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from fastapi import BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
from numpy.typing import NDArray

from src.utils.remove_bg import BackgroundRemovalOptions, BackgroundRemover, RemoveBackgroundHandler


def write_document_image(path: Path, *, background: int = 255, foreground: int = 30) -> NDArray[np.uint8]:
    image = np.full((8, 8, 3), background, dtype=np.uint8)
    image[2:6, 2:6] = foreground
    assert cv2.imwrite(f"{path}", image)
    return image


class TestBackgroundRemover:
    @pytest.mark.parametrize(
        ("color", "expected_bgr"),
        [
            pytest.param("255,0,0", (0, 0, 255), id="red"),
            pytest.param(" 10 , 20 , 30 ", (30, 20, 10), id="spaces"),
            pytest.param("0,0,0", (0, 0, 0), id="black"),
            pytest.param("255,255,255", (255, 255, 255), id="white"),
        ],
    )
    def test_parse_color_returns_bgr(self, color: str, expected_bgr: tuple[int, int, int]) -> None:
        result = BackgroundRemover.parse_color(color)

        assert result == expected_bgr

    @pytest.mark.parametrize(
        ("color", "expected_error"),
        [
            pytest.param("255,0", "Color must be in format", id="missing-channel"),
            pytest.param("255,0,0,0", "Color must be in format", id="extra-channel"),
            pytest.param("256,0,0", "RGB values must be between", id="above-range"),
            pytest.param("-1,0,0", "RGB values must be between", id="below-range"),
            pytest.param("abc,0,0", "Invalid color format", id="invalid-number"),
        ],
    )
    def test_parse_color_rejects_invalid_input(self, color: str, expected_error: str) -> None:
        with pytest.raises(ValueError, match=expected_error):
            BackgroundRemover.parse_color(color)

    @pytest.mark.parametrize(
        ("background", "foreground", "invert", "background_alpha", "foreground_alpha"),
        [
            pytest.param(255, 30, False, 0, 255, id="light-background-auto-inversion"),
            pytest.param(0, 255, False, 0, 255, id="dark-background"),
            pytest.param(0, 255, True, 255, 0, id="explicit-inversion"),
        ],
    )
    def test_remove_preserves_original_color_and_selects_alpha_mask(
        self,
        tmp_path: Path,
        background: int,
        foreground: int,
        invert: bool,
        background_alpha: int,
        foreground_alpha: int,
    ) -> None:
        input_path = tmp_path / "source.png"
        output_path = tmp_path / "result.png"
        image = write_document_image(input_path, background=background, foreground=foreground)
        remover = BackgroundRemover(BackgroundRemovalOptions(invert=invert))
        expected_alpha = np.full((8, 8), background_alpha, dtype=np.uint8)
        expected_alpha[2:6, 2:6] = foreground_alpha

        remover.remove(f"{input_path}", f"{output_path}")

        result = cv2.imread(f"{output_path}", cv2.IMREAD_UNCHANGED)
        assert result is not None
        assert result.shape == (8, 8, 4)
        np.testing.assert_array_equal(result[:, :, :3], image)
        np.testing.assert_array_equal(result[:, :, 3], expected_alpha)

    def test_remove_applies_configured_bgr_color(self, tmp_path: Path) -> None:
        input_path = tmp_path / "source.png"
        output_path = tmp_path / "result.png"
        write_document_image(input_path)
        remover = BackgroundRemover(BackgroundRemovalOptions(text_color=(10, 20, 30)))

        remover.remove(f"{input_path}", f"{output_path}")

        result = cv2.imread(f"{output_path}", cv2.IMREAD_UNCHANGED)
        assert result is not None
        np.testing.assert_array_equal(result[3, 3], [10, 20, 30, 255])
        np.testing.assert_array_equal(result[0, 0], [255, 255, 255, 0])

    def test_remover_reuses_options_without_changing_automatic_inversion(self, tmp_path: Path) -> None:
        light_input = tmp_path / "light.png"
        dark_input = tmp_path / "dark.png"
        light_output = tmp_path / "light-result.png"
        dark_output = tmp_path / "dark-result.png"
        write_document_image(light_input)
        write_document_image(dark_input, background=0, foreground=255)
        options = BackgroundRemovalOptions()
        remover = BackgroundRemover(options)

        remover.remove(f"{light_input}", f"{light_output}")
        remover.remove(f"{dark_input}", f"{dark_output}")

        assert remover.options is options
        assert options.invert is False
        light_result = cv2.imread(f"{light_output}", cv2.IMREAD_UNCHANGED)
        dark_result = cv2.imread(f"{dark_output}", cv2.IMREAD_UNCHANGED)
        assert light_result is not None
        assert dark_result is not None
        assert light_result[0, 0, 3] == 0
        assert dark_result[0, 0, 3] == 0
        assert light_result[3, 3, 3] == 255
        assert dark_result[3, 3, 3] == 255

    def test_remove_missing_image_raises_file_not_found(self, tmp_path: Path) -> None:
        remover = BackgroundRemover()

        with pytest.raises(FileNotFoundError, match="Входное изображение отсутствует"):
            remover.remove(f"{tmp_path / 'missing.png'}", f"{tmp_path / 'result.png'}")

    def test_remove_invalid_image_raises_value_error(self, tmp_path: Path) -> None:
        input_path = tmp_path / "invalid.png"
        input_path.write_bytes(b"invalid image")
        remover = BackgroundRemover()

        with pytest.raises(ValueError, match="Изображение не удалось прочитать"):
            remover.remove(f"{input_path}", f"{tmp_path / 'result.png'}")

    def test_remove_write_failure_raises_and_logs_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        input_path = tmp_path / "source.png"
        output_path = tmp_path / "result.png"
        write_document_image(input_path)
        remover = BackgroundRemover()

        with patch("src.utils.remove_bg.remove_bg_document.cv2.imwrite", return_value=False):
            with pytest.raises(OSError, match="Не удалось сохранить изображение после удаления фона"):
                remover.remove(f"{input_path}", f"{output_path}")

        assert not output_path.exists()
        assert (
            "src.utils.remove_bg.remove_bg_document",
            logging.ERROR,
            "Не удалось удалить фон изображения",
        ) in caplog.record_tuples

    def test_remove_processing_failure_logs_traceback_and_reraises_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        input_path = tmp_path / "source.png"
        write_document_image(input_path)
        remover = BackgroundRemover()

        with patch("src.utils.remove_bg.remove_bg_document.cv2.cvtColor", side_effect=ValueError("Processing error")):
            with pytest.raises(ValueError, match="Processing error"):
                remover.remove(f"{input_path}", f"{tmp_path / 'result.png'}")

        error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
        assert len(error_records) == 1
        assert error_records[0].getMessage() == "Не удалось удалить фон изображения"
        assert error_records[0].exc_info is not None


class TestRemoveBackgroundHandler:
    @pytest.mark.parametrize(
        "extension",
        [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".PNG"],
    )
    @pytest.mark.asyncio
    async def test_handler_returns_png_and_removes_temporary_files_after_response(
        self,
        extension: str,
        tmp_path: Path,
        mock_file_upload: MagicMock,
    ) -> None:
        input_path = tmp_path / "source.png"
        write_document_image(input_path)
        mock_file_upload.filename = f"document{extension}"
        mock_file_upload.file.read.return_value = input_path.read_bytes()
        background_tasks = BackgroundTasks()
        handler = RemoveBackgroundHandler()

        result = handler.handle(background_tasks=background_tasks, file=mock_file_upload, color="255,0,0")

        assert isinstance(result, FileResponse)
        assert result.filename == "document_no_bg.png"
        assert result.media_type == "image/png"
        assert result.background is background_tasks
        assert len(background_tasks.tasks) == 1
        temporary_paths = [Path(f"{path}") for path in background_tasks.tasks[0].args]
        assert all(path.exists() for path in temporary_paths)

        try:
            processed_image = cv2.imread(f"{result.path}", cv2.IMREAD_UNCHANGED)
            assert processed_image is not None
            np.testing.assert_array_equal(processed_image[3, 3], [0, 0, 255, 255])
            assert processed_image[0, 0, 3] == 0

        finally:
            await background_tasks()

        assert all(not path.exists() for path in temporary_paths)

    @pytest.mark.parametrize(
        ("color", "expected_bgr"),
        [
            pytest.param(None, (0, 0, 0), id="default-black"),
            pytest.param("", (0, 0, 0), id="empty-color-black"),
            pytest.param("10,20,30", (30, 20, 10), id="custom-color"),
        ],
    )
    @pytest.mark.asyncio
    async def test_handler_uses_requested_color(
        self,
        color: str | None,
        expected_bgr: tuple[int, int, int],
        tmp_path: Path,
        mock_file_upload: MagicMock,
    ) -> None:
        input_path = tmp_path / "source.png"
        write_document_image(input_path)
        mock_file_upload.filename = "my_image.jpg"
        mock_file_upload.file.read.return_value = input_path.read_bytes()
        background_tasks = BackgroundTasks()

        result = RemoveBackgroundHandler().handle(background_tasks=background_tasks, file=mock_file_upload, color=color)

        assert isinstance(result, FileResponse)
        assert result.filename == "my_image_no_bg.png"

        try:
            processed_image = cv2.imread(f"{result.path}", cv2.IMREAD_UNCHANGED)
            assert processed_image is not None
            np.testing.assert_array_equal(processed_image[3, 3, :3], expected_bgr)

        finally:
            await background_tasks()

    @pytest.mark.parametrize(
        ("filename", "color", "expected_error"),
        [
            pytest.param(None, None, "Файл не был загружен", id="missing-filename"),
            pytest.param("test.pdf", None, "Неподдерживаемый формат файла.", id="unsupported-extension"),
            pytest.param("test.png", "invalid", "Неверный формат цвета:", id="invalid-color"),
        ],
    )
    def test_handler_validation_redirects_with_status_cookie(
        self,
        filename: str | None,
        color: str | None,
        expected_error: str,
        mock_file_upload: MagicMock,
    ) -> None:
        mock_file_upload.filename = filename
        background_tasks = BackgroundTasks()

        result = RemoveBackgroundHandler().handle(background_tasks=background_tasks, file=mock_file_upload, color=color)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/remove_bg"
        assert result.status_code == 303
        assert not background_tasks.tasks
        mock_file_upload.file.read.assert_not_called()
        status = self._get_status(result)
        assert status.startswith(f"Ошибка обработки изображения: {expected_error}")

    def test_handler_processing_exception_redirects_and_logs_traceback(
        self, mock_file_upload: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_file_upload.filename = "test.png"
        background_tasks = BackgroundTasks()

        with patch.object(BackgroundRemover, "remove", side_effect=RuntimeError("Processing error")) as mock_remove:
            result = RemoveBackgroundHandler().handle(background_tasks=background_tasks, file=mock_file_upload, color=None)

        try:
            assert isinstance(result, RedirectResponse)
            assert result.headers["location"] == "/remove_bg"
            assert result.status_code == 303
            assert not background_tasks.tasks
            status = self._get_status(result)
            assert status == "Ошибка обработки изображения: Processing error"
            error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
            assert len(error_records) == 1
            assert error_records[0].getMessage() == "Не удалось обработать изображение"
            assert error_records[0].exc_info is not None

        finally:
            Path(mock_remove.call_args.kwargs["input_path"]).unlink(missing_ok=True)
            Path(mock_remove.call_args.kwargs["output_path"]).unlink(missing_ok=True)

    def test_handler_corrupt_image_redirects_and_removes_temporary_files(self, mock_file_upload: MagicMock) -> None:
        mock_file_upload.filename = "invalid.png"
        mock_file_upload.file.read.return_value = b"invalid image"
        handler = RemoveBackgroundHandler()
        background_tasks = BackgroundTasks()

        with patch.object(
            RemoveBackgroundHandler, "_cleanup_temp_files", wraps=RemoveBackgroundHandler._cleanup_temp_files
        ) as mock_cleanup:
            result = handler.handle(background_tasks=background_tasks, file=mock_file_upload)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert result.headers["location"] == "/remove_bg"
        assert self._get_status(result) == "Ошибка обработки изображения: Изображение не удалось прочитать"
        assert not background_tasks.tasks
        self._assert_temporary_files_removed(mock_cleanup, expected_count=2)

    def test_handler_save_failure_redirects_and_removes_temporary_files(
        self, tmp_path: Path, mock_file_upload: MagicMock
    ) -> None:
        input_path = tmp_path / "source.png"
        write_document_image(input_path)
        mock_file_upload.filename = "document.png"
        mock_file_upload.file.read.return_value = input_path.read_bytes()
        handler = RemoveBackgroundHandler()
        background_tasks = BackgroundTasks()

        with (
            patch("src.utils.remove_bg.remove_bg_document.cv2.imwrite", return_value=False),
            patch.object(
                RemoveBackgroundHandler, "_cleanup_temp_files", wraps=RemoveBackgroundHandler._cleanup_temp_files
            ) as mock_cleanup,
        ):
            result = handler.handle(background_tasks=background_tasks, file=mock_file_upload)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert result.headers["location"] == "/remove_bg"
        assert self._get_status(result) == "Ошибка обработки изображения: Не удалось сохранить изображение после удаления фона"
        assert not background_tasks.tasks
        self._assert_temporary_files_removed(mock_cleanup, expected_count=2)

    def test_handler_read_failure_removes_the_created_input_file(self, mock_file_upload: MagicMock) -> None:
        mock_file_upload.filename = "document.png"
        mock_file_upload.file.read.side_effect = RuntimeError("Upload read error")
        handler = RemoveBackgroundHandler()
        background_tasks = BackgroundTasks()

        with patch.object(
            RemoveBackgroundHandler, "_cleanup_temp_files", wraps=RemoveBackgroundHandler._cleanup_temp_files
        ) as mock_cleanup:
            result = handler.handle(background_tasks=background_tasks, file=mock_file_upload)

        assert isinstance(result, RedirectResponse)
        assert self._get_status(result) == "Ошибка обработки изображения: Upload read error"
        assert not background_tasks.tasks
        self._assert_temporary_files_removed(mock_cleanup, expected_count=1)

    def test_handler_cleanup_failure_preserves_original_error_and_attempts_remaining_files(
        self, mock_file_upload: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_file_upload.filename = "document.png"
        handler = RemoveBackgroundHandler()
        background_tasks = BackgroundTasks()

        with (
            patch.object(BackgroundRemover, "remove", side_effect=ValueError("Processing error")) as mock_remove,
            patch.object(Path, "unlink", side_effect=[PermissionError("Cleanup error"), None]) as mock_unlink,
        ):
            result = handler.handle(background_tasks=background_tasks, file=mock_file_upload)

        try:
            assert isinstance(result, RedirectResponse)
            assert self._get_status(result) == "Ошибка обработки изображения: Processing error"
            assert mock_unlink.call_count == 2
            assert (
                "src.utils.remove_bg.remove_bg_handler",
                logging.WARNING,
                "Не удалось удалить временный файл изображения",
            ) in caplog.record_tuples

        finally:
            Path(mock_remove.call_args.kwargs["input_path"]).unlink(missing_ok=True)
            Path(mock_remove.call_args.kwargs["output_path"]).unlink(missing_ok=True)

    @staticmethod
    def _get_status(response: RedirectResponse) -> str:
        cookies = SimpleCookie()
        cookies.load(response.headers["set-cookie"])
        return base64.b64decode(cookies["remove_bg_status"].value).decode("utf-8")

    @staticmethod
    def _assert_temporary_files_removed(mock_cleanup: MagicMock, *, expected_count: int) -> None:
        mock_cleanup.assert_called_once()
        paths = mock_cleanup.call_args.args
        assert len(paths) == expected_count
        assert all(not path.exists() for path in paths)
