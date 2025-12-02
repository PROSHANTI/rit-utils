"""
Utility for removing background from documents and text images.
Uses Otsu's method for automatic threshold determination.
"""

import sys
from pathlib import Path

import cv2


def parse_rgb_color(color_str: str) -> tuple[int, int, int]:
    """
    Parses RGB color string to BGR tuple for OpenCV.

    Args:
        color_str: RGB color string in format "R,G,B" (e.g., "255,0,0")

    Returns:
        Tuple (B, G, R) for OpenCV
    """
    try:
        parts = color_str.split(',')
        if len(parts) != 3:
            raise ValueError("Color must be in format 'R,G,B'")

        r = int(parts[0].strip())
        g = int(parts[1].strip())
        b = int(parts[2].strip())

        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError("RGB values must be between 0 and 255")

        return (b, g, r)
    except ValueError as e:
        raise ValueError(f"Invalid color format: {e}")


def remove_background(
    input_path: str,
    output_path: str,
    invert: bool = False,
    text_color: tuple[int, int, int] | None = None
) -> None:
    """
    Removes background from document using Otsu's method.

    Args:
        input_path: Path to input image
        output_path: Path to save result
        invert: Invert result (for dark text on light background)
        text_color: Text color in BGR format (B, G, R). If None, preserves original color.
    """
    input_file = Path(input_path)

    if not input_file.exists():
        sys.exit(1)

    try:
        img = cv2.imread(input_path)
        if img is None:
            sys.exit(1)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        if not invert:
            mean_brightness = float(gray.mean())
            if mean_brightness > 128:
                invert = True

        if invert:
            mask = cv2.bitwise_not(binary)
        else:
            mask = binary

        result = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

        if text_color is not None:
            text_mask = mask > 0
            result[text_mask, 0] = text_color[0]
            result[text_mask, 1] = text_color[1]
            result[text_mask, 2] = text_color[2]

        result[:, :, 3] = mask
        cv2.imwrite(output_path, result)

    except Exception:
        sys.exit(1)
