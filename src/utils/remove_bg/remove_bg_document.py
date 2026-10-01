"""Удаление фона документов и изображений с текстом методом Оцу."""

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BackgroundRemovalOptions:
    invert: bool = False
    text_color: tuple[int, int, int] | None = None


class BackgroundRemover:
    def __init__(self, options: BackgroundRemovalOptions | None = None) -> None:
        self.options = options or BackgroundRemovalOptions()

    def remove(self, input_path: str, output_path: str) -> None:
        """Сохраняет PNG с прозрачным фоном и заданным BGR-цветом текста."""
        logger.info("Начато удаление фона изображения")
        input_file = Path(input_path)

        try:
            if not input_file.exists():
                raise FileNotFoundError("Входное изображение отсутствует")

            image = cv2.imread(input_path)

            if image is None:
                raise ValueError("Изображение не удалось прочитать")

            mask = self._create_mask(image)
            result = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)

            if (text_color := self.options.text_color) is not None:
                text_mask = mask > 0
                result[text_mask, 0] = text_color[0]
                result[text_mask, 1] = text_color[1]
                result[text_mask, 2] = text_color[2]

            result[:, :, 3] = mask

            if not cv2.imwrite(output_path, result):
                raise OSError("Не удалось сохранить изображение после удаления фона")

            logger.info("Удаление фона изображения завершено")

        except Exception:
            logger.exception("Не удалось удалить фон изображения")
            raise

    @staticmethod
    def parse_color(color_str: str) -> tuple[int, int, int]:
        """Проверяет RGB-строку и возвращает BGR-кортеж для OpenCV."""
        logger.debug("Начат разбор RGB-цвета")

        try:
            parts = color_str.split(",")

            if len(parts) != 3:
                raise ValueError("Color must be in format 'R,G,B'")

            red = int(parts[0].strip())
            green = int(parts[1].strip())
            blue = int(parts[2].strip())

            if not (0 <= red <= 255 and 0 <= green <= 255 and 0 <= blue <= 255):
                raise ValueError("RGB values must be between 0 and 255")

            logger.debug("Разбор RGB-цвета завершён")
            return blue, green, red

        except ValueError as exc:
            logger.debug("RGB-цвет не прошёл проверку формата")
            raise ValueError(f"Invalid color format: {exc}") from exc

    def _create_mask(self, image: cv2.typing.MatLike) -> cv2.typing.MatLike:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        invert = self.options.invert or float(gray.mean()) > 128

        if invert:
            return cv2.bitwise_not(binary)

        return binary
