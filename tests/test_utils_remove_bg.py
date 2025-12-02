"""
Tests for remove_bg module
"""
import os
from unittest.mock import MagicMock, patch

try:
    import numpy as np
except ImportError:
    np = None
import pytest
from fastapi.responses import FileResponse, RedirectResponse

from src.utils.remove_bg.remove_bg_document import (
    parse_rgb_color,
    remove_background,
)
from src.utils.remove_bg.remove_bg_handler import remove_bg_handler


class TestParseRgbColor:
    """Tests for RGB color parsing"""

    def test_parse_rgb_color_valid(self):
        """Test parsing valid RGB color string"""
        result = parse_rgb_color("255,0,0")

        assert result == (0, 0, 255)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_parse_rgb_color_with_spaces(self):
        """Test parsing RGB color with spaces"""
        result = parse_rgb_color(" 255 , 0 , 0 ")

        assert result == (0, 0, 255)

    def test_parse_rgb_color_black(self):
        """Test parsing black color"""
        result = parse_rgb_color("0,0,0")

        assert result == (0, 0, 0)

    def test_parse_rgb_color_white(self):
        """Test parsing white color"""
        result = parse_rgb_color("255,255,255")

        assert result == (255, 255, 255)

    def test_parse_rgb_color_invalid_format(self):
        """Test parsing invalid format"""
        with pytest.raises(ValueError, match="Color must be in format"):
            parse_rgb_color("255,0")

    def test_parse_rgb_color_invalid_format_too_many(self):
        """Test parsing invalid format with too many values"""
        with pytest.raises(ValueError, match="Color must be in format"):
            parse_rgb_color("255,0,0,0")

    def test_parse_rgb_color_out_of_range_high(self):
        """Test parsing RGB value out of range (too high)"""
        with pytest.raises(ValueError, match="RGB values must be between"):
            parse_rgb_color("256,0,0")

    def test_parse_rgb_color_out_of_range_negative(self):
        """Test parsing RGB value out of range (negative)"""
        with pytest.raises(ValueError, match="RGB values must be between"):
            parse_rgb_color("-1,0,0")

    def test_parse_rgb_color_invalid_characters(self):
        """Test parsing RGB with invalid characters"""
        with pytest.raises(ValueError):
            parse_rgb_color("abc,0,0")


