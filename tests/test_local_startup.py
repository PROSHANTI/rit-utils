import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_application_starts_without_private_email_template():
    project = Path(__file__).resolve().parent.parent
    if (project / "src/utils/send_email/email_templates.py").exists():
        pytest.skip("Private template is present in this checkout")

    result = subprocess.run(
        [sys.executable, "-c", "from src.main import app; assert app is not None"],
        cwd=project,
        env={
            "PATH": os.defpath,
            "PYTHONPATH": str(project),
            "JWT_SECRET_KEY": "public-test-key-for-local-startup",
            "PASSWORD": "public-test-fixture",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
