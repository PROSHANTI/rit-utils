from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError


def validate_xlsx_upload(content: bytes, filename: str, maximum: int) -> None:
    if not filename.lower().endswith(".xlsx") or not content:
        raise ValueError("Выберите файл .xlsx.")
    if len(content) > maximum:
        raise ValueError("Размер файла не должен превышать 5 МБ.")


def validation_detail(error: Mapping[str, Any]) -> str:
    kind, context = error["type"], error.get("ctx", {})
    if kind == "string_too_short":
        return "заполните поле"
    if kind == "string_too_long":
        return f"не более {context['max_length']} символов"
    if kind == "string_pattern_mismatch":
        return "артикул должен содержать только цифры"
    if kind in ("int_type", "int_parsing"):
        return "укажите целое число"
    if kind == "greater_than_equal":
        return f"укажите число не меньше {context['ge']}"
    if kind == "less_than_equal":
        return f"укажите число не больше {context['le']}"
    if kind == "missing":
        return "заполните поле"
    message = str(error.get("msg", "Проверьте значение.")).removeprefix("Value error, ")
    if error["loc"][0] == "expiry" and not _has_cyrillic(message):
        return "укажите существующие месяц и год в формате ММ.ГГГГ"
    return message


def _has_cyrillic(value: str) -> bool:
    return any("А" <= char <= "я" or char in "Ёё" for char in value)


def validation_message(error: ValidationError, labels: Mapping[str, str]) -> str:
    return "; ".join(
        f"{labels.get(str(issue['loc'][0]), str(issue['loc'][0]))}: {validation_detail(issue)}" for issue in error.errors()
    )
