import subprocess
from pathlib import Path

import pytest
from PIL import Image

from ai_watermark_backend import WatermarkBackendError, clean_invisible_watermark
from ai_watermark_backend import backend_available


def test_missing_backend_fails_closed(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    source.write_bytes(b"input")
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(WatermarkBackendError, match="не установлен"):
        clean_invisible_watermark(source, tmp_path / "out.png")


def test_broken_executable_is_not_reported_available(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "remove-ai-watermarks")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", ""),
    )
    assert backend_available() is False


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
        Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(output, format="PNG")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)
    assert clean_invisible_watermark(source, output) == output.resolve()
