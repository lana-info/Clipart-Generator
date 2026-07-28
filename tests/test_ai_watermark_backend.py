import subprocess
from pathlib import Path

import pytest

from ai_watermark_backend import WatermarkBackendError, clean_invisible_watermark


def test_missing_backend_fails_closed(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    source.write_bytes(b"input")
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(WatermarkBackendError, match="не установлен"):
        clean_invisible_watermark(source, tmp_path / "out.png")


def test_backend_output_is_checked(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    output = tmp_path / "out.png"
    source.write_bytes(b"input")
    monkeypatch.setattr("shutil.which", lambda _: "remove-ai-watermarks")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "", ""))
    with pytest.raises(WatermarkBackendError, match="не создал"):
        clean_invisible_watermark(source, output)


def test_backend_accepts_only_created_output(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    output = tmp_path / "out.png"
    source.write_bytes(b"input")
    monkeypatch.setattr("shutil.which", lambda _: "remove-ai-watermarks")

    def fake_run(*args, **kwargs):
        output.write_bytes(b"clean")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)
    assert clean_invisible_watermark(source, output) == output.resolve()
