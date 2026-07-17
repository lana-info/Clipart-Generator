"""Run the no-download Task 42 local diffusion feasibility preflight."""

from __future__ import annotations

import argparse
import ast
import ctypes
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SNAPSHOT_DATE = "2026-07-16"
UPSTREAM_REPOSITORY = "https://github.com/lana-info/remove-ai-watermarks"
UPSTREAM_COMMIT = "190dc89d234fd7e3a61ff755f01251c9c0b87ef0"
GIB = 1024**3
HUGGINGFACE_HOST = "huggingface.co"
MAX_MODEL_METADATA_BYTES = 4 * 1024 * 1024

MODEL_COMPONENTS: dict[str, dict[str, Any]] = {
    "sdxl": {
        "model_id": "stabilityai/stable-diffusion-xl-base-1.0",
        "revision": "462165984030d82259a11f4367a4eed129e94a7b",
        "license": "CreativeML Open RAIL++-M",
        "api_license": "openrail++",
        "serialized_weight_bytes": 13_875_688_436,
        "required_files": {
            "text_encoder/model.safetensors": 492_265_168,
            "text_encoder_2/model.safetensors": 2_778_702_264,
            "unet/diffusion_pytorch_model.safetensors": 10_270_077_736,
            "vae/diffusion_pytorch_model.safetensors": 334_643_268,
        },
        "source": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/tree/462165984030d82259a11f4367a4eed129e94a7b",
    },
    "controlnet": {
        "model_id": "xinsir/controlnet-canny-sdxl-1.0",
        "revision": "1271357eda52d54b857c650cacb5b51144643ccb",
        "license": "Apache-2.0",
        "api_license": "apache-2.0",
        "serialized_weight_bytes": 2_502_139_104,
        "required_files": {
            "diffusion_pytorch_model.safetensors": 2_502_139_104,
        },
        "source": "https://huggingface.co/xinsir/controlnet-canny-sdxl-1.0/tree/1271357eda52d54b857c650cacb5b51144643ccb",
        "combined_pipeline_obligation": "SDXL Open RAIL++-M also applies to the SDXL + ControlNet pipeline.",
    },
    "qwen": {
        "model_id": "Qwen/Qwen-Image",
        "revision": "75e0b4be04f60ec59a75f475837eced720f823b6",
        "license": "Apache-2.0",
        "api_license": "apache-2.0",
        "serialized_weight_bytes": 57_699_249_390,
        "required_files": {
            "text_encoder/model-00001-of-00004.safetensors": 4_968_243_304,
            "text_encoder/model-00002-of-00004.safetensors": 4_991_495_816,
            "text_encoder/model-00003-of-00004.safetensors": 4_932_751_040,
            "text_encoder/model-00004-of-00004.safetensors": 1_691_924_384,
            "transformer/diffusion_pytorch_model-00001-of-00009.safetensors": 4_989_364_312,
            "transformer/diffusion_pytorch_model-00002-of-00009.safetensors": 4_984_214_160,
            "transformer/diffusion_pytorch_model-00003-of-00009.safetensors": 4_946_470_000,
            "transformer/diffusion_pytorch_model-00004-of-00009.safetensors": 4_984_213_736,
            "transformer/diffusion_pytorch_model-00005-of-00009.safetensors": 4_946_471_896,
            "transformer/diffusion_pytorch_model-00006-of-00009.safetensors": 4_946_451_560,
            "transformer/diffusion_pytorch_model-00007-of-00009.safetensors": 4_908_690_520,
            "transformer/diffusion_pytorch_model-00008-of-00009.safetensors": 4_984_232_856,
            "transformer/diffusion_pytorch_model-00009-of-00009.safetensors": 1_170_918_840,
            "vae/diffusion_pytorch_model.safetensors": 253_806_966,
        },
        "source": "https://huggingface.co/Qwen/Qwen-Image/tree/75e0b4be04f60ec59a75f475837eced720f823b6",
    },
    "fp16_vae": {
        "model_id": "madebyollin/sdxl-vae-fp16-fix",
        "revision": "207b116dae70ace3637169f1ddd2434b91b3a8cd",
        "license": "MIT",
        "api_license": "mit",
        "serialized_weight_bytes": 334_643_238,
        "required_files": {
            "diffusion_pytorch_model.safetensors": 334_643_238,
        },
        "source": "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/tree/207b116dae70ace3637169f1ddd2434b91b3a8cd",
        "used_by_local_cpu_preflight": False,
        "license_caveat": "The model card says it is based on SDXL-VAE; MIT metadata alone does not resolve inherited SDXL obligations.",
    },
}