class TestRemoveBackground:
    """Tests for background removal"""

    @patch('src.utils.remove_bg.remove_bg_document.cv2.imwrite')
    @patch('src.utils.remove_bg.remove_bg_document.cv2.cvtColor')
    @patch('src.utils.remove_bg.remove_bg_document.cv2.threshold')
    @patch('src.utils.remove_bg.remove_bg_document.cv2.imread')
    @patch('src.utils.remove_bg.remove_bg_document.Path.exists')
    def test_remove_background_success(
        self,
        mock_exists,
        mock_imread,
        mock_threshold,
        mock_cvtcolor,
        mock_imwrite,
        temp_file
    ):
        """Test successful background removal"""
        mock_exists.return_value = True
        if np is not None:
            mock_img = np.zeros((100, 100, 3), dtype=np.uint8)
            mock_imread.return_value = mock_img
            mock_threshold.return_value = (127, np.zeros((100, 100), dtype=np.uint8))
            mock_cvtcolor.return_value = np.zeros((100, 100, 4), dtype=np.uint8)
        else:
            mock_img = MagicMock()
            mock_imread.return_value = mock_img
            mock_threshold.return_value = (127, MagicMock())
            mock_cvtcolor.return_value = MagicMock()

        input_path = temp_file + ".png"
        output_path = temp_file + "_output.png"

        with open(input_path, 'wb') as f:
            f.write(b"fake image")

        try:
            remove_background(input_path, output_path, invert=False, text_color=None)
            mock_imread.assert_called_once_with(input_path)
            mock_imwrite.assert_called_once()
        finally:
            for path in [input_path]:
                if os.path.exists(path):
                    os.unlink(path)

    @patch('src.utils.remove_bg.remove_bg_document.cv2.imread')
    @patch('src.utils.remove_bg.remove_bg_document.Path.exists')
    def test_remove_background_file_not_exists(self, mock_exists, mock_imread, temp_file):
        """Test background removal with non-existent file"""
        mock_exists.return_value = False

        input_path = temp_file + ".png"
        output_path = temp_file + "_output.png"

        with pytest.raises(SystemExit):
            remove_background(input_path, output_path)

    @patch('src.utils.remove_bg.remove_bg_document.cv2.imread')
    @patch('src.utils.remove_bg.remove_bg_document.Path.exists')
    def test_remove_background_invalid_image(self, mock_exists, mock_imread, temp_file):
        """Test background removal with invalid image"""
        mock_exists.return_value = True
        mock_imread.return_value = None

        input_path = temp_file + ".png"
        output_path = temp_file + "_output.png"

        with open(input_path, 'wb') as f:
            f.write(b"invalid image")

        try:
            with pytest.raises(SystemExit):
                remove_background(input_path, output_path)
        finally:
            if os.path.exists(input_path):
                os.unlink(input_path)

    @patch('src.utils.remove_bg.remove_bg_document.cv2.imwrite')
    @patch('src.utils.remove_bg.remove_bg_document.cv2.cvtColor')
    @patch('src.utils.remove_bg.remove_bg_document.cv2.threshold')
    @patch('src.utils.remove_bg.remove_bg_document.cv2.imread')
    @patch('src.utils.remove_bg.remove_bg_document.Path.exists')
    def test_remove_background_with_color(
        self,
        mock_exists,
        mock_imread,
        mock_threshold,
        mock_cvtcolor,
        mock_imwrite,
        temp_file
    ):
        """Test background removal with custom text color"""
        mock_exists.return_value = True
        if np is not None:
            mock_img = np.zeros((100, 100, 3), dtype=np.uint8)
            mock_imread.return_value = mock_img
            mock_threshold.return_value = (127, np.zeros((100, 100), dtype=np.uint8))
            mock_result = np.zeros((100, 100, 4), dtype=np.uint8)
            mock_cvtcolor.return_value = mock_result
        else:
            mock_img = MagicMock()
            mock_imread.return_value = mock_img
            mock_threshold.return_value = (127, MagicMock())
            mock_result = MagicMock()
            mock_cvtcolor.return_value = mock_result

        input_path = temp_file + ".png"
        output_path = temp_file + "_output.png"

        with open(input_path, 'wb') as f:
            f.write(b"fake image")

        try:
            remove_background(
                input_path,
                output_path,
                invert=False,
                text_color=(255, 0, 0)
            )
            mock_imread.assert_called_once()
            mock_imwrite.assert_called_once()
        finally:
            if os.path.exists(input_path):
                os.unlink(input_path)


