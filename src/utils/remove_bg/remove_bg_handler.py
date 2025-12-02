import os
import tempfile
import base64
from fastapi import File, Form, Request, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse

from src.utils.remove_bg.remove_bg_document import remove_background, parse_rgb_color


def remove_bg_handler(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    color: str | None = Form(None)
):
    """
    Handler for removing background from uploaded image.

    Args:
        request: FastAPI request object
        background_tasks: Background tasks for cleanup
        file: Uploaded image file
        color: RGB color string in format "R,G,B" (default: black "0,0,0")
    """
    try:
        if not file.filename:
            raise ValueError("Файл не был загружен")

        allowed_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
        file_ext = os.path.splitext(file.filename)[1].lower()

        if file_ext not in allowed_extensions:
            raise ValueError(
                f"Неподдерживаемый формат файла. "
                f"Поддерживаемые форматы: {', '.join(allowed_extensions)}"
            )

        text_color = None
        if color:
            try:
                text_color = parse_rgb_color(color)
            except ValueError as e:
                raise ValueError(f"Неверный формат цвета: {e}. Используйте формат 'R,G,B' (например, '255,0,0')")
        else:
            text_color = (0, 0, 0)

        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_input:
            temp_input_path = temp_input.name
            content = file.file.read()
            temp_input.write(content)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_output:
            temp_output_path = temp_output.name

        remove_background(
            input_path=temp_input_path,
            output_path=temp_output_path,
            invert=False,
            text_color=text_color
        )

        output_filename = f"{os.path.splitext(file.filename)[0]}_no_bg.png"

        def cleanup_temp_files():
            try:
                os.unlink(temp_input_path)
                os.unlink(temp_output_path)
            except OSError:
                pass

        background_tasks.add_task(cleanup_temp_files)

        return FileResponse(
            path=temp_output_path,
            filename=output_filename,
            media_type='image/png',
            background=background_tasks
        )

    except Exception as e:
        status = f"Ошибка обработки изображения: {str(e)}"
        response = RedirectResponse(url="/remove_bg", status_code=303)
        encoded_status = base64.b64encode(status.encode('utf-8')).decode('ascii')
        response.set_cookie("remove_bg_status", encoded_status, max_age=10)
        return response
