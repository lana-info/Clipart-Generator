"""Run the isolated, research-only reverse-SynthID M1 pilot.

The upstream implementation is not vendored or imported by the application.
This benchmark runner accepts only the pinned research checkout, pinned local
VAE files, and the three documented user-owned fixtures. Network access is
disabled for execution and outputs are always written to a new directory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


SCHEMA_VERSION = 1
PILOT_ID = "M1"
UPSTREAM_REPOSITORY = "https://github.com/aloshdenny/reverse-SynthID"
UPSTREAM_COMMIT = "b11083676fd3ee3ff97ce9d03c0e409e46905902"
UPSTREAM_LICENSE_SHA256 = (
    "4ab00ab4e98d7316afabd6228d9c568472e8125168c99801bf8642c4e56e146c"
)
UPSTREAM_FILE_HASHES = {
    "requirements.txt": "67e755333674decac85b7397d73197a5745acd9d3aafd34d30ec153ef95a6c61",
    "scripts/dissolve_batch.py": (
        "63c42169eec1e7a93285141b827ef739695da27008fcd52e9d8b4375f2aa646e"
    ),
    "src/extraction/synthid_bypass_v4.py": (
        "0ff9d8357115686ff6e951490027a14eb3cc9335a4bb6d62e01f59b44dd7b779"
    ),
    "src/extraction/synthid_bypass.py": (
        "812712437fba06f819808914f1aad260b6f929577a9c4928091414e9407b6eed"
    ),
    "src/extraction/vae_regen.py": (
        "ec347d545e34a717a1e03e65671d642cb149c35cef98ebc732ea5c0eb18c7667"
    ),
    "artifacts/spectral_codebook_v4.npz": (
        "f105de83ae3aca85330793bf8780d4bcd364a1df009685c1abf24af26dbe5366"
    ),
}
SAFE_CODEBOOK_SHA256 = "56062cd85398d5e9d63f28c4ca8ecdb879954a15290e72b62100a71100ac300c"
SAFE_CODEBOOK_BYTES = 26_470_883
VAE_REPOSITORY = "stabilityai/sd-vae-ft-mse"
VAE_REVISION = "31f26fdeee1355a5c34592e401dd41e45d25a493"
VAE_LICENSE = "MIT"
VAE_FILE_HASHES = {
    "config.json": "92d3dfb746fca211a2c9e019e285f8597412211728dce3c5bcf4eda0f2d62e7e",
    "diffusion_pytorch_model.safetensors": (
        "a1d993488569e928462932c8c38a0760b874d166399b14414135bd9c42df5815"
    ),
}
RUNTIME_VERSIONS = {
    "torch": "2.11.0",
    "numpy": "2.3.5",
    "scipy": "1.17.0",
    "opencv-python": "4.13.0.92",
    "Pillow": "12.1.1",
    "safetensors": "0.8.0",
    "diffusers": "0.36.0",
    "accelerate": "1.12.0",
    "psutil": "7.2.2",
}
INPUT_SPECS = (
    {
        "id": "O1",
        "relative_path": "ai-metla-test-20260719/single-gemini-owned/before.png",
        "sha256": "d0d006a9fc9055726f2a84d3ef3aae1796ddcb18aa0b345d4b5a69cef3e26db9",
        "bytes": 1_435_948,
        "size": [912, 1147],
        "mode": "RGBA",
        "independent_scene": True,
    },
    {
        "id": "O2",
        "relative_path": "ai-metla-test-20260719/single-gemini-owned/after.png",
        "sha256": "226fb2daf426e0f701fd7e21f666aae8a38a849627ac1237c717a3fdbdb620bc",
        "bytes": 2_439_638,
        "size": [911, 1146],
        "mode": "RGBA",
        "independent_scene": False,
    },
    {
        "id": "O3",
        "relative_path": ".scratch/ai-metla-test-20260719/01-gemini-owned-normal-cleaned.png",
        "sha256": "e89ce0c0d931b5a9362d4401ef7cca6615bf344e2201489ac092dfb8fc331243",
        "bytes": 1_532_245,
        "size": [1142, 746],
        "mode": "RGB",
        "independent_scene": True,
    },
)
PROFILES = ("final", "nuke")
ALLOWED_EVIDENCE = {"detected", "not_detected", "not_verified", "unsupported"}
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_RUNS = 7
RECORDED_O1_FINAL = {
    "output_sha256": "6222fc5656c1a7db8735672af3f3e13db9d3bfc4d24c91225dd35884961a3af1",
    "psnr_rgb_db": 23.822557,
    "global_ssim_luma": 0.965238,
}


class PilotError(RuntimeError):
    """A path- and secret-safe M1 pilot failure."""


def _offline_only(function: Any) -> Any:
    """Block Python socket connections for the complete profile execution."""

    @wraps(function)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        original_connect = socket.socket.connect
        original_connect_ex = socket.socket.connect_ex
        original_create_connection = socket.create_connection

        def deny_connection(*_: Any, **__: Any) -> Any:
            raise PilotError("Network access is blocked during the M1 pilot")

        socket.socket.connect = deny_connection
        socket.socket.connect_ex = deny_connection
        socket.create_connection = deny_connection
        try:
            return function(*args, **kwargs)
        finally:
            socket.socket.connect = original_connect
            socket.socket.connect_ex = original_connect_ex
            socket.create_connection = original_create_connection

    return guarded


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def _run_git(upstream: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(upstream), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PilotError("Unable to audit the pinned upstream checkout") from error
    if result.returncode != 0:
        raise PilotError("Unable to audit the pinned upstream checkout")
    return result.stdout.strip()


def audit_upstream(upstream: Path) -> dict[str, Any]:
    upstream = upstream.resolve(strict=True)
    if not upstream.is_dir():
        raise PilotError("Pinned upstream checkout is not a directory")
    if _run_git(upstream, "rev-parse", "HEAD") != UPSTREAM_COMMIT:
        raise PilotError("Upstream revision does not match the M1 pilot")
    if _run_git(upstream, "status", "--porcelain", "--untracked-files=all"):
        raise PilotError("Pinned upstream checkout is not clean")

    license_path = upstream / "LICENSE"
    if sha256_file(license_path) != UPSTREAM_LICENSE_SHA256:
        raise PilotError("Upstream research license does not match the reviewed file")
    license_text = license_path.read_text(encoding="utf-8")
    required_terms = (
        "Non-Commercial Use",
        "Commercial Use of this Software is strictly prohibited",
        "reverse-SynthID by Alosh Denny",
    )
    if not all(term in license_text for term in required_terms):
        raise PilotError("Upstream research license restrictions are incomplete")

    audited_files: dict[str, str] = {}
    for relative, expected in UPSTREAM_FILE_HASHES.items():
        candidate = upstream / relative
        if not candidate.is_file() or sha256_file(candidate) != expected:
            raise PilotError("Pinned upstream file hashes do not match the M1 pilot")
        audited_files[relative] = expected
    return {
        "repository": UPSTREAM_REPOSITORY,
        "commit": UPSTREAM_COMMIT,
        "working_tree_clean": True,
        "license": "reverse-SynthID Research License v1.0",
        "license_sha256": UPSTREAM_LICENSE_SHA256,
        "commercial_integration_allowed": False,
        "required_attribution": (
            "reverse-SynthID by Alosh Denny — "
            "github.com/aloshdenny/reverse-SynthID"
        ),
        "audited_files": audited_files,
    }


def audit_model(model_dir: Path) -> dict[str, Any]:
    model_dir = model_dir.resolve(strict=True)
    if not model_dir.is_dir():
        raise PilotError("Pinned VAE directory is not a directory")
    for relative, expected in VAE_FILE_HASHES.items():
        candidate = model_dir / relative
        if not candidate.is_file() or sha256_file(candidate) != expected:
            raise PilotError("Pinned VAE files do not match the M1 pilot")
    try:
        config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PilotError("Pinned VAE config is invalid") from error
    if config.get("_class_name") != "AutoencoderKL":
        raise PilotError("Pinned VAE config has an unexpected class")
    return {
        "repository": VAE_REPOSITORY,
        "revision": VAE_REVISION,
        "license": VAE_LICENSE,
        "files": dict(VAE_FILE_HASHES),
        "network_required_during_run": False,
    }


def audit_runtime() -> dict[str, Any]:
    installed: dict[str, str] = {}
    for package, expected in RUNTIME_VERSIONS.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as error:
            raise PilotError("Pinned benchmark runtime is incomplete") from error
        if actual != expected:
            raise PilotError("Benchmark runtime versions do not match the M1 pilot")
        installed[package] = actual
    return {
        "python": sys.version.split()[0],
        "packages": installed,
        "auto_update": False,
        "environment": "isolated_venv",
    }


def _validated_image(path: Path) -> tuple[list[int], str]:
    try:
        if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
            raise PilotError("Pilot image is missing or exceeds the size limit")
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.width * image.height > MAX_PIXELS:
                raise PilotError("Pilot image exceeds the pixel limit")
            return [image.width, image.height], image.mode
    except PilotError:
        raise
    except (OSError, ValueError) as error:
        raise PilotError("Pilot image is not decodable") from error


def validate_inputs(input_root: Path) -> list[dict[str, Any]]:
    input_root = input_root.resolve(strict=True)
    records: list[dict[str, Any]] = []
    for spec in INPUT_SPECS:
        path = (input_root / str(spec["relative_path"])).resolve(strict=True)
        if not _is_within(path, input_root):
            raise PilotError("Pilot input escapes the approved input root")
        size, mode = _validated_image(path)
        if (
            sha256_file(path) != spec["sha256"]
            or path.stat().st_size != spec["bytes"]
            or size != spec["size"]
            or mode != spec["mode"]
        ):
            raise PilotError("Pilot input does not match its approved manifest")
        records.append(
            {
                "id": spec["id"],
                "source_path": path,
                "sha256": spec["sha256"],
                "bytes": spec["bytes"],
                "size": size,
                "mode": mode,
                "ownership": "user_owned_documented",
                "independent_scene": spec["independent_scene"],
            }
        )
    return records


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _atomic_copy(source: Path, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            with source.open("rb") as source_stream:
                shutil.copyfileobj(source_stream, stream, length=1024 * 1024)
            stream.flush()
            os.fsync(stream.fileno())
        if sha256_file(temporary) != expected_sha256:
            raise PilotError("Atomic input copy failed its SHA-256 check")
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_run_directory(
    output_dir: Path, inputs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    output_dir = output_dir.resolve(strict=False)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise PilotError("Pilot output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for record in inputs:
        extension = record["source_path"].suffix.lower()
        destination = output_dir / "inputs" / f"{record['id']}{extension}"
        _atomic_copy(record["source_path"], destination, record["sha256"])
        copied.append({**record, "copied_path": destination})
    (output_dir / "outputs").mkdir()
    (output_dir / "contact-sheets").mkdir()
    return copied


class _PeakRssSampler:
    def __init__(self) -> None:
        self.peak = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "_PeakRssSampler":
        try:
            psutil = importlib.import_module("psutil")
        except ImportError as error:
            raise PilotError("Pinned benchmark runtime is incomplete") from error
        process = psutil.Process(os.getpid())

        def sample() -> None:
            while not self._stop.wait(0.05):
                try:
                    self.peak = max(self.peak, int(process.memory_info().rss))
                except (OSError, RuntimeError):
                    return

        self.peak = int(process.memory_info().rss)
        self._thread = threading.Thread(target=sample, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)


def _global_ssim(left: np.ndarray, right: np.ndarray) -> float:
    left = left.astype(np.float64)
    right = right.astype(np.float64)
    mean_left, mean_right = float(left.mean()), float(right.mean())
    var_left, var_right = float(left.var()), float(right.var())
    covariance = float(np.mean((left - mean_left) * (right - mean_right)))
    c1, c2 = 6.5025, 58.5225
    denominator = (mean_left**2 + mean_right**2 + c1) * (
        var_left + var_right + c2
    )
    if denominator == 0:
        return 1.0
    return float(
        ((2 * mean_left * mean_right + c1) * (2 * covariance + c2))
        / denominator
    )


def analyze_output(source_path: Path, output_path: Path) -> dict[str, Any]:
    source_size, source_mode = _validated_image(source_path)
    output_size, output_mode = _validated_image(output_path)
    with Image.open(source_path) as source_image:
        source = np.asarray(source_image.convert("RGBA"), dtype=np.int16)
    with Image.open(output_path) as output_image:
        output = np.asarray(
            output_image.convert("RGBA").resize(
                tuple(source_size), Image.Resampling.LANCZOS
            ),
            dtype=np.int16,
        )
    rgb_delta = np.abs(output[:, :, :3] - source[:, :, :3])
    alpha_delta = np.abs(output[:, :, 3] - source[:, :, 3])
    mse = float(np.mean((rgb_delta.astype(np.float64) / 255.0) ** 2))
    psnr = math.inf if mse == 0 else 10.0 * math.log10(1.0 / mse)
    source_gray = np.asarray(
        Image.fromarray(source.astype(np.uint8), "RGBA").convert("L")
    )
    output_gray = np.asarray(
        Image.fromarray(output.astype(np.uint8), "RGBA").convert("L")
    )
    source_alpha = source[:, :, 3].astype(np.float64) / 255.0
    output_alpha = output[:, :, 3].astype(np.float64) / 255.0
    alpha_union = float(np.maximum(source_alpha, output_alpha).sum())
    alpha_iou = (
        1.0
        if alpha_union == 0.0
        else float(np.minimum(source_alpha, output_alpha).sum() / alpha_union)
    )
    return {
        "source_size": source_size,
        "source_mode": source_mode,
        "output_size": output_size,
        "output_mode": output_mode,
        "output_sha256": sha256_file(output_path),
        "output_bytes": output_path.stat().st_size,
        "psnr_rgb_db": None if math.isinf(psnr) else round(psnr, 6),
        "global_ssim_luma": round(_global_ssim(source_gray, output_gray), 6),
        "rgb_changed_pixel_ratio_gt2": round(
            float(np.mean(np.max(rgb_delta, axis=2) > 2)), 6
        ),
        "rgb_mean_abs_delta": round(float(rgb_delta.mean()), 6),
        "source_transparent_pixels": int(np.count_nonzero(source[:, :, 3] < 255)),
        "output_transparent_pixels": int(np.count_nonzero(output[:, :, 3] < 255)),
        "alpha_changed_pixel_ratio": round(float(np.mean(alpha_delta > 0)), 6),
        "alpha_iou": round(alpha_iou, 6),
    }


_MISSING_MODULE = object()


def audit_safe_codebook(codebook_path: Path) -> dict[str, Any]:
    codebook_path = codebook_path.resolve(strict=True)
    if (
        not codebook_path.is_file()
        or codebook_path.stat().st_size != SAFE_CODEBOOK_BYTES
        or sha256_file(codebook_path) != SAFE_CODEBOOK_SHA256
    ):
        raise PilotError("Pickle-free codebook does not match the M1 pilot")
    try:
        with np.load(codebook_path, allow_pickle=False) as archive:
            if "format_version" not in archive.files or "keys" not in archive.files:
                raise PilotError("Pickle-free codebook is incomplete")
            for key in archive.files:
                if archive[key].dtype.hasobject:
                    raise PilotError("Pickle-free codebook contains an object array")
            profile_count = len(archive["keys"])
            if profile_count != 14:
                raise PilotError("Pickle-free codebook profile count changed")
    except (OSError, ValueError) as error:
        raise PilotError("Pickle-free codebook failed safe loading") from error
    return {
        "sha256": SAFE_CODEBOOK_SHA256,
        "bytes": SAFE_CODEBOOK_BYTES,
        "profile_count": profile_count,
        "pickle_allowed": False,
        "tracked": False,
    }


def _module_from_exact_path(name: str, path: Path) -> Any:
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PilotError("Pinned upstream module has no safe import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        raise PilotError("Pinned upstream could not be imported") from error
    if Path(module.__file__).resolve(strict=True) != path.resolve(strict=True):
        raise PilotError("Pinned upstream module resolved to an unexpected path")
    return module


class _NoPickleNumpyProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(np, name)

    @staticmethod
    def load(path: str | Path, *_: Any, **__: Any) -> Any:
        return np.load(path, allow_pickle=False)


@contextmanager
def _load_upstream(
    upstream: Path,
    model_dir: Path,
    codebook_path: Path,
) -> Iterable[tuple[Any, Any]]:
    extraction = (upstream / "src" / "extraction").resolve(strict=True)
    module_names = ("synthid_bypass", "vae_regen", "synthid_bypass_v4")
    previous_modules = {
        name: sys.modules.get(name, _MISSING_MODULE) for name in module_names
    }
    previous_path = list(sys.path)
    try:
        _module_from_exact_path("synthid_bypass", extraction / "synthid_bypass.py")
        vae_regen = _module_from_exact_path("vae_regen", extraction / "vae_regen.py")
        bypass_module = _module_from_exact_path(
            "synthid_bypass_v4", extraction / "synthid_bypass_v4.py"
        )
        original_load = vae_regen.load_vae

        def load_local_vae(
            model_id: str = "",
            device: str | None = None,
            dtype: str = "float32",
        ) -> tuple[Any, str]:
            del model_id
            return original_load(
                model_id=str(model_dir),
                device=device,
                dtype=dtype,
            )

        vae_regen.load_vae = load_local_vae
        bypass_module.np = _NoPickleNumpyProxy()
        codebook = bypass_module.SpectralCodebookV4()
        codebook.load(str(codebook_path))
        yield bypass_module.SynthIDBypassV4(), codebook
    finally:
        sys.path[:] = previous_path
        for name, previous in previous_modules.items():
            if previous is _MISSING_MODULE:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


@_offline_only
def execute_profiles(
    upstream: Path,
    model_dir: Path,
    codebook_path: Path,
    output_dir: Path,
    inputs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DIFFUSERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
        }
    )
    with _load_upstream(upstream, model_dir, codebook_path) as (bypass, codebook):
        return _execute_profiles_loaded(bypass, codebook, output_dir, inputs)


def _execute_one_profile(
    bypass: Any,
    codebook: Any,
    output_dir: Path,
    record: dict[str, Any],
    profile: str,
    purpose: str,
    output_suffix: str,
) -> dict[str, Any]:
    final_path = output_dir / "outputs" / f"{record['id']}__{output_suffix}.png"
    pending_path = final_path.with_name(f".{final_path.stem}.pending.png")
    started = time.perf_counter()
    try:
        with _PeakRssSampler() as memory:
            result = bypass.bypass_v4_file(
                str(record["copied_path"]),
                str(pending_path),
                codebook,
                strength=profile,
                model=None,
                verify=False,
            )
        _validated_image(pending_path)
        os.replace(pending_path, final_path)
    except Exception as error:
        pending_path.unlink(missing_ok=True)
        raise PilotError("Pinned M1 profile execution failed") from error
    metrics = analyze_output(record["copied_path"], final_path)
    return {
        "input_id": record["id"],
        "input_sha256": record["sha256"],
        "output_sha256": metrics["output_sha256"],
        "profile": profile,
        "purpose": purpose,
        "parameters": dict(bypass.FINAL_PRESETS[profile]),
        "processing": {
            "status": "succeeded",
            "wall_seconds": round(time.perf_counter() - started, 6),
            "peak_rss_bytes": memory.peak,
            "network_policy": "python_socket_connections_blocked",
            "cost_usd": 0.0,
            "runtime": "local_cpu",
        },
        "pixel_evidence": {
            "input": "not_verified",
            "output": "not_verified",
            "detector": "official_gemini_manual_handoff_pending",
        },
        "upstream_result": {
            "psnr": round(float(result.psnr), 6),
            "ssim": round(float(result.ssim), 6),
            "details": {
                key: value
                for key, value in result.details.items()
                if isinstance(value, (str, int, float, bool, type(None)))
            },
            "stages_applied": list(result.stages_applied),
        },
        "metrics": metrics,
        "output_file": final_path.name,
    }


@_offline_only
def execute_secure_repeat(
    upstream: Path,
    model_dir: Path,
    codebook_path: Path,
    output_dir: Path,
    record: dict[str, Any],
) -> dict[str, Any]:
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DIFFUSERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
        }
    )
    with _load_upstream(upstream, model_dir, codebook_path) as (bypass, codebook):
        return _execute_secure_repeat_loaded(bypass, codebook, output_dir, record)


def _execute_secure_repeat_loaded(
    bypass: Any,
    codebook: Any,
    output_dir: Path,
    record: dict[str, Any],
) -> dict[str, Any]:
    return _execute_one_profile(
        bypass,
        codebook,
        output_dir,
        record,
        "final",
        "secure_repeat",
        "secure-repeat",
    )


def _execute_profiles_loaded(
    bypass: Any,
    codebook: Any,
    output_dir: Path,
    inputs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    planned: list[tuple[dict[str, Any], str, str]] = [
        (record, profile, "primary")
        for record in inputs
        for profile in PROFILES
    ]
    planned.append((inputs[0], "final", "repeatability"))
    if len(planned) > MAX_RUNS:
        raise PilotError("M1 pilot exceeds its hard run limit")

    for record, profile, purpose in planned:
        suffix = "repeat" if purpose == "repeatability" else profile
        runs.append(
            _execute_one_profile(
                bypass,
                codebook,
                output_dir,
                record,
                profile,
                purpose,
                suffix,
            )
        )

    primary = next(
        run
        for run in runs
        if run["input_id"] == "O1"
        and run["profile"] == "final"
        and run["purpose"] == "primary"
    )
    repeat = next(run for run in runs if run["purpose"] == "repeatability")
    repeatability = {
        "input_id": "O1",
        "profile": "final",
        "comparable": (
            primary["metrics"]["output_sha256"]
            == repeat["metrics"]["output_sha256"]
        ),
        "output_sha256_equal": (
            primary["metrics"]["output_sha256"]
            == repeat["metrics"]["output_sha256"]
        ),
        "psnr_absolute_delta": abs(
            float(primary["metrics"]["psnr_rgb_db"])
            - float(repeat["metrics"]["psnr_rgb_db"])
        ),
        "ssim_absolute_delta": abs(
            float(primary["metrics"]["global_ssim_luma"])
            - float(repeat["metrics"]["global_ssim_luma"])
        ),
    }
    return runs, repeatability


def _fit_preview(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    preview = image.convert("RGBA")
    preview.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (238, 241, 245, 255))
    x = (size[0] - preview.width) // 2
    y = (size[1] - preview.height) // 2
    canvas.alpha_composite(preview, (x, y))
    return canvas.convert("RGB")


def build_contact_sheet(
    output_dir: Path, inputs: list[dict[str, Any]], runs: list[dict[str, Any]]
) -> Path:
    tile_size = (360, 300)
    header = 44
    sheet = Image.new(
        "RGB",
        (tile_size[0] * 3, (tile_size[1] + header) * len(inputs)),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for row, record in enumerate(inputs):
        files = [
            ("SOURCE", record["copied_path"]),
            (
                "FINAL",
                output_dir
                / "outputs"
                / next(
                    run["output_file"]
                    for run in runs
                    if run["input_id"] == record["id"]
                    and run["profile"] == "final"
                    and run["purpose"] == "primary"
                ),
            ),
            (
                "NUKE",
                output_dir
                / "outputs"
                / next(
                    run["output_file"]
                    for run in runs
                    if run["input_id"] == record["id"]
                    and run["profile"] == "nuke"
                ),
            ),
        ]
        y = row * (tile_size[1] + header)
        for col, (label, path) in enumerate(files):
            with Image.open(path) as image:
                preview = _fit_preview(image, tile_size)
            x = col * tile_size[0]
            sheet.paste(preview, (x, y + header))
            draw.text(
                (x + 12, y + 14),
                f"{record['id']} / {label}",
                fill=(18, 28, 42),
                font=font,
            )
    destination = output_dir / "contact-sheets" / "m1-contact-sheet.png"
    temporary = destination.with_name(".m1-contact-sheet.pending.png")
    sheet.save(temporary, format="PNG")
    os.replace(temporary, destination)
    return destination


def _safe_input_manifest(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in record.items()
            if key not in {"source_path", "copied_path"}
        }
        for record in records
    ]


def build_secure_repeat_report(
    *,
    upstream: Path,
    model_dir: Path,
    codebook_path: Path,
    input_root: Path,
    output_dir: Path,
    research_license_acknowledged: bool,
    ownership_confirmed: bool,
) -> dict[str, Any]:
    if not research_license_acknowledged:
        raise PilotError("Research license acknowledgement is required for execution")
    if not ownership_confirmed:
        raise PilotError("Input ownership confirmation is required for execution")
    upstream_audit = audit_upstream(upstream)
    model_audit = audit_model(model_dir)
    codebook_audit = audit_safe_codebook(codebook_path)
    runtime_audit = audit_runtime()
    source_records = validate_inputs(input_root)
    source_record = source_records[0]
    source_hash_before = sha256_file(source_record["source_path"])
    copied = prepare_run_directory(output_dir, [source_record])
    run = execute_secure_repeat(
        upstream.resolve(),
        model_dir.resolve(),
        codebook_path.resolve(),
        output_dir.resolve(),
        copied[0],
    )
    source_hash_after = sha256_file(source_record["source_path"])
    if source_hash_before != source_hash_after:
        raise PilotError("A source image changed during the secure repeat")
    comparison = {
        "recorded_output_sha256": RECORDED_O1_FINAL["output_sha256"],
        "secure_output_sha256": run["output_sha256"],
        "output_sha256_equal": (
            run["output_sha256"] == RECORDED_O1_FINAL["output_sha256"]
        ),
        "psnr_absolute_delta": abs(
            float(run["metrics"]["psnr_rgb_db"])
            - float(RECORDED_O1_FINAL["psnr_rgb_db"])
        ),
        "ssim_absolute_delta": abs(
            float(run["metrics"]["global_ssim_luma"])
            - float(RECORDED_O1_FINAL["global_ssim_luma"])
        ),
    }
    comparison["comparable"] = bool(
        comparison["output_sha256_equal"]
        and comparison["psnr_absolute_delta"] == 0.0
        and comparison["ssim_absolute_delta"] == 0.0
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "pilot_id": PILOT_ID,
        "status": "secure_repeat_complete_official_evidence_pending",
        "method": "reverse-SynthID V4 Round-06",
        "research_only": True,
        "production_integration_allowed": False,
        "upstream": upstream_audit,
        "model": model_audit,
        "codebook": codebook_audit,
        "runtime": runtime_audit,
        "execution_trust_boundary": {
            "pinned_upstream_hashes": True,
            "pickle_allowed": False,
            "python_socket_connections_blocked": True,
            "os_filesystem_sandbox": False,
        },
        "input": _safe_input_manifest([source_record])[0],
        "run": run,
        "comparison": comparison,
        "source_hash_unchanged": source_hash_before == source_hash_after,
        "processing": "succeeded",
        "pixel_evidence": "not_verified",
        "official_handoff": {
            "required": True,
            "performed": False,
            "network_upload_performed": False,
        },
        "decision": "inconclusive_official_evidence_pending",
    }

def build_report(
    *,
    upstream: Path,
    model_dir: Path,
    codebook_path: Path,
    input_root: Path,
    output_dir: Path,
    execute: bool,
    research_license_acknowledged: bool,
    ownership_confirmed: bool,
) -> dict[str, Any]:
    if execute and not research_license_acknowledged:
        raise PilotError("Research license acknowledgement is required for execution")
    if execute and not ownership_confirmed:
        raise PilotError("Input ownership confirmation is required for execution")
    upstream_audit = audit_upstream(upstream)
    model_audit = audit_model(model_dir)
    codebook_audit = audit_safe_codebook(codebook_path)
    runtime_audit = audit_runtime()
    source_records = validate_inputs(input_root)
    copied = prepare_run_directory(output_dir, source_records)
    source_hashes_before = {
        record["id"]: sha256_file(record["source_path"]) for record in source_records
    }

    runs: list[dict[str, Any]] = []
    repeatability: dict[str, Any] = {
        "status": "not_run",
        "comparable": False,
    }
    contact_sheet: str | None = None
    if execute:
        runs, repeatability = execute_profiles(
            upstream.resolve(),
            model_dir.resolve(),
            codebook_path.resolve(),
            output_dir.resolve(),
            copied,
        )
        contact_sheet_path = build_contact_sheet(output_dir.resolve(), copied, runs)
        contact_sheet = contact_sheet_path.relative_to(output_dir.resolve()).as_posix()

    source_hashes_after = {
        record["id"]: sha256_file(record["source_path"]) for record in source_records
    }
    if source_hashes_before != source_hashes_after:
        raise PilotError("A source image changed during the M1 pilot")

    return {
        "schema_version": SCHEMA_VERSION,
        "pilot_id": PILOT_ID,
        "status": "executed_official_evidence_pending" if execute else "prepared",
        "method": "reverse-SynthID V4 Round-06",
        "research_only": True,
        "production_integration_allowed": False,
        "upstream": upstream_audit,
        "model": model_audit,
        "codebook": codebook_audit,
        "runtime": runtime_audit,
        "inputs": _safe_input_manifest(source_records),
        "profiles": list(PROFILES),
        "runs": runs,
        "repeatability": repeatability,
        "source_hashes_unchanged": source_hashes_before == source_hashes_after,
        "contact_sheet": contact_sheet,
        "processing": "succeeded" if execute else "not_run",
        "pixel_evidence": "not_verified",
        "official_handoff": {
            "required": True,
            "performed": False,
            "network_upload_performed": False,
            "allowed_statuses": sorted(ALLOWED_EVIDENCE),
        },
        "decision": "inconclusive_official_evidence_pending",
        "limitations": [
            "The upstream research license prohibits commercial integration without a separate agreement.",
            "No output may be described as removed without official input/output evidence.",
            "O2 may be derived from O1 and is not an independent scene.",
            "This three-input pilot cannot establish universal effectiveness.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the isolated, research-only reverse-SynthID M1 pilot."
    )
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--secure-repeat-only", action="store_true")
    parser.add_argument("--acknowledge-research-license", action="store_true")
    parser.add_argument("--ownership-confirmed", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.secure_repeat_only:
            report = build_secure_repeat_report(
                upstream=args.upstream,
                model_dir=args.model_dir,
                codebook_path=args.codebook,
                input_root=args.input_root,
                output_dir=args.output_dir,
                research_license_acknowledged=args.acknowledge_research_license,
                ownership_confirmed=args.ownership_confirmed,
            )
        else:
            report = build_report(
                upstream=args.upstream,
                model_dir=args.model_dir,
                codebook_path=args.codebook,
                input_root=args.input_root,
                output_dir=args.output_dir,
                execute=args.execute,
                research_license_acknowledged=args.acknowledge_research_license,
                ownership_confirmed=args.ownership_confirmed,
            )
        _atomic_json(args.output_dir.resolve() / "manifest.json", report)
    except (OSError, PilotError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
