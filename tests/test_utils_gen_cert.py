import base64
import subprocess
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.responses import FileResponse, RedirectResponse

from src.utils.gen_cert.gen_cert_handler import CertificateGenerator, CertificateRequest, LibreOfficeConverter


class TestLibreOfficeConverter:
    @patch("src.utils.gen_cert.gen_cert_handler.subprocess.run")
    def test_convert_runs_original_commands_and_moves_generated_pdf(self, mock_run, tmp_path):
        pptx_path = tmp_path / "source.pptx"
        generated_pdf = tmp_path / "source.pdf"
        pdf_path = tmp_path / "target.pdf"
        generated_pdf.write_bytes(b"PDF data")
        mock_run.return_value.returncode = 0

        LibreOfficeConverter().convert(f"{pptx_path}", f"{pdf_path}")

        assert pdf_path.read_bytes() == b"PDF data"
        assert not generated_pdf.exists()
        assert mock_run.call_args_list == [
            call(["libreoffice", "--version"], capture_output=True, timeout=5),
            call(
                ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", f"{tmp_path}", f"{pptx_path}"],
                capture_output=True,
                text=True,
                timeout=30,
            ),
        ]

    @patch("src.utils.gen_cert.gen_cert_handler.subprocess.run")
    def test_convert_tries_next_executable_when_first_is_unavailable(self, mock_run, tmp_path):
        pptx_path = tmp_path / "source.pptx"
        pdf_path = tmp_path / "source.pdf"
        pdf_path.write_bytes(b"PDF data")
        mock_run.side_effect = [FileNotFoundError("not found"), MagicMock(returncode=0), MagicMock(returncode=0)]

        LibreOfficeConverter().convert(f"{pptx_path}", f"{pdf_path}")

        assert mock_run.call_args.args[0][0] == "/usr/bin/libreoffice"
        assert pdf_path.read_bytes() == b"PDF data"

    @patch("src.utils.gen_cert.gen_cert_handler.subprocess.run", side_effect=FileNotFoundError("not found"))
    def test_convert_reports_unavailable_libreoffice(self, mock_run):
        with pytest.raises(Exception, match="LibreOffice не найден"):
            LibreOfficeConverter().convert("fake.pptx", "fake.pdf")

        assert mock_run.call_count == 6

    @pytest.mark.parametrize(
        ("conversion_result", "error_message"),
        [
            pytest.param(MagicMock(returncode=1, stderr="conversion error"), "LibreOffice error", id="command-failed"),
            pytest.param(subprocess.TimeoutExpired("libreoffice", 30), "Превышено время ожидания", id="timeout"),
            pytest.param(TimeoutError("Timeout"), "Ошибка конвертации", id="unexpected-error"),
        ],
    )
    @patch("src.utils.gen_cert.gen_cert_handler.subprocess.run")
    def test_convert_reports_command_errors(self, mock_run, conversion_result, error_message):
        mock_run.side_effect = [MagicMock(returncode=0), conversion_result]

        with pytest.raises(Exception, match=error_message):
            LibreOfficeConverter().convert("fake.pptx", "fake.pdf")

    @patch("src.utils.gen_cert.gen_cert_handler.subprocess.run")
    def test_convert_reports_missing_generated_pdf(self, mock_run, tmp_path):
        mock_run.return_value.returncode = 0

        with pytest.raises(Exception, match="PDF файл не был создан"):
            LibreOfficeConverter().convert(f"{tmp_path / 'source.pptx'}", f"{tmp_path / 'target.pdf'}")


class TestCertificateGenerator:
    @pytest.mark.parametrize("number", [100000, 999999])
    @patch("src.utils.gen_cert.gen_cert_handler.random.randint")
    def test_serial_number_uses_six_digit_range(self, mock_randint, number):
        mock_randint.return_value = number

        result = CertificateGenerator._get_random_number()

        assert result == number
        mock_randint.assert_called_once_with(100000, 999999)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("name", "price", "expected_name", "expected_price"),
        [
            pytest.param("  recipient  ", "  5000  ", "recipient", "5000 ₽", id="numeric-price"),
            pytest.param("recipient", "бесплатно", "recipient", "бесплатно", id="text-price"),
            pytest.param("", "", "", "", id="empty-values"),
            pytest.param(None, None, "", "", id="missing-values"),
        ],
    )
    @patch.object(Path, "exists", return_value=True)
    @patch("src.utils.gen_cert.gen_cert_handler.Presentation")
    @patch.object(CertificateGenerator, "_get_random_number", return_value=123456)
    async def test_generate_replaces_fields_and_cleans_download(
        self, mock_number, mock_presentation, mock_exists, mock_pptx, name, price, expected_name, expected_price
    ):
        mock_presentation.return_value = mock_pptx
        paragraph = mock_pptx.slides[0].shapes[0].text_frame.paragraphs[0]
        runs = [MagicMock(text="name"), MagicMock(text="price"), MagicMock(text="serial")]
        paragraph.runs = runs
        converter = MagicMock(spec=LibreOfficeConverter)

        response = CertificateGenerator(converter=converter).generate(CertificateRequest(name=name, price=price))

        assert isinstance(response, FileResponse)
        assert response.filename == "Сертификат.pdf"
        assert response.media_type == "application/pdf"
        assert [run.text for run in runs] == [expected_name, expected_price, "123456"]
        converter.convert.assert_called_once()
        pptx_path, pdf_path = converter.convert.call_args.args
        assert response.path == pdf_path
        assert response.background is not None
        await response.background()
        assert not Path(pptx_path).is_file()
        assert not Path(pdf_path).is_file()

    @patch.object(Path, "exists", return_value=False)
    def test_generate_missing_template_returns_status_cookie(self, mock_exists):
        response = CertificateGenerator().generate(CertificateRequest())

        assert isinstance(response, RedirectResponse)
        assert response.status_code == 303
        assert response.headers["location"] == "/gen_rit_cert"
        cookie = SimpleCookie(response.headers["set-cookie"])["gen_cert_status"]
        assert base64.b64decode(cookie.value).decode("utf-8").startswith("Ошибка генерации сертификата: Файл шаблона не найден:")
        assert cookie["max-age"] == "10"

    @patch.object(Path, "exists", return_value=True)
    @patch("src.utils.gen_cert.gen_cert_handler.Presentation")
    def test_generate_conversion_failure_cleans_both_temporary_files(self, mock_presentation, mock_exists, mock_pptx):
        mock_presentation.return_value = mock_pptx
        converter = MagicMock(spec=LibreOfficeConverter)
        converter.convert.side_effect = ValueError("Conversion error")

        response = CertificateGenerator(converter=converter).generate(CertificateRequest(name="recipient", price="5000"))

        assert isinstance(response, RedirectResponse)
        assert response.status_code == 303
        assert response.headers["location"] == "/gen_rit_cert"
        cookie = SimpleCookie(response.headers["set-cookie"])["gen_cert_status"]
        assert base64.b64decode(cookie.value).decode("utf-8") == "Ошибка генерации сертификата: Conversion error"
        assert all(not Path(temporary_path).is_file() for temporary_path in converter.convert.call_args.args)