class TestRemoveBgHandler:
    """Tests for remove background handler"""

    @patch('src.utils.remove_bg.remove_bg_handler.remove_background')
    def test_remove_bg_handler_success(
        self,
        mock_remove_bg,
        mock_request,
        mock_file_upload,
        temp_file
    ):
        """Test successful background removal"""
        mock_file_upload.filename = "test.png"
        mock_file_upload.file.read.return_value = b"fake image content"

        result = remove_bg_handler(
            request=mock_request,
            background_tasks=MagicMock(),
            file=mock_file_upload,
            color="255,0,0"
        )

        assert isinstance(result, FileResponse)
        assert result.filename == "test_no_bg.png"
        assert result.media_type == "image/png"
        mock_remove_bg.assert_called_once()

    @patch('src.utils.remove_bg.remove_bg_handler.remove_background')
    def test_remove_bg_handler_default_color(
        self,
        mock_remove_bg,
        mock_request,
        mock_file_upload
    ):
        """Test background removal with default color (black)"""
        mock_file_upload.filename = "test.jpg"
        mock_file_upload.file.read.return_value = b"fake image content"

        result = remove_bg_handler(
            request=mock_request,
            background_tasks=MagicMock(),
            file=mock_file_upload,
            color=None
        )

        assert isinstance(result, FileResponse)
        mock_remove_bg.assert_called_once()
        call_args = mock_remove_bg.call_args
        assert call_args[1]['text_color'] == (0, 0, 0)

    def test_remove_bg_handler_no_filename(self, mock_request):
        """Test handler with file without filename"""
        mock_file = MagicMock()
        mock_file.filename = None

        result = remove_bg_handler(
            request=mock_request,
            background_tasks=MagicMock(),
            file=mock_file,
            color=None
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/remove_bg"
        assert result.status_code == 303

    def test_remove_bg_handler_invalid_extension(self, mock_request):
        """Test handler with unsupported file extension"""
        mock_file = MagicMock()
        mock_file.filename = "test.pdf"

        result = remove_bg_handler(
            request=mock_request,
            background_tasks=MagicMock(),
            file=mock_file,
            color=None
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/remove_bg"
        assert result.status_code == 303

    def test_remove_bg_handler_invalid_color_format(self, mock_request, mock_file_upload):
        """Test handler with invalid color format"""
        mock_file_upload.filename = "test.png"
        mock_file_upload.file.read.return_value = b"fake image content"

        result = remove_bg_handler(
            request=mock_request,
            background_tasks=MagicMock(),
            file=mock_file_upload,
            color="invalid"
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/remove_bg"
        assert result.status_code == 303

    @patch('src.utils.remove_bg.remove_bg_handler.remove_background')
    def test_remove_bg_handler_allowed_extensions(
        self,
        mock_remove_bg,
        mock_request,
        temp_file
    ):
        """Test handler with all allowed file extensions"""
        allowed_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif']

        for ext in allowed_extensions:
            mock_file = MagicMock()
            mock_file.filename = f"test{ext}"
            mock_file.file.read.return_value = b"fake image content"

            result = remove_bg_handler(
                request=mock_request,
                background_tasks=MagicMock(),
                file=mock_file,
                color=None
            )

            assert isinstance(result, FileResponse)
            mock_remove_bg.reset_mock()

    @patch('src.utils.remove_bg.remove_bg_handler.remove_background')
    def test_remove_bg_handler_output_filename(
        self,
        mock_remove_bg,
        mock_request,
        mock_file_upload
    ):
        """Test handler generates correct output filename"""
        mock_file_upload.filename = "my_image.jpg"
        mock_file_upload.file.read.return_value = b"fake image content"

        result = remove_bg_handler(
            request=mock_request,
            background_tasks=MagicMock(),
            file=mock_file_upload,
            color=None
        )

        assert isinstance(result, FileResponse)
        assert result.filename == "my_image_no_bg.png"

    @patch('src.utils.remove_bg.remove_bg_handler.remove_background')
    def test_remove_bg_handler_background_tasks(
        self,
        mock_remove_bg,
        mock_request,
        mock_file_upload
    ):
        """Test handler adds cleanup task to background tasks"""
        mock_file_upload.filename = "test.png"
        mock_file_upload.file.read.return_value = b"fake image content"
        mock_background_tasks = MagicMock()

        result = remove_bg_handler(
            request=mock_request,
            background_tasks=mock_background_tasks,
            file=mock_file_upload,
            color=None
        )

        assert isinstance(result, FileResponse)
        mock_background_tasks.add_task.assert_called_once()

    @patch('src.utils.remove_bg.remove_bg_handler.remove_background')
    def test_remove_bg_handler_exception_handling(
        self,
        mock_remove_bg,
        mock_request,
        mock_file_upload
    ):
        """Test handler exception handling"""
        mock_file_upload.filename = "test.png"
        mock_file_upload.file.read.return_value = b"fake image content"
        mock_remove_bg.side_effect = Exception("Processing error")

        result = remove_bg_handler(
            request=mock_request,
            background_tasks=MagicMock(),
            file=mock_file_upload,
            color=None
        )

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/remove_bg"
        assert result.status_code == 303
