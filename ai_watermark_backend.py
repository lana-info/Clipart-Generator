"""Optional local backend boundary for invisible AI-watermark cleanup."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image

MAX_OUTPUT_BYTES = 128 * 1024 * 1024

class WatermarkBackendError(RuntimeError):
    pass


def backend_available() -> bool:
    executable = shutil.which("remove-ai-watermarks")
    if not executable:
        return False
    try:
        probe = subprocess.run(
            [executable, "--help"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def clean_invisible_watermark(
    source: Path,
    output: Path,
    *,
    timeout_seconds: int = 300,
    output_root: Path | None = None,
) -> Path:
    source = Path(source).resolve()
    output = Path(output).resolve()
    if not source.is_file():
        raise WatermarkBackendError("Исходный файл не найден")
    if timeout_seconds < 1 or timeout_seconds > 1800:
        raise ValueError("Недопустимый лимит времени")
    executable = shutil.which("remove-ai-watermarks")
    if not executable:
        raise WatermarkBackendError("Экспериментальный backend не установлен")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output == source or source.parent == output.parent and output.name == source.name:
        raise WatermarkBackendError("Выходной файл должен отличаться от исходного")
    if output_root is not None:
        root = Path(output_root).resolve()
        try:
            output.relative_to(root)
        except ValueError as error:
            raise WatermarkBackendError("Выходной файл находится вне рабочей папки") from error
    command = [executable, "invisible", str(source), "-o", str(output), "--force"]
    safe_env = {"PATH": os.environ.get("PATH", "")}
    try:
        completed = subprocess.run(
            command,
            cwd=str(output.parent),
            env=safe_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        raise WatermarkBackendError("Экспериментальная очистка превысила лимит времени") from error
    except OSError as error:
        raise WatermarkBackendError("Не удалось запустить экспериментальный backend") from error
    if completed.returncode != 0:
        raise WatermarkBackendError("Экспериментальный backend вернул ошибку")
    if not output.is_file() or output.stat().st_size == 0:
        raise WatermarkBackendError("Экспериментальный backend не создал результат")
    if output.stat().st_size > MAX_OUTPUT_BYTES:
        raise WatermarkBackendError("Экспериментальный backend создал слишком большой файл")
    try:
        with Image.open(output) as image:
            image.verify()
            if image.width * image.height > 100_000_000:
                raise WatermarkBackendError("Экспериментальный backend создал слишком большое изображение")
    except WatermarkBackendError:
        raise
    except Exception as error:
        raise WatermarkBackendError("Экспериментальный backend создал недопустимое изображение") from error
    return output
