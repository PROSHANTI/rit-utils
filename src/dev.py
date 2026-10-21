"""Локальный HTTPS для разработки с защищёнными cookies авторизации."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import uvicorn


@dataclass(frozen=True, slots=True)
class LocalDevelopmentServer:
    certificates: Path = Path(__file__).resolve().parent.parent / "data" / "localhost"

    def run(self) -> None:
        certificate, key = self._prepare_certificate()
        print("Локальное приложение: https://localhost:8000")
        print("Сертификат самоподписанный: при первом открытии браузер попросит подтвердить исключение.")
        uvicorn.run(
            "src.main:app", host="127.0.0.1", port=8000, reload=True, ssl_certfile=str(certificate), ssl_keyfile=str(key)
        )

    def _prepare_certificate(self) -> tuple[Path, Path]:
        certificate = self.certificates / "certificate.pem"
        key = self.certificates / "key.pem"
        if not certificate.is_file() or not key.is_file():
            openssl = shutil.which("openssl")
            if openssl is None:
                raise RuntimeError("Не найден openssl. На macOS установите его: brew install openssl")
            self.certificates.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    openssl,
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "365",
                    "-keyout",
                    str(key),
                    "-out",
                    str(certificate),
                    "-subj",
                    "/CN=localhost",
                    "-addext",
                    "subjectAltName=DNS:localhost,IP:127.0.0.1",
                ],
                check=True,
                capture_output=True,
            )
            key.chmod(0o600)
        return certificate, key


if __name__ == "__main__":
    LocalDevelopmentServer().run()