PIPELINES: dict[str, dict[str, Any]] = {
    "sdxl": {
        "components": ("sdxl",),
        "required_accelerators": ("cuda", "xpu", "mps"),
        "cpu_dtype": "float32",
    },
    "controlnet": {
        "components": ("sdxl", "controlnet"),
        "required_accelerators": ("cuda", "xpu", "mps"),
        "cpu_dtype": "float32",
    },
    "qwen": {
        "components": ("qwen",),
        "required_accelerators": ("cuda", "xpu"),
        "cpu_dtype": "float32",
    },
}

EXPECTED_UPSTREAM_MODEL_CONSTANTS = {
    "DEFAULT_MODEL_ID": MODEL_COMPONENTS["sdxl"]["model_id"],
    "CONTROLNET_CANNY_MODEL": MODEL_COMPONENTS["controlnet"]["model_id"],
    "QWEN_MODEL_ID": MODEL_COMPONENTS["qwen"]["model_id"],
    "_SDXL_FP16_VAE_ID": MODEL_COMPONENTS["fp16_vae"]["model_id"],
}


class FeasibilityError(RuntimeError):
    """A secret-safe Task 42 preflight failure."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        return None


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("available_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended_virtual", ctypes.c_ulonglong),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.length = ctypes.sizeof(self)


def _memory_snapshot() -> tuple[int, int]:
    if os.name == "nt":
        status = _MemoryStatusEx()
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise FeasibilityError("Unable to read Windows memory status")
        return int(status.total_physical), int(status.available_physical)

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total = page_size * int(os.sysconf("SC_PHYS_PAGES"))
        available = page_size * int(os.sysconf("SC_AVPHYS_PAGES"))
    except (AttributeError, OSError, TypeError, ValueError) as error:
        raise FeasibilityError("Unable to read system memory status") from error
    return total, available


def _windows_gpu_adapters() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    command = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM,DriverVersion,VideoProcessor | "
        "ConvertTo-Json -Compress"
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    adapters = payload if isinstance(payload, list) else [payload]
    return [adapter for adapter in adapters if isinstance(adapter, dict)]


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _model_api_url(model_id: str, revision: str) -> str:
    encoded = "/".join(
        urllib.parse.quote(part, safe="") for part in model_id.split("/")
    )
    encoded_revision = urllib.parse.quote(revision, safe="")
    return (
        f"https://{HUGGINGFACE_HOST}/api/models/{encoded}/revision/"
        f"{encoded_revision}?blobs=true"
    )


def _fetch_model_metadata(model_id: str, revision: str) -> tuple[dict[str, Any], int]:
    url = _model_api_url(model_id, revision)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Clipart-Generator-Task42-Audit/1.0"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=30) as response:
            final_url = urllib.parse.urlparse(response.geturl())
            if (
                final_url.scheme != "https"
                or final_url.hostname != HUGGINGFACE_HOST
                or response.status != 200
            ):
                raise FeasibilityError("Model metadata endpoint was not accepted")
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError as error:
                    raise FeasibilityError(
                        "Model metadata response length is invalid"
                    ) from error
                if declared_size > MAX_MODEL_METADATA_BYTES:
                    raise FeasibilityError("Model metadata response is too large")
            raw = response.read(MAX_MODEL_METADATA_BYTES + 1)
    except FeasibilityError:
        raise
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        raise FeasibilityError("Unable to verify official model metadata") from error
    if len(raw) > MAX_MODEL_METADATA_BYTES:
        raise FeasibilityError("Model metadata response is too large")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FeasibilityError("Model metadata response is invalid") from error
    if not isinstance(payload, dict):
        raise FeasibilityError("Model metadata response is invalid")
    return payload, len(raw)


def verify_model_metadata() -> dict[str, Any]:
    verified: dict[str, Any] = {}
    for component_name, expected in MODEL_COMPONENTS.items():
        payload, response_bytes = _fetch_model_metadata(
            expected["model_id"], expected["revision"]
        )
        card_data = payload.get("cardData")
        siblings = payload.get("siblings")
        if (
            payload.get("id") != expected["model_id"]
            or payload.get("sha") != expected["revision"]
            or not isinstance(card_data, dict)
            or card_data.get("license") != expected["api_license"]
            or not isinstance(siblings, list)
        ):
            raise FeasibilityError("Official model metadata does not match Task 42")

        observed_files: dict[str, int] = {}
        for sibling in siblings:
            if not isinstance(sibling, dict):
                continue
            filename = sibling.get("rfilename")
            size = sibling.get("size")
            if isinstance(filename, str) and isinstance(size, int) and size >= 0:
                observed_files[filename] = size
        required_files = expected["required_files"]
        if any(
            observed_files.get(filename) != expected_size
            for filename, expected_size in required_files.items()
        ):
            raise FeasibilityError("Official model file sizes do not match Task 42")
        selected_bytes = sum(required_files.values())
        if selected_bytes != expected["serialized_weight_bytes"]:
            raise FeasibilityError("Task 42 model manifest is internally inconsistent")
        verified[component_name] = {
            "model_id": expected["model_id"],
            "revision": expected["revision"],
            "api_license": expected["api_license"],
            "required_file_count": len(required_files),
            "serialized_weight_bytes": selected_bytes,
            "metadata_response_bytes": response_bytes,
            "source": expected["source"],
        }
    return {
        "status": "verified",
        "host": HUGGINGFACE_HOST,
        "model_weight_downloads_performed": False,
        "components": verified,
    }


def collect_runtime_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "python": platform.python_version(),
        "executable": sys.executable,
        "torch": _package_version("torch"),
        "diffusers": _package_version("diffusers"),
        "transformers": _package_version("transformers"),
        "remove_ai_watermarks": _package_version("remove-ai-watermarks"),
        "torch_cuda_build": None,
        "cuda_available": False,
        "cuda_devices": 0,
        "xpu_available": False,
        "mps_available": False,
    }
    try:
        import torch
    except ImportError:
        return snapshot

    snapshot["torch_cuda_build"] = torch.version.cuda
    snapshot["cuda_available"] = bool(torch.cuda.is_available())
    snapshot["cuda_devices"] = int(torch.cuda.device_count())
    snapshot["xpu_available"] = bool(hasattr(torch, "xpu") and torch.xpu.is_available())
    snapshot["mps_available"] = bool(
        hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    )
    return snapshot


def collect_hardware_snapshot() -> dict[str, Any]:
    total_memory, available_memory = _memory_snapshot()
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "total_physical_bytes": total_memory,
        "available_physical_bytes": available_memory,
        "gpu_adapters": _windows_gpu_adapters(),
    }


def _literal_assignments(path: Path) -> dict[str, Any]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as error:
        raise FeasibilityError(
            f"Unable to audit upstream source: {path.name}"
        ) from error
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            values[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return values


def verify_upstream(upstream_dir: Path) -> dict[str, Any]:
    upstream_dir = upstream_dir.resolve()
    if not upstream_dir.is_dir():
        raise FeasibilityError("Pinned upstream directory does not exist")
    try:
        result = subprocess.run(
            ["git", "-C", str(upstream_dir), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise FeasibilityError("Unable to inspect pinned upstream revision") from error
    revision = result.stdout.strip()
    if result.returncode != 0 or revision != UPSTREAM_COMMIT:
        raise FeasibilityError("Pinned upstream revision does not match Task 42")
    try:
        status = subprocess.run(
            [
                "git",
                "-C",
                str(upstream_dir),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise FeasibilityError("Unable to inspect pinned upstream status") from error
    if status.returncode != 0 or status.stdout.strip():
        raise FeasibilityError("Pinned upstream checkout is not clean")

    source_root = upstream_dir / "src" / "remove_ai_watermarks" / "noai"
    constants = _literal_assignments(source_root / "watermark_profiles.py")
    constants.update(_literal_assignments(source_root / "watermark_remover.py"))
    actual = {name: constants.get(name) for name in EXPECTED_UPSTREAM_MODEL_CONSTANTS}
    if actual != EXPECTED_UPSTREAM_MODEL_CONSTANTS:
        raise FeasibilityError("Pinned upstream model constants do not match Task 42")
    return {
        "repository": UPSTREAM_REPOSITORY,
        "commit": revision,
        "working_tree_clean": True,
        "model_constants": actual,
        "model_revisions_pinned_by_loader": False,
    }


def assess_feasibility(
    hardware: dict[str, Any], runtime: dict[str, Any]
) -> dict[str, Any]:
    available_accelerators = {
        "cuda": bool(runtime.get("cuda_available")),
        "xpu": bool(runtime.get("xpu_available")),
        "mps": bool(runtime.get("mps_available")),
    }
    total_memory = int(hardware["total_physical_bytes"])
    available_memory = int(hardware["available_physical_bytes"])
    pipeline_results: dict[str, Any] = {}

    for pipeline_name, pipeline in PIPELINES.items():
        weight_bytes = sum(
            int(MODEL_COMPONENTS[component]["serialized_weight_bytes"])
            for component in pipeline["components"]
        )
        supported = [
            name
            for name in pipeline["required_accelerators"]
            if available_accelerators[name]
        ]
        reasons: list[str] = []
        if not supported:
            reasons.append("no_supported_accelerator")
        if weight_bytes > total_memory:
            reasons.append("serialized_weights_exceed_total_ram")
        elif weight_bytes > available_memory:
            reasons.append("serialized_weights_exceed_current_free_ram")

        status = (
            "eligible_for_isolated_gpu_benchmark"
            if supported
            else "not_run_local_production_no_go"
        )
        if weight_bytes > total_memory:
            cpu_diagnostic_status = "not_run_weights_exceed_total_ram"
        elif pipeline_name == "controlnet":
            cpu_diagnostic_status = "not_run_insufficient_safe_headroom"
        else:
            cpu_diagnostic_status = "not_run_resource_risk"
        pipeline_results[pipeline_name] = {
            "status": status,
            "cpu_diagnostic_status": cpu_diagnostic_status,
            "supported_accelerators": supported,
            "components": list(pipeline["components"]),
            "cpu_dtype": pipeline["cpu_dtype"],
            "serialized_weight_bytes": weight_bytes,
            "reasons": reasons,
            "model_download_bytes": 0,
            "runtime_seconds": None,
            "peak_ram_bytes": None,
            "peak_vram_bytes": None,
            "quality": "not_measured_preflight_stop",
            "dimensions": "not_measured_preflight_stop",
            "alpha": "not_measured_preflight_stop",
            "detector_result": "not_verified",
        }

    all_blocked = all(
        result["status"] == "not_run_local_production_no_go"
        for result in pipeline_results.values()
    )
    return {
        "decision": (
            "local_production_hardware_no_go"
            if all_blocked
            else "isolated_gpu_benchmark_required"
        ),
        "production_candidate": False,
        "model_downloads_performed": False,
        "paid_requests_performed": False,
        "pipelines": pipeline_results,
        "limitations": [
            "Upstream supports slow CPU execution, but Task 42 excludes it as a production candidate and did not measure it.",
            "The upstream code has no CUDA, XPU, or MPS path for this machine.",
            "AMD DirectML is not an accepted upstream device.",
            "The audited model revisions are not enforced by the upstream loader.",
            "No local official SynthID pixel detector is available; outputs would remain not_verified.",
        ],
    }


def build_report(
    upstream_dir: Path, *, verify_remote_models: bool = False
) -> dict[str, Any]:
    upstream = verify_upstream(upstream_dir)
    model_metadata_verification = (
        verify_model_metadata()
        if verify_remote_models
        else {
            "status": "not_requested",
            "model_weight_downloads_performed": False,
        }
    )
    runtime = collect_runtime_snapshot()
    hardware = collect_hardware_snapshot()
    return {
        "schema": 1,
        "task": 42,
        "snapshot_date": SNAPSHOT_DATE,
        "upstream": upstream,
        "model_metadata_verification": model_metadata_verification,
        "runtime": runtime,
        "hardware": hardware,
        "model_components": MODEL_COMPONENTS,
        "assessment": assess_feasibility(hardware, runtime),
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Task 42 no-download local diffusion feasibility preflight."
    )
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--verify-model-metadata",
        action="store_true",
        help="Verify pinned model SHAs, licenses, and selected file sizes via the official Hugging Face metadata API.",
    )
    args = parser.parse_args(argv)
    try:
        report = build_report(
            args.upstream_dir,
            verify_remote_models=args.verify_model_metadata,
        )
        if args.output:
            _write_json_atomic(args.output, report)
    except FeasibilityError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
