import sys
import os
import json
import ast
import csv
import time
import uuid
import tempfile
import hashlib
import mimetypes
import re
import ssl
import math
import subprocess
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from types import MappingProxyType
from io import BytesIO, StringIO
from urllib.parse import urlparse
from urllib import error as urlerror
from urllib import request, parse
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np


_GUI_NULL_STREAMS = []


def ensure_gui_standard_streams():
    """Provide writable streams when a windowed executable has no console."""
    created_streams = []
    for stream_name in ("stdout", "stderr"):
        if getattr(sys, stream_name, None) is not None:
            continue
        stream = open(os.devnull, "w", encoding="utf-8")
        setattr(sys, stream_name, stream)
        _GUI_NULL_STREAMS.append(stream)
        created_streams.append(stream)
    return tuple(created_streams)


# PyInstaller's Windows --windowed mode sets both streams to None. Some local
# ML dependencies (notably tqdm during rembg model download) still write to
# stderr and otherwise fail before inference starts.
ensure_gui_standard_streams()

from PIL import Image, ImageChops, ImageFilter, PngImagePlugin, UnidentifiedImageError
from background_mask import has_usable_alpha
from chroma_key import (
    KEY_COLORS,
    ChromaKeyAmbiguousError,
    remove_chroma_key_automatic,
)
from license_client import LicenseClient, LicenseError
from metadata_cleanup import MetadataCleanupError, MetadataCleanupOptions, cleanup_image_metadata
from ai_watermark_backend import (
    WatermarkBackendError,
    clean_invisible_watermark,
    gpu_backend_available,
    hidden_window_creation_flags,
)
from metadata_inspector import inspect_image_metadata
from visible_mark_cleanup import (
    VisibleMarkCleanupCancelled,
    VisibleMarkCleanupError,
    cleanup_visible_mark,
    normalize_confirmed_region,
    visible_mark_region_key,
)
from v3_api_settings import check_photoroom_balance as check_photoroom_balance_api
from output_naming import (
    BatchOutputNameReservation,
    generated_output_path,
    processed_output_path,
)
from api_credentials import EnvCredentialStore, ProviderCredentialStore, SECRET_CONFIG_KEYS
from runtime_settings import build_runtime_settings
from runtime_settings import normalize_kie_concurrency, normalize_provider_concurrency
from worker_runtime import launch_worker
from run_modes import label_for as run_mode_label, worker_mode_for
from run_validation import validate_inputs
from app_identity import APP_NAME, APP_UPDATE_USER_AGENT, APP_USER_AGENT
from v3_localization import app_locale_from_settings
from release_contract import resolve_release_version
from security_redaction import redact_absolute_paths, redact_text
from provider_diagnostics import (
    build_provider_event,
    count_provider_results,
    inspect_image_metadata as inspect_diagnostic_image,
)
from fal_provider import (
    FalClient,
    FalConfig,
    FalProviderError,
    FalTaskJournal,
    fal_image_data_uri,
    fal_image_url,
    fal_lifecycle_urls,
)
from fal_model_catalog import (
    fal_generation_payload,
    is_fal_generation_model,
)
from provider_contract import ProviderTaskRequest
from processing_contract import publish_atomic, run_workspace
from local_ben2 import load_local_ben2_onnx_model
from network_security import HttpsOnlyRedirectHandler as SharedHttpsOnlyRedirectHandler
from legacy_visible_mark_widget import VisibleMarkSettingsWidget
from model_catalog import (
    GENERATION_MODEL_META as CATALOG_GENERATION_MODEL_META,
    GENERATION_MODELS as CATALOG_GENERATION_MODELS,
    PROCESSING_PRICING as CATALOG_PROCESSING_PRICING,
    REFERENCE_MODEL_SHORTLIST as CATALOG_REFERENCE_MODEL_SHORTLIST,
    SUPPORTED_GENERATION_MODEL_IDS as CATALOG_SUPPORTED_GENERATION_MODEL_IDS,
    VISIBLE_GENERATION_MODEL_IDS as CATALOG_VISIBLE_GENERATION_MODEL_IDS,
    MODEL_SPECS,
    ratios_for_mode,
    resolve_generation_endpoint,
    validate_generation_contract,
)
from v3_provider_registry import (
    FAL_BRIA_UPSCALE_MODEL_ID,
    FAL_RECRAFT_CRISP_MODEL_ID,
    FAL_TOPAZ_TRANSPARENT_MODEL_ID,
    KIE_TOPAZ_MODEL_ID,
    TOPAZ_MAX_FILE_BYTES,
    TOPAZ_MAX_OUTPUT_SIDE,
    normalize_kie_upscale_model,
    normalize_fal_upscale_model,
    normalize_fal_upscale_factor,
    normalize_topaz_upscale_factor,
    upscale_model_preserves_alpha,
)

try:
    import certifi
except Exception:
    certifi = None

from PyQt6.QtCore import (
    Qt,
    QThread,
    pyqtSignal,
    QTimer,
    QEvent,
    QSize,
    QPoint,
    QRect,
    QStandardPaths,
)
from PyQt6.QtGui import QKeySequence, QIcon, QPixmap, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QSpinBox,
    QFileDialog,
    QMessageBox,
    QTextEdit,
    QProgressBar,
    QRadioButton,
    QButtonGroup,
    QGridLayout,
    QCheckBox,
    QComboBox,
    QTabWidget,
    QScrollArea,
    QLineEdit,
    QHeaderView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
)

def resolve_app_version(resource_root=None):
    """Read the version bundled by the release build and fail closed if absent."""
    root = resource_root or getattr(
        sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))
    )
    return resolve_release_version(os.path.join(root, "release"))


APP_VERSION = resolve_app_version()
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/lana-info/Clipart-Generator-Updates/main/version.json"
LICENSE_SERVICE_BASE_URL = "https://services.etsyneuroclub.com/licenses"
LICENSE_PRODUCT_ID = "clipart-generator"
LICENSE_PUBLIC_KEYS = {
    "license-v1": "2J5W6NVq8-zE5g0MocublzW5aER1hzRqwFLGuzKuwMw",
}
PHOTOROOM_SEGMENT_URL = "https://sdk.photoroom.com/v1/segment"
PHOTOROOM_LAUNCH_INTERVAL_SECONDS = 1.0
MAX_REMOTE_CONCURRENCY = 6
MODEL_PROBE_SAMPLE_IMAGE_URL = "https://picsum.photos/768/768"
MAX_API_RESPONSE_BYTES = 128 * 1024 * 1024
MAX_API_JSON_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_API_UPLOAD_BYTES = 128 * 1024 * 1024
MAX_PROVIDER_IMAGE_DIMENSION = 32_768
MAX_PROVIDER_IMAGE_PIXELS = 70_000_000
RECRAFT_CRISP_MAX_BYTES = 10 * 1024 * 1024
FAL_RECRAFT_CRISP_MAX_BYTES = 5 * 1024 * 1024
FAL_RECRAFT_CRISP_MAX_DIMENSION = 4096
FAL_RECRAFT_CRISP_MAX_PIXELS = 4_000_000
FAL_RECRAFT_CRISP_MIN_DIMENSION = 32
RECRAFT_REMOVE_BG_MAX_BYTES = 5 * 1024 * 1024
RECRAFT_REMOVE_BG_MAX_DIMENSION = 4096
RECRAFT_REMOVE_BG_MAX_PIXELS = 16 * 1024 * 1024
RECRAFT_REMOVE_BG_MIN_DIMENSION = 256
PHOTOROOM_MAX_BYTES = 50 * 1024 * 1024
PHOTOROOM_MAX_DIMENSION = 6000
MAX_UPDATE_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_UPDATE_INSTALLER_BYTES = 512 * 1024 * 1024
MAX_UPDATE_DOWNLOAD_RETRIES = 3
UPDATE_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
UPDATE_DOWNLOAD_TIMEOUT_SECONDS = 300
LOCAL_REALESRGAN_TIMEOUT_SECONDS = 600


class ProcessingCancelled(RuntimeError):
    pass


class ItemExecutionError(RuntimeError):
    def __init__(self, message, *, stage="", provider="", model=""):
        super().__init__(str(message or "Item processing failed")[:500])
        self.stage = str(stage or "")[:100]
        self.provider = str(provider or "")[:100]
        self.model = str(model or "")[:200]


class ResponseLimitError(RuntimeError):
    pass


class HttpsOnlyRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        source = urlparse(req.full_url)
        target = urlparse(newurl)
        if source.scheme.lower() == "https" and (
            target.scheme.lower() != "https" or not target.hostname
        ):
            return None
        if target.username or target.password:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Compatibility name: legacy transport now uses the shared security policy.
HttpsOnlyRedirectHandler = SharedHttpsOnlyRedirectHandler


REFERENCE_MODEL_SHORTLIST = {
    "gpt-image/1.5-image-to-image",
    "gpt-image-2",
    "nano-banana-2",
    "nano-banana-pro",
    "qwen-image-2",
    "flux-2/pro-image-to-image",
    "flux-2/flex-image-to-image",
}

# Показываем только выбранные модели; остальные остаются в коде, чтобы быстро вернуть их обратно.
VISIBLE_GENERATION_MODEL_IDS = {
    "gpt-image/1.5-text-to-image",
    "gpt-image-2",
    "nano-banana-2",
    "nano-banana-pro",
    "qwen-image-2",
    "flux-2/pro-text-to-image",
    "flux-2/flex-text-to-image",
    "gpt-image/1.5-image-to-image",
    "flux-2/pro-image-to-image",
    "flux-2/flex-image-to-image",
}

MODEL_CAPABILITIES = {
    "gpt-image/1.5-text-to-image": {
        "ratios": {"1:1", "2:3", "3:2"},
        "qualities": {"medium", "high"},
        "pricing": "4 / 22 credits ($0.02 / $0.11)",
        "reference_compatible_text": False,
    },
    "gpt-image/1.5-image-to-image": {
        "ratios": {"1:1", "2:3", "3:2"},
        "qualities": {"medium", "high"},
        "pricing": "4 / 22 credits ($0.02 / $0.11)",
        "reference_compatible_text": False,
    },
    "gpt-image-2": {
        "ratios": {"auto", "1:1", "9:16", "16:9", "4:3", "3:4"},
        "resolutions": {"1K", "2K", "4K"},
        "pricing": {"1K": "6 credits / $0.03", "2K": "10 credits / $0.05", "4K": "16 credits / $0.08"},
        "reference_compatible_text": True,
    },
    "nano-banana-2": {
        "ratios": {"auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"},
        "resolutions": {"1K", "2K", "4K"},
        "pricing": {"1K": "8 credits / $0.04", "2K": "12 credits / $0.06", "4K": "18 credits / $0.09"},
        "reference_compatible_text": True,
    },
    "nano-banana-pro": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"},
        "resolutions": {"1K", "2K", "4K"},
        "pricing": {"1K": "18 credits / $0.09", "2K": "18 credits / $0.09", "4K": "24 credits / $0.12"},
        "reference_compatible_text": True,
    },
    "qwen-image-2": {
        "ratios": {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"},
        "pricing": "6 credits / $0.03",
        "reference_compatible_text": True,
    },
    "flux-2/flex-text-to-image": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"},
        "resolutions": {"1K", "2K"},
        "pricing": {"1K": "14 credits / $0.07", "2K": "24 credits / $0.12"},
        "reference_compatible_text": False,
    },
    "flux-2/pro-text-to-image": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"},
        "resolutions": {"1K", "2K"},
        "pricing": {"1K": "5 credits / $0.025", "2K": "7 credits / $0.035"},
        "reference_compatible_text": False,
    },
    "flux-2/flex-image-to-image": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"},
        "resolutions": {"1K", "2K"},
        "pricing": {"1K": "14 credits / $0.07", "2K": "24 credits / $0.12"},
        "reference_compatible_text": False,
    },
    "flux-2/pro-image-to-image": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"},
        "resolutions": {"1K", "2K"},
        "pricing": {"1K": "5 credits / $0.025", "2K": "7 credits / $0.035"},
        "reference_compatible_text": False,
    },
}

RATIO_OPTIONS_ORDER = [
    "auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
    "1:2", "2:1", "1:3", "3:1", "9:16", "16:9", "9:21", "21:9",
    "1:4", "4:1", "1:8", "8:1",
]
RESOLUTION_OPTIONS_ORDER = ["1K", "2K", "4K", "8K"]

PROCESSING_PRICING = {
    "topaz/image-upscale": "40 credits / $0.20",
    "recraft/crisp-upscale": "0.5 credits / $0.0025",
    "recraft/remove-background": "1 credit / $0.005",
}

# Compatibility names: all consumers use the immutable catalog above.
REFERENCE_MODEL_SHORTLIST = CATALOG_REFERENCE_MODEL_SHORTLIST
VISIBLE_GENERATION_MODEL_IDS = CATALOG_VISIBLE_GENERATION_MODEL_IDS
SUPPORTED_GENERATION_MODEL_IDS = CATALOG_SUPPORTED_GENERATION_MODEL_IDS
GENERATION_MODELS = CATALOG_GENERATION_MODELS
GENERATION_MODEL_META = CATALOG_GENERATION_MODEL_META
PROCESSING_PRICING = CATALOG_PROCESSING_PRICING
MODEL_CAPABILITIES = MappingProxyType({
    model_id: {
        "ratios": frozenset(spec.ratios),
        "resolutions": frozenset(spec.resolutions),
        "qualities": frozenset(spec.qualities),
        "pricing": spec.pricing,
        "reference_compatible_text": spec.reference_compatible_text,
    }
    for model_id, spec in MODEL_SPECS.items()
})

REALESRGAN_EXE_NAME = "realesrgan-ncnn-vulkan.exe"
REALESRGAN_PROFILE_MODELS = {
    "photo": "realesrgan-x4plus",
    "clipart": "realesrgan-x4plus-anime",
}
REALESRGAN_PROFILE_SCALE_MODELS = {
    ("clipart", 2): "realesr-animevideov3-x2",
    ("clipart", 4): "realesrgan-x4plus-anime",
}


def application_base_dir():
    """Return the directory that contains the source tree or packaged app."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def bundled_brand_icon_path():
    """Return the packaged or source path for the Vibix Images application icon."""
    resource_root = getattr(sys, "_MEIPASS", application_base_dir())
    return os.path.join(resource_root, "assets", "vibix-images.ico")


def configure_application_identity(app):
    """Apply the visible Windows identity before creating application windows."""
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("Vibix")
    icon_path = bundled_brand_icon_path()
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))


def bundled_local_realesrgan_dir():
    resource_root = getattr(sys, "_MEIPASS", application_base_dir())
    runtime_dir = (
        "realesrgan-ncnn-vulkan-20220424-macos"
        if sys.platform == "darwin"
        else "realesrgan-ncnn-vulkan-20211212-windows"
    )
    return os.path.join(resource_root, runtime_dir)


def realesrgan_executable_name():
    return "realesrgan-ncnn-vulkan" if sys.platform == "darwin" else REALESRGAN_EXE_NAME


def resolve_local_realesrgan_exe_path(local_realesrgan_dir):
    raw_path = str(local_realesrgan_dir or "").strip().strip('"')
    if not raw_path:
        return ""

    resolved_path = os.path.abspath(os.path.expanduser(os.path.expandvars(raw_path)))
    executable_name = realesrgan_executable_name()
    if os.path.basename(resolved_path).lower() == executable_name.lower():
        return resolved_path
    return os.path.join(resolved_path, executable_name)


def validate_local_realesrgan_exe(local_realesrgan_dir):
    raw_path = str(local_realesrgan_dir or "").strip().strip('"')
    if not raw_path:
        return "", "Укажите папку Local Real-ESRGAN в настройках обработки"

    resolved_path = os.path.abspath(os.path.expanduser(os.path.expandvars(raw_path)))
    executable_name = realesrgan_executable_name()
    base_dir = os.path.dirname(resolved_path) if os.path.basename(resolved_path).lower() == executable_name.lower() else resolved_path
    exe_path = resolve_local_realesrgan_exe_path(resolved_path)

    if not os.path.isdir(base_dir):
        return "", f"Папка Real-ESRGAN не найдена: {base_dir}"
    if not os.path.isfile(exe_path):
        return "", f"Не найден {executable_name}: {exe_path}"
    models_dir = os.path.join(base_dir, "models")
    if not os.path.isdir(models_dir):
        return "", f"Папка models Real-ESRGAN не найдена: {models_dir}"
    return exe_path, ""


def get_local_realesrgan_model_name(profile, scale=None):
    profile_value = str(profile or "").strip().lower()
    try:
        scale_value = int(scale)
    except (TypeError, ValueError):
        scale_value = None
    scale_model = REALESRGAN_PROFILE_SCALE_MODELS.get((profile_value, scale_value))
    if scale_model:
        return scale_model
    return REALESRGAN_PROFILE_MODELS.get(profile_value, REALESRGAN_PROFILE_MODELS["clipart"])


def normalize_local_realesrgan_scale(scale):
    try:
        scale_value = int(scale)
    except (TypeError, ValueError):
        scale_value = 4
    if scale_value not in {2, 4}:
        scale_value = 4
    return scale_value


def import_rembg_tools():
    try:
        from rembg import new_session, remove
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        raise RuntimeError(f"Local rembg is not available: {exc}") from exc
    return new_session, remove


def load_local_ben2_model(progress=None, cancel_check=None):
    return load_local_ben2_onnx_model(
        os.path.join(USER_DATA_DIR, "models", "ben2"),
        progress=progress,
        cancel_check=cancel_check,
    )


def normalize_edge_shrink_pixels(pixels):
    try:
        pixel_value = int(pixels)
    except (TypeError, ValueError):
        pixel_value = 1
    return max(1, min(3, pixel_value))


def normalize_visible_mark_cleanup_mode(mode):
    mode_value = str(mode or "gemini_auto").strip().lower()
    if mode_value not in {"gemini_auto", "confirmed_area"}:
        mode_value = "gemini_auto"
    return mode_value


def normalize_local_rembg_edge_quality(quality):
    quality_value = str(quality or "normal").strip().lower()
    if quality_value not in {"soft", "normal", "sharp"}:
        quality_value = "normal"
    return quality_value


def normalize_unsharp_amount(amount):
    try:
        amount_value = int(amount)
    except (TypeError, ValueError):
        amount_value = 30
    return max(0, min(500, amount_value))


def normalize_unsharp_radius(radius):
    try:
        radius_value = float(radius)
    except (TypeError, ValueError):
        radius_value = 100.0
    return max(0.1, min(200.0, radius_value))


def normalize_unsharp_threshold(threshold):
    try:
        threshold_value = int(threshold)
    except (TypeError, ValueError):
        threshold_value = 0
    return max(0, min(255, threshold_value))


def normalize_ben2_alpha_threshold(threshold):
    try:
        threshold_value = int(threshold)
    except (TypeError, ValueError):
        threshold_value = 24
    return max(0, min(255, threshold_value))


def normalize_ben2_edge_softness(pixels):
    try:
        pixel_value = int(pixels)
    except (TypeError, ValueError):
        pixel_value = 0
    return max(0, min(3, pixel_value))


def normalize_ben2_corner_radius(pixels):
    try:
        pixel_value = int(pixels)
    except (TypeError, ValueError):
        pixel_value = 0
    return max(0, min(3, pixel_value))


def get_model_capabilities(model_id):
    spec = MODEL_SPECS[model_id]
    return {
        "ratios": set(spec.ratios),
        "resolutions": set(spec.resolutions),
        "qualities": set(spec.qualities),
        "pricing": spec.pricing,
        "reference_compatible_text": spec.reference_compatible_text,
    }


def resolve_kie_generation_model(model_id, has_references=False):
    return resolve_generation_endpoint(model_id, has_references)


SUPPORTED_GENERATION_MODEL_IDS = {
    "gpt4o-image",
    "gpt-image/1.5-text-to-image",
    "gpt-image-2",
    "nano-banana-2",
    "qwen-image-2",
    "z-image",
    "google/imagen4",
    "google/imagen4-fast",
    "google/imagen4-ultra",
    "google/nano-banana",
    "nano-banana-pro",
    "flux-2/flex-text-to-image",
    "flux-2/pro-text-to-image",
    "grok-imagine/text-to-image",
    "qwen/text-to-image",
    "flux-2/pro-image-to-image",
    "flux-2/flex-image-to-image",
    "grok-imagine/image-to-image",
    "gpt-image/1.5-image-to-image",
    "qwen/image-to-image",
    "google/nano-banana-edit",
    "qwen/image-edit",
}

GENERATION_MODELS = [
    # Text -> Image
    {"id": "gpt4o-image", "label": "GPT‑4o Image", "type": "text_to_image"},
    {"id": "gpt-image/1.5-text-to-image", "label": "GPT Image 1.5 (Text→Image)", "type": "text_to_image"},
    {"id": "gpt-image-2", "label": "GPT Image 2", "type": "text_to_image"},
    {"id": "nano-banana-2", "label": "Nano Banana 2", "type": "text_to_image"},
    {"id": "z-image", "label": "Z-Image", "type": "text_to_image"},
    {"id": "google/imagen4", "label": "Google Imagen 4", "type": "text_to_image"},
    {"id": "google/imagen4-fast", "label": "Google Imagen 4 Fast", "type": "text_to_image"},
    {"id": "google/imagen4-ultra", "label": "Google Imagen 4 Ultra", "type": "text_to_image"},
    {"id": "google/nano-banana", "label": "Google Nano Banana", "type": "text_to_image"},
    {"id": "qwen-image-2", "label": "Qwen Image 2.0", "type": "text_to_image"},
    {"id": "flux-2/flex-text-to-image", "label": "FLUX.2 Flex (Text→Image)", "type": "text_to_image"},
    {"id": "flux-2/pro-text-to-image", "label": "FLUX.2 Pro (Text→Image)", "type": "text_to_image"},
    {"id": "grok-imagine/text-to-image", "label": "Grok Imagine (Text→Image)", "type": "text_to_image"},
    {"id": "qwen/text-to-image", "label": "Qwen (Text→Image)", "type": "text_to_image"},

    # Image -> Image
    {"id": "nano-banana-pro", "label": "Google Nano Banana Pro", "type": "image_to_image"},
    {"id": "gpt-image-2", "label": "GPT Image 2", "type": "image_to_image"},
    {"id": "nano-banana-2", "label": "Nano Banana 2", "type": "image_to_image"},
    {"id": "flux-2/pro-image-to-image", "label": "FLUX.2 Pro (Image→Image)", "type": "image_to_image"},
    {"id": "flux-2/flex-image-to-image", "label": "FLUX.2 Flex (Image→Image)", "type": "image_to_image"},
    {"id": "qwen-image-2", "label": "Qwen Image 2.0", "type": "edit"},
    {"id": "grok-imagine/image-to-image", "label": "Grok Imagine (Image→Image)", "type": "image_to_image"},
    {"id": "gpt-image/1.5-image-to-image", "label": "GPT Image 1.5 (Image→Image)", "type": "image_to_image"},
    {"id": "qwen/image-to-image", "label": "Qwen (Image→Image)", "type": "image_to_image"},

    # Edit
    {"id": "google/nano-banana-edit", "label": "Google Nano Banana Edit", "type": "edit"},
    {"id": "qwen/image-edit", "label": "Qwen Image Edit", "type": "edit"},
]

# Для моделей, которые встречаются несколько раз (text/image/edit),
# в базовой карте фиксируем первое объявление (обычно text_to_image).
GENERATION_MODEL_META = {}
for _entry in GENERATION_MODELS:
    _model_id = _entry.get("id")
    if _model_id and _model_id not in GENERATION_MODEL_META:
        GENERATION_MODEL_META[_model_id] = _entry

# Re-apply compatibility exports after the legacy declarations above.  The
# catalog is the runtime source of truth; the names remain for older callers.
REFERENCE_MODEL_SHORTLIST = CATALOG_REFERENCE_MODEL_SHORTLIST
VISIBLE_GENERATION_MODEL_IDS = CATALOG_VISIBLE_GENERATION_MODEL_IDS
SUPPORTED_GENERATION_MODEL_IDS = CATALOG_SUPPORTED_GENERATION_MODEL_IDS
GENERATION_MODELS = CATALOG_GENERATION_MODELS
GENERATION_MODEL_META = CATALOG_GENERATION_MODEL_META
MAX_REFERENCES_PER_PROMPT = 5
PROMPT_RATIO_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*(?:[:xÑ…])\s*(\d{1,2})(?!\d)", re.IGNORECASE)


def split_references(raw_value):
    if isinstance(raw_value, list):
        values = [str(item).strip() for item in raw_value]
        return [item for item in values if item]
    text = str(raw_value or "").strip()
    if not text:
        return []
    chunks = [part.strip() for part in re.split(r"\s*\|\s*", text)]
    return [part for part in chunks if part]


def join_references(references):
    items = split_references(references)
    return " | ".join(items)


def get_user_data_dir():
    if sys.platform == "darwin":
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    user_data_dir = os.path.join(base_dir, APP_NAME)
    os.makedirs(user_data_dir, exist_ok=True)
    return user_data_dir


USER_DATA_DIR = get_user_data_dir()
CONFIG_FILE = os.path.join(USER_DATA_DIR, "config.json")
ENV_FILE = os.path.join(USER_DATA_DIR, ".env")
PROMPTS_STORAGE_FILE = os.path.join(USER_DATA_DIR, "prompts.json")
LICENSE_CACHE_FILE = os.path.join(USER_DATA_DIR, "license_cache.json")
LICENSE_STATE_FILE = os.path.join(USER_DATA_DIR, "license_state.json")



def build_ssl_context():
    """Создаёт SSL-контекст с системными сертификатами и fallback на certifi."""
    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


def open_url_secure(req, timeout, context=None):
    ssl_context = context or build_ssl_context()
    opener = request.build_opener(
        request.HTTPSHandler(context=ssl_context),
        HttpsOnlyRedirectHandler(),
    )
    return opener.open(req, timeout=timeout)


def protect_secret_headers_from_redirects(req):
    for header_name in ("Authorization", "X-api-key"):
        value = req.get_header(header_name)
        if value is None:
            continue
        req.remove_header(header_name)
        req.add_unredirected_header(header_name, value)


def read_response_limited(response, max_bytes):
    headers = getattr(response, "headers", None)
    content_length = headers.get("Content-Length") if headers is not None else None
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise ResponseLimitError("API response exceeds size limit")
        except (TypeError, ValueError):
            pass
    payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ResponseLimitError("API response exceeds size limit")
    return payload


def validate_https_url(url, label):
    parsed_url = urlparse(str(url or "").strip())
    if parsed_url.scheme.lower() != "https" or not parsed_url.hostname:
        raise RuntimeError(f"{label} must use HTTPS")
    if parsed_url.username or parsed_url.password:
        raise RuntimeError(f"{label} must not contain credentials")
    return parsed_url


def validate_local_image_input(image_path, *, decode_pixels=False):
    try:
        with Image.open(image_path) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Local input image must be single-frame")
            if max(image.size) > MAX_PROVIDER_IMAGE_DIMENSION:
                raise ValueError("Local input image exceeds dimension limit")
            if image.width * image.height > MAX_PROVIDER_IMAGE_PIXELS:
                raise ValueError("Local input image exceeds pixel limit")
            if decode_pixels:
                image.load()
    except ValueError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("Local input image is invalid") from exc


def validate_local_realesrgan_output_size(image_path, scale):
    with Image.open(image_path) as image:
        width = image.width * scale
        height = image.height * scale
    if max(width, height) > MAX_PROVIDER_IMAGE_DIMENSION:
        raise ValueError("Local Real-ESRGAN result exceeds dimension limit")
    if width * height > MAX_PROVIDER_IMAGE_PIXELS:
        raise ValueError("Local Real-ESRGAN result exceeds pixel limit")


def validate_recraft_crisp_upscale_input(image_path):
    """Validate the local file against Recraft Crisp Upscale limits."""
    try:
        file_size = os.path.getsize(image_path)
        if file_size > RECRAFT_CRISP_MAX_BYTES:
            raise RuntimeError("Recraft Crisp input file size exceeds 10 MB")
        with Image.open(image_path) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise RuntimeError("Recraft Crisp input must be PNG, JPG, or WEBP")
            if getattr(image, "n_frames", 1) != 1:
                raise RuntimeError("Recraft Crisp input must be single-frame")
            image.load()
    except RuntimeError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise RuntimeError("Recraft Crisp input image is invalid") from exc


def prepare_fal_recraft_crisp_input(image_path, output_path):
    """Create the opaque PNG required by Fal.ai Recraft Crisp before billing."""
    try:
        with Image.open(image_path) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise RuntimeError("Fal.ai Recraft Crisp принимает только один кадр")
            if min(image.size) < FAL_RECRAFT_CRISP_MIN_DIMENSION:
                raise RuntimeError(
                    "Fal.ai Recraft Crisp: минимальная сторона изображения — 32 px"
                )
            if max(image.size) > FAL_RECRAFT_CRISP_MAX_DIMENSION:
                raise RuntimeError(
                    "Fal.ai Recraft Crisp: максимальная сторона изображения — 4096 px"
                )
            if image.width * image.height > FAL_RECRAFT_CRISP_MAX_PIXELS:
                raise RuntimeError(
                    "Fal.ai Recraft Crisp: исходное изображение превышает 4 MP"
                )
            if has_usable_alpha(image):
                raise RuntimeError(
                    "Fal.ai Recraft Crisp не сохраняет прозрачность. "
                    "Для прозрачного PNG выберите Bria Creative."
                )
            image.convert("RGB").save(output_path, format="PNG")
        if os.path.getsize(output_path) > FAL_RECRAFT_CRISP_MAX_BYTES:
            try:
                os.unlink(output_path)
            except OSError:
                pass
            raise RuntimeError(
                "Fal.ai Recraft Crisp: PNG после подготовки превышает 5 MB"
            )
        return output_path
    except RuntimeError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise RuntimeError("Fal.ai Recraft Crisp: исходное изображение повреждено") from exc


def validate_recraft_remove_background_input(image_path):
    """Validate a local source before upload to Recraft Remove Background."""
    try:
        if os.path.getsize(image_path) > RECRAFT_REMOVE_BG_MAX_BYTES:
            raise RuntimeError("Recraft Remove Background input exceeds 5 MB")
        with Image.open(image_path) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise RuntimeError("Recraft Remove Background input must be PNG, JPG, or WEBP")
            if getattr(image, "n_frames", 1) != 1:
                raise RuntimeError("Recraft Remove Background input must be single-frame")
            if min(image.size) < RECRAFT_REMOVE_BG_MIN_DIMENSION:
                raise RuntimeError("Recraft Remove Background input dimension is below 256 pixels")
            if max(image.size) > RECRAFT_REMOVE_BG_MAX_DIMENSION:
                raise RuntimeError("Recraft Remove Background input dimension exceeds 4096 pixels")
            if image.width * image.height > RECRAFT_REMOVE_BG_MAX_PIXELS:
                raise RuntimeError("Recraft Remove Background input exceeds 16 MP")
            image.load()
    except RuntimeError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise RuntimeError("Recraft Remove Background input image is invalid") from exc


def validate_photoroom_input(image_path):
    """Validate a local source against PhotoRoom Remove Background limits."""
    try:
        if os.path.getsize(image_path) > PHOTOROOM_MAX_BYTES:
            raise RuntimeError("PhotoRoom input exceeds 50 MB")
        if Path(image_path).suffix.lower() in {".heic", ".heif"}:
            raise RuntimeError("PhotoRoom input must be PNG, JPG, or WEBP")
        with Image.open(image_path) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise RuntimeError("PhotoRoom input must be PNG, JPG, or WEBP")
            if getattr(image, "n_frames", 1) != 1:
                raise RuntimeError("PhotoRoom input must be single-frame")
            if max(image.size) > PHOTOROOM_MAX_DIMENSION:
                raise RuntimeError("PhotoRoom input dimension exceeds 6000 pixels")
            image.load()
    except RuntimeError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise RuntimeError("PhotoRoom input image is invalid") from exc


def validate_upscale_after_background_order(remove_bg, upscale_after, provider, model):
    provider_id = str(provider or "").strip()
    model_id = str(model or "").strip()
    if remove_bg and upscale_after and not upscale_model_preserves_alpha(provider_id, model_id):
        return (
            "Выбранный апскейлер нельзя использовать после удаления фона: "
            "модель не поддерживает прозрачный вход. Выберите апскейлер с "
            "поддержкой прозрачности или перенесите его до удаления фона."
        )
    return ""


def safe_error_text(error, secrets=(), limit=500):
    message = str(error).strip() or error.__class__.__name__
    return redact_text(message, tuple(secrets), limit=limit)


_QUOTED_ABSOLUTE_PATH = re.compile(
    r"(?P<quote>['\"])(?P<path>(?:[A-Za-z]:[\\/]|\\{2,}|/)[^'\"\r\n]+)(?P=quote)"
)
_WINDOWS_ABSOLUTE_FILE_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(?:[A-Z]:[\\/]|\\{2,}[^\\/\r\n,;:'\"<>|?*]+[\\/]"
    r"[^\\/\r\n,;:'\"<>|?*]+[\\/])"
    r"(?:[^\\/\r\n,;:'\"<>|?*]+[\\/])*"
    r"[^\\/\r\n,;:'\"<>|?*]+?\.[A-Z0-9]{1,10}"
    r"(?=$|[\s,;:'\"<>\]\)}])"
)
_POSIX_ABSOLUTE_FILE_PATH = re.compile(
    r"(?i)(?<![:/A-Za-z0-9_])/"
    r"(?:[^/\r\n,;:'\"<>]+/)+"
    r"[^/\r\n,;:'\"<>]+?\.[A-Z0-9]{1,10}"
    r"(?=$|[\s,;:'\"<>\]\)}])"
)
_WINDOWS_ABSOLUTE_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/](?:[^\\/\s,;:'\"<>|?*]+[\\/])*[^\\/\s,;:'\"<>|?*]+"
)
_POSIX_ABSOLUTE_PATH = re.compile(
    r"(?<![:/A-Za-z0-9_])/(?:[^/\s,;:'\"<>]+/)+[^/\s,;:'\"<>]+"
)


def _is_absolute_path_text(value):
    text = str(value or "")
    return bool(text) and (
        PurePosixPath(text).is_absolute()
        or PureWindowsPath(text).is_absolute()
    )


def _item_error_known_paths(error, operation_args, max_paths=64):
    paths = []
    seen_paths = set()

    def add_path(value):
        try:
            raw_path = os.fspath(value)
        except TypeError:
            return
        if isinstance(raw_path, bytes):
            raw_path = os.fsdecode(raw_path)
        raw_path = str(raw_path or "")
        if (
            raw_path
            and raw_path not in seen_paths
            and _is_absolute_path_text(raw_path)
        ):
            seen_paths.add(raw_path)
            paths.append(raw_path)

    current_error = error
    seen_errors = set()
    while current_error is not None and len(seen_errors) < 8:
        error_id = id(current_error)
        if error_id in seen_errors:
            break
        seen_errors.add(error_id)
        add_path(getattr(current_error, "filename", None))
        add_path(getattr(current_error, "filename2", None))
        current_error = (
            getattr(current_error, "__cause__", None)
            or getattr(current_error, "__context__", None)
        )

    pending = list(operation_args)
    seen_containers = set()
    while pending and len(paths) < max_paths:
        item = pending.pop()
        if isinstance(item, (str, bytes, os.PathLike)):
            add_path(item)
            continue
        if isinstance(item, dict):
            item_id = id(item)
            if item_id in seen_containers:
                continue
            seen_containers.add(item_id)
            pending.extend(item.values())
            continue
        if isinstance(item, (list, tuple, set, frozenset)):
            item_id = id(item)
            if item_id in seen_containers:
                continue
            seen_containers.add(item_id)
            pending.extend(item)
    return tuple(paths[:max_paths])


def sanitize_item_error_paths(value, known_paths=(), limit=500):
    return redact_absolute_paths(value, tuple(known_paths), limit=limit)


def is_schema_required_error_message(message):
    text = str(message or "").lower()
    return (
        text == "schema_required"
        or "is required" in text
        or "field is required" in text
        or "required field" in text
        or "missing required" in text
    )


class WorkerThread(QThread):
    progress = pyqtSignal(str)
    item_progress = pyqtSignal(object)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    diagnostic = pyqtSignal(object)

    def __init__(self, mode, work_dir, settings, selected_files=None, generated_prompts=None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.work_dir = work_dir
        self.settings = settings
        self.selected_files = selected_files or []
        self.generated_prompts = generated_prompts or []
        self.is_running = True
        self.stop_after_current_requested = False
        self._paid_submission_open = True
        self._publish_lock = threading.Lock()
        self._local_operation_lock = threading.Lock()
        self._shared_state_lock = threading.Lock()
        self._claimed_fal_task_ids: set[str] = set()
        self._claimed_kie_task_ids: set[str] = set()
        self._fal_poll_attempts: dict[str, int] = {}
        self._kie_uploaded_content_ids: dict[str, str] = {}
        self._precleaned_paths: set[str] = set()
        self._item_context = threading.local()
        self.run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.run_id = uuid.uuid4().hex
        self._run_raw_dir = None
        self._diagnostic_context = threading.local()
        self._provider_lease_context = threading.local()
        self.fal_task_journal = FalTaskJournal(
            os.path.join(self.work_dir, ".vibix_fal_tasks.json")
        )
        self.kie_task_journal = FalTaskJournal(
            os.path.join(self.work_dir, ".vibix_kie_tasks.json")
        )

        sensitive_markers = ("api_key", "license_key", "password", "secret", "token")
        self._secret_values = tuple(
            {
                value.strip()
                for key, value in settings.items()
                if isinstance(value, str)
                and value.strip()
                and any(marker in str(key).lower() for marker in sensitive_markers)
            }
        )

        self.kie_api_key = settings.get("kie_api_key", "").strip()
        self.photoroom_api_key = settings.get("photoroom_api_key", "").strip()
        self.fal_api_key = settings.get("fal_api_key", "").strip()
        self.kie_upload_path = settings.get("kie_upload_path", "clipart-generator")
        self.text_generation_model = settings.get(
            "text_generation_model",
            settings.get("generation_model", "gpt-image/1.5-text-to-image"),
        )
        self.reference_generation_model = settings.get(
            "reference_generation_model",
            "gpt-image/1.5-image-to-image",
        )
        legacy_ratio = settings.get("generation_size", "1:1")
        self.text_generation_ratio = settings.get("text_generation_ratio", legacy_ratio)
        self.reference_generation_ratio = settings.get("reference_generation_ratio", legacy_ratio)
        self.text_generation_resolution = settings.get("text_generation_resolution", "1K")
        self.reference_generation_resolution = settings.get("reference_generation_resolution", "1K")
        self.timeout = max(10, int(settings.get("timeout", 60)))
        self.retries = max(0, int(settings.get("retries", 3)))
        self.kie_concurrency = normalize_kie_concurrency(
            settings.get("kie_concurrency"),
            legacy_value=settings.get("generation_concurrency"),
        )
        self.photoroom_concurrency = normalize_provider_concurrency(
            settings.get("photoroom_concurrency")
        )
        self.fal_concurrency = normalize_provider_concurrency(
            settings.get("fal_concurrency"),
        )
        # Compatibility name for the generation-only executor. The same value
        # now governs every KIE operation in the run.
        self.generation_concurrency = self.kie_concurrency
        self._kie_slots = threading.BoundedSemaphore(self.kie_concurrency)
        self._photoroom_slots = threading.BoundedSemaphore(
            self.photoroom_concurrency
        )
        self._fal_slots = threading.BoundedSemaphore(self.fal_concurrency)
        try:
            configured_interval = float(settings.get("generation_launch_interval", 1.0))
        except (TypeError, ValueError):
            configured_interval = 1.0
        self.generation_launch_interval = max(0.0, configured_interval)
        self._generation_launch_lock = threading.Lock()
        self._next_generation_launch_at = 0.0
        self._photoroom_launch_interval = PHOTOROOM_LAUNCH_INTERVAL_SECONDS
        self._photoroom_launch_lock = threading.Lock()
        self._photoroom_initial_launches = 0
        self._next_photoroom_launch_at = 0.0
        self.generation_wait_timeout = max(120, int(settings.get("generation_wait_timeout", 300)))
        self.status_poll_interval = max(5.0, min(60.0, float(settings.get("status_poll_interval", 20))))
        self.output_dir = settings.get("output_dir") or os.path.join(self.work_dir, "output")
        self.workspace_root = settings.get("workspace_root") or str(Path(self.output_dir).parent)
        self.overwrite_existing = bool(settings.get("overwrite_existing", False))

        # Legacy `upscale` remains the before-background pass for old configs.
        self.visible_mark_cleanup_enabled = bool(settings.get("visible_mark_cleanup_enabled", False))
        self.invisible_watermark_cleanup_enabled = bool(
            settings.get("invisible_watermark_cleanup_enabled", False)
        ) and gpu_backend_available()
        self.visible_mark_cleanup_mode = normalize_visible_mark_cleanup_mode(
            settings.get("visible_mark_cleanup_mode", "gemini_auto")
        )
        self.visible_mark_confirmed_regions = {}
        raw_visible_mark_regions = settings.get("visible_mark_confirmed_regions", {})
        if isinstance(raw_visible_mark_regions, dict):
            for path_key, region in raw_visible_mark_regions.items():
                if isinstance(region, (tuple, list)) and len(region) == 4:
                    try:
                        self.visible_mark_confirmed_regions[visible_mark_region_key(path_key)] = tuple(
                            int(value) for value in region
                        )
                    except (TypeError, ValueError):
                        continue
        self.upscale = bool(settings.get("upscale", True))
        self.upscale_after = bool(settings.get("upscale_after", False))
        self.remove_bg = settings.get("remove_bg", True)
        self.trim_enabled = bool(settings.get("trim_enabled", False))
        self.trim_mode = str(settings.get("trim_mode", "alpha") or "alpha")
        self.export_300_dpi = bool(settings.get("export_300_dpi", False))
        self.kie_upscale_model = normalize_kie_upscale_model(
            settings.get("kie_upscale_model", KIE_TOPAZ_MODEL_ID)
        )
        self.kie_upscale_after_model = normalize_kie_upscale_model(
            settings.get("kie_upscale_after_model", self.kie_upscale_model)
        )
        self.fal_upscale_model = normalize_fal_upscale_model(
            settings.get("fal_upscale_model", FAL_BRIA_UPSCALE_MODEL_ID)
        )
        self.fal_upscale_after_model = normalize_fal_upscale_model(
            settings.get(
                "fal_upscale_after_model",
                FAL_TOPAZ_TRANSPARENT_MODEL_ID,
            )
        )
        self._has_fal_upscale_scale = "fal_upscale_scale" in settings
        self._has_fal_upscale_after_scale = "fal_upscale_after_scale" in settings
        self.fal_upscale_scale = normalize_fal_upscale_factor(
            self.fal_upscale_model,
            settings.get("fal_upscale_scale", 4),
        )
        self.fal_upscale_after_scale = normalize_fal_upscale_factor(
            self.fal_upscale_after_model,
            settings.get("fal_upscale_after_scale", 4),
        )
        self.kie_remove_bg_model = settings.get("kie_remove_bg_model", "recraft/remove-background")
        self.fal_remove_bg_model = settings.get("fal_remove_bg_model", "fal-ai/bria/background/remove")
        if self.fal_remove_bg_model == "fal-ai/birefnet":
            self.fal_remove_bg_model = "fal-ai/birefnet/v2"
        self.fal_birefnet_model = settings.get("fal_birefnet_model", "General Use (Light)")
        self.fal_birefnet_resolution = settings.get("fal_birefnet_resolution", "1024x1024")
        self.fal_birefnet_refine_foreground = bool(settings.get("fal_birefnet_refine_foreground", True))
        self.fal_rembg_crop_to_bbox = bool(settings.get("fal_rembg_crop_to_bbox", False))
        self.chroma_key_color = str(
            settings.get("chroma_key_color", "blue") or "blue"
        ).strip().lower()
        if self.chroma_key_color not in KEY_COLORS:
            self.chroma_key_color = "blue"
        self.upscale_factor = normalize_topaz_upscale_factor(
            settings.get("upscale_factor", 4)
        )
        self.upscale_provider = settings.get("upscale_provider", "kie")
        self.upscale_after_provider = settings.get("upscale_after_provider", "fal")
        self.unsharp_enabled = bool(settings.get("unsharp_enabled", False))
        self.unsharp_amount = normalize_unsharp_amount(settings.get("unsharp_amount", 30))
        self.unsharp_radius = normalize_unsharp_radius(settings.get("unsharp_radius", 100))
        self.unsharp_threshold = normalize_unsharp_threshold(settings.get("unsharp_threshold", 0))
        self.local_realesrgan_dir = settings.get("local_realesrgan_dir", "")
        self.local_realesrgan_profile = settings.get("local_realesrgan_profile", "clipart")
        self.local_realesrgan_scale = normalize_local_realesrgan_scale(settings.get("local_realesrgan_scale", 4))
        self.local_realesrgan_after_scale = normalize_local_realesrgan_scale(
            settings.get("local_realesrgan_after_scale", self.local_realesrgan_scale)
        )
        self.remove_bg_provider = settings.get("remove_bg_provider", "kie")
        self.skip_remover_for_alpha = bool(settings.get("skip_remover_for_alpha", True))
        self.local_rembg_profile = settings.get("local_rembg_profile", "clipart")
        self.local_rembg_model = settings.get("local_rembg_model", "birefnet-general")
        self.local_rembg_edge_quality = normalize_local_rembg_edge_quality(
            settings.get("local_rembg_edge_quality", "normal")
        )
        self.local_rembg_session = None
        self.local_rembg_remove = None
        self.local_ben2_refine_foreground = bool(settings.get("local_ben2_refine_foreground", False))
        self.local_ben2_alpha_threshold = normalize_ben2_alpha_threshold(
            settings.get("local_ben2_alpha_threshold", 24)
        )
        self.local_ben2_edge_softness = normalize_ben2_edge_softness(
            settings.get("local_ben2_edge_softness", 0)
        )
        self.local_ben2_corner_radius = normalize_ben2_corner_radius(
            settings.get("local_ben2_corner_radius", 0)
        )
        self.local_ben2_model = None
        self.edge_shrink_enabled = bool(settings.get("edge_shrink_enabled", False))
        self.edge_shrink_pixels = normalize_edge_shrink_pixels(settings.get("edge_shrink_pixels", 1))
        self.metadata_cleanup_options = MetadataCleanupOptions(
            remove_exif=bool(settings.get("cleanup_remove_exif", False)),
            remove_xmp=bool(settings.get("cleanup_remove_xmp", False)),
            remove_iptc=bool(settings.get("cleanup_remove_iptc", False)),
            remove_comments_text=bool(settings.get("cleanup_remove_comments_text", False)),
            remove_embedded_thumbnail=bool(settings.get("cleanup_remove_embedded_thumbnail", False)),
            remove_generator_fields=bool(settings.get("cleanup_remove_generator_fields", False)),
            preserve_icc=bool(settings.get("cleanup_preserve_icc", True)),
            preserve_dpi=bool(settings.get("cleanup_preserve_dpi", True)) or self.export_300_dpi,
            remove_embedded_c2pa=bool(settings.get("cleanup_remove_embedded_c2pa", False)),
        )

    def run(self):
        try:
            if self.mode == "mode1_full":
                self._mode1_generate(process_generated=True)
            elif self.mode == "mode1_generate_only":
                self._mode1_generate(process_generated=False)
            elif self.mode == "mode_both":
                self._mode1_generate(process_generated=True)
            else:
                self._mode2_process_files()
        except ProcessingCancelled as error:
            self.progress.emit(self._safe_error_text(error))
        except Exception as error:
            self.error.emit(self._safe_error_text(error))

    def stop(self):
        with self._publish_lock:
            self.is_running = False
            self._paid_submission_open = False

    def request_stop_after_current(self):
        with self._publish_lock:
            self.stop_after_current_requested = True
            self._paid_submission_open = False

    def _stop_after_current_if_requested(self):
        with self._publish_lock:
            if not self.stop_after_current_requested:
                return False
            self.is_running = False
        self.progress.emit("Остановлено после текущего файла")
        return True

    def _ensure_running(self):
        if not self.is_running:
            raise ProcessingCancelled("Остановлено пользователем")

    def _ensure_provider_submission_allowed(self):
        with self._publish_lock:
            if not self.is_running or not self._paid_submission_open:
                raise ProcessingCancelled("Остановлено пользователем")
            if self.stop_after_current_requested:
                raise ProcessingCancelled("Остановлено после текущего файла")

    def _admit_paid_submission(self, provider: str, method: str) -> None:
        """Atomically admit one paid POST attempt immediately before send."""
        if not provider or str(method or "").upper() != "POST":
            return
        with self._publish_lock:
            if not self.is_running or not self._paid_submission_open:
                message = (
                    "Остановлено после текущего файла"
                    if self.stop_after_current_requested
                    else "Остановлено пользователем"
                )
                raise ProcessingCancelled(message)

    @contextmanager
    def _provider_lease(self, provider):
        provider_name = str(provider or "")
        depths = getattr(self._provider_lease_context, "depths", None)
        if depths is None:
            depths = {}
            self._provider_lease_context.depths = depths
        current_depth = int(depths.get(provider_name, 0))
        if current_depth:
            depths[provider_name] = current_depth + 1
            try:
                yield
            finally:
                depths[provider_name] -= 1
            return

        slots = {
            "kie": self._kie_slots,
            "photoroom": self._photoroom_slots,
            "fal": self._fal_slots,
        }[provider_name]
        acquired = False
        try:
            while not acquired:
                self._ensure_provider_submission_allowed()
                acquired = slots.acquire(timeout=0.05)
            self._ensure_provider_submission_allowed()
            depths[provider_name] = 1
            yield
        finally:
            depths.pop(provider_name, None)
            if acquired:
                slots.release()

    def _safe_error_text(self, error, limit=500):
        prompt_text = str(
            getattr(self._diagnostic_context, "prompt_text", "") or ""
        ).strip()
        redactions = self._secret_values + ((prompt_text,) if prompt_text else ())
        return safe_error_text(error, redactions, limit=limit)

    def _set_diagnostic_context(
        self,
        item_index: int,
        item_total: int,
        stage: str = "",
    ) -> None:
        for name in ("model", "provider", "prompt_text", "last_http_status"):
            setattr(self._diagnostic_context, name, None)
        self._diagnostic_context.item_index = max(1, int(item_index))
        self._diagnostic_context.item_total = max(1, int(item_total))
        self._diagnostic_context.stage = str(stage or "")
        self._item_context.paid_results_ready = []

    def _set_provider_diagnostic_context(self, stage, provider, model):
        self._diagnostic_context.stage = str(stage or "")
        self._diagnostic_context.provider = str(provider or "")
        self._diagnostic_context.model = str(model or "")

    def _diagnostic_context_values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for name in ("item_index", "item_total", "stage", "provider", "model"):
            value = getattr(self._diagnostic_context, name, None)
            if value not in (None, ""):
                values[name] = value
        return values

    def _emit_diagnostic(self, event: str, **values: object) -> None:
        try:
            context = self._diagnostic_context_values()
            context.update(values)
            self.diagnostic.emit(build_provider_event(event, **context))
        except Exception:
            return

    def _emit_item_progress(
        self,
        item_index: int,
        total_items: int,
        stage: str,
        status: str = "running",
        **values: object,
    ) -> None:
        event = {
            "item_index": max(1, int(item_index)),
            "total_items": max(1, int(total_items)),
            "stage": str(stage or ""),
            "status": str(status or "running"),
        }
        for key in (
            "message",
            "provider",
            "model",
            "percent",
            "indeterminate",
            "source_path",
            "output_path",
            "recovery_attempts",
        ):
            if key in values and values[key] not in (None, ""):
                event[key] = values[key]
        self.item_progress.emit(event)

    def _emit_cancelled_run_terminal(self) -> None:
        self._emit_diagnostic(
            "run_finished",
            outcome="cancelled",
            status="cancelled",
        )

    def _execute_item_entry(self, operation, *args):
        try:
            return operation(*args)
        except ProcessingCancelled:
            raise
        except ItemExecutionError:
            raise
        except Exception as error:
            known_paths = _item_error_known_paths(error, args)
            raise ItemExecutionError(
                sanitize_item_error_paths(
                    self._safe_error_text(error, limit=2000),
                    known_paths=known_paths,
                    limit=500,
                ),
                stage=getattr(self._diagnostic_context, "stage", ""),
                provider=getattr(self._diagnostic_context, "provider", ""),
                model=getattr(self._diagnostic_context, "model", ""),
            ) from error

    def _item_failure_details(self, error, fallback_stage):
        if isinstance(error, ItemExecutionError):
            return (
                str(error),
                error.stage or fallback_stage,
                error.provider,
                error.model,
            )
        return self._safe_error_text(error), fallback_stage, "", ""

    def _protect_secret_headers_from_redirects(self, req):
        protect_secret_headers_from_redirects(req)

    def _request_provider(self, req):
        parsed = urlparse(str(getattr(req, "full_url", "") or ""))
        hostname = str(parsed.hostname or "").lower()
        if str(getattr(req, "full_url", "")) == PHOTOROOM_SEGMENT_URL:
            return "photoroom"
        if (
            hostname == "kie.ai"
            or hostname.endswith(".kie.ai")
            or hostname == "redpandaai.co"
            or hostname.endswith(".redpandaai.co")
        ):
            return "kie"
        return ""

    @contextmanager
    def _network_attempt_lease(self, provider):
        if provider:
            with self._provider_lease(provider):
                yield
            return
        yield

    def _mode1_generate(self, process_generated, emit_final=True):
        self.progress.emit("Mode 1: Генерация из промптов")
        self.progress.emit(f"Рабочая папка: {self.work_dir}")
        if self._uses_fal_generation():
            if not self.fal_api_key:
                raise ValueError("Не указан Fal.ai API Key")
        if self._uses_kie_generation() and not self.kie_api_key:
            raise ValueError("Не указан KIE API Key")
        if process_generated and self._uses_photoroom_remove_bg() and not self.photoroom_api_key:
            raise ValueError("Не указан PhotoRoom API Key")
        if process_generated:
            self._log_upscale_plan()
        self._mode1_generate_parallel(
            process_generated=process_generated,
            emit_final=emit_final,
        )
        return

        raw_dir = self._create_run_raw_dir()
        output_dir = self.output_dir
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        entries = self._normalize_prompt_entries(self.generated_prompts)
        if not entries:
            if emit_final:
                self.completed.emit("Mode 1: Нет записей. Добавьте промпты")
            return

        total = len(entries)
        done = 0
        self.progress.emit(f"Записей к обработке: {total}")

        for idx, entry in enumerate(entries, start=1):
            if not self.is_running:
                self.progress.emit("Остановлено пользователем")
                return

            self.progress.emit(f"[{idx}/{total}] Генерация")
            self._set_diagnostic_context(idx, total, "generation")
            self._emit_file_progress(idx, total, 4)
            try:
                prompt_text = entry.get("prompt", "")
                self._diagnostic_context.prompt_text = prompt_text
                references = entry.get("references", [])
                self._emit_diagnostic(
                    "item_input_inspected",
                    prompt_index=idx,
                    prompt_chars=len(prompt_text),
                    reference_count=len(split_references(references)),
                    operation_type="generation",
                )
                self._emit_file_progress(idx, total, 18)
                image_url = self._kie_generate_image(prompt_text, references)
                self._emit_file_progress(idx, total, 36)
                self._ensure_running()
                gen_path = os.path.join(raw_dir, f"gen_{idx:03d}_{self.run_stamp}.png")
                self._download_file(image_url, gen_path)
                self._ensure_running()
                self.progress.emit(f"  Сгенерировано: {gen_path}")
                self._emit_file_progress(idx, total, 50)

                source_path = gen_path

                final_url = image_url
                if process_generated:
                    self._emit_file_progress(idx, total, 58)
                    if (
                        self.visible_mark_cleanup_enabled
                        or self.invisible_watermark_cleanup_enabled
                        or self.upscale
                        or self.upscale_after
                        or self.unsharp_enabled
                        or self.remove_bg
                    ):
                        final_url = self._run_processing_pipeline(source_path, image_url, raw_dir, idx, "gen")
                    elif self.edge_shrink_enabled:
                        final_url = self._edge_shrink_alpha_source_if_available(source_path, raw_dir, idx, "gen")
                    else:
                        final_url = None
                    self._emit_file_progress(idx, total, 84)
                else:
                    self._emit_file_progress(idx, total, 70)

                self._emit_file_progress(idx, total, 92)
                self._ensure_running()
                out_path = os.path.join(output_dir, f"result_{idx:03d}_{self.run_stamp}.png")
                self._save_final_output(
                    final_url,
                    source_path,
                    out_path,
                    raw_dir,
                    idx,
                    "gen",
                )
                self._emit_file_progress(idx, total, 100)
                self.progress.emit(f"  Итог сохранён: {out_path}")
                self._emit_diagnostic(
                    "item_finished",
                    outcome="succeeded",
                    **inspect_diagnostic_image(out_path),
                )
                done += 1
            except (ProcessingCancelled, VisibleMarkCleanupCancelled):
                self.progress.emit("Остановлено пользователем")
                return
            except Exception as e:
                self._emit_diagnostic(
                    "item_finished",
                    outcome="failed",
                    error_message=self._safe_error_text(e),
                )
                self.progress.emit(f"  Ошибка: {self._safe_error_text(e)}")

            if self._stop_after_current_if_requested():
                return

        self.progress_value.emit(100)
        if emit_final:
            if done == 0:
                self.completed.emit(f"Mode 1: Готово (0/{total}). Изображения не созданы.")
            else:
                self.completed.emit(f"Mode 1: Готово ({done}/{total})")

    def _wait_for_generation_launch_slot(self) -> None:
        while True:
            self._ensure_provider_submission_allowed()
            with self._generation_launch_lock:
                now = time.monotonic()
                if now >= self._next_generation_launch_at:
                    self._next_generation_launch_at = (
                        now + self.generation_launch_interval
                    )
                    return
                delay = self._next_generation_launch_at - now
            time.sleep(min(delay, 0.1))

    def _wait_for_photoroom_launch(self) -> None:
        while True:
            self._ensure_provider_submission_allowed()
            with self._photoroom_launch_lock:
                now = time.monotonic()
                in_initial_burst = (
                    self._photoroom_initial_launches < self.photoroom_concurrency
                )
                if in_initial_burst or now >= self._next_photoroom_launch_at:
                    if in_initial_burst:
                        self._photoroom_initial_launches += 1
                    self._next_photoroom_launch_at = (
                        now + self._photoroom_launch_interval
                    )
                    return
                delay = self._next_photoroom_launch_at - now
            time.sleep(min(delay, 0.1))

    def _wait_for_photoroom_launch_slot(self) -> None:
        """Compatibility helper that returns with one paced slot reserved."""
        acquired = False
        try:
            while not acquired:
                self._ensure_provider_submission_allowed()
                acquired = self._photoroom_slots.acquire(timeout=0.05)
            self._ensure_provider_submission_allowed()
            self._wait_for_photoroom_launch()
        except Exception:
            if acquired:
                self._photoroom_slots.release()
            raise

    def _generate_entry(
        self,
        idx: int,
        total: int,
        entry: dict[str, Any],
        raw_dir: str,
        out_path: str,
        process_generated: bool,
    ) -> str:
        self._item_context.manual_transparency_required = False
        self._set_diagnostic_context(idx, total, "generation")
        self.progress.emit(f"[{idx}/{total}] Генерация")
        self._emit_file_progress(idx, total, 4)
        prompt_text = entry.get("prompt", "")
        self._diagnostic_context.prompt_text = prompt_text
        references = entry.get("references", [])
        self._emit_diagnostic(
            "item_input_inspected",
            prompt_index=idx,
            prompt_chars=len(prompt_text),
            reference_count=len(split_references(references)),
            operation_type="generation",
        )
        self._emit_file_progress(idx, total, 18)
        image_url = self._kie_generate_image(prompt_text, references)
        self._emit_file_progress(idx, total, 36)
        self._ensure_running()
        gen_path = os.path.join(raw_dir, f"gen_{idx:03d}_{self.run_stamp}.png")
        self._download_file(image_url, gen_path)
        self._ensure_running()
        self.progress.emit(f"  Сгенерировано: {gen_path}")
        self._emit_item_progress(
            idx,
            total,
            "generation",
            "generated",
            percent=50,
            source_path=gen_path,
        )
        final_url = image_url
        if process_generated:
            self._emit_file_progress(idx, total, 58)
            if (
                self.visible_mark_cleanup_enabled
                or self.invisible_watermark_cleanup_enabled
                or self.upscale
                or self.upscale_after
                or self.unsharp_enabled
                or self.remove_bg
            ):
                final_url = self._run_processing_pipeline(
                    gen_path,
                    image_url,
                    raw_dir,
                    idx,
                    "gen",
                )
            elif self.edge_shrink_enabled:
                with self._local_operation_lock:
                    final_url = self._edge_shrink_alpha_source_if_available(
                        gen_path,
                        raw_dir,
                        idx,
                        "gen",
                    )
            else:
                final_url = None
            self._emit_file_progress(idx, total, 84)
        else:
            self._emit_file_progress(idx, total, 70)
        self._save_final_output(
            final_url,
            gen_path,
            out_path,
            raw_dir,
            idx,
            "gen",
        )
        self._emit_file_progress(idx, total, 100)
        self.progress.emit(f"  Итог сохранён: {out_path}")
        self._emit_diagnostic(
            "item_finished",
            outcome="succeeded",
            **inspect_diagnostic_image(out_path),
        )
        return out_path

    def _mode1_generate_parallel(self, process_generated=False, emit_final=True):
        raw_dir = self._create_run_raw_dir()
        output_dir = self.output_dir
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        entries = self._normalize_prompt_entries(self.generated_prompts)
        if not entries:
            if emit_final:
                self.completed.emit("Mode 1: Нет записей. Добавьте промпты")
            return

        total = len(entries)
        done_count = 0
        self._next_generation_launch_at = 0.0
        output_names = BatchOutputNameReservation(output_dir)
        planned_entries = [
            (
                idx,
                entry,
                str(output_names.reserve_generated(idx, entry.get("prompt", ""))),
            )
            for idx, entry in enumerate(entries, start=1)
        ]
        pending = iter(planned_entries)
        active = {}
        worker_limit = self._remote_worker_limit(
            include_generation=True,
            include_processing=process_generated,
        )

        with ThreadPoolExecutor(max_workers=worker_limit) as executor:
            def submit_next() -> bool:
                if not self.is_running or self.stop_after_current_requested:
                    return False
                try:
                    idx, entry, out_path = next(pending)
                except StopIteration:
                    return False
                future = executor.submit(
                    self._execute_item_entry,
                    self._generate_entry,
                    idx,
                    total,
                    entry,
                    raw_dir,
                    out_path,
                    process_generated,
                )
                active[future] = idx
                return True

            for _ in range(worker_limit):
                if not submit_next():
                    break

            while active:
                completed, _ = wait(
                    tuple(active),
                    return_when=FIRST_COMPLETED,
                )
                for future in completed:
                    idx = active.pop(future)
                    try:
                        out_path = future.result()
                    except ProcessingCancelled:
                        self._emit_item_progress(
                            idx,
                            total,
                            "processing" if process_generated else "generation",
                            "cancelled",
                        )
                        self.progress.emit(f"[{idx}/{total}] Остановлено")
                    except Exception as error:
                        safe_error, stage, provider, model = self._item_failure_details(
                            error,
                            "processing" if process_generated else "generation",
                        )
                        self._emit_diagnostic(
                            "item_finished",
                            item_index=idx,
                            item_total=total,
                            stage=stage,
                            provider=provider,
                            model=model,
                            outcome="failed",
                            error_message=safe_error,
                        )
                        self.progress.emit(
                            f"[{idx}/{total}] Ошибка: {safe_error}"
                        )
                        self._emit_item_progress(
                            idx,
                            total,
                            stage,
                            "failed",
                            provider=provider,
                            model=model,
                            message=safe_error,
                        )
                    else:
                        self._emit_item_progress(
                            idx,
                            total,
                            "export",
                            "succeeded",
                            percent=100,
                            output_path=out_path,
                        )
                        done_count += 1
                    submit_next()

        self._persist_rough_outputs(raw_dir)
        if not self.is_running:
            self.progress.emit("Остановлено пользователем")
            self._emit_cancelled_run_terminal()
            return
        if self.stop_after_current_requested:
            self.progress.emit("Остановлено после текущего файла")
            self._emit_cancelled_run_terminal()
            return
        self.progress_value.emit(100)
        if emit_final:
            if done_count == 0:
                self.completed.emit(
                    f"Mode 1: Готово (0/{total}). Изображения не созданы."
                )
            else:
                self.completed.emit(f"Mode 1: Готово ({done_count}/{total})")

    def _emit_file_progress(
        self,
        item_index: int,
        total_items: int,
        local_percent: int,
    ) -> None:
        if total_items <= 0:
            return
        local = max(0, min(100, int(local_percent)))
        self._emit_item_progress(
            item_index,
            total_items,
            str(getattr(self._diagnostic_context, "stage", "processing") or "processing"),
            "running",
            percent=local,
            indeterminate=local <= 0,
        )
        base = ((item_index - 1) / total_items) * 100
        self.progress_value.emit(int(base + local / total_items))

    def _normalize_prompt_entries(self, raw_entries):
        entries = []
        for item in raw_entries or []:
            if isinstance(item, dict):
                prompt_text = str(item.get("prompt", "")).strip()
                references = split_references(item.get("references", ""))
                if prompt_text or references:
                    entries.append({"prompt": prompt_text, "references": references})
                continue
            prompt_text = str(item).strip()
            if prompt_text:
                entries.append({"prompt": prompt_text, "references": []})
        return entries

    def _mode2_process_files(self, emit_final=True):
        self.progress.emit("Mode 2: Обработка существующих файлов")
        self.progress.emit(f"Рабочая папка: {self.work_dir}")
        self._log_upscale_plan()

        if not (
            self.visible_mark_cleanup_enabled
            or self.invisible_watermark_cleanup_enabled
            or self.upscale
            or self.upscale_after
            or self.unsharp_enabled
            or self.remove_bg
            or self.trim_enabled
            or self.edge_shrink_enabled
            or self._metadata_cleanup_requested()
            or self.export_300_dpi
        ):
            raise ValueError(
                "Включите хотя бы один этап: удаление видимой метки, апскейл, "
                "удаление фона, trim, 300 DPI или очистку файла"
            )

        if (self._uses_any_kie_upscale() or self._uses_kie_remove_bg()) and not self.kie_api_key:
            raise ValueError("Не указан KIE API Key")
        if (self._uses_any_fal_upscale() or self._uses_fal_remove_bg()) and not self.fal_api_key:
            raise ValueError("Не указан Fal.ai API Key")
        if self._uses_photoroom_remove_bg() and not self.photoroom_api_key:
            raise ValueError("Не указан PhotoRoom API Key")

        if not self.selected_files:
            if emit_final:
                self.completed.emit("Mode 2: Файлы не выбраны")
            return

        raw_dir = self._create_run_raw_dir()
        output_dir = self.output_dir
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        self._mode2_process_files_parallel(
            raw_dir,
            output_dir,
            emit_final=emit_final,
        )
        return

        total = len(self.selected_files)
        done = 0
        for idx, file_path in enumerate(self.selected_files, start=1):
            if not self.is_running:
                self.progress.emit("Остановлено пользователем")
                return

            self.progress.emit(f"[{idx}/{total}] Обработка файла: {os.path.basename(file_path)}")
            self._set_diagnostic_context(idx, total, "processing")
            self._emit_file_progress(idx, total, 4)
            try:
                if not os.path.isfile(file_path):
                    # Keep the marker at the start so the V3 queue can classify
                    # the item as unavailable instead of leaving it running.
                    self.progress.emit(f"Файл не найден: {file_path}")
                    if self._stop_after_current_if_requested():
                        return
                    continue

                source_path = file_path
                self._emit_diagnostic(
                    "item_input_inspected",
                    operation_type="processing",
                    **inspect_diagnostic_image(source_path),
                )

                if (
                    self.visible_mark_cleanup_enabled
                    or self.invisible_watermark_cleanup_enabled
                    or self.upscale
                    or self.upscale_after
                    or self.unsharp_enabled
                    or self.remove_bg
                ):
                    self._emit_file_progress(idx, total, 24)
                    final_url = self._run_processing_pipeline(source_path, None, raw_dir, idx, "file")
                elif self.edge_shrink_enabled:
                    self._emit_file_progress(idx, total, 40)
                    final_url = self._edge_shrink_alpha_source_if_available(source_path, raw_dir, idx, "file")
                else:
                    self._emit_file_progress(idx, total, 50)
                    final_url = None

                self._emit_file_progress(idx, total, 80)
                self._ensure_running()
                out_path = str(
                    processed_output_path(
                        output_dir,
                        file_path,
                        self.run_stamp,
                        overwrite=self.overwrite_existing,
                    )
                )

                self._save_final_output(
                    final_url,
                    source_path,
                    out_path,
                    raw_dir,
                    idx,
                    "file",
                )
                self._emit_file_progress(idx, total, 100)

                self.progress.emit(f"  Итог сохранён: {out_path}")
                self._emit_diagnostic(
                    "item_finished",
                    outcome="succeeded",
                    **inspect_diagnostic_image(out_path),
                )
                done += 1
            except (ProcessingCancelled, VisibleMarkCleanupCancelled):
                self.progress.emit("Остановлено пользователем")
                return
            except Exception as e:
                self._emit_diagnostic(
                    "item_finished",
                    outcome="failed",
                    error_message=self._safe_error_text(e),
                )
                self.progress.emit(f"  Ошибка: {self._safe_error_text(e)}")

            if self._stop_after_current_if_requested():
                return

        self.progress_value.emit(100)
        if emit_final:
            if done == 0:
                self.completed.emit(f"Mode 2: Готово (0/{total}). Изображения не созданы.")
            else:
                self.completed.emit(f"Mode 2: Готово ({done}/{total})")

    def _process_file_entry(
        self,
        idx: int,
        total: int,
        file_path: str,
        raw_dir: str,
        out_path: str,
    ) -> str:
        self._item_context.manual_transparency_required = False
        self._set_diagnostic_context(idx, total, "processing")
        self.progress.emit(
            f"[{idx}/{total}] Обработка файла: {os.path.basename(file_path)}"
        )
        self._emit_file_progress(idx, total, 4)
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        source_path = file_path
        with self._local_operation_lock:
            validate_local_image_input(source_path, decode_pixels=True)
        self._emit_diagnostic(
            "item_input_inspected",
            operation_type="processing",
            **inspect_diagnostic_image(source_path),
        )
        if (
            self.visible_mark_cleanup_enabled
            or self.invisible_watermark_cleanup_enabled
            or self.upscale
            or self.upscale_after
            or self.unsharp_enabled
            or self.remove_bg
        ):
            self._emit_file_progress(idx, total, 24)
            final_url = self._run_processing_pipeline(
                source_path,
                None,
                raw_dir,
                idx,
                "file",
            )
        elif self.edge_shrink_enabled:
            self._emit_file_progress(idx, total, 40)
            with self._local_operation_lock:
                final_url = self._edge_shrink_alpha_source_if_available(
                    source_path,
                    raw_dir,
                    idx,
                    "file",
                )
        else:
            self._emit_file_progress(idx, total, 50)
            final_url = None

        self._emit_file_progress(idx, total, 80)
        self._ensure_running()
        self._save_final_output(
            final_url,
            source_path,
            out_path,
            raw_dir,
            idx,
            "file",
        )
        self._emit_file_progress(idx, total, 100)
        self.progress.emit(f"  Итог сохранён: {out_path}")
        self._emit_diagnostic(
            "item_finished",
            outcome="succeeded",
            **inspect_diagnostic_image(out_path),
        )
        return out_path

    def _mode2_process_files_parallel(
        self,
        raw_dir: str,
        output_dir: str,
        *,
        emit_final: bool,
    ) -> None:
        total = len(self.selected_files)
        done_count = 0
        output_names = BatchOutputNameReservation(output_dir)
        planned_files = [
            (
                idx,
                file_path,
                str(
                    output_names.reserve_processed(
                        file_path,
                        overwrite=self.overwrite_existing,
                    )
                ),
            )
            for idx, file_path in enumerate(self.selected_files, start=1)
        ]
        worker_limit = self._remote_worker_limit()
        if worker_limit == 1:
            for idx, file_path, out_path in planned_files:
                if not self.is_running:
                    break
                try:
                    out_path = self._execute_item_entry(
                        self._process_file_entry,
                        idx,
                        total,
                        file_path,
                        raw_dir,
                        out_path,
                    )
                except ProcessingCancelled:
                    self._emit_item_progress(
                        idx,
                        total,
                        "processing",
                        "cancelled",
                    )
                    self.progress.emit("Остановлено пользователем")
                    break
                except Exception as error:
                    safe_error, stage, provider, model = self._item_failure_details(
                        error,
                        "processing",
                    )
                    self._emit_diagnostic(
                        "item_finished",
                        item_index=idx,
                        item_total=total,
                        stage=stage,
                        provider=provider,
                        model=model,
                        outcome="failed",
                        error_message=safe_error,
                    )
                    self.progress.emit(f"[{idx}/{total}] Ошибка: {safe_error}")
                    self._emit_item_progress(
                        idx,
                        total,
                        stage,
                        "failed",
                        provider=provider,
                        model=model,
                        message=safe_error,
                    )
                else:
                    self._emit_item_progress(
                        idx,
                        total,
                        "export",
                        "succeeded",
                        percent=100,
                        output_path=out_path,
                    )
                    done_count += 1
                if self._stop_after_current_if_requested():
                    break
            if not self.is_running:
                self._persist_rough_outputs(raw_dir)
                return
            self._persist_rough_outputs(raw_dir)
            self.progress_value.emit(100)
            if emit_final:
                if done_count == 0:
                    self.completed.emit(
                        f"Mode 2: Готово (0/{total}). Изображения не созданы."
                    )
                else:
                    self.completed.emit(f"Mode 2: Готово ({done_count}/{total})")
            return

        pending = iter(planned_files)
        active: dict[Any, int] = {}

        with ThreadPoolExecutor(max_workers=worker_limit) as executor:
            def submit_next() -> bool:
                if not self.is_running or self.stop_after_current_requested:
                    return False
                try:
                    idx, file_path, out_path = next(pending)
                except StopIteration:
                    return False
                future = executor.submit(
                    self._execute_item_entry,
                    self._process_file_entry,
                    idx,
                    total,
                    file_path,
                    raw_dir,
                    out_path,
                )
                active[future] = idx
                return True

            for _ in range(worker_limit):
                if not submit_next():
                    break

            while active:
                completed, _ = wait(tuple(active), return_when=FIRST_COMPLETED)
                for future in completed:
                    idx = active.pop(future)
                    try:
                        out_path = future.result()
                    except ProcessingCancelled:
                        self._emit_item_progress(
                            idx,
                            total,
                            "processing",
                            "cancelled",
                        )
                    except Exception as error:
                        safe_error, stage, provider, model = self._item_failure_details(
                            error,
                            "processing",
                        )
                        self._emit_diagnostic(
                            "item_finished",
                            item_index=idx,
                            item_total=total,
                            stage=stage,
                            provider=provider,
                            model=model,
                            outcome="failed",
                            error_message=safe_error,
                        )
                        self.progress.emit(f"[{idx}/{total}] Ошибка: {safe_error}")
                        self._emit_item_progress(
                            idx,
                            total,
                            stage,
                            "failed",
                            provider=provider,
                            model=model,
                            message=safe_error,
                        )
                    else:
                        self._emit_item_progress(
                            idx,
                            total,
                            "export",
                            "succeeded",
                            percent=100,
                            output_path=out_path,
                        )
                        done_count += 1
                    submit_next()

        self._persist_rough_outputs(raw_dir)
        if not self.is_running:
            self.progress.emit("Остановлено пользователем")
            self._emit_cancelled_run_terminal()
            return
        if self.stop_after_current_requested:
            self.progress.emit("Остановлено после текущего файла")
            self._emit_cancelled_run_terminal()
            return
        self.progress_value.emit(100)
        if emit_final:
            if done_count == 0:
                self.completed.emit(
                    f"Mode 2: Готово (0/{total}). Изображения не созданы."
                )
            else:
                self.completed.emit(f"Mode 2: Готово ({done_count}/{total})")

    def _create_run_raw_dir(self):
        """Create an isolated intermediate directory for this run.

        Intermediate files must never be derived from a possibly stale or
        invalid persisted workspace path. Final exports remain controlled by
        ``self.output_dir``.
        """
        candidate = str(
            run_workspace(self.workspace_root or self.work_dir, self.run_id)
        )
        try:
            os.makedirs(candidate, exist_ok=True)
            self._run_raw_dir = candidate
            return candidate
        except OSError:
            pass
        fallback = tempfile.mkdtemp(prefix="clipart-generator-raw-")
        self._run_raw_dir = fallback
        return fallback

    def _persist_rough_outputs(self, raw_dir):
        """Publish meaningful PNG intermediates with short stable names."""
        rough_dir = Path(self.workspace_root) / "rough"
        rough_dir.mkdir(parents=True, exist_ok=True)
        stage_markers = (
            ("visible_mark", "visible-mark-cleaned"),
            ("edgeshrink", "edge-cleaned"),
            ("chroma_key_nobg", "bg-removed"),
            ("photoroom_nobg", "bg-removed"),
            ("fal_nobg", "bg-removed"),
            ("nobg", "bg-removed"),
            ("unsharp", "sharpened"),
            ("pretrim", "pre-trim"),
        )
        generated_name = re.compile(
            rf"^gen_\d{{3}}_{re.escape(self.run_stamp)}\.png$",
            re.IGNORECASE,
        )
        counters = {}
        for source in sorted(Path(raw_dir).glob("*.png")):
            lower_name = source.name.casefold()
            upscale_result = re.search(
                rf"_upscaled_(before|after)(?:_fal)?_\d{{3}}_{re.escape(self.run_stamp)}\.png$",
                lower_name,
                re.IGNORECASE,
            )
            if upscale_result:
                stage = f"upscaled-{upscale_result.group(1).casefold()}"
            else:
                stage = next(
                    (label for marker, label in stage_markers if marker in lower_name),
                    None,
                )
            if stage is None and generated_name.fullmatch(source.name):
                stage = "generated"
            if stage is None:
                continue
            counters[stage] = counters.get(stage, 0) + 1
            target = rough_dir / f"rough_{counters[stage]:02d}_{stage}.png"
            while target.exists():
                counters[stage] += 1
                target = rough_dir / f"rough_{counters[stage]:02d}_{stage}.png"
            shutil.copy2(source, target)
        transient = Path(self.workspace_root) / ".run"
        try:
            owned_run = Path(str(self._run_raw_dir or "")).resolve()
            if Path(raw_dir).resolve() == owned_run and owned_run.is_dir():
                shutil.rmtree(owned_run)
                if transient.is_dir():
                    transient.rmdir()
        except OSError:
            # Results are already published; stale transient data can be retried
            # on the next terminal run without affecting user files.
            pass

    def _uses_local_upscale(self):
        return self.upscale and self.upscale_provider == "local_realesrgan"

    def _uses_kie_upscale(self):
        return self.upscale and self.upscale_provider == "kie"

    def _uses_fal_upscale(self):
        return self.upscale and self.upscale_provider == "fal"

    def _uses_local_upscale_after(self):
        return self.upscale_after and self.upscale_after_provider == "local_realesrgan"

    def _uses_kie_upscale_after(self):
        return self.upscale_after and self.upscale_after_provider == "kie"

    def _uses_fal_upscale_after(self):
        return self.upscale_after and self.upscale_after_provider == "fal"

    def _uses_any_kie_upscale(self):
        return self._uses_kie_upscale() or self._uses_kie_upscale_after()

    def _uses_any_fal_upscale(self):
        return self._uses_fal_upscale() or self._uses_fal_upscale_after()

    def _upscale_pass_factor(
        self,
        provider,
        local_scale,
        kie_model,
        fal_model,
        fal_scale,
    ):
        if provider == "local_realesrgan":
            return normalize_local_realesrgan_scale(local_scale)
        if provider == "fal":
            return normalize_fal_upscale_factor(fal_model, fal_scale)
        return self._resolve_upscale_factor(kie_model)

    def _combined_upscale_factor(self):
        factor = 1
        if self.upscale:
            factor *= self._upscale_pass_factor(
                self.upscale_provider,
                self.local_realesrgan_scale,
                self.kie_upscale_model,
                self.fal_upscale_model,
                self.fal_upscale_scale,
            )
        if self.upscale_after:
            factor *= self._upscale_pass_factor(
                self.upscale_after_provider,
                self.local_realesrgan_after_scale,
                self.kie_upscale_after_model,
                self.fal_upscale_after_model,
                self.fal_upscale_after_scale,
            )
        return factor

    def _log_upscale_plan(self):
        if self.upscale or self.upscale_after:
            self.progress.emit(f"Итоговая кратность апскейла: {self._combined_upscale_factor()}x")

    def _uses_local_rembg_remove_bg(self):
        return self.remove_bg and self.remove_bg_provider == "local_rembg"

    def _uses_local_ben2_remove_bg(self):
        return self.remove_bg and self.remove_bg_provider == "local_ben2"

    def _uses_local_chroma_key_remove_bg(self):
        return self.remove_bg and self.remove_bg_provider == "local_chroma_key"

    def _uses_photoroom_remove_bg(self):
        return self.remove_bg and self.remove_bg_provider == "photoroom"

    def _uses_local_remove_bg(self):
        return (
            self._uses_local_rembg_remove_bg()
            or self._uses_local_ben2_remove_bg()
            or self._uses_local_chroma_key_remove_bg()
        )

    def _uses_kie_remove_bg(self):
        return self.remove_bg and self.remove_bg_provider == "kie"

    def _uses_fal_remove_bg(self):
        return self.remove_bg and self.remove_bg_provider == "fal"

    def _remote_worker_limit(
        self,
        *,
        include_generation: bool = False,
        include_processing: bool = True,
    ) -> int:
        uses_kie = (include_generation and self._uses_kie_generation()) or (
            include_processing
            and (self._uses_any_kie_upscale() or self._uses_kie_remove_bg())
        )
        uses_photoroom = include_processing and self._uses_photoroom_remove_bg()
        uses_fal = (include_generation and self._uses_fal_generation()) or (
            include_processing
            and (self._uses_any_fal_upscale() or self._uses_fal_remove_bg())
        )
        limit = 0
        if uses_kie:
            limit += self.kie_concurrency
        if uses_photoroom:
            limit += self.photoroom_concurrency
        if uses_fal:
            limit += self.fal_concurrency
        return max(1, min(MAX_REMOTE_CONCURRENCY, limit))

    def _can_use_legacy_kie_processing_pipeline(self):
        return (
            self._uses_kie_upscale()
            and not self.visible_mark_cleanup_enabled
            and not self.upscale_after
            and not self._uses_local_remove_bg()
            and not self._uses_photoroom_remove_bg()
            and not self.edge_shrink_enabled
            and not self.unsharp_enabled
        )

    def _ensure_kie_url(self, current_url, current_path):
        if current_url:
            return current_url
        uploaded_url = self._kie_upload_file(current_path)
        self.progress.emit("  Загружено в KIE")
        return uploaded_url

    def _ensure_local_path(self, current_path, current_url, raw_dir, idx, prefix, step_name):
        if current_path and os.path.isfile(current_path):
            return current_path
        local_path = os.path.join(raw_dir, f"{prefix}_{step_name}_{idx:03d}_{self.run_stamp}.png")
        self._download_file(current_url, local_path)
        self.progress.emit(f"  Промежуточный локальный источник: {local_path}")
        return local_path

    def _run_processing_pipeline(self, source_path, source_url, raw_dir, idx, prefix):
        self._ensure_running()
        self._item_context.metadata_cleaned = False
        self._item_context.manual_transparency_required = False
        order_error = validate_upscale_after_background_order(
            self.remove_bg,
            self.upscale_after,
            self.upscale_after_provider,
            (
                self.fal_upscale_after_model
                if self.upscale_after_provider == "fal"
                else self.kie_upscale_after_model
            ),
        )
        if order_error:
            raise ValueError(order_error)
        if self._can_use_legacy_kie_processing_pipeline():
            self._set_provider_diagnostic_context(
                "upscale_before",
                "kie",
                self.kie_upscale_model,
            )
            if self.kie_upscale_model == "recraft/crisp-upscale" and not source_url:
                validate_recraft_crisp_upscale_input(source_path)
            if (
                self.kie_upscale_model == KIE_TOPAZ_MODEL_ID
                and not source_url
                and source_path
                and os.path.isfile(source_path)
            ):
                self._validate_topaz_source_file(
                    source_path,
                    self._resolve_upscale_factor(self.kie_upscale_model),
                )
            uploaded_url = source_url or self._kie_upload_file(source_path)
            self._ensure_running()
            if not source_url:
                self.progress.emit("  Загружено в KIE")
            result = self._run_kie_processing_pipeline(
                uploaded_url,
                raw_dir,
                idx,
                prefix,
                source_path,
            )
            self._ensure_running()
            return result

        current_path = source_path
        current_url = source_url
        local_result = False

        if (
            self._metadata_cleanup_requested()
            and not self._uses_any_kie_upscale()
            and not self._uses_kie_remove_bg()
            and not self._uses_photoroom_remove_bg()
        ):
            with self._local_operation_lock:
                current_path = self._ensure_local_path(
                    current_path, current_url, raw_dir, idx, prefix, "metadata_source"
                )
                metadata_path = os.path.join(raw_dir, f"{prefix}_metadata_{idx:03d}_{self.run_stamp}.png")
                try:
                    cleanup_image_metadata(
                        current_path, metadata_path, self.metadata_cleanup_options
                    )
                    current_path, current_url, local_result = metadata_path, None, True
                    with self._shared_state_lock:
                        self._precleaned_paths.add(os.path.abspath(metadata_path))
                    self._item_context.metadata_cleaned = True
                except MetadataCleanupError as error:
                    self.progress.emit(f"  Очистка файла: ошибка — {error}")
                    raise
            self._ensure_running()

        if self.visible_mark_cleanup_enabled:
            current_path = self._ensure_local_path(
                current_path,
                current_url,
                raw_dir,
                idx,
                prefix,
                "visible_mark_source",
            )
            with self._local_operation_lock:
                visible_mark_path = self._visible_mark_cleanup_pipeline_step(
                    current_path,
                    raw_dir,
                    idx,
                    prefix,
                )
            if visible_mark_path:
                current_path = visible_mark_path
                current_url = None
                local_result = True
            self._ensure_running()

        if self.invisible_watermark_cleanup_enabled:
            current_path = self._ensure_local_path(
                current_path, current_url, raw_dir, idx, prefix, "invisible_source"
            )
            invisible_path = os.path.join(raw_dir, f"{prefix}_invisible_{idx:03d}_{self.run_stamp}.png")
            try:
                self.progress.emit("  Экспериментальная очистка невидимого watermark")
                with self._local_operation_lock:
                    clean_invisible_watermark(
                        Path(current_path), Path(invisible_path), output_root=Path(raw_dir)
                    )
                current_path, current_url, local_result = invisible_path, None, True
            except WatermarkBackendError as error:
                self.progress.emit(f"  Экспериментальный этап пропущен: {error}")
            self._ensure_running()

        if self.upscale:
            current_path, current_url, local_result = self._run_upscale_pass(
                current_path=current_path,
                current_url=current_url,
                raw_dir=raw_dir,
                idx=idx,
                prefix=prefix,
                step_name="upscaled_before",
                provider=self.upscale_provider,
                local_scale=self.local_realesrgan_scale,
                kie_model=self.kie_upscale_model,
            )
            self._ensure_running()

        if self.remove_bg:
            self._diagnostic_context.stage = "background_removal"
            remove_started = time.monotonic()
            remove_provider = self.remove_bg_provider
            remove_model = (
                self.local_rembg_model
                if self._uses_local_rembg_remove_bg()
                else "ben2"
                if self._uses_local_ben2_remove_bg()
                else "chroma-key"
                if self._uses_local_chroma_key_remove_bg()
                else "remove-background-v1"
                if self._uses_photoroom_remove_bg()
                else self.kie_remove_bg_model
            )
            if self._uses_fal_remove_bg():
                remove_model = self.fal_remove_bg_model
            self._diagnostic_context.provider = remove_provider
            self._diagnostic_context.model = remove_model
            self._emit_diagnostic(
                "stage_started",
                provider=remove_provider,
                model=remove_model,
                outcome="started",
            )
            self.progress.emit("  Этап обработки: background_removal; status=running")
            try:
                reuse_alpha = False
                if (
                    self.skip_remover_for_alpha
                    and current_path
                    and os.path.isfile(current_path)
                ):
                    with Image.open(current_path) as source_image:
                        reuse_alpha = has_usable_alpha(source_image)
                if reuse_alpha:
                    nobg_path = os.path.join(
                        raw_dir,
                        f"{prefix}_existing_alpha_{idx:03d}_{self.run_stamp}.png",
                    )
                    with Image.open(current_path) as source_image:
                        source_image.convert("RGBA").save(nobg_path, format="PNG")
                    self.progress.emit(
                        "  Использована сохранённая alpha-маска; remover не вызывается"
                    )
                    current_path = nobg_path
                    current_url = None
                    local_result = True
                elif self._uses_local_rembg_remove_bg():
                    with self._local_operation_lock:
                        current_path = self._ensure_local_path(current_path, current_url, raw_dir, idx, prefix, "local_source")
                        nobg_path = os.path.join(raw_dir, f"{prefix}_nobg_{idx:03d}_{self.run_stamp}.png")
                        self._run_local_rembg(current_path, nobg_path)
                    self.progress.emit(f"  Промежуточный локальный без фона: {nobg_path}")
                    current_path = nobg_path
                    current_url = None
                    local_result = True
                elif self._uses_local_ben2_remove_bg():
                    with self._local_operation_lock:
                        current_path = self._ensure_local_path(current_path, current_url, raw_dir, idx, prefix, "local_source")
                        nobg_path = os.path.join(raw_dir, f"{prefix}_ben2_nobg_{idx:03d}_{self.run_stamp}.png")
                        self._run_local_ben2(current_path, nobg_path)
                    self.progress.emit(f"  Промежуточный BEN2 без фона: {nobg_path}")
                    current_path = nobg_path
                    current_url = None
                    local_result = True
                elif self._uses_local_chroma_key_remove_bg():
                    with self._local_operation_lock:
                        current_path = self._ensure_local_path(
                            current_path, current_url, raw_dir, idx, prefix, "chroma_key_source"
                        )
                        nobg_path = os.path.join(
                            raw_dir, f"{prefix}_chroma_key_nobg_{idx:03d}_{self.run_stamp}.png"
                        )
                        validate_local_image_input(current_path)
                        try:
                            with Image.open(current_path) as source_image:
                                result = remove_chroma_key_automatic(
                                    source_image,
                                    self.chroma_key_color,
                                )
                                self._save_image_object_as_png(result, nobg_path)
                        except ChromaKeyAmbiguousError as error:
                            safe_error = self._safe_error_text(error)
                            self._item_context.manual_transparency_required = True
                            self.progress.emit(
                                "  Local Chroma Key не применён: "
                                f"{safe_error}. Откройте результат для ручной "
                                "коррекции прозрачности."
                            )
                            self._emit_item_progress(
                                idx,
                                int(
                                    getattr(
                                        self._diagnostic_context,
                                        "item_total",
                                        1,
                                    )
                                    or 1
                                ),
                                "background_removal",
                                "stage_skipped",
                                message=(
                                    "Local Chroma Key не применён; требуется "
                                    "ручная коррекция прозрачности."
                                ),
                            )
                            self._emit_diagnostic(
                                "stage_finished",
                                provider=remove_provider,
                                model=remove_model,
                                outcome="skipped",
                                status="manual_transparency_required",
                                error_message=safe_error,
                                elapsed_ms=round(
                                    (time.monotonic() - remove_started) * 1000
                                ),
                                **inspect_diagnostic_image(current_path),
                            )
                            return current_path
                    self.progress.emit(f"  Локальный Chroma Key без фона: {nobg_path}")
                    current_path = nobg_path
                    current_url = None
                    local_result = True
                elif self._uses_photoroom_remove_bg():
                    current_path = self._ensure_local_path(
                        current_path, current_url, raw_dir, idx, prefix, "photoroom_source"
                    )
                    nobg_path = os.path.join(raw_dir, f"{prefix}_photoroom_nobg_{idx:03d}_{self.run_stamp}.png")
                    self._run_photoroom_remove_bg(current_path, nobg_path)
                    self.progress.emit(f"  Промежуточный PhotoRoom без фона: {nobg_path}")
                    current_path = nobg_path
                    current_url = None
                    local_result = True
                elif self._uses_fal_remove_bg():
                    current_url = self._fal_source_url(current_path, current_url)
                    with self._provider_lease("fal"):
                        current_url = self._fal_process_image(
                            current_url,
                            operation="remove_background",
                            model_id=self.fal_remove_bg_model,
                            parameters=self._fal_remove_bg_parameters(),
                        )
                    nobg_path = os.path.join(raw_dir, f"{prefix}_fal_nobg_{idx:03d}_{self.run_stamp}.png")
                    self._download_file(current_url, nobg_path)
                    current_path = nobg_path
                    local_result = True
                else:
                    if (
                        self.kie_remove_bg_model == "recraft/remove-background"
                        and not current_url
                        and current_path
                        and os.path.isfile(current_path)
                    ):
                        validate_recraft_remove_background_input(current_path)
                    current_url = self._ensure_kie_url(current_url, current_path)
                    self.progress.emit(f"  Удаление фона через {self.kie_remove_bg_model}...")
                    current_url = self._kie_run_model_task(self.kie_remove_bg_model, current_url)
                    nobg_path = os.path.join(raw_dir, f"{prefix}_nobg_{idx:03d}_{self.run_stamp}.png")
                    self._download_file(current_url, nobg_path)
                    self.progress.emit(f"  Промежуточный без фона: {nobg_path}")
                    current_path = nobg_path
                    local_result = False
            except Exception:
                self._emit_diagnostic(
                    "stage_finished",
                    provider=remove_provider,
                    model=remove_model,
                    outcome="failed",
                    elapsed_ms=round((time.monotonic() - remove_started) * 1000),
                )
                self.progress.emit("  Этап обработки: background_removal; status=failed")
                raise
            try:
                if not current_path or not os.path.isfile(current_path):
                    raise RuntimeError("Fal.ai не создал локальный файл результата")
                with Image.open(current_path) as output_image:
                    if not has_usable_alpha(output_image):
                        raise RuntimeError(
                            "Провайдер удаления фона вернул изображение без прозрачности"
                        )
            except (OSError, UnidentifiedImageError, RuntimeError) as error:
                self._emit_diagnostic(
                    "stage_finished",
                    provider=remove_provider,
                    model=remove_model,
                    outcome="failed",
                    elapsed_ms=round((time.monotonic() - remove_started) * 1000),
                )
                self.progress.emit("  Этап обработки: background_removal; status=failed")
                raise RuntimeError(str(error)) from error
            self.progress.emit("  Этап обработки: background_removal; status=complete")
            self._emit_diagnostic(
                "stage_finished",
                provider=remove_provider,
                model=remove_model,
                outcome="skipped" if reuse_alpha else "succeeded",
                status="already_alpha" if reuse_alpha else None,
                elapsed_ms=round((time.monotonic() - remove_started) * 1000),
                **(
                    inspect_diagnostic_image(current_path)
                    if current_path and os.path.isfile(current_path)
                    else {}
                ),
            )
            self._ensure_running()

        if self.upscale_after:
            current_path, current_url, local_result = self._run_upscale_pass(
                current_path=current_path,
                current_url=current_url,
                raw_dir=raw_dir,
                idx=idx,
                prefix=prefix,
                step_name="upscaled_after",
                provider=self.upscale_after_provider,
                local_scale=self.local_realesrgan_after_scale,
                kie_model=self.kie_upscale_after_model,
            )
            self._ensure_running()

        if self.edge_shrink_enabled:
            self._diagnostic_context.stage = "edge_cleanup"
            edge_started = time.monotonic()
            self._emit_diagnostic(
                "stage_started",
                provider="local",
                model="alpha-edge-cleanup",
                parameters={"edge_pixels": self.edge_shrink_pixels},
                outcome="started",
            )
            current_path = self._ensure_local_path(current_path, current_url, raw_dir, idx, prefix, "local_source")
            edge_applied = self.remove_bg or self._has_alpha_channel(current_path)
            if edge_applied:
                with self._local_operation_lock:
                    current_path = self._edge_shrink_pipeline_step(current_path, raw_dir, idx, prefix)
                current_url = None
                local_result = True
            else:
                self.progress.emit("  Удаление контура: пропущено, у изображения нет alpha-канала")
            self._emit_diagnostic(
                "stage_finished",
                provider="local",
                model="alpha-edge-cleanup",
                outcome="succeeded" if edge_applied else "skipped",
                elapsed_ms=round((time.monotonic() - edge_started) * 1000),
                **inspect_diagnostic_image(current_path),
            )
            self._ensure_running()

        return current_path if local_result else current_url

    def _visible_mark_cleanup_pipeline_step(self, input_path, raw_dir, idx, prefix):
        confirmed_region = None
        if self.visible_mark_cleanup_mode == "confirmed_area":
            confirmed_region = self.visible_mark_confirmed_regions.get(
                visible_mark_region_key(input_path)
            )
            if confirmed_region is None:
                self.progress.emit("  Видимая метка: файл пропущен, область не подтверждена")
                return None

        output_path = os.path.join(
            raw_dir,
            f"{prefix}_visible_mark_{idx:03d}_{self.run_stamp}.png",
        )
        mode_label = (
            "Gemini автоматически"
            if self.visible_mark_cleanup_mode == "gemini_auto"
            else "подтвержденная область, MI-GAN"
        )
        self.progress.emit(f"  Видимая метка: локальная обработка ({mode_label})...")
        result = cleanup_visible_mark(
            input_path,
            output_path,
            self.visible_mark_cleanup_mode,
            confirmed_region=confirmed_region,
            cancelled=lambda: not self.is_running,
        )

        if not result.changed:
            if self.visible_mark_cleanup_mode == "gemini_auto":
                self.progress.emit(
                    f"  Видимая метка Gemini не найдена уверенно ({result.confidence:.3f}); файл не изменен"
                )
            else:
                self.progress.emit("  Видимая метка: подтвержденная область не потребовала изменений")
            return None

        if self.visible_mark_cleanup_mode == "gemini_auto":
            self.progress.emit(
                f"  Видимая метка Gemini удалена локально: {output_path} "
                f"(вне области изменено {result.changed_pixels_outside_mask} px)"
            )
        else:
            self.progress.emit(
                f"  Подтвержденная область обработана локально: {output_path} "
                f"(вне области изменено {result.changed_pixels_outside_mask} px); "
                "результат требует визуальной проверки"
            )
        return output_path

    def _run_upscale_pass(
        self,
        current_path,
        current_url,
        raw_dir,
        idx,
        prefix,
        step_name,
        provider,
        local_scale,
        kie_model,
    ):
        stage = "upscale_after" if "after" in step_name else "upscale_before"
        self._diagnostic_context.stage = stage
        upscale_started = time.monotonic()
        upscale_model = (
            "realesrgan-ncnn-vulkan"
            if provider == "local_realesrgan"
            else (
                self.fal_upscale_after_model
                if stage == "upscale_after"
                else self.fal_upscale_model
            )
            if provider == "fal"
            else kie_model
        )
        fal_scale = local_scale
        if provider == "fal":
            if stage == "upscale_after" and self._has_fal_upscale_after_scale:
                fal_scale = self.fal_upscale_after_scale
            elif stage != "upscale_after" and self._has_fal_upscale_scale:
                fal_scale = self.fal_upscale_scale
        effective_scale = (
            normalize_fal_upscale_factor(upscale_model, fal_scale)
            if provider == "fal"
            else local_scale
            if provider == "local_realesrgan"
            else self._resolve_upscale_factor(kie_model)
        )
        self._set_provider_diagnostic_context(stage, provider, upscale_model)
        if provider == "fal" and upscale_model == FAL_RECRAFT_CRISP_MODEL_ID:
            current_path = self._ensure_local_path(
                current_path,
                current_url,
                raw_dir,
                idx,
                prefix,
                f"{step_name}_fal_source",
            )
            recraft_input = os.path.join(
                raw_dir,
                f"{prefix}_{step_name}_recraft_input_{idx:03d}_{self.run_stamp}.png",
            )
            current_path = prepare_fal_recraft_crisp_input(
                current_path,
                recraft_input,
            )
            current_url = None
        upscale_parameters = {"scale": effective_scale}
        self._emit_diagnostic(
            "stage_started",
            provider=provider,
            model=upscale_model,
            parameters=upscale_parameters,
            outcome="started",
        )
        self.progress.emit(f"  Этап обработки: {stage}; status=running")
        if provider == "fal":
            alpha_source_path = ""
            alpha_safe_after = (
                stage == "upscale_after"
                and upscale_model_preserves_alpha(provider, upscale_model)
            )
            if alpha_safe_after:
                alpha_source_path = self._ensure_local_path(
                    current_path,
                    current_url,
                    raw_dir,
                    idx,
                    prefix,
                    f"{step_name}_transparent_source",
                )
                try:
                    with Image.open(alpha_source_path) as source_image:
                        if not has_usable_alpha(source_image):
                            raise RuntimeError(
                                "Апскейл после удаления фона требует PNG с прозрачностью"
                            )
                except RuntimeError:
                    raise
                except (OSError, UnidentifiedImageError) as error:
                    raise RuntimeError(
                        "Не удалось проверить прозрачный PNG перед апскейлом"
                    ) from error
                current_path = alpha_source_path
                current_url = None
            current_url = self._fal_source_url(current_path, current_url)
            with self._provider_lease("fal"):
                current_url = self._fal_process_image(
                    current_url,
                    operation="upscale",
                    model_id=upscale_model,
                    scale=effective_scale,
                )
            current_path = os.path.join(
                raw_dir, f"{prefix}_{step_name}_fal_{idx:03d}_{self.run_stamp}.png"
            )
            self._download_file(current_url, current_path)
            if alpha_safe_after:
                self._validate_alpha_safe_upscale_output(
                    alpha_source_path,
                    current_path,
                    effective_scale,
                )
            self.progress.emit(f"  Промежуточный Fal.ai апскейл: {current_path}")
            self.progress.emit(f"  Этап обработки: {stage}; status=complete")
            self._emit_diagnostic(
                "stage_finished",
                provider="fal",
                model=upscale_model,
                outcome="succeeded",
                elapsed_ms=round((time.monotonic() - upscale_started) * 1000),
                **inspect_diagnostic_image(current_path),
            )
            return current_path, current_url, True
        if provider == "local_realesrgan":
            with self._local_operation_lock:
                current_path = self._ensure_local_path(
                    current_path,
                    current_url,
                    raw_dir,
                    idx,
                    prefix,
                    f"{step_name}_source",
                )
                previous_scale = getattr(self, "_active_local_realesrgan_scale", None)
                self._active_local_realesrgan_scale = normalize_local_realesrgan_scale(local_scale)
                try:
                    current_path = self._local_realesrgan_pipeline_step(
                        current_path,
                        raw_dir,
                        idx,
                        prefix,
                        step_name,
                    )
                finally:
                    if previous_scale is None:
                        del self._active_local_realesrgan_scale
                    else:
                        self._active_local_realesrgan_scale = previous_scale
            self.progress.emit(f"  Этап обработки: {stage}; status=complete")
            self._emit_diagnostic(
                "stage_finished",
                provider=provider,
                model=upscale_model,
                parameters=upscale_parameters,
                outcome="succeeded",
                elapsed_ms=round((time.monotonic() - upscale_started) * 1000),
                **inspect_diagnostic_image(current_path),
            )
            return current_path, None, True

        if kie_model == "recraft/crisp-upscale" and current_path and os.path.isfile(current_path):
            validate_recraft_crisp_upscale_input(current_path)
        if kie_model == KIE_TOPAZ_MODEL_ID and current_path and os.path.isfile(current_path):
            self._validate_topaz_source_file(
                current_path,
                self._resolve_upscale_factor(kie_model),
            )
        current_url = self._ensure_kie_url(current_url, current_path)
        current_url = self._upscale_pipeline_step(
            current_url,
            raw_dir,
            idx,
            prefix,
            step_name,
            self._resolve_upscale_factor(kie_model),
            model_name=kie_model,
        )
        current_path = os.path.join(raw_dir, f"{prefix}_{step_name}_{idx:03d}_{self.run_stamp}.png")
        self.progress.emit(f"  Этап обработки: {stage}; status=complete")
        self._emit_diagnostic(
            "stage_finished",
            provider=provider,
            model=upscale_model,
            parameters=upscale_parameters,
            outcome="succeeded",
            elapsed_ms=round((time.monotonic() - upscale_started) * 1000),
        )
        return current_path, current_url, False

    @staticmethod
    def _validate_alpha_safe_upscale_output(source_path, output_path, scale):
        try:
            with Image.open(source_path) as source_image:
                expected_size = (
                    source_image.width * int(scale),
                    source_image.height * int(scale),
                )
            with Image.open(output_path) as output_image:
                if output_image.format != "PNG":
                    raise RuntimeError("Fal.ai вернул не PNG после прозрачного апскейла")
                if output_image.size != expected_size:
                    raise RuntimeError("Fal.ai вернул неверный размер прозрачного апскейла")
                if not has_usable_alpha(output_image):
                    raise RuntimeError(
                        "Fal.ai не сохранил прозрачность после апскейла"
                    )
                output_image.load()
        except RuntimeError:
            raise
        except (OSError, UnidentifiedImageError) as error:
            raise RuntimeError(
                "Fal.ai вернул повреждённый прозрачный PNG"
            ) from error

    def _fal_source_url(self, current_path, current_url):
        if current_url and str(current_url).startswith("https://"):
            return str(current_url)
        return fal_image_data_uri(current_path)

    def _fal_remove_bg_parameters(self):
        if self.fal_remove_bg_model == "fal-ai/birefnet/v2":
            return {
                "model": self.fal_birefnet_model,
                "operating_resolution": self.fal_birefnet_resolution,
                "refine_foreground": self.fal_birefnet_refine_foreground,
                "output_format": "png",
            }
        if self.fal_remove_bg_model == "fal-ai/imageutils/rembg":
            return {"crop_to_bbox": self.fal_rembg_crop_to_bbox}
        return {}

    def _fal_process_image(self, image_url, *, operation, model_id, scale=2, parameters=None):
        if operation == "upscale":
            scale = normalize_fal_upscale_factor(model_id, scale)
        self._ensure_fal_cost_confirmed()
        client = FalClient(
            FalConfig(
                api_key=self.fal_api_key,
                model_id=model_id,
                timeout_seconds=max(10.0, float(self.timeout)),
                before_paid_submit=lambda: self._admit_paid_submission(
                    "fal", "POST"
                ),
            )
        )
        self.progress.emit(f"  Fal.ai операция: {operation}; модель={model_id}")
        task = {"request_id": ""}
        input_fingerprint = self._paid_task_fingerprint(
            {
                "image_url": image_url,
                "scale": scale,
                "parameters": parameters or {},
            }
        )

        def record_submission(request_id, lifecycle_urls):
            task["request_id"] = str(request_id or "")
            self._record_fal_task(
                task["request_id"],
                operation,
                model_id,
                "queued",
                input_fingerprint=input_fingerprint,
                **dict(lifecycle_urls),
            )
            self._emit_diagnostic(
                "provider_task_submitted",
                provider="fal",
                model=model_id,
                task=task["request_id"],
                provider_state="queued",
            )

        pending_task = self._claim_pending_task(
            self.fal_task_journal,
            operation,
            model_id,
            self._claimed_fal_task_ids,
            input_fingerprint=input_fingerprint,
        )
        try:
            if pending_task is not None:
                task["request_id"] = pending_task.request_id
                self.progress.emit(
                    f"  Продолжаем Fal.ai Request ID: {pending_task.request_id}"
                )
                completed = client.wait_for_result(
                    pending_task.request_id,
                    timeout_seconds=float(self.generation_wait_timeout),
                    poll_interval_seconds=float(self.status_poll_interval),
                    is_cancelled=lambda: not self.is_running,
                    on_status=lambda status: self._record_fal_poll_status(
                        task["request_id"],
                        pending_task.operation,
                        model_id,
                        status,
                        input_fingerprint=input_fingerprint,
                    ),
                    status_url=pending_task.status_url,
                    response_url=pending_task.response_url,
                    cancel_url=pending_task.cancel_url,
                )
            else:
                completed = client.run_image_operation(
                    operation,
                    image_url,
                    scale=scale,
                    model_id=model_id,
                    parameters=parameters,
                    is_cancelled=lambda: not self.is_running,
                    on_submitted_task=record_submission,
                    on_status=lambda status: self._record_fal_poll_status(
                        task["request_id"],
                        operation,
                        model_id,
                        status,
                        input_fingerprint=input_fingerprint,
                    ),
                )
        except (FalProviderError, TimeoutError, OSError) as error:
            self._emit_fal_task_failure(
                task["request_id"],
                model_id,
                error,
            )
            raise
        self._ensure_running()
        try:
            result_url = fal_image_url(completed.get("result"))
        except FalProviderError as error:
            self._emit_fal_task_failure(task["request_id"], model_id, error)
            self._record_fal_task(
                task["request_id"],
                pending_task.operation if pending_task is not None else operation,
                model_id,
                "failed",
                input_fingerprint=input_fingerprint,
            )
            raise
        self._emit_fal_task_succeeded(
            task["request_id"],
            model_id,
            completed.get("status"),
        )
        self._record_fal_task(
            task["request_id"],
            pending_task.operation if pending_task is not None else operation,
            model_id,
            "result_ready",
            input_fingerprint=input_fingerprint,
        )
        self._register_paid_result_ready("fal", task["request_id"])
        return result_url

    def _record_fal_task(
        self,
        request_id,
        operation,
        model_id,
        status,
        *,
        input_fingerprint="",
        status_url="",
        response_url="",
        cancel_url="",
    ):
        request_id = str(request_id or "").strip()
        if not request_id:
            return
        try:
            self.fal_task_journal.upsert(
                request_id,
                self._task_operation_key(operation),
                model_id,
                status,
                input_fingerprint=str(input_fingerprint or ""),
                status_url=str(status_url or ""),
                response_url=str(response_url or ""),
                cancel_url=str(cancel_url or ""),
            )
        except (OSError, ValueError, FalProviderError):
            # A journal failure must not expose secrets or turn a successful
            # provider result into a false failure.
            return

    def _record_fal_poll_status(
        self,
        request_id,
        operation,
        model_id,
        status,
        *,
        input_fingerprint="",
    ):
        task_id = str(request_id or "").strip()
        normalized = str(status or "unknown").strip().casefold() or "unknown"
        with self._shared_state_lock:
            attempt = self._fal_poll_attempts.get(task_id, 0) + 1
            self._fal_poll_attempts[task_id] = attempt
        if normalized not in {"completed", "completed_after_cancel"}:
            self._record_fal_task(
                task_id,
                operation,
                model_id,
                normalized,
                input_fingerprint=input_fingerprint,
            )
        self._emit_diagnostic(
            "provider_task_polled",
            provider="fal",
            model=model_id,
            task=task_id,
            provider_state=normalized,
            poll_attempt=attempt,
        )

    def _emit_fal_task_succeeded(self, request_id, model_id, status):
        task_id = str(request_id or "").strip()
        normalized = str(status or "completed").strip().casefold() or "completed"
        with self._shared_state_lock:
            attempt = self._fal_poll_attempts.get(task_id, 0)
        self._emit_diagnostic(
            "provider_task_succeeded",
            provider="fal",
            model=model_id,
            task=task_id,
            provider_state=normalized,
            poll_attempt=attempt,
            outcome="succeeded",
        )

    def _emit_fal_task_failure(
        self,
        request_id,
        model_id,
        error,
        **details,
    ):
        task_id = str(request_id or "").strip()
        self._emit_diagnostic(
            "provider_task_failed",
            provider="fal",
            model=model_id,
            task=task_id,
            error_message=self._safe_error_text(error),
            outcome="failed",
            **details,
        )

    def _record_kie_task(
        self,
        task_id,
        *,
        operation="",
        model_id="",
        status,
        input_fingerprint="",
    ):
        task_id = str(task_id or "").strip()
        if not task_id:
            return
        try:
            if operation and model_id:
                self.kie_task_journal.upsert(
                    task_id,
                    self._task_operation_key(operation),
                    str(model_id),
                    str(status),
                    input_fingerprint=str(input_fingerprint or ""),
                )
            else:
                self.kie_task_journal.update_status(task_id, str(status))
        except (OSError, ValueError, FalProviderError):
            return

    def _task_operation_key(self, operation):
        operation = str(operation or "task").strip() or "task"
        if re.search(r":\d+$", operation):
            return operation
        try:
            item_index = int(getattr(self._diagnostic_context, "item_index", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            item_index = 0
        return f"{operation}:{item_index}" if item_index > 0 else operation

    def _paid_task_fingerprint(self, input_payload):
        with self._shared_state_lock:
            uploaded_content_ids = dict(self._kie_uploaded_content_ids)

        def stable_value(value):
            if isinstance(value, str) and value in uploaded_content_ids:
                return {"kie_upload_sha256": uploaded_content_ids[value]}
            if isinstance(value, dict):
                return {key: stable_value(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [stable_value(item) for item in value]
            return value

        canonical = json.dumps(
            stable_value(input_payload),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _claim_pending_task(
        self,
        journal,
        operation,
        model_id,
        claimed_ids,
        *,
        input_fingerprint,
    ):
        desired_operation = self._task_operation_key(operation)
        base_operation = desired_operation.rsplit(":", 1)[0]
        with self._shared_state_lock:
            try:
                pending = journal.pending()
            except (OSError, ValueError, FalProviderError):
                return None
            exact = [
                task
                for task in pending
                if task.request_id not in claimed_ids
                and task.model_id == str(model_id)
                and task.operation == desired_operation
                and task.input_fingerprint == str(input_fingerprint)
            ]
            legacy = [
                task
                for task in pending
                if task.request_id not in claimed_ids
                and task.model_id == str(model_id)
                and task.operation == base_operation
                and task.input_fingerprint == str(input_fingerprint)
            ]
            candidates = exact or legacy
            if not candidates:
                return None
            task = candidates[0]
            claimed_ids.add(task.request_id)
            return task

    def _has_pending_kie_task(self, task_id):
        try:
            return any(
                record.request_id == str(task_id)
                for record in self.kie_task_journal.pending()
            )
        except (OSError, ValueError, FalProviderError):
            return False

    def recover_pending_fal_tasks(self):
        """Resume polling recorded tasks without submitting them again."""

        recovered = []
        for task in self.fal_task_journal.pending():
            try:
                client = FalClient(
                    FalConfig(
                        api_key=self.fal_api_key,
                        model_id=task.model_id,
                        timeout_seconds=max(10.0, float(self.timeout)),
                    )
                )
                result = client.wait_for_result(
                    task.request_id,
                    timeout_seconds=float(self.generation_wait_timeout),
                    poll_interval_seconds=float(self.status_poll_interval),
                    is_cancelled=lambda: not self.is_running,
                    on_status=lambda status, task=task: self._record_fal_poll_status(
                        task.request_id, task.operation, task.model_id, status
                    ),
                    status_url=task.status_url,
                    response_url=task.response_url,
                    cancel_url=task.cancel_url,
                )
            except (FalProviderError, TimeoutError, OSError) as error:
                self._emit_diagnostic(
                    "provider_task_recovery_deferred",
                    provider="fal",
                    model=task.model_id,
                    task=task.request_id,
                    outcome="deferred",
                    error_message=self._safe_error_text(error),
                )
                continue
            try:
                fal_image_url(result.get("result"))
            except FalProviderError as error:
                self._emit_fal_task_failure(
                    task.request_id,
                    task.model_id,
                    error,
                )
                self._record_fal_task(
                    task.request_id,
                    task.operation,
                    task.model_id,
                    "failed",
                )
                continue
            self._emit_fal_task_succeeded(
                task.request_id,
                task.model_id,
                result.get("status"),
            )
            self._record_fal_task(
                task.request_id,
                task.operation,
                task.model_id,
                "result_ready",
            )
            recovered.append(result)
        return tuple(recovered)

    def _validate_topaz_source_file(self, source_path, upscale_factor):
        file_size = os.path.getsize(source_path)
        if file_size > TOPAZ_MAX_FILE_BYTES:
            raise ValueError(
                "Topaz принимает файлы размером не более 10 МБ; "
                "задача KIE не была создана"
            )
        try:
            with Image.open(source_path) as source_image:
                image_format = str(source_image.format or "").upper()
                width, height = source_image.size
        except (OSError, UnidentifiedImageError) as error:
            raise ValueError(
                "Topaz не смог прочитать исходное изображение; "
                "задача KIE не была создана"
            ) from error
        if image_format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError(
                "Topaz поддерживает только JPEG, PNG и WEBP; "
                "задача KIE не была создана"
            )
        if max(width, height) * upscale_factor > TOPAZ_MAX_OUTPUT_SIDE:
            raise ValueError(
                "После апскейла самая длинная сторона превысит 20 000 px; "
                "уменьшите масштаб или исходное изображение. "
                "Задача KIE не была создана"
            )

    def _run_kie_processing_pipeline(self, image_url, raw_dir, idx, prefix, source_image_path=""):
        pipeline_url = image_url

        if self.upscale:
            self._set_provider_diagnostic_context(
                "upscale_before",
                "kie",
                self.kie_upscale_model,
            )
            self.progress.emit("  Этап обработки: upscale_before; status=running")
            pipeline_url = self._upscale_pipeline_step(
                pipeline_url,
                raw_dir,
                idx,
                prefix,
                "upscaled",
                self._resolve_upscale_factor(),
            )
            self.progress.emit("  Этап обработки: upscale_before; status=complete")

        if self.remove_bg:
            self._set_provider_diagnostic_context(
                "background_removal",
                "kie",
                self.kie_remove_bg_model,
            )
            self.progress.emit(f"  Удаление фона через {self.kie_remove_bg_model}...")
            pipeline_url = self._kie_run_model_task(self.kie_remove_bg_model, pipeline_url)
            nobg_path = os.path.join(raw_dir, f"{prefix}_nobg_{idx:03d}_{self.run_stamp}.png")
            self._download_file(pipeline_url, nobg_path)
            self.progress.emit(f"  Промежуточный без фона: {nobg_path}")
            if self.edge_shrink_enabled:
                return self._edge_shrink_pipeline_step(nobg_path, raw_dir, idx, prefix)

        return pipeline_url

    def _upscale_pipeline_step(
        self,
        image_url,
        raw_dir,
        idx,
        prefix,
        step_name,
        upscale_factor,
        model_name=None,
    ):
        model_name = (model_name or self.kie_upscale_model).strip()
        self.progress.emit(f"  Апскейл через {model_name}...")
        if model_name == KIE_TOPAZ_MODEL_ID:
            upscale_input = {
                "image_url": image_url,
                "upscale_factor": str(upscale_factor),
            }
        elif model_name == "recraft/crisp-upscale":
            upscale_input = None
        else:
            upscale_input = {"scale": upscale_factor}
        self.progress.emit(f"  Кратность апскейла: {upscale_factor}x")
        pipeline_url = self._kie_run_model_task(model_name, image_url, extra_input=upscale_input)
        upscaled_path = os.path.join(raw_dir, f"{prefix}_{step_name}_{idx:03d}_{self.run_stamp}.png")
        self._download_file(pipeline_url, upscaled_path)
        self.progress.emit(f"  Промежуточный апскейл: {upscaled_path}")
        return pipeline_url

    def _local_realesrgan_pipeline_step(self, input_path, raw_dir, idx, prefix, step_name):
        upscaled_path = os.path.join(raw_dir, f"{prefix}_{step_name}_{idx:03d}_{self.run_stamp}.png")
        scale = normalize_local_realesrgan_scale(
            getattr(self, "_active_local_realesrgan_scale", self.local_realesrgan_scale)
        )
        model_name = get_local_realesrgan_model_name(self.local_realesrgan_profile, scale)
        self.progress.emit(f"  Локальный апскейл Real-ESRGAN: {model_name}, {scale}x...")
        self._run_local_realesrgan(input_path, upscaled_path, scale=scale)
        self.progress.emit(f"  Промежуточный локальный апскейл: {upscaled_path}")
        return upscaled_path

    def _unsharp_mask_pipeline_step(self, input_path, raw_dir, idx, prefix):
        output_path = os.path.join(raw_dir, f"{prefix}_unsharp_{idx:03d}_{self.run_stamp}.png")
        self.progress.emit(
            f"  Резкость: amount {self.unsharp_amount}, radius {self.unsharp_radius:g}, "
            f"threshold {self.unsharp_threshold}..."
        )
        self._apply_unsharp_mask_file(input_path, output_path)
        self.progress.emit(f"  Резкость применена: {output_path}")
        return output_path

    def _run_local_realesrgan(self, input_path, output_path, scale=None):
        exe_path, error_message = validate_local_realesrgan_exe(self.local_realesrgan_dir)
        if error_message:
            raise ValueError(error_message)
        validate_local_image_input(input_path)

        scale = normalize_local_realesrgan_scale(scale or self.local_realesrgan_scale)
        validate_local_realesrgan_output_size(input_path, scale)
        model_name = get_local_realesrgan_model_name(self.local_realesrgan_profile, scale)
        models_dir = os.path.join(os.path.dirname(exe_path), "models")
        for suffix in (".bin", ".param"):
            model_path = os.path.join(models_dir, model_name + suffix)
            if not os.path.isfile(model_path):
                raise ValueError(f"Не найдена модель Real-ESRGAN: {model_path}")
        actual_input_path = input_path
        alpha_channel = None
        temp_dir = None
        with Image.open(input_path) as source_img:
            if "A" in source_img.getbands():
                source_rgba = source_img.convert("RGBA")
                alpha_channel = source_rgba.getchannel("A")
                temp_dir = tempfile.TemporaryDirectory()
                actual_input_path = os.path.join(temp_dir.name, "realesrgan_rgb_input.png")
                source_rgba.convert("RGB").save(actual_input_path, format="PNG")
        try:
            command = [
                exe_path,
                "-i",
                actual_input_path,
                "-o",
                output_path,
                "-n",
                model_name,
                "-s",
                str(scale),
            ]
            process = subprocess.Popen(
                command,
                cwd=os.path.dirname(exe_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=hidden_window_creation_flags(),
            )
            deadline = time.monotonic() + LOCAL_REALESRGAN_TIMEOUT_SECONDS
            while True:
                self._ensure_running()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Local Real-ESRGAN exceeded {LOCAL_REALESRGAN_TIMEOUT_SECONDS} seconds"
                    )
                try:
                    stdout, stderr = process.communicate(timeout=min(0.25, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except (ProcessingCancelled, TimeoutError):
            if "process" in locals() and process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
            raise
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()
        if process.returncode != 0:
            stderr = (stderr or "").strip()
            stdout = (stdout or "").strip()
            details = stderr or stdout or f"exit code {process.returncode}"
            raise RuntimeError(f"Local Real-ESRGAN failed: {details}")
        if not os.path.isfile(output_path):
            raise RuntimeError(f"Local Real-ESRGAN did not create output file: {output_path}")
        if alpha_channel is not None:
            self._restore_upscaled_alpha(output_path, alpha_channel)
        return output_path

    def _restore_upscaled_alpha(self, output_path, alpha_channel):
        with Image.open(output_path) as result_img:
            result = result_img.convert("RGBA")
            alpha_histogram = alpha_channel.histogram()
            has_soft_alpha = any(alpha_histogram[1:255])
            resample = Image.Resampling.LANCZOS if has_soft_alpha else Image.Resampling.NEAREST
            upscaled_alpha = alpha_channel.resize(result.size, resample)
            result.putalpha(upscaled_alpha)
            self._save_image_object_as_png(result, output_path)

    def _apply_unsharp_mask_file(self, input_path, output_path):
        with Image.open(input_path) as img:
            unsharp = ImageFilter.UnsharpMask(
                radius=self.unsharp_radius,
                percent=self.unsharp_amount,
                threshold=self.unsharp_threshold,
            )
            if "A" not in img.getbands():
                sharpened = img.convert("RGB").filter(unsharp)
            else:
                rgba = np.asarray(img.convert("RGBA"), dtype=np.uint8)
                alpha_bytes = rgba[:, :, 3].copy()
                alpha = alpha_bytes.astype(np.float32) / 255.0
                premultiplied = np.rint(
                    rgba[:, :, :3].astype(np.float32) * alpha[:, :, None]
                ).astype(np.uint8)
                sharpened_premultiplied = np.asarray(
                    Image.fromarray(premultiplied, mode="RGB").filter(unsharp),
                    dtype=np.float32,
                )
                restored = np.zeros_like(sharpened_premultiplied, dtype=np.float32)
                visible = alpha > 0
                restored[visible] = (
                    sharpened_premultiplied[visible]
                    / alpha[visible, None]
                )
                restored = np.clip(np.rint(restored), 0, 255).astype(np.uint8)
                sharpened = Image.fromarray(
                    np.dstack((restored, alpha_bytes)),
                    mode="RGBA",
                )
            sharpened.info.update(dict(getattr(img, "info", {}) or {}))
            self._save_image_object_as_png(sharpened, output_path)
        return output_path

    def _get_local_rembg_session(self):
        if self.local_rembg_session is None or self.local_rembg_remove is None:
            new_session, remove = import_rembg_tools()
            self.progress.emit(
                f"  Local rembg: загрузка модели {self.local_rembg_model}. Первый запуск может быть долгим..."
            )
            self.local_rembg_session = new_session(self.local_rembg_model)
            self.local_rembg_remove = remove
        return self.local_rembg_session, self.local_rembg_remove

    def _run_local_rembg(self, input_path, output_path):
        validate_local_image_input(input_path)
        session, remove = self._get_local_rembg_session()
        with open(input_path, "rb") as src:
            result_data = remove(src.read(), session=session)
        with Image.open(BytesIO(result_data)) as img:
            result = self._apply_local_rembg_edge_quality(img.convert("RGBA"))
            self._save_image_object_as_png(result, output_path)
        return output_path

    def _apply_local_rembg_edge_quality(self, image):
        rgba = image.convert("RGBA")
        quality = normalize_local_rembg_edge_quality(self.local_rembg_edge_quality)
        if quality == "normal":
            return rgba

        red, green, blue, alpha = rgba.split()
        if quality == "soft":
            alpha = alpha.filter(ImageFilter.GaussianBlur(radius=0.45))
        elif quality == "sharp":
            alpha = alpha.point(lambda value: 0 if value <= 24 else (255 if value >= 232 else value))
            alpha = alpha.filter(ImageFilter.MedianFilter(size=3))
        return Image.merge("RGBA", (red, green, blue, alpha))

    def _get_local_ben2_model(self):
        if self.local_ben2_model is None:
            self.progress.emit("  Local BEN2: подготовка ONNX-модели. Первый запуск может быть долгим...")
            self.local_ben2_model = load_local_ben2_model(
                progress=self.progress.emit,
                cancel_check=self._ensure_running,
            )
        return self.local_ben2_model

    def _run_local_ben2(self, input_path, output_path):
        validate_local_image_input(input_path)
        model = self._get_local_ben2_model()
        with Image.open(input_path) as img:
            source = img.convert("RGB")
            try:
                result = model.inference(source, refine_foreground=self.local_ben2_refine_foreground)
            except TypeError:
                result = model.inference(source)
        if not isinstance(result, Image.Image):
            raise RuntimeError(f"Local BEN2 returned unsupported result type: {type(result)!r}")
        result = self._apply_ben2_alpha_settings(result.convert("RGBA"))
        self._save_image_object_as_png(result, output_path)
        return output_path

    def _apply_ben2_alpha_threshold(self, image):
        return self._apply_ben2_alpha_settings(image)

    def _apply_ben2_alpha_settings(self, image):
        rgba = image.convert("RGBA")
        threshold = normalize_ben2_alpha_threshold(self.local_ben2_alpha_threshold)
        red, green, blue, alpha = rgba.split()
        alpha = alpha.point(lambda value: 0 if value <= threshold else 255)
        corner_radius = normalize_ben2_corner_radius(self.local_ben2_corner_radius)
        for _ in range(corner_radius):
            alpha = alpha.filter(ImageFilter.MedianFilter(size=3))
            alpha = alpha.point(lambda value: 255 if value >= 128 else 0)
        softness = normalize_ben2_edge_softness(self.local_ben2_edge_softness)
        if softness > 0:
            alpha = alpha.filter(ImageFilter.GaussianBlur(radius=softness))
        return Image.merge("RGBA", (red, green, blue, alpha))

    def _edge_shrink_pipeline_step(self, input_path, raw_dir, idx, prefix):
        edge_path = os.path.join(raw_dir, f"{prefix}_edgeshrink_{idx:03d}_{self.run_stamp}.png")
        self.progress.emit(f"  Удаление контура: {self.edge_shrink_pixels} px...")
        self._shrink_alpha_edges(input_path, edge_path, self.edge_shrink_pixels)
        self.progress.emit(f"  Промежуточный без контура: {edge_path}")
        return edge_path

    def _edge_shrink_alpha_source_if_available(self, input_path, raw_dir, idx, prefix):
        if not self._has_alpha_channel(input_path):
            self.progress.emit("  Удаление контура: пропущено, у изображения нет alpha-канала")
            return None
        return self._edge_shrink_pipeline_step(input_path, raw_dir, idx, prefix)

    def _shrink_alpha_edges(self, input_path, output_path, pixels):
        try:
            shrink_pixels = int(pixels)
        except (TypeError, ValueError):
            shrink_pixels = 0

        with Image.open(input_path) as img:
            rgba = img.convert("RGBA")
            if shrink_pixels <= 0:
                self._save_image_object_as_png(rgba, output_path)
                return output_path

            red, green, blue, alpha = rgba.split()
            cleaned_alpha = alpha.point(lambda value: 0 if value <= 12 else value)
            for _ in range(shrink_pixels):
                cleaned_alpha = cleaned_alpha.filter(ImageFilter.MinFilter(size=3))

            result = Image.merge("RGBA", (red, green, blue, cleaned_alpha))
            self._save_image_object_as_png(result, output_path)
        return output_path

    def _has_alpha_channel(self, image_path):
        with Image.open(image_path) as img:
            return "A" in img.getbands()

    def _metadata_cleanup_requested(self):
        options = self.metadata_cleanup_options
        return any(
            (
                options.remove_exif,
                options.remove_xmp,
                options.remove_iptc,
                options.remove_comments_text,
                options.remove_embedded_thumbnail,
                options.remove_generator_fields,
                options.remove_embedded_c2pa,
                not options.preserve_icc,
                not options.preserve_dpi,
            )
        )

    def _save_final_output(self, result_url, source_path, output_path, raw_dir, idx, prefix):
        self._ensure_running()
        trim_enabled = self.trim_enabled and not bool(
            getattr(self._item_context, "manual_transparency_required", False)
        )
        output_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(output_dir, exist_ok=True)
        stage_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".clipart-final-",
                suffix=".stage.png",
                dir=output_dir,
                delete=False,
            ) as stage_file:
                stage_path = stage_file.name

            local_cleanup_source = None
            if self._metadata_cleanup_requested() and not trim_enabled and not self.export_300_dpi:
                if result_url and os.path.isfile(str(result_url)):
                    local_cleanup_source = str(result_url)
                elif not result_url and source_path and os.path.isfile(str(source_path)):
                    local_cleanup_source = str(source_path)

            source_inspection = None
            if local_cleanup_source:
                source_inspection = self._inspect_precleanup_source(local_cleanup_source)
                shutil.copyfile(local_cleanup_source, stage_path)
            elif result_url:
                source_inspection = self._save_pipeline_result(
                    result_url,
                    stage_path,
                    raw_dir,
                    idx,
                    prefix,
                    trim_enabled=trim_enabled,
                )
            elif trim_enabled:
                source_inspection = self._inspect_precleanup_source(source_path)
                self._trim_image_file(
                    source_path,
                    stage_path,
                    "в конце",
                    trim_mode=self._normalize_trim_mode(self.trim_mode),
                )
            else:
                source_inspection = self._inspect_precleanup_source(source_path)
                self._save_image_as_png(source_path, stage_path)

            self._ensure_running()
            if self.unsharp_enabled:
                self._diagnostic_context.stage = "unsharp"
                unsharp_started = time.monotonic()
                self._emit_diagnostic(
                    "stage_started",
                    provider="local",
                    model="pillow-unsharp-mask-alpha-aware",
                    parameters={
                        "amount": self.unsharp_amount,
                        "radius": self.unsharp_radius,
                        "threshold": self.unsharp_threshold,
                    },
                    outcome="started",
                )
                with self._local_operation_lock:
                    sharpened_path = self._unsharp_mask_pipeline_step(
                        stage_path,
                        raw_dir,
                        idx,
                        prefix,
                    )
                    shutil.copyfile(sharpened_path, stage_path)
                self._emit_diagnostic(
                    "stage_finished",
                    provider="local",
                    model="pillow-unsharp-mask-alpha-aware",
                    outcome="succeeded",
                    elapsed_ms=round((time.monotonic() - unsharp_started) * 1000),
                    **inspect_diagnostic_image(stage_path),
                )
                self._ensure_running()
            if self.export_300_dpi:
                self._verify_png_dpi(stage_path, dpi=300)
            self._validate_published_png(stage_path)
            for attempt in range(1, 4):
                self._ensure_running()
                target_existed = os.path.exists(output_path)
                try:
                    self._publish_final_output(
                        stage_path,
                        output_path,
                        source_inspection=source_inspection,
                    )
                    self._validate_published_png(
                        output_path,
                        expected_path=stage_path,
                    )
                    break
                except ProcessingCancelled:
                    raise
                except (OSError, RuntimeError) as error:
                    if attempt >= 3 or not self._is_recoverable_output_error(error):
                        raise
                    if not target_existed:
                        try:
                            os.remove(output_path)
                        except FileNotFoundError:
                            pass
                        except OSError:
                            pass
                    self.progress.emit(
                        f"  Сохранение не удалось, автоматический повтор {attempt + 1}/3"
                    )
                    self._emit_diagnostic(
                        "output_recovery_retry",
                        provider="local",
                        attempt=attempt,
                        error_message=self._safe_error_text(error),
                        outcome="retrying",
                    )
                    self._wait_before_output_recovery(attempt)
            if attempt > 1:
                self.progress.emit(
                    f"  Файл автоматически восстановлен и сохранён с {attempt}-й попытки"
                )
                self._emit_item_progress(
                    idx,
                    int(getattr(self._diagnostic_context, "item_total", 1) or 1),
                    "export",
                    "auto_recovered",
                    recovery_attempts=attempt,
                )
                self._emit_diagnostic(
                    "output_recovered",
                    provider="local",
                    attempt=attempt,
                    outcome="succeeded",
                )
            self._finalize_paid_results()
            if self.export_300_dpi:
                self.progress.emit(
                    f"  Установлен DPI 300 для {os.path.basename(output_path)}"
                )
        finally:
            if stage_path and os.path.exists(stage_path):
                try:
                    os.remove(stage_path)
                except OSError:
                    pass

    @staticmethod
    def _is_recoverable_output_error(error):
        if isinstance(error, OSError):
            return True
        return str(error) in {
            "Итоговый PNG не сохранён",
            "Итоговый PNG недоступен для проверки",
            "Итоговый PNG повреждён",
            "Итоговый PNG повреждён: файл пуст",
            "Итоговый PNG имеет неверный размер",
            "Итоговый PNG потерял прозрачность",
        }

    @staticmethod
    def _wait_before_output_recovery(attempt):
        time.sleep(0.15 * max(1, int(attempt)))

    def _register_paid_result_ready(self, provider, task_id):
        task_id = str(task_id or "").strip()
        if not task_id:
            return
        records = getattr(self._item_context, "paid_results_ready", None)
        if records is None:
            records = []
            self._item_context.paid_results_ready = records
        record = (str(provider or "").strip().lower(), task_id)
        if record not in records:
            records.append(record)

    def _finalize_paid_results(self):
        records = tuple(getattr(self._item_context, "paid_results_ready", ()) or ())
        for provider, task_id in records:
            if provider == "fal":
                try:
                    self.fal_task_journal.update_status(task_id, "completed")
                except (OSError, ValueError, FalProviderError):
                    continue
            elif provider == "kie":
                self._record_kie_task(task_id, status="completed")
        self._item_context.paid_results_ready = []

    def _validate_published_png(self, output_path, *, expected_path=None):
        expected_size = None
        expected_alpha = False
        if expected_path:
            try:
                with Image.open(expected_path) as expected_image:
                    expected_size = expected_image.size
                    expected_alpha = has_usable_alpha(expected_image)
                    expected_image.load()
            except (OSError, UnidentifiedImageError, ValueError) as error:
                raise RuntimeError("Итоговый PNG повреждён") from error
        try:
            if os.path.getsize(output_path) <= 0:
                raise RuntimeError("Итоговый PNG повреждён: файл пуст")
        except FileNotFoundError as error:
            raise RuntimeError("Итоговый PNG не сохранён") from error
        except OSError as error:
            raise RuntimeError("Итоговый PNG недоступен для проверки") from error

        try:
            with Image.open(output_path) as image:
                if image.format != "PNG" or image.width <= 0 or image.height <= 0:
                    raise RuntimeError("Итоговый PNG повреждён")
                if expected_size is not None and image.size != expected_size:
                    raise RuntimeError("Итоговый PNG имеет неверный размер")
                if expected_alpha and not has_usable_alpha(image):
                    raise RuntimeError("Итоговый PNG потерял прозрачность")
                image.load()
        except RuntimeError:
            raise
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise RuntimeError("Итоговый PNG повреждён") from error

    def _inspect_precleanup_source(self, source_path):
        if not self._metadata_cleanup_requested():
            return None

        inspection = inspect_image_metadata(source_path)
        if inspection.get("status") != "ok":
            return inspection
        c2pa = inspection.get("c2pa", {})
        try:
            if c2pa.get("presence") != "not_present":
                if not self.metadata_cleanup_options.remove_embedded_c2pa:
                    raise MetadataCleanupError("C2PA input requires explicit C2PA cleanup")
                if c2pa.get("scan_status") != "ok" or c2pa.get("embedded_presence") == "unknown":
                    raise MetadataCleanupError("embedded C2PA structure cannot be classified safely")
                if (
                    "unknown"
                    in {
                        c2pa.get("embedded_reference_presence"),
                        c2pa.get("external_reference_presence"),
                    }
                    or c2pa.get("unclassified_reference_presence") != "not_present"
                ) and not self.metadata_cleanup_options.remove_xmp:
                    raise MetadataCleanupError("C2PA XMP references cannot be classified safely")
        except MetadataCleanupError as error:
            self._log_metadata_cleanup_inspection(inspection)
            message = str(error).strip() or "неизвестная ошибка проверки"
            self.progress.emit(f"  Очистка файла: ошибка — {message}; итог не опубликован")
            raise RuntimeError(f"Очистка файла не выполнена: {message}") from error
        return inspection

    def _replace_output_if_running(self, stage_path, output_path):
        with self._publish_lock:
            if not self.is_running:
                raise ProcessingCancelled("Остановлено пользователем")
            publish_atomic(
                stage_path,
                output_path,
                overwrite=self.overwrite_existing,
            )

    def _publish_final_output(self, stage_path, output_path, source_inspection=None):
        self._ensure_running()
        if bool(getattr(self._item_context, "metadata_cleaned", False)):
            self._item_context.metadata_cleaned = False
            self._replace_output_if_running(stage_path, output_path)
            return None
        if not self._metadata_cleanup_requested():
            self._replace_output_if_running(stage_path, output_path)
            return None

        publish_path = None
        try:
            output_dir = os.path.dirname(os.path.abspath(output_path))
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".clipart-publish-",
                suffix=".png",
                dir=output_dir,
                delete=False,
            ) as publish_file:
                publish_path = publish_file.name
            os.remove(publish_path)

            inspection = source_inspection or inspect_image_metadata(stage_path)
            self._log_metadata_cleanup_inspection(inspection)
            result = cleanup_image_metadata(
                stage_path,
                publish_path,
                self.metadata_cleanup_options,
            )
            self._replace_output_if_running(publish_path, output_path)
        except ProcessingCancelled:
            raise
        except MetadataCleanupError as error:
            message = str(error).strip() or "неизвестная ошибка проверки"
            self.progress.emit(f"  Очистка файла: ошибка — {message}; итог не опубликован")
            raise RuntimeError(f"Очистка файла не выполнена: {message}") from error
        except OSError:
            raise
        except Exception as error:
            self.progress.emit("  Очистка файла: непредвиденная ошибка; итог не опубликован")
            raise RuntimeError("Очистка файла не выполнена; итог не опубликован") from error
        finally:
            if publish_path and os.path.exists(publish_path):
                try:
                    os.remove(publish_path)
                except OSError:
                    pass

        self._apply_precleanup_action_overrides(result, inspection)
        self._log_metadata_cleanup_result(result)
        return result

    def _apply_precleanup_action_overrides(self, result, inspection):
        if not inspection or inspection.get("status") != "ok":
            return
        actions = result.get("actions", {})
        categories = inspection.get("categories", {})
        if categories.get("iptc", {}).get("present") and actions.get("iptc") == "absent":
            actions["iptc"] = (
                "removed"
                if self.metadata_cleanup_options.remove_iptc
                else "not_preserved_output_unsupported"
            )

        c2pa = inspection.get("c2pa", {})
        if not self.metadata_cleanup_options.remove_embedded_c2pa:
            return
        if c2pa.get("embedded_presence") == "present":
            actions["embedded_c2pa"] = "removed"
        if c2pa.get("external_reference_presence") == "present":
            actions["c2pa_external_reference"] = "removed_from_output"
        if c2pa.get("embedded_reference_presence") == "present":
            actions["c2pa_embedded_reference"] = "removed_from_output"
        if (
            c2pa.get("unclassified_reference_presence") != "not_present"
            and self.metadata_cleanup_options.remove_xmp
        ):
            actions["c2pa_unclassified_reference"] = "removed_with_xmp_category"

    def _log_metadata_cleanup_inspection(self, inspection):
        labels = {
            "exif": "EXIF",
            "xmp": "XMP",
            "iptc": "IPTC",
            "comments_text": "комментарии/текст",
            "embedded_thumbnail": "встроенная миниатюра",
            "icc_profile": "ICC-профиль",
            "dpi": "DPI",
            "generator_fields": "данные генератора",
        }
        if inspection.get("status") != "ok":
            self.progress.emit("  Очистка файла: найдено — проверка итогового формата не поддерживается")
            return

        categories = inspection.get("categories", {})
        found = [label for key, label in labels.items() if categories.get(key, {}).get("present")]
        c2pa = inspection.get("c2pa", {})
        if c2pa.get("embedded_presence") == "present":
            found.append("встроенный C2PA")
        if c2pa.get("embedded_reference_presence") == "present":
            found.append("встроенная ссылка C2PA")
        if c2pa.get("external_reference_presence") == "present":
            found.append("внешняя ссылка C2PA")
        if c2pa.get("unclassified_reference_presence") not in {None, "not_present"}:
            found.append("неопределённая ссылка provenance")
        self.progress.emit(f"  Очистка файла: найдено — {', '.join(found) if found else 'нет'}")

    def _log_metadata_cleanup_result(self, result):
        labels = {
            "exif": "EXIF",
            "xmp": "XMP",
            "iptc": "IPTC",
            "comments_text": "комментарии/текст",
            "embedded_thumbnail": "встроенная миниатюра",
            "generator_fields": "данные генератора",
            "icc_profile": "ICC-профиль",
            "dpi": "DPI",
            "embedded_c2pa": "встроенный C2PA",
            "c2pa_external_reference": "внешняя ссылка C2PA",
            "c2pa_embedded_reference": "встроенная ссылка C2PA",
            "c2pa_unclassified_reference": "неопределённая ссылка provenance",
        }
        removed_statuses = {
            "removed",
            "removed_from_output",
            "removed_with_selected_category",
            "removed_with_xmp_category",
            "unclassified_xmp_removed",
        }
        unsupported_statuses = {"not_preserved", "not_preserved_output_unsupported"}
        groups = {"removed": [], "preserved": [], "unsupported": [], "failed": []}
        for key, status in result.get("actions", {}).items():
            label = labels.get(key, key)
            if status in removed_statuses:
                groups["removed"].append(label)
            elif status == "preserved":
                groups["preserved"].append(label)
            elif status in unsupported_statuses:
                groups["unsupported"].append(label)
            elif status != "absent":
                groups["failed"].append(label)

        messages = (
            ("удалено", groups["removed"]),
            ("сохранено", groups["preserved"]),
            ("не поддерживается", groups["unsupported"]),
            ("не выполнено", groups["failed"]),
        )
        for title, values in messages:
            self.progress.emit(f"  Очистка файла: {title} — {', '.join(values) if values else 'нет'}")

    def _save_pipeline_result(
        self,
        result_url,
        output_path,
        raw_dir,
        idx,
        prefix,
        *,
        trim_enabled=None,
    ):
        if trim_enabled is None:
            trim_enabled = self.trim_enabled
        if os.path.isfile(str(result_url)):
            inspection = self._inspect_precleanup_source(result_url)
            if trim_enabled:
                self._trim_image_file(result_url, output_path, "в конце", trim_mode=self._normalize_trim_mode(self.trim_mode))
            else:
                self._save_image_as_png(result_url, output_path)
            return inspection
        if trim_enabled:
            pretrim_path = os.path.join(raw_dir, f"{prefix}_pretrim_{idx:03d}_{self.run_stamp}.png")
            self._download_precleanup_result(result_url, pretrim_path)
            inspection = self._inspect_precleanup_source(pretrim_path)
            self._trim_image_file(pretrim_path, output_path, "в конце", trim_mode=self._normalize_trim_mode(self.trim_mode))
            return inspection
        self._download_precleanup_result(result_url, output_path)
        inspection = self._inspect_precleanup_source(output_path)
        if self.export_300_dpi and self._metadata_cleanup_requested():
            self._set_png_dpi(output_path, dpi=300)
        return inspection

    def _download_precleanup_result(self, result_url, output_path):
        if not self._metadata_cleanup_requested():
            self._download_file(result_url, output_path)
            return
        export_300_dpi = self.export_300_dpi
        self.export_300_dpi = False
        try:
            self._download_file(result_url, output_path)
        finally:
            self.export_300_dpi = export_300_dpi

    def _save_image_as_png(self, source_path, output_path):
        with Image.open(source_path) as img:
            self._save_image_object_as_png(img, output_path)

    def _save_image_object_as_png(self, image, output_path):
        image_to_save = image
        if image_to_save.mode not in {"RGB", "RGBA"}:
            image_to_save = image_to_save.convert("RGBA")
        save_kwargs = self._get_png_save_kwargs(image)
        image_to_save.save(output_path, format="PNG", **save_kwargs)

    def _get_png_save_kwargs(self, source_image=None, dpi_override=None):
        save_kwargs = {}
        if source_image is not None and self._metadata_cleanup_requested():
            source_info = dict(getattr(source_image, "info", {}) or {})
            raw_icc = source_info.get("icc_profile")
            if isinstance(raw_icc, bytes) and raw_icc:
                save_kwargs["icc_profile"] = raw_icc

            raw_exif = source_info.get("exif")
            if not isinstance(raw_exif, bytes):
                try:
                    exif = source_image.getexif()
                    raw_exif = exif.tobytes() if exif else b""
                except (OSError, SyntaxError, ValueError):
                    raw_exif = b""
            if raw_exif:
                save_kwargs["exif"] = raw_exif

            text_entries = dict(getattr(source_image, "text", {}) or {})
            for key, value in source_info.items():
                if isinstance(value, str):
                    text_entries.setdefault(str(key), value)
                elif str(key).casefold() in {"comment", "xmp", "xml:com.adobe.xmp"} and isinstance(
                    value, bytes
                ):
                    text_entries.setdefault(str(key), value.decode("utf-8", errors="replace"))
            if text_entries:
                pnginfo = PngImagePlugin.PngInfo()
                for key, value in text_entries.items():
                    pnginfo.add_itxt(str(key), str(value))
                save_kwargs["pnginfo"] = pnginfo

            transparency = source_info.get("transparency")
            if transparency is not None and source_image.mode == "RGB":
                save_kwargs["transparency"] = transparency

            source_dpi = source_info.get("dpi")
            if (
                dpi_override is None
                and not self.export_300_dpi
                and isinstance(source_dpi, (tuple, list))
                and len(source_dpi) >= 2
            ):
                save_kwargs["dpi"] = (source_dpi[0], source_dpi[1])

        if dpi_override is not None:
            save_kwargs["dpi"] = (dpi_override, dpi_override)
        elif self.export_300_dpi:
            save_kwargs["dpi"] = (300, 300)
        return save_kwargs

    def _trim_image_file(self, source_path, output_path, stage_label, trim_mode=None):
        with Image.open(source_path) as img:
            bbox = self._detect_trim_bbox(img, trim_mode=trim_mode)
            if not bbox:
                self.progress.emit(f"  Trim {stage_label}: пустые края не найдены")
                self._save_image_as_png(source_path, output_path)
                return output_path

            if bbox == (0, 0, img.width, img.height):
                self.progress.emit(f"  Trim {stage_label}: обрезка не требуется")
                self._save_image_as_png(source_path, output_path)
                return output_path

            cropped = img.crop(bbox)
            self._save_image_object_as_png(cropped, output_path)
            self.progress.emit(f"  Trim {stage_label}: {img.width}x{img.height} → {cropped.width}x{cropped.height}")
            return output_path

    def _detect_trim_bbox(self, image, trim_mode=None):
        mode = self._normalize_trim_mode(trim_mode or self.trim_mode)
        if mode == "white":
            return self._detect_white_trim_bbox(image)
        if mode == "black":
            return self._detect_black_trim_bbox(image)
        return self._detect_alpha_trim_bbox(image)

    def _detect_alpha_trim_bbox(self, image):
        rgba = image.convert("RGBA")
        alpha = rgba.split()[-1]
        # У некоторых моделей по краям остаётся «грязная» полупрозрачность
        # (alpha 1..10), из-за которой getbbox() возвращает весь кадр.
        # Считаем полезной областью только пиксели с заметной непрозрачностью.
        alpha_threshold = 12
        solid_alpha = alpha.point(lambda v: 255 if v > alpha_threshold else 0)
        bbox = solid_alpha.getbbox()
        if not bbox:
            return None

        full_bbox = (0, 0, image.width, image.height)
        if bbox != full_bbox:
            return bbox

        # Если картинка полностью непрозрачная, многие модели всё равно
        # дорисовывают белые поля без прозрачности. В таком случае делаем
        # запасной поиск по почти белому фону, чтобы Trim работал предсказуемо.
        if self._is_fully_opaque(alpha):
            fallback_bbox = self._detect_white_trim_bbox(image)
            if fallback_bbox:
                return fallback_bbox

        return bbox

    def _detect_white_trim_bbox(self, image):
        threshold = 250
        rgb = image.convert("RGB")
        r, g, b = rgb.split()
        mask_r = r.point(lambda v: 255 if v < threshold else 0)
        mask_g = g.point(lambda v: 255 if v < threshold else 0)
        mask_b = b.point(lambda v: 255 if v < threshold else 0)
        mask = ImageChops.lighter(mask_r, ImageChops.lighter(mask_g, mask_b))

        rgba = image.convert("RGBA")
        alpha_non_empty = rgba.split()[-1].point(lambda v: 255 if v > 0 else 0)
        mask = ImageChops.multiply(mask, alpha_non_empty)
        return mask.getbbox()

    def _detect_black_trim_bbox(self, image):
        threshold = 5
        rgb = image.convert("RGB")
        r, g, b = rgb.split()
        mask_r = r.point(lambda v: 255 if v > threshold else 0)
        mask_g = g.point(lambda v: 255 if v > threshold else 0)
        mask_b = b.point(lambda v: 255 if v > threshold else 0)
        mask = ImageChops.lighter(mask_r, ImageChops.lighter(mask_g, mask_b))

        rgba = image.convert("RGBA")
        alpha_non_empty = rgba.split()[-1].point(lambda v: 255 if v > 0 else 0)
        mask = ImageChops.multiply(mask, alpha_non_empty)
        return mask.getbbox()

    def _is_fully_opaque(self, alpha_channel):
        extrema = alpha_channel.getextrema()
        if not extrema:
            return False
        return extrema[0] == 255 and extrema[1] == 255

    def _resolve_upscale_factor(self, model_name=None):
        model_name = (model_name or self.kie_upscale_model or "").strip()
        if model_name == "recraft/crisp-upscale":
            return 4
        if model_name == KIE_TOPAZ_MODEL_ID:
            return normalize_topaz_upscale_factor(self.upscale_factor)
        return 4

    def _normalize_trim_mode(self, value):
        mode = str(value or "alpha").strip().lower()
        if mode in {"alpha", "white", "black"}:
            return mode
        legacy_map = {
            "transparent": "alpha",
            "opaque": "white",
        }
        return legacy_map.get(mode, "alpha")

    def _get_generation_profile(self, has_references):
        if has_references:
            return (
                self._normalize_ratio(self.reference_generation_ratio),
                str(self.reference_generation_resolution or "1K").strip() or "1K",
            )
        return (
            self._normalize_ratio(self.text_generation_ratio),
            str(self.text_generation_resolution or "1K").strip() or "1K",
        )

    def _get_model_capabilities(self, model_id):
        return get_model_capabilities(model_id)

    def _get_model_label(self, model_id):
        normalized = self._normalize_generation_model_id(model_id)
        for entry in GENERATION_MODELS:
            if entry.get("id") == normalized:
                return str(entry.get("label") or normalized)
        return normalized

    def _is_model_unavailable_error(self, message):
        text = str(message or "").lower()
        markers = [
            "model not supported",
            "not supported",
            "model unavailable",
            "unsupported model",
            "не поддерж",
            "недоступ",
        ]
        return any(marker in text for marker in markers)

    def _select_combo_model_id(self, combo_box, model_id):
        idx = combo_box.findData(model_id)
        if idx >= 0:
            combo_box.setCurrentIndex(idx)
            return True
        return False

    def _probe_model_with_fallback_prompt(
        self,
        combo_box,
        preferred_model_id,
        fallback_model_id,
        ratio,
        headers,
        timeout,
        probe_reference_urls=None,
    ):
        selected_model = self._normalize_generation_model_id(preferred_model_id)
        fallback_model = self._normalize_generation_model_id(fallback_model_id)

        while True:
            ok, error_message, _ = self._probe_model_with_ratio(
                selected_model,
                ratio,
                headers,
                timeout,
                reference_urls=probe_reference_urls,
            )
            if ok:
                self._select_combo_model_id(combo_box, selected_model)
                return True

            if probe_reference_urls and is_schema_required_error_message(error_message):
                self.log(
                    "Reference-model preflight skipped: the API requires fields that are only available during the real run."
                )
                return True

            if not self._is_model_unavailable_error(error_message):
                safe_message = safe_error_text(
                    error_message,
                    (self.kie_api_key,),
                )
                self.progress.emit(
                    f"Запуск остановлен: проверка модели не завершена ({safe_message})"
                )
                return False

            unavailable_label = self._get_model_label(selected_model)
            fallback_label = self._get_model_label(fallback_model)
            answer = QMessageBox.question(
                self,
                "Модель недоступна",
                (
                    f'Модель "{unavailable_label}" недоступна.\n'
                    f'Заменить на модель по умолчанию "{fallback_label}"?'
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.log("Запуск остановлен: пользователь отказался от замены недоступной модели")
                return False

            if selected_model == fallback_model:
                QMessageBox.warning(
                    self,
                    "Модель недоступна",
                    f'Модель по умолчанию "{fallback_label}" тоже недоступна. Запуск остановлен.',
                )
                self.log(f"Запуск остановлен: модель по умолчанию '{fallback_label}' недоступна")
                return False

            self.log(f"Модель '{unavailable_label}' недоступна. Переключаемся на '{fallback_label}'.")
            selected_model = fallback_model

    def _ensure_models_available_before_run(self, run_mode, prompts):
        # Ordinary runs must never create paid provider tasks as an availability
        # probe. Contract compatibility is validated locally before upload; a
        # live model check remains available only through the explicit UI action.
        return True

    def _kie_headers(self):
        return {
            "Authorization": f"Bearer {self.kie_api_key}",
            "Accept": "application/json",
            "User-Agent": APP_USER_AGENT,
        }

    def _request_with_retries(self, req, timeout=None):
        req_timeout = timeout or self.timeout
        last_error = None
        ssl_context = build_ssl_context()
        self._protect_secret_headers_from_redirects(req)
        provider = self._request_provider(req)
        method = req.get_method().upper()
        retry_limit = self.retries if method in {"GET", "HEAD", "OPTIONS"} else 0
        rate_limit_retry_limit = min(max(self.retries, 1), 2)
        for attempt in range(max(retry_limit, rate_limit_retry_limit) + 1):
            self._ensure_running()
            try:
                with self._network_attempt_lease(provider):
                    if provider == "photoroom":
                        self._wait_for_photoroom_launch()
                    self._admit_paid_submission(provider, method)
                    with open_url_secure(req, timeout=req_timeout, context=ssl_context) as resp:
                        response_status = getattr(resp, "status", None)
                        response_getcode = getattr(resp, "getcode", None)
                        if response_status is None and callable(response_getcode):
                            try:
                                response_status = response_getcode()
                            except Exception:
                                response_status = None
                        self._diagnostic_context.last_http_status = int(response_status or 200)
                        response = read_response_limited(resp, MAX_API_RESPONSE_BYTES)
                self._ensure_running()
                return response
            except urlerror.HTTPError as e:
                self._diagnostic_context.last_http_status = int(e.code)
                last_error = RuntimeError(f"HTTP status={e.code}")

                # Не ретраим ошибки авторизации/доступа, чтобы лог был понятнее.
                if e.code in {400, 401, 402, 403, 404}:
                    break

                # 429 безопасно повторить даже для POST: KIE отклонил запрос
                # лимитом и не создал задачу. Остальные POST-ошибки не повторяем,
                # чтобы не рисковать дублированием платной операции.
                if e.code == 429 and method == "POST":
                    retry_limit = rate_limit_retry_limit

                if attempt >= retry_limit:
                    break
                self.progress.emit(f"  Повтор запроса {attempt + 1}/{retry_limit}")
                time.sleep(min(2 * (attempt + 1), 6))
            except ProcessingCancelled:
                raise
            except ResponseLimitError as error:
                last_error = error
                break
            except Exception as e:
                last_error = e
                if attempt >= retry_limit:
                    break
                self.progress.emit(f"  Повтор запроса {attempt + 1}/{retry_limit}")
                time.sleep(min(2 * (attempt + 1), 6))
        raise RuntimeError(f"Ошибка HTTP-запроса: {self._safe_error_text(last_error)}")

    def _request_json(self, url, method="GET", payload=None, headers=None, timeout=None):
        req_headers = headers or {}
        data_bytes = None
        if payload is not None:
            data_bytes = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data_bytes, headers=req_headers, method=method)
        raw = self._request_with_retries(req, timeout=timeout)
        return json.loads(raw.decode("utf-8"))

    def _read_upload_file(self, file_path):
        if os.path.getsize(file_path) > MAX_API_UPLOAD_BYTES:
            raise ResponseLimitError("Upload file exceeds size limit")
        with open(file_path, "rb") as source_file:
            payload = source_file.read(MAX_API_UPLOAD_BYTES + 1)
        if len(payload) > MAX_API_UPLOAD_BYTES:
            raise ResponseLimitError("Upload file exceeds size limit")
        return payload

    def _run_photoroom_remove_bg(self, input_path, output_path):
        if not self.photoroom_api_key:
            raise ValueError("Не указан PhotoRoom API Key")
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"Файл для PhotoRoom не найден: {input_path}")
        validate_photoroom_input(input_path)

        boundary = "----ClipartPhotoRoomBoundary" + uuid.uuid4().hex
        filename = re.sub(r'[\r\n"]', "_", os.path.basename(input_path)) or "image.png"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        image_bytes = self._read_upload_file(input_path)

        parts = []
        for field_name, field_value in (
            ("format", "png"),
            ("channels", "rgba"),
            ("size", "full"),
            ("crop", "false"),
            ("despill", "false"),
        ):
            parts.extend(
                [
                    f"--{boundary}\r\n".encode("ascii"),
                    f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode("ascii"),
                    field_value.encode("ascii"),
                    b"\r\n",
                ]
            )
        parts.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="image_file"; filename="{filename}"\r\n'.encode(
                    "utf-8"
                ),
                f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
                image_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode("ascii"),
            ]
        )
        req = request.Request(
            PHOTOROOM_SEGMENT_URL,
            data=b"".join(parts),
            headers={
                "x-api-key": self.photoroom_api_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "image/png",
            },
            method="POST",
        )

        with self._provider_lease("photoroom"):
            return self._execute_photoroom_remove_bg_request(
                req,
                input_path,
                output_path,
            )

    def _execute_photoroom_remove_bg_request(self, req, input_path, output_path):
        self.progress.emit("  Удаление фона через PhotoRoom Standard...")
        started = time.monotonic()
        self._emit_diagnostic(
            "provider_task_submitted",
            provider="photoroom",
            model="remove-background-v1",
            parameters={"output_format": "png"},
            **inspect_diagnostic_image(input_path),
        )
        try:
            response_bytes = self._request_with_retries(req, timeout=max(60, self.timeout))
        except Exception as error:
            self._emit_diagnostic(
                "provider_task_failed",
                provider="photoroom",
                model="remove-background-v1",
                http_status=getattr(self._diagnostic_context, "last_http_status", None),
                error_message=self._safe_error_text(error),
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise
        try:
            with Image.open(BytesIO(response_bytes)) as response_image:
                if response_image.format != "PNG" or "A" not in response_image.getbands():
                    raise ValueError("ответ не является PNG с alpha-каналом")
                if getattr(response_image, "n_frames", 1) != 1:
                    raise ValueError("ответ должен содержать один кадр")
                if max(response_image.size) > MAX_PROVIDER_IMAGE_DIMENSION:
                    raise ValueError("ответ превышает лимит стороны изображения")
                if response_image.width * response_image.height > MAX_PROVIDER_IMAGE_PIXELS:
                    raise ValueError("ответ превышает лимит пикселей")
                response_image.load()
                self._ensure_running()
                result_image = response_image.convert("RGBA").copy()
                save_kwargs = self._get_png_save_kwargs(response_image)
        except ProcessingCancelled:
            raise
        except Exception as exc:
            self._emit_diagnostic(
                "provider_task_failed",
                provider="photoroom",
                model="remove-background-v1",
                http_status=getattr(self._diagnostic_context, "last_http_status", None),
                error_message=(
                    "PhotoRoom вернул некорректное изображение: "
                    f"{self._safe_error_text(exc)}"
                ),
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise RuntimeError("PhotoRoom вернул некорректное изображение") from exc

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        result_image.save(output_path, format="PNG", **save_kwargs)
        self._emit_diagnostic(
            "stage_finished",
            provider="photoroom",
            model="remove-background-v1",
            outcome="succeeded",
            http_status=getattr(self._diagnostic_context, "last_http_status", 200),
            output_bytes=len(response_bytes),
            elapsed_ms=round((time.monotonic() - started) * 1000),
            **inspect_diagnostic_image(output_path),
        )
        return output_path

    def _kie_upload_file(self, file_path):
        with self._provider_lease("kie"):
            return self._kie_upload_file_leased(file_path)

    def _kie_upload_file_leased(self, file_path):
        boundary = "----ClipartBoundary" + uuid.uuid4().hex
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        started = time.monotonic()
        self._emit_diagnostic(
            "provider_upload_started",
            provider="kie",
            **inspect_diagnostic_image(file_path),
        )
        try:
            file_bytes = self._read_upload_file(file_path)
        except ProcessingCancelled:
            raise
        except Exception as error:
            self._emit_diagnostic(
                "stage_finished",
                provider="kie",
                outcome="failed",
                error_message=self._safe_error_text(error),
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise RuntimeError(
                "Не удалось прочитать файл для загрузки в KIE; "
                "задача KIE не была создана: "
                f"{self._safe_error_text(error)}"
            ) from error

        parts = []
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(b'Content-Disposition: form-data; name="uploadPath"\r\n\r\n')
        parts.append(self.kie_upload_path.encode("utf-8"))
        parts.append(b"\r\n")
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        parts.append(file_bytes)
        parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        upload_url = "https://kieai.redpandaai.co/api/file-stream-upload"
        body = b"".join(parts)
        try:
            headers = self._kie_headers()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            headers["x-api-key"] = self.kie_api_key
            self.progress.emit(f"  Upload endpoint: {upload_url}")
            req = request.Request(upload_url, data=body, headers=headers, method="POST")
            payload = json.loads(
                self._request_with_retries(req, timeout=max(60, self.timeout)).decode("utf-8")
            )
            if payload.get("success") is False:
                raise RuntimeError("KIE upload rejected the file")
            data = payload.get("data") or {}
            download_url = data.get("downloadUrl") or data.get("url") or payload.get("url")
            if download_url:
                with self._shared_state_lock:
                    self._kie_uploaded_content_ids[str(download_url)] = hashlib.sha256(
                        file_bytes
                    ).hexdigest()
                self._emit_diagnostic(
                    "provider_upload_finished",
                    provider="kie",
                    outcome="succeeded",
                    http_status=getattr(self._diagnostic_context, "last_http_status", 200),
                    uploaded_bytes=len(file_bytes),
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                    filename=filename,
                )
                return download_url
            raise RuntimeError("KIE upload did not return a download URL")
        except ProcessingCancelled:
            raise
        except Exception as error:
            self._emit_diagnostic(
                "stage_finished",
                provider="kie",
                outcome="failed",
                http_status=getattr(self._diagnostic_context, "last_http_status", None),
                error_message=self._safe_error_text(error),
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise RuntimeError(
                "Не удалось загрузить файл в KIE; задача KIE не была создана: "
                f"{self._safe_error_text(error)}"
            ) from error

    def _kie_create_task(self, model, input_payload):
        input_fingerprint = self._paid_task_fingerprint(input_payload)
        self._wait_for_generation_launch_slot()
        started = time.monotonic()
        self._diagnostic_context.model = str(model or "")
        headers = self._kie_headers()
        headers["Content-Type"] = "application/json"
        try:
            result = self._request_json(
                "https://api.kie.ai/api/v1/jobs/createTask",
                method="POST",
                payload={"model": model, "input": input_payload},
                headers=headers,
                timeout=max(30, self.timeout),
            )
        except Exception as error:
            self._emit_diagnostic(
                "provider_task_failed",
                provider="kie",
                model=model,
                http_status=getattr(self._diagnostic_context, "last_http_status", None),
                error_message=self._safe_error_text(error),
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise
        if int(result.get("code", 0)) != 200:
            self._emit_diagnostic(
                "provider_task_failed",
                provider="kie",
                model=model,
                http_status=getattr(self._diagnostic_context, "last_http_status", None),
                error_code=result.get("code"),
                error_message=self._safe_error_text(result.get("msg") or "request rejected"),
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise RuntimeError(
                f"KIE createTask rejected [errorCode={result.get('code', '-')}; "
                f"message={self._safe_error_text(result.get('msg') or 'request rejected')}]"
            )
        task_id = (result.get("data") or {}).get("taskId")
        if not task_id:
            self._emit_diagnostic(
                "provider_task_failed",
                provider="kie",
                model=model,
                http_status=getattr(self._diagnostic_context, "last_http_status", None),
                error_message="KIE createTask не вернул taskId",
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise RuntimeError("KIE createTask не вернул taskId")
        self._record_kie_task(
            task_id,
            operation=str(getattr(self._diagnostic_context, "stage", "") or "kie"),
            model_id=model,
            status="queued",
            input_fingerprint=input_fingerprint,
        )
        self._emit_diagnostic(
            "provider_task_submitted",
            provider="kie",
            model=model,
            task=task_id,
            http_status=getattr(self._diagnostic_context, "last_http_status", 200),
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        return task_id

    def _kie_run_model_task(self, model, image_url, extra_input=None):
        with self._provider_lease("kie"):
            self._set_provider_diagnostic_context(
                getattr(self._diagnostic_context, "stage", ""),
                "kie",
                model,
            )
            input_payload = {} if model == KIE_TOPAZ_MODEL_ID else {"image": image_url}
            if isinstance(extra_input, dict):
                input_payload.update(extra_input)
            input_fingerprint = self._paid_task_fingerprint(input_payload)
            operation = str(
                getattr(self._diagnostic_context, "stage", "") or "kie"
            )
            pending_task = self._claim_pending_task(
                self.kie_task_journal,
                operation,
                model,
                self._claimed_kie_task_ids,
                input_fingerprint=input_fingerprint,
            )
            task_id = (
                pending_task.request_id
                if pending_task is not None
                else self._kie_create_task(model, input_payload)
            )
            if pending_task is not None:
                self.progress.emit(f"  Продолжаем KIE Task ID: {task_id}")
            self.progress.emit(f"  Task ID: {task_id}")
            return self._kie_wait_result(task_id)

    def _resolve_reference_url(self, reference_value):
        ref = str(reference_value or "").strip()
        if not ref:
            return ""
        parsed = urlparse(ref)
        if parsed.scheme in {"http", "https"}:
            return ref
        if not os.path.isfile(ref):
            raise RuntimeError(f"Референс не найден: {ref}")
        self.progress.emit(f"  Загрузка референса: {os.path.basename(ref)}")
        return self._kie_upload_file(ref)

    def _resolve_reference_urls(self, references=None):
        ref_items = split_references(references or [])
        if len(ref_items) > MAX_REFERENCES_PER_PROMPT:
            raise RuntimeError(f"Максимум {MAX_REFERENCES_PER_PROMPT} референсов на один промпт")
        urls = []
        for ref in ref_items:
            resolved = self._resolve_reference_url(ref)
            if resolved:
                urls.append(resolved)
        return urls

    def _kie_generate_image(self, prompt, references=None):
        reference_items = split_references(references or [])
        normalized_model = self._select_generation_model(reference_items)
        if is_fal_generation_model(normalized_model):
            with self._provider_lease("fal"):
                self._set_provider_diagnostic_context(
                    "generation", "fal", normalized_model
                )
                if reference_items:
                    raise RuntimeError(
                        "Выбранный Fal.ai generation endpoint пока не поддерживает локальные референсы"
                    )
                return self._fal_generate_image(prompt, normalized_model)
        with self._provider_lease("kie"):
            self._set_provider_diagnostic_context(
                "generation",
                "kie",
                normalized_model,
            )
            has_references = bool(reference_items)
            ratio, resolution = self._get_generation_profile(has_references)
            reference_sizes = tuple(
                os.path.getsize(reference)
                for reference in reference_items
                if not urlparse(reference).scheme and os.path.isfile(reference)
            )
            validate_generation_contract(
                normalized_model,
                has_references=has_references,
                ratio=ratio,
                resolution=resolution,
                prompt=prompt,
                reference_count=len(reference_items),
                reference_sizes=reference_sizes,
            )
            reference_urls = self._resolve_reference_urls(reference_items)
            model_meta = GENERATION_MODEL_META.get(normalized_model, {})
            model_type = model_meta.get("type", "text_to_image")

            if model_type in {"image_to_image", "edit"} and not reference_urls:
                raise RuntimeError("Для выбранной модели нужен референс изображения")

            if normalized_model == "gpt4o-image":
                if reference_urls:
                    raise RuntimeError("Модель GPT‑4o Image не поддерживает референс в этом режиме")
                return self._kie_generate_4o_image(prompt)
            return self._kie_generate_generic_model(
                normalized_model,
                prompt,
                reference_urls=reference_urls,
            )

    def _uses_fal_generation(self):
        return any(is_fal_generation_model(model) for model in self._generation_models_in_use())

    def _uses_kie_generation(self):
        return any(not is_fal_generation_model(model) for model in self._generation_models_in_use())

    def _generation_models_in_use(self):
        entries = self.generated_prompts or []
        if not entries:
            return {str(self.text_generation_model or "").strip()}
        models = set()
        for entry in entries:
            references = split_references(entry.get("references", [])) if isinstance(entry, dict) else []
            model = self.reference_generation_model if references else self.text_generation_model
            models.add(str(model or "").strip())
        return models

    def _fal_generate_image(self, prompt, model_id):
        self._ensure_fal_cost_confirmed()
        client = FalClient(
            FalConfig(
                api_key=self.fal_api_key,
                model_id=model_id,
                timeout_seconds=max(10.0, float(self.timeout)),
                before_paid_submit=lambda: self._admit_paid_submission(
                    "fal", "POST"
                ),
            )
        )
        ratio, resolution = self._get_generation_profile(False)
        payload = fal_generation_payload(model_id, str(prompt or ""), ratio, resolution)
        input_fingerprint = self._paid_task_fingerprint(payload)
        request = ProviderTaskRequest(
            provider_id="fal",
            operation="generation",
            model_id=model_id,
            input_payload=payload,
        )
        request_id = ""
        try:
            pending_task = self._claim_pending_task(
                self.fal_task_journal,
                "generation",
                model_id,
                self._claimed_fal_task_ids,
                input_fingerprint=input_fingerprint,
            )
            if pending_task is not None:
                request_id = pending_task.request_id
                task_operation = pending_task.operation
                lifecycle_urls = {
                    "status_url": pending_task.status_url,
                    "response_url": pending_task.response_url,
                    "cancel_url": pending_task.cancel_url,
                }
                self.progress.emit(f"  Продолжаем Fal.ai Request ID: {request_id}")
            else:
                submitted = client.submit_task(request)
                request_id = str(submitted.get("request_id") or "").strip()
                task_operation = "generation"
                lifecycle_urls = fal_lifecycle_urls(submitted, request_id)
                self._record_fal_task(
                    request_id,
                    task_operation,
                    model_id,
                    "queued",
                    input_fingerprint=input_fingerprint,
                    **lifecycle_urls,
                )
                self.progress.emit(f"  Fal.ai Request ID: {request_id}")
                self._emit_diagnostic(
                    "provider_task_submitted",
                    provider="fal",
                    model=model_id,
                    task=request_id,
                    provider_state="queued",
                )
            completed = client.wait_for_result(
                request_id,
                timeout_seconds=float(self.generation_wait_timeout),
                poll_interval_seconds=float(self.status_poll_interval),
                is_cancelled=lambda: not self.is_running,
                on_status=lambda status: self._record_fal_poll_status(
                    request_id,
                    task_operation,
                    model_id,
                    status,
                    input_fingerprint=input_fingerprint,
                ),
                **lifecycle_urls,
            )
        except (FalProviderError, TimeoutError, OSError) as error:
            self._emit_fal_task_failure(
                request_id,
                model_id,
                error,
            )
            raise
        self._ensure_running()
        try:
            result_url = fal_image_url(completed.get("result"))
        except FalProviderError as error:
            self._emit_fal_task_failure(request_id, model_id, error)
            self._record_fal_task(
                request_id,
                task_operation,
                model_id,
                "failed",
                input_fingerprint=input_fingerprint,
            )
            raise
        self._emit_fal_task_succeeded(
            request_id,
            model_id,
            completed.get("status"),
        )
        self._record_fal_task(
            request_id,
            task_operation,
            model_id,
            "result_ready",
            input_fingerprint=input_fingerprint,
        )
        self._register_paid_result_ready("fal", request_id)
        return result_url

    def _ensure_fal_cost_confirmed(self):
        # Legacy test/runtime entry points may omit this field. The main UI
        # adds it only after the user confirms the current Fal.ai price.
        if "fal_cost_confirmed" in self.settings and not bool(
            self.settings.get("fal_cost_confirmed")
        ):
            raise RuntimeError(
                "Запуск Fal.ai остановлен: подтвердите актуальную цену модели перед запуском"
            )

    def _normalize_model_ratio(self, model_name, ratio, has_references=False):
        allowed = set(ratios_for_mode(model_name, has_references))
        if ratio in allowed or not allowed:
            return ratio
        fallback_ratio = "1:1" if "1:1" in allowed else next(iter(sorted(allowed)))
        self.progress.emit(
            f"  Соотношение {ratio} не подтверждено для {model_name}. Используем {fallback_ratio}."
        )
        return fallback_ratio

    def _reduce_ratio(self, left, right):
        a = int(left)
        b = int(right)
        if a <= 0 or b <= 0:
            return ""
        g = math.gcd(a, b) or 1
        return f"{a // g}:{b // g}"

    def _extract_ratio_from_prompt(self, prompt):
        text = str(prompt or "")
        # Supports only: 2:3, 2 x 3, 2Ñ…3.
        match = PROMPT_RATIO_PATTERN.search(text)
        if not match:
            return ""
        return self._reduce_ratio(match.group(1), match.group(2))

    def _normalize_model_quality(self, model_name, quality="medium"):
        allowed = self._get_model_capabilities(model_name)["qualities"]
        if quality in allowed or not allowed:
            return quality
        return "medium"

    def _build_documented_model_input(self, model_name, prompt, reference_urls=None):
        reference_urls = reference_urls or []
        ratio_setting, resolution_setting = self._get_generation_profile(bool(reference_urls))
        if ratio_setting == "auto":
            prompt_ratio = self._extract_ratio_from_prompt(prompt)
            if prompt_ratio:
                ratio_setting = prompt_ratio
                self.progress.emit(f"  Пропорция из промпта: {prompt_ratio} (UI=auto)")
        ratio = self._normalize_model_ratio(
            model_name,
            ratio_setting,
            has_references=bool(reference_urls),
        )
        quality = self._normalize_model_quality(model_name)
        capabilities = self._get_model_capabilities(model_name)
        allowed_resolutions = capabilities["resolutions"]
        resolution = resolution_setting if resolution_setting in allowed_resolutions else ("1K" if "1K" in allowed_resolutions else (next(iter(sorted(allowed_resolutions))) if allowed_resolutions else "1K"))

        if model_name == "gpt-image/1.5-text-to-image":
            return {"prompt": prompt, "aspect_ratio": ratio, "quality": quality}

        if model_name == "gpt-image/1.5-image-to-image":
            return {
                "prompt": prompt,
                "input_urls": list(reference_urls),
                "aspect_ratio": ratio,
                "quality": quality,
            }

        if model_name == "gpt-image-2":
            payload = {
                "prompt": prompt,
                "aspect_ratio": ratio,
                "resolution": resolution,
            }
            if reference_urls:
                payload["input_urls"] = list(reference_urls)
            return payload

        if model_name == "nano-banana-2":
            payload = {
                "prompt": prompt,
                "aspect_ratio": ratio,
                "resolution": resolution,
                "output_format": "png",
            }
            if reference_urls:
                payload["image_input"] = list(reference_urls)
            return payload

        if model_name == "nano-banana-pro":
            payload = {
                "prompt": prompt,
                "aspect_ratio": ratio,
                "resolution": resolution,
                "output_format": "png",
            }
            if reference_urls:
                payload["image_input"] = list(reference_urls)
            return payload

        if model_name in {"flux-2/pro-text-to-image", "flux-2/flex-text-to-image"}:
            return {"prompt": prompt, "aspect_ratio": ratio, "resolution": resolution}

        if model_name in {"flux-2/pro-image-to-image", "flux-2/flex-image-to-image"}:
            return {
                "prompt": prompt,
                "input_urls": list(reference_urls),
                "aspect_ratio": ratio,
                "resolution": resolution,
            }

        if model_name == "google/nano-banana":
            return {"prompt": prompt, "image_size": ratio}

        if model_name == "google/nano-banana-edit":
            return {"prompt": prompt, "image_urls": list(reference_urls), "image_size": ratio}

        if model_name == "qwen/text-to-image":
            return {"prompt": prompt, "image_size": self._ratio_to_qwen_image_size(ratio), "output_format": "png", "nsfw_checker": True}

        if model_name == "qwen/image-to-image":
            return {"prompt": prompt, "image_url": reference_urls[0]}

        if model_name == "qwen-image-2":
            payload = {
                "prompt": prompt,
                "image_size": self._ratio_to_qwen_image_size(ratio),
                "output_format": "png",
                "nsfw_checker": True,
            }
            if reference_urls:
                payload["image_url"] = reference_urls[0]
            return payload

        if model_name == "qwen/image-edit":
            return {"prompt": prompt, "image_url": reference_urls[0]}

        if model_name in {"grok-imagine/text-to-image", "google/imagen4", "google/imagen4-fast", "google/imagen4-ultra"}:
            return {"prompt": prompt, "aspect_ratio": ratio}

        if model_name == "grok-imagine/image-to-image":
            return {"prompt": prompt, "image_urls": list(reference_urls), "aspect_ratio": ratio}

        if model_name == "z-image":
            return {"prompt": prompt, "aspect_ratio": ratio}

        return {"prompt": prompt, "size": ratio}

    def _select_generation_model(self, reference_urls):
        has_references = bool(reference_urls)
        preferred_model = self.reference_generation_model if has_references else self.text_generation_model
        normalized = self._normalize_generation_model(preferred_model)
        model_meta = GENERATION_MODEL_META.get(normalized, {})
        model_type = model_meta.get("type")

        reference_compatible = self._get_model_capabilities(normalized)["reference_compatible_text"]
        if has_references and (model_type in {"image_to_image", "edit"} or reference_compatible):
            return normalized
        if not has_references and model_type == "text_to_image":
            return normalized

        fallback = self._default_generation_model("image_to_image" if has_references else "text_to_image")
        self.progress.emit(
            (
                f"  Выбранная модель '{normalized}' не подходит для текущего режима. "
                f"Используем '{fallback}'."
            )
        )
        return fallback

    def _default_generation_model(self, required_type):
        for entry in GENERATION_MODELS:
            model_id = entry.get("id")
            if model_id not in VISIBLE_GENERATION_MODEL_IDS:
                continue
            if is_fal_generation_model(model_id):
                continue
            if entry.get("type") == required_type and model_id in SUPPORTED_GENERATION_MODEL_IDS:
                return model_id
        return "gpt-image/1.5-text-to-image"

    def _normalize_generation_model(self, model_name):
        model = (model_name or "").strip()
        if not model:
            self.progress.emit("  Модель не указана. Используем gpt-image/1.5-text-to-image.")
            return "gpt-image/1.5-text-to-image"

        if model in {"gpt4o-image", "gpt-image-1", "gpt-image-1.5"}:
            return "gpt-image/1.5-text-to-image"

        if model == "flux-kontext":
            return "flux-kontext"

        if model in {"z-image", "zai-org/z-image"}:
            return "z-image"

        if model in {
            "google/nano-banana",
            "google/nano-banana-edit",
            "gpt-image-2",
            "gpt-image-2-text-to-image",
            "gpt-image-2-image-to-image",
            "nano-banana-2",
            "nano-banana-pro",
            "qwen-image-2",
            "google/imagen4",
            "google/imagen4-fast",
            "google/imagen4-ultra",
            "flux-2/flex-text-to-image",
            "flux-2/pro-text-to-image",
        }:
            if model in {"gpt-image-2-text-to-image", "gpt-image-2-image-to-image"}:
                return "gpt-image-2"
            return model

        # Возвращаем исходное имя, чтобы поддерживать новые модели без обновления кода.
        self.progress.emit(f"  Используется пользовательская модель: {model}")
        return model

    def _kie_generate_4o_image(self, prompt):
        ratio, _ = self._get_generation_profile(False)
        payload = {"prompt": prompt, "size": ratio}
        input_fingerprint = self._paid_task_fingerprint(payload)
        pending_task = self._claim_pending_task(
            self.kie_task_journal,
            "gpt4o_generation",
            "gpt4o-image",
            self._claimed_kie_task_ids,
            input_fingerprint=input_fingerprint,
        )
        if pending_task is not None:
            self.progress.emit(f"  Продолжаем 4o Task ID: {pending_task.request_id}")
            return self._kie_wait_4o_result(pending_task.request_id)
        self._wait_for_generation_launch_slot()
        headers = self._kie_headers()
        headers["Content-Type"] = "application/json"
        result = self._request_json(
            "https://api.kie.ai/api/v1/gpt4o-image/generate",
            method="POST",
            payload=payload,
            headers=headers,
            timeout=max(30, self.timeout),
        )
        if int(result.get("code", 0)) != 200:
            raise RuntimeError(f"KIE 4o Image rejected the request (code {result.get('code', '-')})")

        task_id = (result.get("data") or {}).get("taskId")
        if not task_id:
            raise RuntimeError("4o Image не вернул taskId")
        self._record_kie_task(
            task_id,
            operation="gpt4o_generation",
            model_id="gpt4o-image",
            status="queued",
            input_fingerprint=input_fingerprint,
        )
        self.progress.emit(f"  4o Task ID: {task_id}")
        return self._kie_wait_4o_result(task_id)

    def _kie_generate_generic_model(self, model_name, prompt, reference_urls=None):
        reference_urls = reference_urls or []
        payload = self._build_documented_model_input(model_name, prompt, reference_urls)
        input_fingerprint = self._paid_task_fingerprint(payload)
        task_model = resolve_kie_generation_model(model_name, bool(reference_urls))
        operation = str(
            getattr(self._diagnostic_context, "stage", "") or "generation"
        )
        pending_task = self._claim_pending_task(
            self.kie_task_journal,
            operation,
            task_model,
            self._claimed_kie_task_ids,
            input_fingerprint=input_fingerprint,
        )
        task_id = (
            pending_task.request_id
            if pending_task is not None
            else self._kie_create_task(task_model, payload)
        )
        if pending_task is not None:
            self.progress.emit(f"  Продолжаем KIE Task ID: {task_id}")
        self.progress.emit(f"  Task ID: {task_id}")
        return self._kie_wait_result(task_id)

    def _build_reference_input_variants(self, model_name, prompt, reference_urls, ratio, legacy_size):
        del ratio, legacy_size
        payload = self._build_documented_model_input(model_name, prompt, reference_urls)
        return [payload]

    def _build_reference_probe_variants(self, model_name, prompt, sample_image_url, ratio, legacy_size):
        reference_variants = self._build_reference_input_variants(
            model_name,
            prompt,
            [sample_image_url],
            ratio,
            legacy_size,
        )
        task_model = resolve_kie_generation_model(model_name, True)
        return [{"model": task_model, "input": payload} for payload in reference_variants]

    def _build_text_probe_variants(self, model_name, prompt, ratio, legacy_size):
        payload = self._build_documented_model_input(model_name, prompt, [])
        task_model = resolve_kie_generation_model(model_name, False)
        return [{"model": task_model, "input": payload}]

    def _probe_model_with_ratio(self, raw_model, ratio, headers, timeout, reference_urls=None):
        prompt = "simple test image"
        legacy_size = self._ratio_to_legacy_size(ratio)
        sample_image_url = MODEL_PROBE_SAMPLE_IMAGE_URL
        probe_timeout = min(max(8, timeout), 20)
        probe_reference_urls = list(reference_urls or [])

        model = self._normalize_generation_model(raw_model)
        if model in {"gpt4o-image", "gpt-image-1", "gpt-image-1.5"}:
            model = "gpt4o-image"

        if not model:
            model = "gpt4o-image"

        model_type = (GENERATION_MODEL_META.get(model) or {}).get("type", "text_to_image")

        if model == "gpt4o-image":
            url = "https://api.kie.ai/api/v1/gpt4o-image/generate"
            payload_variants = [
                {"prompt": prompt, "size": legacy_size},
                {"prompt": prompt, "size": ratio},
                {"prompt": prompt, "aspectRatio": ratio},
                {"prompt": prompt, "aspect_ratio": ratio},
            ]
        else:
            url = "https://api.kie.ai/api/v1/jobs/createTask"
            test_model = model
            if probe_reference_urls and (model_type in {"image_to_image", "edit"} or self._get_model_capabilities(model)["reference_compatible_text"]):
                payload_variants = self._build_reference_probe_variants(
                    test_model,
                    prompt,
                    probe_reference_urls[0] or sample_image_url,
                    ratio,
                    legacy_size,
                )
            elif model_type == "text_to_image":
                payload_variants = self._build_text_probe_variants(
                    test_model,
                    prompt,
                    ratio,
                    legacy_size,
                )
            else:
                payload_variants = self._build_reference_probe_variants(
                    test_model,
                    prompt,
                    sample_image_url,
                    ratio,
                    legacy_size,
                )

        payload = payload_variants[0]
        try:
            req = request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            self._protect_secret_headers_from_redirects(req)
            with open_url_secure(req, timeout=probe_timeout, context=build_ssl_context()) as resp:
                raw = read_response_limited(resp, MAX_API_JSON_RESPONSE_BYTES)
            data = json.loads(raw.decode("utf-8"))
            response_code = int(data.get("code", 0))
            if response_code == 200:
                task_id = (data.get("data") or {}).get("taskId", "-")
                return True, "OK", task_id
            provider_message = data.get("msg") or data.get("message") or ""
            if response_code in {400, 422} and is_schema_required_error_message(provider_message):
                return False, "schema_required", "-"
            return False, f"KIE probe rejected the request (code {data.get('code', '-')})", "-"
        except urlerror.HTTPError as error:
            if error.code in {400, 422}:
                try:
                    raw = read_response_limited(error, MAX_API_JSON_RESPONSE_BYTES)
                    data = json.loads(raw.decode("utf-8"))
                    provider_message = data.get("msg") or data.get("message") or ""
                    if is_schema_required_error_message(provider_message):
                        return False, "schema_required", "-"
                except Exception:
                    pass
            return False, f"HTTP {error.code}", "-"
        except Exception as error:
            return False, self._safe_error_text(error), "-"

    def _normalize_ratio(self, value):
        raw = (value or "").strip()
        allowed = {
            "auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
            "1:2", "2:1", "1:3", "3:1", "9:16", "16:9", "9:21", "21:9",
            "1:4", "4:1", "1:8", "8:1",
        }
        legacy_map = {
            "1024x1024": "1:1",
            "1024x1536": "3:4",
            "1536x1024": "4:3",
        }
        if raw in allowed:
            return raw
        if raw in legacy_map:
            return legacy_map[raw]
        return "1:1"

    def _ratio_to_legacy_size(self, ratio):
        return {
            "1:1": "1024x1024",
            "4:3": "1536x1024",
            "3:4": "1024x1536",
            "16:9": "1536x1024",
            "9:16": "1024x1536",
        }.get(ratio, "1024x1024")

    def _ratio_to_qwen_image_size(self, ratio):
        return {
            "1:1": "1:1",
            "2:3": "2:3",
            "3:2": "3:2",
            "3:4": "3:4",
            "4:3": "4:3",
            "9:16": "9:16",
            "16:9": "16:9",
            "21:9": "21:9",
        }.get(ratio, "1:1")

    def _kie_wait_4o_result(self, task_id):
        timeout_sec = self.generation_wait_timeout
        deadline = time.time() + timeout_sec
        headers = self._kie_headers()
        started = time.monotonic()
        poll_attempt = 0
        while time.time() < deadline:
            self._ensure_running()
            poll_attempt += 1

            url = f"https://api.kie.ai/api/v1/gpt4o-image/record-info?{parse.urlencode({'taskId': task_id})}"
            try:
                result = self._request_json(url, method="GET", headers=headers, timeout=30)
            except Exception as error:
                http_status = getattr(self._diagnostic_context, "last_http_status", None)
                can_defer = (
                    self._has_pending_kie_task(task_id)
                    and not isinstance(error, (ProcessingCancelled, ResponseLimitError))
                    and http_status not in {400, 401, 402, 403, 404}
                )
                self._emit_diagnostic(
                    "provider_task_recovery_deferred"
                    if can_defer
                    else "provider_task_failed",
                    provider="kie",
                    task=task_id,
                    http_status=http_status,
                    error_message=self._safe_error_text(error),
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
                if not can_defer:
                    raise
                self._record_kie_task(task_id, status="poll_deferred")
                time.sleep(self.status_poll_interval)
                continue
            if int(result.get("code", 0)) != 200:
                raise RuntimeError(f"KIE 4o status failed (code {result.get('code', '-')})")

            data = result.get("data") or {}
            status = str(data.get("status", "")).upper()
            self._emit_diagnostic(
                "provider_task_polled",
                provider="kie",
                task=task_id,
                provider_state=status or "UNKNOWN",
                poll_attempt=poll_attempt,
                http_status=getattr(self._diagnostic_context, "last_http_status", 200),
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            self.progress.emit(f"  4o статус: {status}")
            self._record_kie_task(task_id, status=status.lower() or "unknown")
            if status == "SUCCESS":
                urls = ((data.get("response") or {}).get("resultUrls") or [])
                if urls:
                    self._emit_diagnostic(
                        "provider_task_succeeded",
                        provider="kie",
                        task=task_id,
                        provider_state=status,
                        result_count=len(urls),
                        elapsed_ms=round((time.monotonic() - started) * 1000),
                    )
                    self._record_kie_task(task_id, status="result_ready")
                    self._register_paid_result_ready("kie", task_id)
                    return urls[0]
                raise RuntimeError("4o Image не вернул resultUrls")
            if status in {"FAILED", "FAIL", "ERROR"}:
                fail_message = self._safe_error_text(
                    data.get("errorMessage") or "4o Image вернул ошибку"
                )
                self._emit_diagnostic(
                    "provider_task_failed",
                    provider="kie",
                    task=task_id,
                    provider_state=status,
                    error_message=fail_message,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
                self._record_kie_task(task_id, status="failed")
                raise RuntimeError(fail_message)
            time.sleep(self.status_poll_interval)
        self._emit_diagnostic(
            "provider_task_failed",
            provider="kie",
            task=task_id,
            provider_state="timeout",
            error_code="timeout",
            error_message="Превышено время ожидания 4o Image",
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        self._record_kie_task(task_id, status="timeout")
        raise TimeoutError("Превышено время ожидания 4o Image")

    def _kie_wait_result(self, task_id):
        timeout_sec = self.generation_wait_timeout
        deadline = time.time() + timeout_sec
        headers = self._kie_headers()
        poll_attempt = 0
        started = time.monotonic()
        while time.time() < deadline:
            self._ensure_running()
            poll_attempt += 1

            url = f"https://api.kie.ai/api/v1/jobs/recordInfo?{parse.urlencode({'taskId': task_id})}"
            try:
                result = self._request_json(url, method="GET", headers=headers, timeout=30)
            except Exception as error:
                http_status = getattr(self._diagnostic_context, "last_http_status", None)
                can_defer = (
                    self._has_pending_kie_task(task_id)
                    and not isinstance(error, (ProcessingCancelled, ResponseLimitError))
                    and http_status not in {400, 401, 402, 403, 404}
                )
                self._emit_diagnostic(
                    "provider_task_recovery_deferred"
                    if can_defer
                    else "provider_task_failed",
                    provider="kie",
                    task=task_id,
                    http_status=http_status,
                    error_message=self._safe_error_text(error),
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
                if not can_defer:
                    raise
                self._record_kie_task(task_id, status="poll_deferred")
                time.sleep(self.status_poll_interval)
                continue
            if int(result.get("code", 0)) != 200:
                raise RuntimeError(f"KIE status failed (code {result.get('code', '-')})")

            data = result.get("data") or {}
            state = str(data.get("state", "")).lower()
            self._emit_diagnostic(
                "provider_task_polled",
                provider="kie",
                task=task_id,
                provider_state=state or "unknown",
                poll_attempt=poll_attempt,
                http_status=getattr(self._diagnostic_context, "last_http_status", 200),
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            self.progress.emit(f"  Статус: {state}")
            self._record_kie_task(task_id, status=state or "unknown")
            if state in {"success", "succeeded"}:
                result_url = self._extract_result_url(data.get("resultJson"))
                self._emit_diagnostic(
                    "provider_task_succeeded",
                    provider="kie",
                    task=task_id,
                    provider_state=state,
                    result_count=count_provider_results(data.get("resultJson")),
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
                self._record_kie_task(task_id, status="result_ready")
                self._register_paid_result_ready("kie", task_id)
                return result_url
            if state in {"fail", "failed", "error"}:
                error_code = data.get("failCode") or data.get("errorCode") or "unknown"
                fail_message = self._safe_error_text(data.get("failMsg") or "KIE вернул fail")
                self._emit_diagnostic(
                    "provider_task_failed",
                    provider="kie",
                    task=task_id,
                    provider_state=state,
                    error_code=error_code,
                    error_message=fail_message,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
                self._record_kie_task(task_id, status="failed")
                raise RuntimeError(
                    f"KIE task failed [taskId={task_id}; errorCode={error_code}; "
                    f"message={fail_message}]"
                )
            time.sleep(self.status_poll_interval)
        self._emit_diagnostic(
            "provider_task_failed",
            provider="kie",
            task=task_id,
            provider_state="timeout",
            error_code="timeout",
            error_message="Превышено время ожидания результата KIE",
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        self._record_kie_task(task_id, status="timeout")
        raise TimeoutError("Превышено время ожидания результата KIE")

    def _extract_result_url(self, result_json_raw):
        if not result_json_raw:
            raise RuntimeError("KIE не вернул resultJson")

        parsed = result_json_raw
        if isinstance(result_json_raw, str):
            parsed = json.loads(result_json_raw)

        if isinstance(parsed, dict):
            result_urls = parsed.get("resultUrls")
            if isinstance(result_urls, list) and result_urls:
                return result_urls[0]
            output = parsed.get("output")
            if isinstance(output, dict) and output.get("mediaUrl"):
                return output["mediaUrl"]

        raise RuntimeError("Не удалось извлечь URL результата из resultJson")

    def _download_file(self, url, output_path):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        }

        parsed_url = validate_https_url(url, "Provider download URL")
        host = (parsed_url.hostname or "").lower().rstrip(".")
        # Некоторые CDN KIE/Redpanda отдают 403 (Cloudflare 1010) без auth-заголовков.
        trusted_kie_host = parsed_url.scheme.lower() == "https" and (
            host in {"kie.ai", "redpandaai.co"}
            or host.endswith((".kie.ai", ".redpandaai.co"))
        )
        if trusted_kie_host:
            headers["Authorization"] = f"Bearer {self.kie_api_key}"
            headers["x-api-key"] = self.kie_api_key
            headers["Referer"] = "https://docs.kie.ai/"

        last_error = None
        attempts = [headers, {"User-Agent": headers["User-Agent"], "Accept": "*/*"}, {}]
        started = time.monotonic()
        for idx, h in enumerate(attempts, start=1):
            try:
                self._ensure_running()
                req = request.Request(url, headers=h, method="GET")
                content = self._request_with_retries(req, timeout=60)
                self._ensure_running()
                if output_path.lower().endswith(".png"):
                    self._save_png_from_any_image_bytes(content, output_path)
                else:
                    with open(output_path, "wb") as f:
                        f.write(content)
                if self.export_300_dpi and output_path.lower().endswith(".png") and "output" in output_path.lower():
                    self._set_png_dpi(output_path, dpi=300)
                self._emit_diagnostic(
                    "provider_result_downloaded",
                    provider="kie" if trusted_kie_host else "external",
                    result_index=1,
                    http_status=getattr(self._diagnostic_context, "last_http_status", 200),
                    downloaded_bytes=len(content),
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                    **inspect_diagnostic_image(output_path),
                )
                return
            except ProcessingCancelled:
                raise
            except Exception as e:
                last_error = e
                self.progress.emit(
                    f"  Download попытка {idx} не удалась: {self._safe_error_text(e)}"
                )

        self._emit_diagnostic(
            "stage_finished",
            provider="kie" if trusted_kie_host else "external",
            outcome="failed",
            http_status=getattr(self._diagnostic_context, "last_http_status", None),
            error_message=self._safe_error_text(last_error),
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        raise RuntimeError(
            f"Не удалось скачать файл по URL ({host}): {self._safe_error_text(last_error)}"
        )

    def _save_png_from_any_image_bytes(self, content, output_path):
        if len(content) > MAX_API_RESPONSE_BYTES:
            raise RuntimeError("Provider image exceeds size limit")
        try:
            with Image.open(BytesIO(content)) as img:
                if getattr(img, "n_frames", 1) != 1:
                    raise RuntimeError("Provider image must be single-frame")
                if max(img.size) > MAX_PROVIDER_IMAGE_DIMENSION:
                    raise RuntimeError("Provider image exceeds dimension limit")
                if img.width * img.height > MAX_PROVIDER_IMAGE_PIXELS:
                    raise RuntimeError("Provider image exceeds pixel limit")
                img.load()
                self._ensure_running()
                if img.format == "PNG":
                    with open(output_path, "wb") as output_file:
                        output_file.write(content)
                    if self.export_300_dpi:
                        self._set_png_dpi(output_path, dpi=300)
                    return
                self._save_image_object_as_png(img, output_path)
            self.progress.emit("  Формат ответа не PNG: выполнена конвертация в PNG")
            return
        except ProcessingCancelled:
            raise
        except RuntimeError:
            raise
        except Exception as error:
            raise RuntimeError("Сервер вернул невалидный контент вместо изображения") from error

    def _set_png_dpi(self, file_path, dpi=300):
        try:
            with Image.open(file_path) as img:
                if img.format != "PNG":
                    return
                img.save(
                    file_path,
                    format="PNG",
                    **self._get_png_save_kwargs(img, dpi_override=dpi),
                )
        except Exception as e:
            raise RuntimeError(
                f"Не удалось установить DPI для {os.path.basename(file_path)}: "
                f"{self._safe_error_text(e, limit=200)}"
            ) from e

    @staticmethod
    def _verify_png_dpi(file_path, dpi=300):
        try:
            with Image.open(file_path) as image:
                actual = image.info.get("dpi")
                if (
                    not isinstance(actual, (tuple, list))
                    or len(actual) < 2
                    or abs(float(actual[0]) - dpi) > 1
                    or abs(float(actual[1]) - dpi) > 1
                ):
                    raise ValueError("DPI metadata does not match")
        except Exception as error:
            raise RuntimeError(
                f"Не удалось подтвердить DPI {dpi} для итогового PNG: "
                f"{safe_error_text(error, limit=200)}"
            ) from error


class PromptTableWidget(QTableWidget):
    bulkTextPasted = pyqtSignal(str)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            text = QApplication.clipboard().text()
            if text:
                self.bulkTextPasted.emit(text)
                event.accept()
                return
        super().keyPressEvent(event)


class CsvImportDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._headers = []
        self._rows = []
        self._entries = []
        self._last_error = ""
        self._setup_ui()
        self._reload_data()

    def _setup_ui(self):
        self.setWindowTitle("Импорт промптов из CSV")
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.delimiter_combo = QComboBox()
        self.delimiter_combo.addItem("Авто", "auto")
        self.delimiter_combo.addItem(",", ",")
        self.delimiter_combo.addItem(";", ";")
        self.delimiter_combo.addItem("Таб", "\t")
        self.delimiter_combo.addItem("|", "|")

        self.header_checkbox = QCheckBox("Первая строка — заголовки")
        self.header_checkbox.setChecked(True)

        self.column_combo = QComboBox()
        self.references_column_combo = QComboBox()

        form.addRow("Разделитель:", self.delimiter_combo)
        form.addRow("Колонка с промптом:", self.column_combo)
        form.addRow("Колонка с референсами:", self.references_column_combo)
        form.addRow("", self.header_checkbox)
        layout.addLayout(form)

        self.info_label = QLabel("")
        layout.addWidget(self.info_label)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Здесь будет предпросмотр промптов")
        layout.addWidget(self.preview_text)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("Импортировать")
        layout.addWidget(self.button_box)

        self.delimiter_combo.currentIndexChanged.connect(self._reload_data)
        self.header_checkbox.toggled.connect(self._reload_data)
        self.column_combo.currentIndexChanged.connect(self._refresh_preview)
        self.references_column_combo.currentIndexChanged.connect(self._refresh_preview)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def _read_csv_text(self):
        encodings = ["utf-8-sig", "cp1251", "utf-8"]
        last_error = None
        for enc in encodings:
            try:
                with open(self.file_path, "r", encoding=enc, newline="") as f:
                    return f.read()
            except Exception as e:
                last_error = e
        raise RuntimeError(f"Не удалось прочитать CSV: {last_error}")

    def _detect_delimiter(self, sample_text):
        selected = self.delimiter_combo.currentData()
        if selected and selected != "auto":
            return selected
        try:
            sniffed = csv.Sniffer().sniff(sample_text[:4096], delimiters=[",", ";", "\t", "|"])
            return sniffed.delimiter
        except Exception:
            return ","

    def _parse_rows(self, text, delimiter):
        reader = csv.reader(StringIO(text), delimiter=delimiter)
        rows = [row for row in reader if any(str(cell).strip() for cell in row)]
        if not rows:
            raise RuntimeError("CSV-файл пуст или не содержит данных")
        return rows

    def _reload_data(self):
        prev_column = self.column_combo.currentData()
        prev_references_column = self.references_column_combo.currentData()
        self._entries = []
        self._last_error = ""
        try:
            text = self._read_csv_text()
            delimiter = self._detect_delimiter(text)
            rows = self._parse_rows(text, delimiter)

            has_header = self.header_checkbox.isChecked()
            if has_header:
                headers = [str(h).strip() or f"Колонка {i + 1}" for i, h in enumerate(rows[0])]
                data_rows = rows[1:]
            else:
                max_cols = max(len(r) for r in rows)
                headers = [f"Колонка {i + 1}" for i in range(max_cols)]
                data_rows = rows

            max_cols = max(len(headers), max((len(r) for r in data_rows), default=0))
            headers = headers + [f"Колонка {i + 1}" for i in range(len(headers), max_cols)]
            normalized_rows = [r + [""] * (max_cols - len(r)) for r in data_rows]

            self._headers = headers
            self._rows = normalized_rows

            self.column_combo.blockSignals(True)
            self.column_combo.clear()
            for index, name in enumerate(self._headers):
                self.column_combo.addItem(name, index)
            target_index = prev_column if isinstance(prev_column, int) and 0 <= prev_column < len(self._headers) else 0
            self.column_combo.setCurrentIndex(target_index)
            self.column_combo.blockSignals(False)

            self.references_column_combo.blockSignals(True)
            self.references_column_combo.clear()
            self.references_column_combo.addItem("Без референсов", -1)
            for index, name in enumerate(self._headers):
                self.references_column_combo.addItem(name, index)
            if isinstance(prev_references_column, int) and -1 <= prev_references_column < len(self._headers):
                ref_index = self.references_column_combo.findData(prev_references_column)
                self.references_column_combo.setCurrentIndex(ref_index if ref_index >= 0 else 0)
            else:
                self.references_column_combo.setCurrentIndex(0)
            self.references_column_combo.blockSignals(False)

            selected_col = self.column_combo.currentData()
            selected_refs_col = self.references_column_combo.currentData()
            self._entries = self._build_entries(selected_col, selected_refs_col)
            delim_name = "TAB" if delimiter == "\t" else delimiter
            self.info_label.setText(
                f"Строк данных: {len(self._rows)} | Распознано записей: {len(self._entries)} | Разделитель: {delim_name}"
            )
            self._refresh_preview()
        except Exception as e:
            self._headers = []
            self._rows = []
            self._last_error = str(e)
            self.info_label.setText(f"Ошибка импорта: {self._last_error}")
            self.preview_text.setPlainText("")

    def _build_entries(self, prompt_column_index, references_column_index):
        if not isinstance(prompt_column_index, int):
            return []
        entries = []
        for row in self._rows:
            if prompt_column_index >= len(row):
                continue
            prompt_text = str(row[prompt_column_index]).strip()
            references_text = ""
            if isinstance(references_column_index, int) and 0 <= references_column_index < len(row):
                references_text = str(row[references_column_index]).strip()
            references = split_references(references_text)
            if prompt_text or references:
                entries.append({"prompt": prompt_text, "references": references})
        return entries

    def _refresh_preview(self):
        if self._last_error:
            self.preview_text.setPlainText("")
            return
        selected_col = self.column_combo.currentData()
        selected_refs_col = self.references_column_combo.currentData()
        self._entries = self._build_entries(selected_col, selected_refs_col)
        preview_items = self._entries[:8]
        if not preview_items:
            self.preview_text.setPlainText("Нет записей для выбранных колонок")
            return
        parts = []
        for idx, entry in enumerate(preview_items, start=1):
            prompt_text = entry.get("prompt", "")
            references_text = join_references(entry.get("references", []))
            detail_lines = [f"{idx}. {prompt_text}"]
            if references_text:
                detail_lines.append(f"Референсы: {references_text}")
            parts.append("\n".join(detail_lines))
        self.preview_text.setPlainText("\n\n──────────\n\n".join(parts))

    def get_entries(self):
        result = []
        for entry in self._entries:
            prompt_text = str(entry.get("prompt", "")).strip()
            references = split_references(entry.get("references", []))
            if prompt_text or references:
                result.append({"prompt": prompt_text, "references": references})
        return result


class PromptReferencesDialog(QDialog):
    def __init__(self, prompt_text, references, parent=None, refs_only=False):
        super().__init__(parent)
        self.refs_only = refs_only
        self._source_prompt = str(prompt_text or "")
        self.setWindowTitle("Референсы промпта" if refs_only else "Редактирование промпта и референсов")
        self.resize(760, 520)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(str(prompt_text or ""))

        self.references_list = QListWidget()
        self.references_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.references_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.references_list.setMovement(QListWidget.Movement.Static)
        self.references_list.setWordWrap(True)
        self.references_list.setSpacing(8)
        self.references_list.setIconSize(QSize(96, 96))
        self.references_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.references_list.setStyleSheet(
            "QListWidget::item {border: 2px solid transparent; border-radius: 8px; padding: 4px;}"
            "QListWidget::item:selected {border: 2px solid #14b8a6; background: rgba(20, 184, 166, 0.08);}"
            "QListWidget::item:selected:!active {border: 2px solid #14b8a6; background: rgba(20, 184, 166, 0.08);}"
        )
        for ref in split_references(references):
            self._append_reference_item(ref)

        main_layout = QVBoxLayout(self)
        if not self.refs_only:
            main_layout.addWidget(QLabel("Промпт:"))
            main_layout.addWidget(self.prompt_edit)

        refs_header = QHBoxLayout()
        refs_header.addWidget(QLabel("Референсы (до 5):"))
        refs_header.addStretch()
        main_layout.addLayout(refs_header)
        main_layout.addWidget(self.references_list)

        buttons_row = QHBoxLayout()
        self.btn_add_files = QPushButton("Добавить файлы")
        self.btn_remove_selected = QPushButton("Удалить выбранный")
        self.btn_clear_all = QPushButton("Очистить все")
        buttons_row.addWidget(self.btn_add_files)
        buttons_row.addWidget(self.btn_remove_selected)
        buttons_row.addWidget(self.btn_clear_all)
        buttons_row.addStretch()
        main_layout.addLayout(buttons_row)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText("Применить" if self.refs_only else "Сохранить")
        main_layout.addWidget(self.button_box)

        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_remove_selected.clicked.connect(self.remove_selected)
        self.btn_clear_all.clicked.connect(self.clear_all)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выбрать изображения",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not files:
            return

        existing = [
            self.references_list.item(i).data(Qt.ItemDataRole.UserRole) or self.references_list.item(i).text()
            for i in range(self.references_list.count())
        ]
        merged = []
        for item in existing + [f for f in files if str(f).strip()]:
            if item not in merged:
                merged.append(item)

        if len(merged) > MAX_REFERENCES_PER_PROMPT:
            QMessageBox.warning(
                self,
                "Ограничение",
                f"Можно добавить максимум {MAX_REFERENCES_PER_PROMPT} референсов",
            )
            merged = merged[:MAX_REFERENCES_PER_PROMPT]

        self.references_list.clear()
        for ref in merged:
            self._append_reference_item(ref)

    def _append_reference_item(self, ref):
        reference_path = str(ref or "").strip()
        if not reference_path:
            return
        title = os.path.basename(reference_path) or reference_path
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, reference_path)
        if os.path.isfile(reference_path):
            pixmap = QPixmap(reference_path)
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap))
        self.references_list.addItem(item)

    def remove_selected(self):
        selected_items = self.references_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            self.references_list.takeItem(self.references_list.row(item))

    def clear_all(self):
        self.references_list.clear()

    def get_data(self):
        prompt = self._source_prompt if self.refs_only else self.prompt_edit.toPlainText().strip()
        refs = [
            str(self.references_list.item(i).data(Qt.ItemDataRole.UserRole) or self.references_list.item(i).text()).strip()
            for i in range(self.references_list.count())
        ]
        refs = [r for r in refs if r]
        return prompt, refs[:MAX_REFERENCES_PER_PROMPT]


class ImageRegionSelector(QLabel):
    selection_changed = pyqtSignal(bool)

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        source_pixmap = QPixmap(image_path)
        if source_pixmap.isNull():
            raise ValueError(f"Не удалось открыть изображение: {image_path}")

        self.source_size = source_pixmap.size()
        self.display_pixmap = source_pixmap.scaled(
            QSize(820, 560),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(self.display_pixmap)
        self.setFixedSize(self.display_pixmap.size())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._drag_start = None
        self._selection = QRect()

    def _bounded_point(self, point):
        return QPoint(
            max(0, min(self.width() - 1, point.x())),
            max(0, min(self.height() - 1, point.y())),
        )

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._drag_start = self._bounded_point(event.position().toPoint())
        self._selection = QRect(self._drag_start, self._drag_start)
        self.update()
        self.selection_changed.emit(False)

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return super().mouseMoveEvent(event)
        current = self._bounded_point(event.position().toPoint())
        self._selection = QRect(self._drag_start, current).normalized().intersected(self.rect())
        self.update()
        self.selection_changed.emit(self.has_selection())

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._drag_start is None:
            return super().mouseReleaseEvent(event)
        current = self._bounded_point(event.position().toPoint())
        self._selection = QRect(self._drag_start, current).normalized().intersected(self.rect())
        self._drag_start = None
        self.update()
        self.selection_changed.emit(self.has_selection())

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.has_selection():
            return
        painter = QPainter(self)
        painter.fillRect(self._selection, QColor(20, 184, 166, 55))
        painter.setPen(QPen(QColor(20, 184, 166), 2))
        painter.drawRect(self._selection)

    def has_selection(self):
        return self._selection.width() >= 2 and self._selection.height() >= 2

    def set_selection(self, rectangle):
        self._selection = QRect(rectangle).normalized().intersected(self.rect())
        self.update()
        self.selection_changed.emit(self.has_selection())

    def selected_source_region(self):
        if not self.has_selection():
            return None
        source_width = self.source_size.width()
        source_height = self.source_size.height()
        display_width = self.display_pixmap.width()
        display_height = self.display_pixmap.height()
        x1 = math.floor(self._selection.x() * source_width / display_width)
        y1 = math.floor(self._selection.y() * source_height / display_height)
        x2 = math.ceil(
            (self._selection.x() + self._selection.width()) * source_width / display_width
        )
        y2 = math.ceil(
            (self._selection.y() + self._selection.height()) * source_height / display_height
        )
        return (
            max(0, x1),
            max(0, y1),
            min(source_width, x2) - max(0, x1),
            min(source_height, y2) - max(0, y1),
        )


class VisibleMarkRegionDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Область видимой метки")
        self._selected_region = None
        self._skipped = False

        layout = QVBoxLayout(self)
        file_label = QLabel(os.path.basename(image_path))
        file_label.setWordWrap(True)
        layout.addWidget(file_label)

        self.selector = ImageRegionSelector(image_path, self)
        layout.addWidget(self.selector, alignment=Qt.AlignmentFlag.AlignCenter)

        self.selection_status = QLabel("Область не выбрана")
        layout.addWidget(self.selection_status)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.skip_button = self.button_box.addButton(
            "Пропустить файл",
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        self.ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        layout.addWidget(self.button_box)

        self.selector.selection_changed.connect(self._update_selection_state)
        self.button_box.accepted.connect(self._accept_selection)
        self.button_box.rejected.connect(self.reject)
        self.skip_button.clicked.connect(self._skip_file)

    def _update_selection_state(self, _has_selection):
        region = self.selector.selected_source_region()
        if region is None:
            self.ok_button.setEnabled(False)
            self.selection_status.setStyleSheet("")
            self.selection_status.setText("Область не выбрана")
            return
        try:
            region = normalize_confirmed_region(
                region,
                (self.selector.source_size.width(), self.selector.source_size.height()),
            )
        except VisibleMarkCleanupError as error:
            self.ok_button.setEnabled(False)
            self.selection_status.setText(str(error))
            self.selection_status.setStyleSheet("color:#ef4444;")
            return
        self.ok_button.setEnabled(True)
        self.selection_status.setStyleSheet("")
        self.selection_status.setText(f"Область: {region[2]} x {region[3]} px")

    def _accept_selection(self):
        region = self.selector.selected_source_region()
        if region is None:
            return
        try:
            self._selected_region = normalize_confirmed_region(
                region,
                (self.selector.source_size.width(), self.selector.source_size.height()),
            )
        except VisibleMarkCleanupError as error:
            self.selection_status.setText(str(error))
            return
        self.accept()

    def _skip_file(self):
        self._skipped = True
        self._selected_region = None
        self.accept()

    def selected_region(self):
        return self._selected_region

    def was_skipped(self):
        return self._skipped


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(980, 700)

        self.work_dir = ""
        self.worker = None
        self.generated_prompts = []
        self.selected_files = []
        self.has_generated_output_in_run = False
        self.stop_pending = False
        self.api_key_locked = True
        self.photoroom_api_key_locked = True
        self.fal_api_key_locked = True
        self.secret_settings = {key: "" for key in SECRET_CONFIG_KEYS}
        self.credential_store = ProviderCredentialStore(
            ENV_FILE,
            os.path.join(USER_DATA_DIR, "fal_api_key.bin"),
        )
        self.credential_store_error = ""
        self.is_updating_prompts_table = False
        self.settings_save_timer = QTimer(self)
        self.settings_save_timer.setSingleShot(True)
        self.settings_save_timer.setInterval(400)
        self.settings_save_timer.timeout.connect(self.persist_ui_settings)
        self.api_key_mask_timer = QTimer(self)
        self.api_key_mask_timer.setSingleShot(True)
        self.api_key_mask_timer.setInterval(2500)
        self.api_key_mask_timer.timeout.connect(self.enforce_api_key_hidden)

        self.load_config()
        self.setup_ui()
        self.restore_last_work_dir()
        self.load_saved_prompts()
        self.setup_settings_autosave_connections()
    def load_saved_prompts(self):
        try:
            if not os.path.exists(PROMPTS_STORAGE_FILE):
                return
            with open(PROMPTS_STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            entries = []
            if isinstance(data, dict):
                raw_prompts = data.get("prompts", [])
                if isinstance(raw_prompts, list):
                    for item in raw_prompts:
                        if isinstance(item, dict):
                            prompt_text = str(item.get("prompt", "")).strip()
                            references = split_references(item.get("references", ""))
                            if prompt_text or references:
                                entries.append({"prompt": prompt_text, "references": references})
                        else:
                            prompt_text = str(item).strip()
                            if prompt_text:
                                entries.append({"prompt": prompt_text, "references": []})
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        prompt_text = str(item.get("prompt", "")).strip()
                        references = split_references(item.get("references", ""))
                        if prompt_text or references:
                            entries.append({"prompt": prompt_text, "references": references})
                    else:
                        prompt_text = str(item).strip()
                        if prompt_text:
                            entries.append({"prompt": prompt_text, "references": []})

            self.generated_prompts = entries
            if hasattr(self, "table"):
                self.refresh_prompts_table()
        except Exception as e:
            self.log(f"Не удалось загрузить сохранённые промпты: {e}")

    def save_prompts_storage(self):
        try:
            normalized_entries = []
            for item in self.generated_prompts:
                if isinstance(item, dict):
                    prompt_text = str(item.get("prompt", "")).strip()
                    references = split_references(item.get("references", []))
                else:
                    prompt_text = str(item).strip()
                    references = []
                if prompt_text or references:
                    normalized_entries.append({"prompt": prompt_text, "references": references})

            payload = {
                "prompts": normalized_entries,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            with open(PROMPTS_STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Не удалось сохранить промпты: {e}")

    def load_config(self):
        default_config = {
            "retries": 3,
            "timeout": 60,
            "generation_concurrency": 3,
            "kie_concurrency": 3,
            "photoroom_concurrency": 3,
            "fal_concurrency": 3,
            "generation_launch_interval": 1.0,
            "generation_wait_timeout": 300,
            "status_poll_interval": 20,
            "app_version": APP_VERSION,
            "update_manifest_url": UPDATE_MANIFEST_URL,
            "kie_upload_path": "clipart-generator",
            "text_generation_model": "gpt-image/1.5-text-to-image",
            "reference_generation_model": "gpt-image/1.5-image-to-image",
            "generation_model": "gpt-image/1.5-text-to-image",
            "generation_size": "1:1",
            "text_generation_ratio": "1:1",
            "reference_generation_ratio": "1:1",
            "text_generation_resolution": "1K",
            "reference_generation_resolution": "1K",
            "remove_bg": True,
            "upscale": True,
            "upscale_after": False,
            "trim_enabled": False,
            "trim_mode": "alpha",
            "export_300_dpi": False,
            "upscale_factor": 4,
            "upscale_provider": "kie",
            "upscale_after_provider": "local_realesrgan",
            "unsharp_enabled": False,
            "unsharp_amount": 30,
            "unsharp_radius": 100,
            "unsharp_threshold": 0,
            "local_realesrgan_dir": bundled_local_realesrgan_dir(),
            "local_realesrgan_profile": "clipart",
            "local_realesrgan_scale": 4,
            "local_realesrgan_after_scale": 4,
            "remove_bg_provider": "kie",
            "local_rembg_profile": "clipart",
            "local_rembg_model": "birefnet-general",
            "local_rembg_edge_quality": "normal",
            "local_ben2_refine_foreground": False,
            "local_ben2_alpha_threshold": 24,
            "local_ben2_edge_softness": 0,
            "local_ben2_corner_radius": 0,
            "edge_shrink_enabled": False,
            "edge_shrink_pixels": 1,
            "visible_mark_cleanup_enabled": False,
            "visible_mark_cleanup_mode": "gemini_auto",
            "cleanup_remove_exif": False,
            "cleanup_remove_xmp": False,
            "cleanup_remove_iptc": False,
            "cleanup_remove_comments_text": False,
            "cleanup_remove_embedded_thumbnail": False,
            "cleanup_remove_generator_fields": False,
            "cleanup_remove_embedded_c2pa": False,
            "cleanup_remove_all": False,
            "cleanup_preserve_icc": True,
            "cleanup_preserve_dpi": True,
            "kie_upscale_model": KIE_TOPAZ_MODEL_ID,
            "kie_upscale_after_model": KIE_TOPAZ_MODEL_ID,
            "kie_remove_bg_model": "recraft/remove-background",
            "run_mode": "generate_only",
            "prompt_input_mode": "list",
            "last_work_dir": "",
            "last_updates_expired_notice_at": "",
            "app_language": "ru",
        }
        self._migrate_legacy_local_files()
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            had_kie_concurrency = "kie_concurrency" in self.config
            had_photoroom_concurrency = "photoroom_concurrency" in self.config
            had_fal_concurrency = "fal_concurrency" in self.config
            for key, value in default_config.items():
                if key not in self.config:
                    self.config[key] = value
            if not had_kie_concurrency:
                self.config["kie_concurrency"] = normalize_kie_concurrency(
                    None,
                    legacy_value=self.config.get("generation_concurrency"),
                )
            if not had_photoroom_concurrency:
                self.config["photoroom_concurrency"] = normalize_provider_concurrency(None)
            if not had_fal_concurrency:
                self.config["fal_concurrency"] = normalize_provider_concurrency(None)
        else:
            self.config = default_config
        self.config["app_language"] = app_locale_from_settings(self.config)
        self.config["kie_upscale_model"] = normalize_kie_upscale_model(
            self.config.get("kie_upscale_model")
        )
        self.config["kie_upscale_after_model"] = normalize_kie_upscale_model(
            self.config.get(
                "kie_upscale_after_model",
                self.config["kie_upscale_model"],
            )
        )
        self.config["upscale_factor"] = normalize_topaz_upscale_factor(
            self.config.get("upscale_factor", 4)
        )
        # Local Real-ESRGAN is shipped with the application; an old external path is ignored.
        self.config["local_realesrgan_dir"] = bundled_local_realesrgan_dir()
        # URL обновлений всегда фиксированный и не редактируется в UI.
        self.config["update_manifest_url"] = UPDATE_MANIFEST_URL

        legacy_generation_model = self._normalize_generation_model_id(self.config.get("generation_model", "gpt-image/1.5-text-to-image"))
        legacy_meta = GENERATION_MODEL_META.get(legacy_generation_model, {})
        legacy_type = legacy_meta.get("type", "text_to_image")

        text_model = self._normalize_generation_model_id(self.config.get("text_generation_model", ""))
        text_meta = GENERATION_MODEL_META.get(text_model, {})
        if text_model not in VISIBLE_GENERATION_MODEL_IDS:
            text_model = "gpt-image/1.5-text-to-image"
        elif text_meta.get("type") != "text_to_image":
            if legacy_type == "text_to_image":
                text_model = legacy_generation_model
            else:
                text_model = "gpt-image/1.5-text-to-image"
        self.config["text_generation_model"] = text_model

        reference_model = self._normalize_generation_model_id(self.config.get("reference_generation_model", ""))
        if reference_model not in VISIBLE_GENERATION_MODEL_IDS:
            reference_model = "gpt-image/1.5-image-to-image"
        elif reference_model not in REFERENCE_MODEL_SHORTLIST:
            if legacy_generation_model in REFERENCE_MODEL_SHORTLIST:
                reference_model = legacy_generation_model
            else:
                reference_model = "gpt-image/1.5-image-to-image"
        self.config["reference_generation_model"] = reference_model

        legacy_ratio = str(self.config.get("generation_size", "1:1") or "1:1")
        self.config["text_generation_ratio"] = str(self.config.get("text_generation_ratio", legacy_ratio) or "1:1")
        self.config["reference_generation_ratio"] = str(self.config.get("reference_generation_ratio", legacy_ratio) or "1:1")
        self.config["text_generation_resolution"] = str(self.config.get("text_generation_resolution", "1K") or "1K")
        self.config["reference_generation_resolution"] = str(self.config.get("reference_generation_resolution", "1K") or "1K")

        # Оставляем legacy-ключ для обратной совместимости.
        self.config["generation_model"] = self.config["text_generation_model"]

        # Текущая версия приложения берётся из кода сборки, а не из пользовательского конфига.
        # Это предотвращает цикл обновлений, если в конфиге осталось старое значение.
        self.config["app_version"] = APP_VERSION
        self._sync_credential_settings()

    def save_config(self, *, include_secrets: bool = False):
        sanitized = dict(self.config)
        if include_secrets:
            sanitized.update(
                {
                    key: self.secret_settings.get(key, "").strip()
                    for key in SECRET_CONFIG_KEYS
                    if self.secret_settings.get(key, "").strip()
                }
            )
        else:
            sanitized = {
                key: value
                for key, value in sanitized.items()
                if key not in SECRET_CONFIG_KEYS
            }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, indent=2, ensure_ascii=False)

    def _sync_credential_settings(self):
        loaded_credentials = self.credential_store.load()
        existing_file_values = {
            key: str(value).strip()
            for key, value in loaded_credentials.items()
            if key in SECRET_CONFIG_KEYS and str(value).strip()
        }
        legacy_values = {
            key: str(self.config.get(key, "")).strip()
            for key in SECRET_CONFIG_KEYS
            if str(self.config.get(key, "")).strip()
        }
        if legacy_values:
            merged_values = dict(existing_file_values)
            merged_values.update(legacy_values)
            if merged_values != existing_file_values:
                try:
                    self.credential_store.save(merged_values)
                except Exception as error:
                    self.credential_store_error = safe_error_text(error)
                    if hasattr(self, "log_text"):
                        self.log(
                            f"Не удалось сохранить секреты в user-data .env: {self.credential_store_error}"
                        )
                    return
                existing_file_values = merged_values
        self.secret_settings.update(existing_file_values)
        changed = False
        for key in SECRET_CONFIG_KEYS:
            if key in self.config:
                self.config.pop(key, None)
                changed = True
        if "license_key" in self.config:
            self.config.pop("license_key", None)
            changed = True
        if any(key not in SECRET_CONFIG_KEYS for key in loaded_credentials):
            try:
                self.credential_store.save(existing_file_values)
            except Exception as error:
                self.credential_store_error = safe_error_text(error)
        if changed:
            self.save_config()

    def _migrate_legacy_local_files(self):
        try:
            legacy_config = os.path.join(os.getcwd(), "config.json")
            legacy_prompts = os.path.join(os.getcwd(), "prompts.json")
            if os.path.exists(legacy_config) and not os.path.exists(CONFIG_FILE):
                with open(legacy_config, "r", encoding="utf-8") as src, open(CONFIG_FILE, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            if os.path.exists(legacy_prompts) and not os.path.exists(PROMPTS_STORAGE_FILE):
                with open(legacy_prompts, "r", encoding="utf-8") as src, open(PROMPTS_STORAGE_FILE, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
        except Exception:
            pass

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(8)

        self.primary_button_style = (
            "QPushButton {background:#14b8a6; color:white; font-weight:700; border-radius:8px; padding:8px 16px;}"
            "QPushButton:hover {background:#0f9f90;}"
            "QPushButton:disabled {background:#9ca3af; color:white;}"
        )
        self.compact_button_style = (
            "QPushButton {background:#14b8a6; color:white; font-weight:700; border-radius:7px; padding:5px 10px;}"
            "QPushButton:hover {background:#0f9f90;}"
            "QPushButton:disabled {background:#9ca3af; color:white;}"
        )
        self.standard_button_width = 140
        self.standard_button_height = 36

        self.setStyleSheet(
            "QRadioButton::indicator, QCheckBox::indicator {width: 16px; height: 16px;}"
            "QRadioButton::indicator:unchecked, QCheckBox::indicator:unchecked {"
            "border: 2px solid #14b8a6; background: #ffffff; border-radius: 8px;}"
            "QRadioButton::indicator:checked, QCheckBox::indicator:checked {"
            "border: 2px solid #14b8a6; background: #14b8a6; border-radius: 8px;}"
        )

        top_layout = QHBoxLayout()
        self.lbl_work_dir = QLabel("Рабочая папка: не выбрана")
        self.btn_select_dir = QPushButton("Выбрать папку")
        self.btn_select_dir.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_select_dir.setStyleSheet(self.primary_button_style)
        self.btn_select_dir.clicked.connect(self.select_work_dir)
        top_layout.addWidget(self.lbl_work_dir)
        top_layout.addSpacing(8)
        top_layout.addWidget(self.btn_select_dir)
        top_layout.addStretch()
        self.btn_api_settings = QPushButton("Настройки API")
        self.btn_api_settings.setFixedSize(150, self.standard_button_height)
        self.btn_api_settings.setStyleSheet(self.compact_button_style)
        self.btn_api_settings.setToolTip("Общие настройки API для всех режимов")
        top_layout.addWidget(self.btn_api_settings)
        main_layout.addLayout(top_layout)

        run_mode_group = QGroupBox("Сценарий запуска")
        run_mode_layout = QHBoxLayout()
        self.run_mode_group = QButtonGroup()

        self.radio_run_generate = QRadioButton("Только генерация изображений")
        self.radio_run_process = QRadioButton("Только обработка файлов")
        self.radio_run_both = QRadioButton("Все вместе")

        run_mode = self.config.get("run_mode", "generate_only")
        if run_mode == "process_only":
            self.radio_run_process.setChecked(True)
        elif run_mode == "both":
            self.radio_run_both.setChecked(True)
        else:
            self.radio_run_generate.setChecked(True)

        self.radio_run_generate.toggled.connect(self.on_mode_changed)
        self.radio_run_process.toggled.connect(self.on_mode_changed)
        self.radio_run_both.toggled.connect(self.on_mode_changed)

        self.run_mode_group.addButton(self.radio_run_generate, 1)
        self.run_mode_group.addButton(self.radio_run_process, 2)
        self.run_mode_group.addButton(self.radio_run_both, 3)
        run_mode_layout.addWidget(self.radio_run_generate)
        run_mode_layout.addWidget(self.radio_run_process)
        run_mode_layout.addWidget(self.radio_run_both)
        run_mode_layout.addStretch()
        run_mode_group.setLayout(run_mode_layout)
        main_layout.addWidget(run_mode_group)

        self.tabs = QTabWidget()
        prompt_tab = QWidget()
        prompt_tab_layout = QVBoxLayout(prompt_tab)
        process_tab = QWidget()
        process_tab_layout = QVBoxLayout(process_tab)
        settings_tab = QWidget()
        settings_tab_layout = QVBoxLayout(settings_tab)
        settings_tab_layout.setSpacing(8)

        process_scroll = QScrollArea()
        process_scroll.setWidgetResizable(True)
        process_scroll.setWidget(process_tab)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_tab)
        self.tabs.addTab(prompt_tab, "Промпты")
        self.tabs.addTab(process_scroll, "Обработка")
        self.tabs.addTab(settings_scroll, "Настройки")
        self.btn_api_settings.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        main_layout.addWidget(self.tabs)

        prompt_btn_layout = QHBoxLayout()
        self.btn_add_prompt_row = QPushButton("+")
        self.btn_add_prompt_row.clicked.connect(self.add_prompt_row)
        self.btn_add_prompt_row.setToolTip("Добавить строку")
        self.btn_add_refs_selected = QPushButton("🖼+")
        self.btn_add_refs_selected.clicked.connect(self.add_references_to_selected_prompts)
        self.btn_add_refs_selected.setToolTip("Добавить референсы к выделенным строкам")
        self.btn_clear_refs_selected = QPushButton("🖼−")
        self.btn_clear_refs_selected.clicked.connect(self.clear_references_for_selected_prompts)
        self.btn_clear_refs_selected.setToolTip("Очистить референсы у выделенных строк")
        self.btn_import_csv = QPushButton("Импорт CSV")
        self.btn_import_csv.clicked.connect(self.import_prompts_from_csv)
        self.btn_import_csv.setToolTip("Импортирует промпты из CSV-файла")
        self.btn_export_csv = QPushButton("Экспорт CSV")
        self.btn_export_csv.clicked.connect(self.export_prompts)
        self.btn_export_csv.setToolTip("Экспортирует промпты и референсы в CSV-файл")
        self.btn_clear_prompts = QPushButton("Удалить все")
        self.btn_clear_prompts.clicked.connect(self.clear_all_prompts)
        self.btn_clear_prompts.setToolTip("Очищает список промптов в предпросмотре")
        self.btn_import_csv.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_export_csv.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_clear_prompts.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_add_refs_selected.setFixedSize(72, self.standard_button_height)
        self.btn_clear_refs_selected.setFixedSize(72, self.standard_button_height)
        self.btn_add_prompt_row.setStyleSheet(self.primary_button_style)
        self.btn_add_refs_selected.setStyleSheet(self.primary_button_style)
        self.btn_clear_refs_selected.setStyleSheet(self.primary_button_style)
        self.btn_import_csv.setStyleSheet(self.primary_button_style)
        self.btn_export_csv.setStyleSheet(self.primary_button_style)
        self.btn_clear_prompts.setStyleSheet(self.primary_button_style)
        prompt_btn_layout.addWidget(self.btn_add_prompt_row)
        prompt_btn_layout.addWidget(self.btn_add_refs_selected)
        prompt_btn_layout.addWidget(self.btn_clear_refs_selected)
        prompt_btn_layout.addWidget(self.btn_import_csv)
        prompt_btn_layout.addWidget(self.btn_export_csv)
        prompt_btn_layout.addStretch()
        prompt_btn_layout.addWidget(self.btn_clear_prompts)
        prompt_tab_layout.addLayout(prompt_btn_layout)

        preview_group = QGroupBox("Список записей")
        preview_layout = QVBoxLayout()
        self.table = PromptTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Промпт", "🖼", "Добавить", "Заменить", "Удалить референсы", "Удалить промпт"])
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.verticalHeader().setFixedWidth(24)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 52)
        self.table.setColumnWidth(2, 38)
        self.table.setColumnWidth(3, 38)
        self.table.setColumnWidth(4, 38)
        self.table.setColumnWidth(5, 38)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setMinimumHeight(280)
        self.table.bulkTextPasted.connect(self.on_table_bulk_paste)
        self.table.itemChanged.connect(self.on_prompt_item_changed)
        self.table.itemDoubleClicked.connect(self.on_prompt_item_double_clicked)
        preview_layout.addWidget(self.table)
        preview_group.setLayout(preview_layout)
        prompt_tab_layout.addWidget(preview_group)

        files_group = QGroupBox("Файлы для обработки")
        files_layout = QVBoxLayout()
        self.btn_select_files = QPushButton("Выбрать файлы")
        self.btn_select_files.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_select_files.setStyleSheet(self.primary_button_style)
        self.btn_select_files.clicked.connect(self.select_files)
        self.lbl_files_count = QLabel("Файлов не выбрано")
        self.chk_overwrite_existing = QCheckBox("Перезаписывать существующие файлы результата")
        self.chk_overwrite_existing.setChecked(bool(self.config.get("overwrite_existing", False)))
        self.chk_overwrite_existing.setStyleSheet("QCheckBox { color:#b45309; font-weight:700; }")
        self.chk_overwrite_existing.setToolTip("Если в папке результата уже есть файл с таким именем, он будет заменён.")
        files_layout.addWidget(self.btn_select_files)
        files_layout.addWidget(self.lbl_files_count)
        files_layout.addWidget(self.chk_overwrite_existing)
        files_group.setLayout(files_layout)
        process_tab_layout.addWidget(files_group)

        self.process_flags_group = QGroupBox("Параметры обработки")
        process_flags_layout = QGridLayout()
        process_flags_layout.setHorizontalSpacing(12)
        process_flags_layout.setVerticalSpacing(8)
        self.chk_visible_mark_cleanup = QCheckBox("Удалить видимый водяной знак")
        self.chk_visible_mark_cleanup.setChecked(
            bool(self.config.get("visible_mark_cleanup_enabled", False))
        )
        self.chk_visible_mark_cleanup.setToolTip(
            "Удаляет видимый текстовый или логотипный водяной знак. "
            "Только для собственных или лицензированных изображений."
        )
        visible_mark_mode = normalize_visible_mark_cleanup_mode(
            self.config.get("visible_mark_cleanup_mode", "gemini_auto")
        )
        self.visible_mark_settings = VisibleMarkSettingsWidget(visible_mark_mode)
        self.visible_mark_mode_combo = self.visible_mark_settings.mode_combo
        self.visible_mark_confirmation_label = self.visible_mark_settings.confirmation_label
        self.chk_upscale = QCheckBox("Апскейл до удаления фона")
        self.chk_upscale.setChecked(self.config.get("upscale", True))
        self.chk_upscale_after = QCheckBox("Апскейл после удаления фона")
        self.chk_upscale_after.setChecked(bool(self.config.get("upscale_after", False)))
        self.upscale_total_label = QLabel("")
        self.upscale_total_label.setStyleSheet("color:#14b8a6; font-weight:700;")
        self.chk_remove_bg = QCheckBox("Удаление фона")
        self.chk_remove_bg.setChecked(self.config.get("remove_bg", True))
        self.chk_trim = QCheckBox("Trim (обрезка пустых краёв)")
        self.chk_trim.setChecked(bool(self.config.get("trim_enabled", False)))
        self.chk_unsharp = QCheckBox("Резкость")
        self.chk_unsharp.setChecked(bool(self.config.get("unsharp_enabled", False)))
        self.chk_export_300_dpi = QCheckBox("Экспорт для печати (300 DPI)")
        self.chk_export_300_dpi.setChecked(bool(self.config.get("export_300_dpi", False)))
        self.chk_edge_shrink = QCheckBox("Удалять контур")
        self.chk_edge_shrink.setChecked(bool(self.config.get("edge_shrink_enabled", False)))
        self.edge_shrink_pixels_combo = QComboBox()
        for pixel_value in (1, 2, 3):
            self.edge_shrink_pixels_combo.addItem(f"{pixel_value} px", pixel_value)
        edge_shrink_pixels = int(self.config.get("edge_shrink_pixels", 1) or 1)
        edge_shrink_pixels_index = self.edge_shrink_pixels_combo.findData(edge_shrink_pixels)
        self.edge_shrink_pixels_combo.setCurrentIndex(edge_shrink_pixels_index if edge_shrink_pixels_index >= 0 else 0)
        self.edge_shrink_pixels_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.edge_shrink_pixels_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.edge_shrink_pixels_combo.setFixedSize(72, 32)
        self.trim_mode_combo = QComboBox()
        self.trim_mode_combo.addItem("Прозрачные края", "alpha")
        self.trim_mode_combo.addItem("Белые края", "white")
        self.trim_mode_combo.addItem("Черные края", "black")
        trim_mode = str(self.config.get("trim_mode", "alpha") or "alpha")
        trim_mode_index = self.trim_mode_combo.findData(trim_mode)
        self.trim_mode_combo.setCurrentIndex(trim_mode_index if trim_mode_index >= 0 else 0)
        self.unsharp_amount_spin = QSpinBox()
        self.unsharp_amount_spin.setRange(0, 500)
        self.unsharp_amount_spin.setValue(normalize_unsharp_amount(self.config.get("unsharp_amount", 30)))
        self.unsharp_radius_spin = QSpinBox()
        self.unsharp_radius_spin.setRange(1, 200)
        self.unsharp_radius_spin.setValue(int(round(normalize_unsharp_radius(self.config.get("unsharp_radius", 100)))))
        self.unsharp_threshold_spin = QSpinBox()
        self.unsharp_threshold_spin.setRange(0, 255)
        self.unsharp_threshold_spin.setValue(normalize_unsharp_threshold(self.config.get("unsharp_threshold", 0)))

        unsharp_params_widget = QWidget()
        unsharp_params_layout = QHBoxLayout(unsharp_params_widget)
        unsharp_params_layout.setContentsMargins(0, 0, 0, 0)
        unsharp_params_layout.setSpacing(8)
        unsharp_params_layout.addWidget(QLabel("Amount:"))
        unsharp_params_layout.addWidget(self.unsharp_amount_spin)
        unsharp_params_layout.addWidget(QLabel("Radius:"))
        unsharp_params_layout.addWidget(self.unsharp_radius_spin)
        unsharp_params_layout.addWidget(QLabel("Threshold:"))
        unsharp_params_layout.addWidget(self.unsharp_threshold_spin)
        unsharp_params_layout.addStretch()

        trim_params_widget = QWidget()
        trim_params_layout = QHBoxLayout(trim_params_widget)
        trim_params_layout.setContentsMargins(0, 0, 0, 0)
        trim_params_layout.setSpacing(8)
        trim_params_layout.addWidget(QLabel("Удаляемый цвет:"))
        trim_params_layout.addWidget(self.trim_mode_combo)
        trim_params_layout.addStretch()

        visible_mark_params_widget = self.visible_mark_settings

        process_flags_layout.addWidget(self.chk_visible_mark_cleanup, 0, 0)
        process_flags_layout.addWidget(visible_mark_params_widget, 0, 1)
        process_flags_layout.addWidget(self.chk_upscale, 1, 0)
        process_flags_layout.addWidget(self.chk_unsharp, 2, 0)
        process_flags_layout.addWidget(unsharp_params_widget, 2, 1)
        process_flags_layout.addWidget(self.chk_remove_bg, 3, 0)
        process_flags_layout.addWidget(self.chk_upscale_after, 4, 0)
        process_flags_layout.addWidget(self.upscale_total_label, 4, 1)
        process_flags_layout.addWidget(self.chk_edge_shrink, 5, 0)
        process_flags_layout.addWidget(self.edge_shrink_pixels_combo, 5, 1)
        process_flags_layout.addWidget(self.chk_trim, 6, 0)
        process_flags_layout.addWidget(trim_params_widget, 6, 1)
        process_flags_layout.addWidget(self.chk_export_300_dpi, 7, 0)
        process_flags_layout.setColumnStretch(1, 1)
        self.process_flags_group.setLayout(process_flags_layout)
        process_tab_layout.addWidget(self.process_flags_group)

        self.cleanup_group = QGroupBox("Очистка файла")
        cleanup_layout = QVBoxLayout()
        cleanup_layout.setSpacing(6)

        self.chk_cleanup_all = QCheckBox("Очистить данные файла полностью")
        self.chk_cleanup_all.setToolTip(
            "Удаляет все служебные данные, кроме ICC-профиля и DPI. "
            "Пиксели и прозрачность изображения не меняются."
        )
        cleanup_all_enabled = bool(self.config.get("cleanup_remove_all", False)) or any(
            bool(self.config.get(key, False))
            for key in (
                "cleanup_remove_exif",
                "cleanup_remove_xmp",
                "cleanup_remove_iptc",
                "cleanup_remove_comments_text",
                "cleanup_remove_embedded_thumbnail",
                "cleanup_remove_generator_fields",
                "cleanup_remove_embedded_c2pa",
            )
        )
        self.chk_cleanup_all.setChecked(cleanup_all_enabled)
        cleanup_intro = QLabel(
            "Удаляются EXIF, XMP, IPTC, комментарии, встроенная миниатюра, "
            "данные генератора и встроенный C2PA. ICC-профиль и DPI сохраняются."
        )
        cleanup_intro.setWordWrap(True)
        cleanup_layout.addWidget(self.chk_cleanup_all)
        cleanup_layout.addWidget(cleanup_intro)
        self.cleanup_group.setLayout(cleanup_layout)
        process_tab_layout.addWidget(self.cleanup_group)

        kie_group = QGroupBox("Подключения и генерация")
        kie_group.setMaximumWidth(720)
        kie_layout = QGridLayout()
        kie_layout.setHorizontalSpacing(6)
        kie_layout.setVerticalSpacing(6)
        self.kie_api_key_input = QLineEdit()
        self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.kie_api_key_input.setText(
            self.secret_settings.get("kie_api_key", self.config.get("kie_api_key", ""))
        )
        self.kie_api_key_input.setReadOnly(True)

        self.fal_api_key_input = QLineEdit()
        self.fal_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.fal_api_key_input.setText(
            self.secret_settings.get("fal_api_key", self.config.get("fal_api_key", ""))
        )
        self.fal_api_key_input.setReadOnly(True)
        self.btn_fal_api_key_lock = QPushButton("🔒")
        self.btn_fal_api_key_lock.setFixedSize(40, 32)
        self.btn_fal_api_key_lock.setToolTip("Ключ заблокирован")
        self.btn_fal_api_key_lock.clicked.connect(self.toggle_fal_api_key_lock)

        self.btn_api_key_lock = QPushButton("🔒")
        self.btn_api_key_lock.setFixedSize(40, 32)
        self.btn_api_key_lock.setToolTip("Ключ заблокирован")
        self.btn_api_key_lock.clicked.connect(self.toggle_api_key_lock)

        self.text_generation_model_combo = QComboBox()
        self.populate_generation_models(self.text_generation_model_combo, {"text_to_image"})
        self.set_generation_model_selection(
            self.text_generation_model_combo,
            self.config.get("text_generation_model", "gpt-image/1.5-text-to-image"),
            {"text_to_image"},
            "gpt-image/1.5-text-to-image",
        )
        self.text_model_price_label = QLabel("")
        self.text_model_price_label.setStyleSheet("color:#14b8a6; font-weight:700;")

        self.reference_generation_model_combo = QComboBox()
        self.populate_generation_models(
            self.reference_generation_model_combo,
            set(),
            include_model_ids=REFERENCE_MODEL_SHORTLIST,
        )
        self.set_generation_model_selection(
            self.reference_generation_model_combo,
            self.config.get("reference_generation_model", "gpt-image/1.5-image-to-image"),
            set(),
            "gpt-image/1.5-image-to-image",
            include_model_ids=REFERENCE_MODEL_SHORTLIST,
        )
        self.reference_model_price_label = QLabel("")
        self.reference_model_price_label.setStyleSheet("color:#14b8a6; font-weight:700;")

        self.text_ratio_combo = QComboBox()
        self.text_resolution_combo = QComboBox()
        self.reference_ratio_combo = QComboBox()
        self.reference_resolution_combo = QComboBox()
        self.btn_check_balance = QPushButton("Проверить баланс")
        self.btn_check_balance.setFixedSize(130, 32)
        self.btn_check_balance.setStyleSheet(self.compact_button_style)
        self.btn_check_balance.clicked.connect(self.check_kie_balance)

        self.api_key_buttons_widget = QWidget()
        self.api_key_buttons_layout = QHBoxLayout(self.api_key_buttons_widget)
        self.api_key_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.api_key_buttons_layout.setSpacing(6)
        self.api_key_buttons_layout.addWidget(self.btn_api_key_lock)
        self.api_key_buttons_layout.addWidget(self.btn_check_balance)

        settings_field_width = 220
        self.kie_api_key_input.setFixedSize(settings_field_width, 32)
        self.fal_api_key_input.setFixedSize(settings_field_width, 32)
        self.text_generation_model_combo.setFixedSize(settings_field_width, 32)
        self.reference_generation_model_combo.setFixedSize(settings_field_width, 32)
        self.text_ratio_combo.setFixedSize(110, 32)
        self.text_resolution_combo.setFixedSize(110, 32)
        self.reference_ratio_combo.setFixedSize(110, 32)
        self.reference_resolution_combo.setFixedSize(110, 32)

        lbl_api_key = QLabel("KIE API Key:")
        lbl_api_key.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_fal_api_key = QLabel("Fal.ai API Key:")
        lbl_fal_api_key.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_text_model = QLabel("Для текстовых промптов:")
        lbl_text_model.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_reference_model = QLabel("Для промптов с референсами:")
        lbl_reference_model.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_text_options = QLabel("Параметры текста:")
        lbl_text_options.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_reference_options = QLabel("Параметры референса:")
        lbl_reference_options.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        text_options_widget = QWidget()
        text_options_layout = QHBoxLayout(text_options_widget)
        text_options_layout.setContentsMargins(0, 0, 0, 0)
        text_options_layout.setSpacing(8)
        text_options_layout.addWidget(self.text_ratio_combo)
        text_options_layout.addWidget(self.text_resolution_combo)
        text_options_layout.addStretch()

        reference_options_widget = QWidget()
        reference_options_layout = QHBoxLayout(reference_options_widget)
        reference_options_layout.setContentsMargins(0, 0, 0, 0)
        reference_options_layout.setSpacing(8)
        reference_options_layout.addWidget(self.reference_ratio_combo)
        reference_options_layout.addWidget(self.reference_resolution_combo)
        reference_options_layout.addStretch()

        def model_with_price(model_combo, price_label):
            model_widget = QWidget()
            model_layout = QHBoxLayout(model_widget)
            model_layout.setContentsMargins(0, 0, 0, 0)
            model_layout.setSpacing(8)
            model_layout.addWidget(model_combo)
            model_layout.addWidget(price_label)
            model_layout.addStretch()
            return model_widget

        text_model_widget = model_with_price(
            self.text_generation_model_combo,
            self.text_model_price_label,
        )
        reference_model_widget = model_with_price(
            self.reference_generation_model_combo,
            self.reference_model_price_label,
        )

        kie_layout.addWidget(lbl_api_key, 0, 0)
        kie_layout.addWidget(self.kie_api_key_input, 0, 1)
        kie_layout.addWidget(self.api_key_buttons_widget, 0, 2)
        fal_access_widget = QWidget()
        fal_access_layout = QHBoxLayout(fal_access_widget)
        fal_access_layout.setContentsMargins(0, 0, 0, 0)
        fal_access_layout.setSpacing(6)
        fal_access_layout.addWidget(self.fal_api_key_input)
        fal_access_layout.addWidget(self.btn_fal_api_key_lock)
        fal_access_layout.addWidget(QLabel("очередь · стоимость зависит от модели"))
        kie_layout.addWidget(lbl_fal_api_key, 1, 0)
        kie_layout.addWidget(fal_access_widget, 1, 1, 1, 3)
        kie_layout.addWidget(lbl_text_model, 2, 0)
        kie_layout.addWidget(text_model_widget, 2, 1, 1, 3)
        kie_layout.addWidget(lbl_text_options, 3, 0)
        kie_layout.addWidget(text_options_widget, 3, 1)
        kie_layout.addWidget(lbl_reference_model, 4, 0)
        kie_layout.addWidget(reference_model_widget, 4, 1, 1, 3)
        kie_layout.addWidget(lbl_reference_options, 5, 0)
        kie_layout.addWidget(reference_options_widget, 5, 1)
        kie_group.setLayout(kie_layout)
        settings_tab_layout.addWidget(kie_group, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.photoroom_api_key_input = QLineEdit()
        self.photoroom_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.photoroom_api_key_input.setText(
            self.secret_settings.get(
                "photoroom_api_key", self.config.get("photoroom_api_key", "")
            )
        )
        self.photoroom_api_key_input.setReadOnly(True)
        self.photoroom_api_key_input.setFixedSize(settings_field_width, 32)
        self.btn_photoroom_api_key_lock = QPushButton("🔒")
        self.btn_photoroom_api_key_lock.setFixedSize(40, 32)
        self.btn_photoroom_api_key_lock.setToolTip("Ключ заблокирован")
        self.btn_photoroom_api_key_lock.clicked.connect(self.toggle_photoroom_api_key_lock)
        self.btn_photoroom_check_balance = QPushButton("Проверить баланс")
        self.btn_photoroom_check_balance.setFixedSize(130, 32)
        self.btn_photoroom_check_balance.setStyleSheet(self.compact_button_style)
        self.btn_photoroom_check_balance.clicked.connect(self.check_photoroom_balance)
        photoroom_price_label = QLabel("Standard · $0.02 / изображение")
        photoroom_price_label.setStyleSheet("color:#14b8a6; font-weight:700;")
        photoroom_access_widget = QWidget()
        photoroom_access_layout = QHBoxLayout(photoroom_access_widget)
        photoroom_access_layout.setContentsMargins(0, 0, 0, 0)
        photoroom_access_layout.setSpacing(6)
        photoroom_access_layout.addWidget(self.photoroom_api_key_input)
        photoroom_access_layout.addWidget(self.btn_photoroom_api_key_lock)
        photoroom_access_layout.addWidget(self.btn_photoroom_check_balance)
        photoroom_access_layout.addWidget(photoroom_price_label)
        photoroom_access_layout.addStretch()
        lbl_photoroom_api_key = QLabel("PhotoRoom API Key:")
        lbl_photoroom_api_key.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        kie_layout.addWidget(lbl_photoroom_api_key, 6, 0)
        kie_layout.addWidget(photoroom_access_widget, 6, 1, 1, 3)

        self.btn_next_to_processing = QPushButton("Далее: обработка →")
        self.btn_next_to_processing.setFixedSize(190, 36)
        self.btn_next_to_processing.setStyleSheet(self.primary_button_style)
        self.btn_next_to_processing.setToolTip("Перейти к отдельному шагу настроек обработки")
        self.btn_next_to_processing.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        settings_tab_layout.addWidget(self.btn_next_to_processing, alignment=Qt.AlignmentFlag.AlignRight)

        process_settings_group = QGroupBox("Обработка изображений")
        process_settings_group.setMaximumWidth(1080)
        process_settings_layout = QVBoxLayout()
        process_settings_layout.setSpacing(10)

        self.upscale_provider_combo = QComboBox()
        self.upscale_provider_combo.addItem("KIE", "kie")
        self.upscale_provider_combo.addItem("Fal.ai", "fal")
        self.upscale_provider_combo.addItem("Local Real-ESRGAN", "local_realesrgan")
        upscale_provider = str(self.config.get("upscale_provider", "kie") or "kie")
        upscale_provider_index = self.upscale_provider_combo.findData(upscale_provider)
        self.upscale_provider_combo.setCurrentIndex(upscale_provider_index if upscale_provider_index >= 0 else 0)

        self.upscale_after_provider_combo = QComboBox()
        self.upscale_after_provider_combo.addItem("KIE", "kie")
        self.upscale_after_provider_combo.addItem("Fal.ai", "fal")
        self.upscale_after_provider_combo.addItem("Local Real-ESRGAN", "local_realesrgan")
        upscale_after_provider = str(
            self.config.get("upscale_after_provider", "local_realesrgan") or "local_realesrgan"
        )
        upscale_after_provider_index = self.upscale_after_provider_combo.findData(upscale_after_provider)
        self.upscale_after_provider_combo.setCurrentIndex(
            upscale_after_provider_index if upscale_after_provider_index >= 0 else 1
        )

        self.local_realesrgan_dir_input = QLineEdit()
        self.local_realesrgan_dir_input.setText(bundled_local_realesrgan_dir())
        self.local_realesrgan_dir_input.setReadOnly(True)
        self.local_realesrgan_dir_input.setVisible(False)
        self.local_realesrgan_bundle_label = QLabel("Встроен в приложение")
        self.local_realesrgan_bundle_label.setToolTip(
            "Real-ESRGAN входит в пакет приложения и не требует выбора папки."
        )

        self.local_realesrgan_profile_combo = QComboBox()
        self.local_realesrgan_profile_combo.addItem("Photo", "photo")
        self.local_realesrgan_profile_combo.addItem("Clipart", "clipart")
        local_realesrgan_profile = str(self.config.get("local_realesrgan_profile", "clipart") or "clipart")
        local_realesrgan_profile_index = self.local_realesrgan_profile_combo.findData(local_realesrgan_profile)
        self.local_realesrgan_profile_combo.setCurrentIndex(
            local_realesrgan_profile_index if local_realesrgan_profile_index >= 0 else 1
        )

        self.local_realesrgan_scale_combo = QComboBox()
        for scale_value in (2, 4):
            self.local_realesrgan_scale_combo.addItem(f"{scale_value}x", scale_value)
        local_realesrgan_scale = int(self.config.get("local_realesrgan_scale", 4) or 4)
        local_realesrgan_scale_index = self.local_realesrgan_scale_combo.findData(local_realesrgan_scale)
        self.local_realesrgan_scale_combo.setCurrentIndex(
            local_realesrgan_scale_index if local_realesrgan_scale_index >= 0 else 2
        )

        self.local_realesrgan_after_scale_combo = QComboBox()
        for scale_value in (2, 4):
            self.local_realesrgan_after_scale_combo.addItem(f"{scale_value}x", scale_value)
        local_realesrgan_after_scale = int(self.config.get("local_realesrgan_after_scale", 4) or 4)
        local_realesrgan_after_scale_index = self.local_realesrgan_after_scale_combo.findData(
            local_realesrgan_after_scale
        )
        self.local_realesrgan_after_scale_combo.setCurrentIndex(
            local_realesrgan_after_scale_index if local_realesrgan_after_scale_index >= 0 else 1
        )

        self.kie_upscale_model_combo = QComboBox()
        self.kie_upscale_model_combo.addItems([KIE_TOPAZ_MODEL_ID, "recraft/crisp-upscale"])
        uim = self.config.get("kie_upscale_model", KIE_TOPAZ_MODEL_ID)
        ui_index = self.kie_upscale_model_combo.findText(uim)
        self.kie_upscale_model_combo.setCurrentIndex(ui_index if ui_index >= 0 else 0)

        self.kie_upscale_after_model_combo = QComboBox()
        self.kie_upscale_after_model_combo.addItems([KIE_TOPAZ_MODEL_ID, "recraft/crisp-upscale"])
        upscale_after_model = self.config.get("kie_upscale_after_model", uim)
        upscale_after_model_index = self.kie_upscale_after_model_combo.findText(upscale_after_model)
        self.kie_upscale_after_model_combo.setCurrentIndex(
            upscale_after_model_index if upscale_after_model_index >= 0 else 0
        )
        self.upscale_after_note = QLabel()
        self.upscale_after_note.setWordWrap(True)
        self.upscale_after_note.setStyleSheet("color:#f0b44d; max-width:720px;")

        self.remove_bg_provider_combo = QComboBox()
        self.remove_bg_provider_combo.addItem("KIE", "kie")
        self.remove_bg_provider_combo.addItem("Fal.ai", "fal")
        self.remove_bg_provider_combo.addItem("PhotoRoom Standard", "photoroom")
        self.remove_bg_provider_combo.addItem("Local rembg", "local_rembg")
        self.remove_bg_provider_combo.addItem("Local BEN2", "local_ben2")
        remove_bg_provider = str(self.config.get("remove_bg_provider", "kie") or "kie")
        remove_bg_provider_index = self.remove_bg_provider_combo.findData(remove_bg_provider)
        self.remove_bg_provider_combo.setCurrentIndex(remove_bg_provider_index if remove_bg_provider_index >= 0 else 0)

        self.local_rembg_profile_combo = QComboBox()
        self.local_rembg_profile_combo.addItem("Clipart", "clipart")
        self.local_rembg_profile_combo.addItem("People", "people")
        self.local_rembg_profile_combo.addItem("Anime", "anime")
        self.local_rembg_profile_combo.addItem("Fallback", "fallback")
        local_rembg_profile = str(self.config.get("local_rembg_profile", "clipart") or "clipart")
        local_rembg_profile_index = self.local_rembg_profile_combo.findData(local_rembg_profile)
        self.local_rembg_profile_combo.setCurrentIndex(local_rembg_profile_index if local_rembg_profile_index >= 0 else 0)

        self.local_rembg_model_combo = QComboBox()
        self.local_rembg_model_combo.addItem("BiRefNet — общий", "birefnet-general")
        self.local_rembg_model_combo.addItem("BiRefNet — портрет", "birefnet-portrait")
        self.local_rembg_model_combo.addItem("IS-Net — аниме", "isnet-anime")
        self.local_rembg_model_combo.addItem("IS-Net — общий", "isnet-general-use")
        local_rembg_model = str(self.config.get("local_rembg_model", "birefnet-general") or "birefnet-general")
        local_rembg_model_index = self.local_rembg_model_combo.findData(local_rembg_model)
        self.local_rembg_model_combo.setCurrentIndex(local_rembg_model_index if local_rembg_model_index >= 0 else 0)

        self.local_rembg_edge_quality_combo = QComboBox()
        self.local_rembg_edge_quality_combo.addItem("Мягкий", "soft")
        self.local_rembg_edge_quality_combo.addItem("Обычный", "normal")
        self.local_rembg_edge_quality_combo.addItem("Четкий", "sharp")
        local_rembg_edge_quality = normalize_local_rembg_edge_quality(
            self.config.get("local_rembg_edge_quality", "normal")
        )
        local_rembg_edge_quality_index = self.local_rembg_edge_quality_combo.findData(local_rembg_edge_quality)
        self.local_rembg_edge_quality_combo.setCurrentIndex(
            local_rembg_edge_quality_index if local_rembg_edge_quality_index >= 0 else 1
        )

        self.local_ben2_refine_checkbox = QCheckBox("Уточнять передний план")
        self.local_ben2_refine_checkbox.setChecked(bool(self.config.get("local_ben2_refine_foreground", False)))
        self.local_ben2_download_note = QLabel(
            "При первом запуске будет загружена официальная ONNX-модель BEN2 — около 230 МБ. "
            "Нужен интернет; рекомендуется не менее 300 МБ свободного места. "
            "Во время обработки требуется около 4 ГБ свободной оперативной памяти. "
            "После загрузки обработка выполняется локально."
        )
        self.local_ben2_download_note.setWordWrap(True)
        self.local_ben2_download_note.setStyleSheet("color:#f0b44d;")
        self.local_ben2_alpha_threshold_spin = QSpinBox()
        self.local_ben2_alpha_threshold_spin.setRange(0, 255)
        self.local_ben2_alpha_threshold_spin.setValue(
            normalize_ben2_alpha_threshold(self.config.get("local_ben2_alpha_threshold", 24))
        )
        self.local_ben2_edge_softness_combo = QComboBox()
        for pixel_value in (0, 1, 2, 3):
            self.local_ben2_edge_softness_combo.addItem(f"{pixel_value} px", pixel_value)
        local_ben2_edge_softness = normalize_ben2_edge_softness(self.config.get("local_ben2_edge_softness", 0))
        local_ben2_edge_softness_index = self.local_ben2_edge_softness_combo.findData(local_ben2_edge_softness)
        self.local_ben2_edge_softness_combo.setCurrentIndex(
            local_ben2_edge_softness_index if local_ben2_edge_softness_index >= 0 else 0
        )
        self.local_ben2_corner_radius_combo = QComboBox()
        for pixel_value in (0, 1, 2, 3):
            self.local_ben2_corner_radius_combo.addItem(f"{pixel_value} px", pixel_value)
        local_ben2_corner_radius = normalize_ben2_corner_radius(self.config.get("local_ben2_corner_radius", 0))
        local_ben2_corner_radius_index = self.local_ben2_corner_radius_combo.findData(local_ben2_corner_radius)
        self.local_ben2_corner_radius_combo.setCurrentIndex(
            local_ben2_corner_radius_index if local_ben2_corner_radius_index >= 0 else 0
        )

        self.kie_remove_bg_model_combo = QComboBox()
        self.kie_remove_bg_model_combo.addItems(["recraft/remove-background"])
        rim = self.config.get("kie_remove_bg_model", "recraft/remove-background")
        ri_index = self.kie_remove_bg_model_combo.findText(rim)
        self.kie_remove_bg_model_combo.setCurrentIndex(ri_index if ri_index >= 0 else 0)
        self.kie_upscale_price_label = QLabel("")
        self.kie_upscale_price_label.setStyleSheet("color:#14b8a6; font-weight:700;")
        self.kie_upscale_price_label.setMinimumWidth(120)
        self.kie_upscale_after_price_label = QLabel("")
        self.kie_upscale_after_price_label.setStyleSheet("color:#14b8a6; font-weight:700;")
        self.kie_upscale_after_price_label.setMinimumWidth(120)
        self.kie_remove_bg_price_label = QLabel("")
        self.kie_remove_bg_price_label.setStyleSheet("color:#14b8a6; font-weight:700;")
        self.kie_remove_bg_price_label.setMinimumWidth(120)

        kie_upscale_model_widget = QWidget()
        kie_upscale_model_layout = QHBoxLayout(kie_upscale_model_widget)
        kie_upscale_model_layout.setContentsMargins(0, 0, 0, 0)
        kie_upscale_model_layout.setSpacing(8)
        kie_upscale_model_layout.addWidget(self.kie_upscale_model_combo)
        kie_upscale_model_layout.addWidget(self.kie_upscale_price_label)
        kie_upscale_model_layout.addStretch()

        kie_upscale_after_model_widget = QWidget()
        kie_upscale_after_model_layout = QHBoxLayout(kie_upscale_after_model_widget)
        kie_upscale_after_model_layout.setContentsMargins(0, 0, 0, 0)
        kie_upscale_after_model_layout.setSpacing(8)
        kie_upscale_after_model_layout.addWidget(self.kie_upscale_after_model_combo)
        kie_upscale_after_model_layout.addWidget(self.kie_upscale_after_price_label)
        kie_upscale_after_model_layout.addStretch()

        kie_remove_bg_model_widget = QWidget()
        kie_remove_bg_model_layout = QHBoxLayout(kie_remove_bg_model_widget)
        kie_remove_bg_model_layout.setContentsMargins(0, 0, 0, 0)
        kie_remove_bg_model_layout.setSpacing(8)
        kie_remove_bg_model_layout.addWidget(self.kie_remove_bg_model_combo)
        kie_remove_bg_model_layout.addWidget(self.kie_remove_bg_price_label)
        kie_remove_bg_model_layout.addStretch()

        process_settings_field_width = 190
        self.upscale_provider_combo.setFixedSize(process_settings_field_width, 32)
        self.upscale_after_provider_combo.setFixedSize(process_settings_field_width, 32)
        self.local_realesrgan_dir_input.setFixedSize(process_settings_field_width * 2 + 10, 32)
        self.local_realesrgan_profile_combo.setFixedSize(process_settings_field_width, 32)
        self.local_realesrgan_scale_combo.setFixedSize(110, 32)
        self.local_realesrgan_after_scale_combo.setFixedSize(110, 32)
        self.kie_upscale_model_combo.setFixedSize(process_settings_field_width, 32)
        self.kie_upscale_after_model_combo.setFixedSize(process_settings_field_width, 32)
        self.remove_bg_provider_combo.setFixedSize(process_settings_field_width, 32)
        self.local_rembg_profile_combo.setFixedSize(process_settings_field_width, 32)
        self.local_rembg_model_combo.setFixedSize(process_settings_field_width, 32)
        self.local_rembg_edge_quality_combo.setFixedSize(process_settings_field_width, 32)
        self.local_ben2_alpha_threshold_spin.setFixedSize(90, 32)
        self.local_ben2_edge_softness_combo.setFixedSize(72, 32)
        self.local_ben2_corner_radius_combo.setFixedSize(72, 32)
        self.kie_remove_bg_model_combo.setFixedSize(process_settings_field_width, 32)

        def make_processing_subgroup(title, rows):
            subgroup = QGroupBox(title)
            subgroup_layout = QGridLayout()
            subgroup_layout.setHorizontalSpacing(12)
            subgroup_layout.setVerticalSpacing(6)
            subgroup_layout.setColumnMinimumWidth(0, 320)
            subgroup_layout.setColumnStretch(1, 1)
            for row_index, (label_text, widget) in enumerate(rows):
                label_widget = QLabel(label_text)
                label_widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                subgroup_layout.addWidget(label_widget, row_index, 0)
                subgroup_layout.addWidget(
                    widget,
                    row_index,
                    1,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                )
            subgroup.setLayout(subgroup_layout)
            return subgroup

        upscale_before_group = make_processing_subgroup(
            "Апскейл до удаления фона",
            [
                ("Провайдер:", self.upscale_provider_combo),
                ("Модель KIE:", kie_upscale_model_widget),
                ("Масштаб Local Real-ESRGAN:", self.local_realesrgan_scale_combo),
                ("Профиль Local Real-ESRGAN:", self.local_realesrgan_profile_combo),
                ("Local Real-ESRGAN:", self.local_realesrgan_bundle_label),
            ],
        )
        upscale_after_group = make_processing_subgroup(
            "Апскейл после удаления фона",
            [
                ("Провайдер:", self.upscale_after_provider_combo),
                ("Модель KIE:", kie_upscale_after_model_widget),
                ("Масштаб Local Real-ESRGAN:", self.local_realesrgan_after_scale_combo),
                ("Важно:", self.upscale_after_note),
            ],
        )
        remove_background_group = make_processing_subgroup(
            "Удаление фона",
            [
                ("Провайдер:", self.remove_bg_provider_combo),
                ("Модель KIE:", kie_remove_bg_model_widget),
            ],
        )
        rembg_group = make_processing_subgroup(
            "Local rembg",
            [
                ("Профиль:", self.local_rembg_profile_combo),
                ("Модель:", self.local_rembg_model_combo),
                ("Край:", self.local_rembg_edge_quality_combo),
            ],
        )
        ben2_group = make_processing_subgroup(
            "BEN2: локальное уточнение маски",
            [
                ("Когда:", QLabel("При выборе BEN2: после апскейла до фона, до обрезки края")),
                ("Первая загрузка:", self.local_ben2_download_note),
                ("Уточнять передний план:", self.local_ben2_refine_checkbox),
                ("Порог прозрачности:", self.local_ben2_alpha_threshold_spin),
                ("Мягкость края:", self.local_ben2_edge_softness_combo),
                ("Радиус углов:", self.local_ben2_corner_radius_combo),
            ],
        )
        ben2_group.setToolTip(
            "BEN2 — отдельный локальный экспериментальный удалитель фона. "
            "Это не удаление водяных знаков; первый запуск может загружать модель."
        )
        process_settings_layout.addWidget(upscale_before_group)
        process_settings_layout.addWidget(upscale_after_group)
        process_settings_layout.addWidget(remove_background_group)
        process_settings_layout.addWidget(rembg_group)
        process_settings_layout.addWidget(ben2_group)
        process_settings_group.setLayout(process_settings_layout)
        process_tab_layout.addWidget(process_settings_group)
        process_tab_layout.addStretch()

        settings_tab_layout.addStretch()

        log_group = QGroupBox("Лог и прогресс")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(80)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        run_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_start.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_start.clicked.connect(self.start_work)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedSize(self.standard_button_width, self.standard_button_height)
        self.btn_stop.clicked.connect(self.stop_work)
        self.btn_stop.setEnabled(False)
        self.btn_start.setStyleSheet(self.primary_button_style)
        self.btn_stop.setStyleSheet(self.primary_button_style)
        run_layout.addWidget(self.btn_start)
        run_layout.addWidget(self.btn_stop)
        run_layout.addStretch()

        log_layout.addWidget(self.log_text)
        log_layout.addWidget(self.progress_bar)
        log_layout.addLayout(run_layout)
        log_group.setLayout(log_layout)
        log_group.setMinimumHeight(220)
        log_group.setMaximumHeight(260)
        main_layout.setStretch(2, 1)
        main_layout.setStretch(3, 0)
        main_layout.addWidget(log_group)

        self.refresh_generation_controls()
        self.refresh_processing_price_labels()
        self.update_visible_mark_controls_state()
        self.update_trim_controls_state()
        self.update_edge_shrink_controls_state()
        self.update_unsharp_controls_state()
        self.update_upscale_provider_controls_state()
        self.update_upscale_total_label()
        self.update_remove_bg_provider_controls_state()
        self.chk_visible_mark_cleanup.toggled.connect(self.update_visible_mark_controls_state)
        self.visible_mark_mode_combo.currentIndexChanged.connect(self.update_visible_mark_controls_state)
        self.chk_trim.toggled.connect(self.update_trim_controls_state)
        self.chk_edge_shrink.toggled.connect(self.update_edge_shrink_controls_state)
        self.chk_unsharp.toggled.connect(self.update_unsharp_controls_state)
        self.trim_mode_combo.currentIndexChanged.connect(self.update_trim_controls_state)
        self.upscale_provider_combo.currentIndexChanged.connect(self.update_upscale_provider_controls_state)
        self.upscale_after_provider_combo.currentIndexChanged.connect(self.update_upscale_provider_controls_state)
        self.chk_remove_bg.toggled.connect(self.update_upscale_provider_controls_state)
        self.chk_upscale_after.toggled.connect(self.update_upscale_provider_controls_state)
        self.chk_upscale.toggled.connect(self.update_upscale_total_label)
        self.chk_upscale_after.toggled.connect(self.update_upscale_total_label)
        self.local_realesrgan_scale_combo.currentIndexChanged.connect(self.update_upscale_total_label)
        self.local_realesrgan_after_scale_combo.currentIndexChanged.connect(self.update_upscale_total_label)
        self.kie_upscale_model_combo.currentIndexChanged.connect(self.update_upscale_total_label)
        self.kie_upscale_after_model_combo.currentIndexChanged.connect(self.update_upscale_total_label)
        self.remove_bg_provider_combo.currentIndexChanged.connect(self.update_remove_bg_provider_controls_state)
        self.on_mode_changed(True)

    def _normalize_generation_model_id(self, model_id):
        model = (model_id or "").strip()
        alias_map = {
            "gpt-image-1": "gpt-image/1.5-text-to-image",
            "gpt-image-1.5": "gpt-image/1.5-text-to-image",
            "gpt-image-2-text-to-image": "gpt-image-2",
            "gpt-image-2-image-to-image": "gpt-image-2",
            "google/pro-image-to-image": "nano-banana-pro",
            "flux-kontext": "black-forest-labs/flux-kontext-pro",
            "zai-org/z-image": "z-image",
        }
        if not model:
            return "gpt-image/1.5-text-to-image"
        return alias_map.get(model, model)

    def _model_type_title(self, model_type):
        return {
            "text_to_image": "Text→Image",
            "image_to_image": "Image→Image",
            "edit": "Edit",
        }.get(model_type or "", "Other")

    def populate_generation_models(self, combo_box, allowed_types, include_model_ids=None):
        combo_box.clear()
        extra_ids = set(include_model_ids or set())
        seen_model_ids = set()
        entries = list(GENERATION_MODELS)
        if extra_ids and not allowed_types:
            entries.sort(key=lambda item: 0 if item.get("type") in {"image_to_image", "edit"} else 1)
        for entry in entries:
            model_id = entry.get("id")
            model_type = entry.get("type")
            if model_id not in VISIBLE_GENERATION_MODEL_IDS and model_id not in extra_ids:
                continue
            if model_type not in allowed_types and model_id not in extra_ids:
                continue
            # For the reference combo prefer the image/edit declaration, not
            # the same model's text-to-image label shown earlier in the list.
            if model_id in seen_model_ids:
                continue
            label = entry.get("label", model_id or "")
            combo_box.addItem(label, model_id)
            seen_model_ids.add(model_id)

    def set_generation_model_selection(self, combo_box, model_id, allowed_types, fallback_id, include_model_ids=None):
        normalized = self._normalize_generation_model_id(model_id)
        model_meta = GENERATION_MODEL_META.get(normalized, {})
        extra_ids = set(include_model_ids or set())
        if normalized not in VISIBLE_GENERATION_MODEL_IDS and normalized not in extra_ids:
            normalized = fallback_id
        elif model_meta.get("type") not in allowed_types and normalized not in extra_ids:
            normalized = fallback_id

        idx = combo_box.findData(normalized)
        if idx >= 0:
            combo_box.setCurrentIndex(idx)
            return

        label_idx = combo_box.findText(str(model_id or "").strip())
        if label_idx >= 0:
            combo_box.setCurrentIndex(label_idx)
            return

        fallback_idx = combo_box.findData(fallback_id)
        combo_box.setCurrentIndex(fallback_idx if fallback_idx >= 0 else 0)

    def get_selected_generation_model_id(self, combo_box):
        model_id = combo_box.currentData()
        if not model_id:
            model_id = combo_box.currentText()
        return self._normalize_generation_model_id(model_id)

    def _get_model_capabilities(self, model_id):
        return get_model_capabilities(model_id)

    def _get_ordered_ratios_for_model(self, model_id, has_references=False):
        allowed = set(ratios_for_mode(model_id, has_references))
        if not allowed:
            return ["1:1"]
        ordered = [value for value in RATIO_OPTIONS_ORDER if value in allowed]
        return ordered or sorted(allowed)

    def _get_ordered_resolutions_for_model(self, model_id):
        allowed = self._get_model_capabilities(model_id)["resolutions"]
        if not allowed:
            return []
        ordered = [value for value in RESOLUTION_OPTIONS_ORDER if value in allowed]
        return ordered or sorted(allowed)

    def _set_combo_values(self, combo, values, preferred_value):
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        if not values:
            combo.blockSignals(False)
            return
        if preferred_value in values:
            combo.setCurrentText(preferred_value)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _format_model_price(self, model_id, selected_resolution):
        price_data = self._get_model_capabilities(model_id)["pricing"]
        if isinstance(price_data, dict):
            if selected_resolution in price_data:
                return price_data[selected_resolution]
            for fallback in RESOLUTION_OPTIONS_ORDER:
                if fallback in price_data:
                    return price_data[fallback]
            return next(iter(price_data.values())) if price_data else "-"
        return str(price_data or "-")

    def refresh_generation_controls(self, *_):
        text_model = self.get_selected_generation_model_id(self.text_generation_model_combo)
        reference_model = self.get_selected_generation_model_id(self.reference_generation_model_combo)
        preferred_text_ratio = self.text_ratio_combo.currentText().strip() or str(self.config.get("text_generation_ratio", "1:1") or "1:1")
        preferred_reference_ratio = self.reference_ratio_combo.currentText().strip() or str(self.config.get("reference_generation_ratio", "1:1") or "1:1")
        preferred_text_resolution = self.text_resolution_combo.currentText().strip() or str(self.config.get("text_generation_resolution", "1K") or "1K")
        preferred_reference_resolution = self.reference_resolution_combo.currentText().strip() or str(self.config.get("reference_generation_resolution", "1K") or "1K")

        self._set_combo_values(
            self.text_ratio_combo,
            self._get_ordered_ratios_for_model(text_model),
            preferred_text_ratio,
        )
        self._set_combo_values(
            self.reference_ratio_combo,
            self._get_ordered_ratios_for_model(reference_model, has_references=True),
            preferred_reference_ratio,
        )

        text_resolutions = self._get_ordered_resolutions_for_model(text_model)
        ref_resolutions = self._get_ordered_resolutions_for_model(reference_model)
        self._set_combo_values(
            self.text_resolution_combo,
            text_resolutions or ["—"],
            preferred_text_resolution,
        )
        self._set_combo_values(
            self.reference_resolution_combo,
            ref_resolutions or ["—"],
            preferred_reference_resolution,
        )
        self.text_resolution_combo.setEnabled(bool(text_resolutions))
        self.reference_resolution_combo.setEnabled(bool(ref_resolutions))

        self.refresh_generation_price_labels()
        self.schedule_settings_save()

    def refresh_generation_price_labels(self, *_):
        text_model = self.get_selected_generation_model_id(self.text_generation_model_combo)
        reference_model = self.get_selected_generation_model_id(self.reference_generation_model_combo)
        text_resolution = self.text_resolution_combo.currentText().strip()
        reference_resolution = self.reference_resolution_combo.currentText().strip()
        self.text_model_price_label.setText(self._format_model_price(text_model, text_resolution))
        self.reference_model_price_label.setText(self._format_model_price(reference_model, reference_resolution))

    def refresh_processing_price_labels(self, *_):
        upscale_model = self.kie_upscale_model_combo.currentText().strip()
        upscale_after_model = self.kie_upscale_after_model_combo.currentText().strip()
        remove_bg_model = self.kie_remove_bg_model_combo.currentText().strip()
        self.kie_upscale_price_label.setText(PROCESSING_PRICING.get(upscale_model, "-"))
        self.kie_upscale_after_price_label.setText(PROCESSING_PRICING.get(upscale_after_model, "-"))
        self.kie_remove_bg_price_label.setText(PROCESSING_PRICING.get(remove_bg_model, "-"))

    def create_template_values_table(self, placeholder_prefix):
        table = QTableWidget(0, 2)
        table.horizontalHeader().hide()
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 36)
        table.setWordWrap(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setMinimumHeight(100)
        table.setProperty("placeholderPrefix", placeholder_prefix)
        return table

    def create_template_column(self, title, table):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"{title}:"))
        header_layout.addStretch()
        layout.addLayout(header_layout)
        layout.addWidget(table)
        return container

    def add_template_value_row(self, table):
        row = table.rowCount()
        table.insertRow(row)
        prefix = str(table.property("placeholderPrefix") or "")
        item = QTableWidgetItem("")
        item.setToolTip(f"{prefix}: значение для подстановки")
        table.setItem(row, 0, item)

        delete_btn = QPushButton("🗑")
        delete_btn.setToolTip("Удалить строку")
        delete_btn.setMinimumHeight(24)
        delete_btn.clicked.connect(lambda _, r=row, t=table: self.remove_template_value_row(t, r))
        table.setCellWidget(row, 1, delete_btn)
        table.setCurrentCell(row, 0)
        table.editItem(item)

    def remove_template_value_row(self, table, row_index):
        if 0 <= row_index < table.rowCount():
            table.removeRow(row_index)
            self.refresh_template_value_delete_buttons(table)

    def refresh_template_value_delete_buttons(self, table):
        for row in range(table.rowCount()):
            delete_btn = QPushButton("🗑")
            delete_btn.setToolTip("Удалить строку")
            delete_btn.setMinimumHeight(24)
            delete_btn.clicked.connect(lambda _, r=row, t=table: self.remove_template_value_row(t, r))
            table.setCellWidget(row, 1, delete_btn)

    def get_template_values(self, table):
        values = []
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            text = (item.text() if item else "").strip()
            if text:
                values.append(text)
        return values

    def setup_settings_autosave_connections(self):
        self.kie_api_key_input.textChanged.connect(self.schedule_settings_save)
        self.kie_api_key_input.textChanged.connect(self.on_api_key_changed)
        self.fal_api_key_input.textChanged.connect(self.schedule_settings_save)
        self.photoroom_api_key_input.textChanged.connect(self.schedule_settings_save)
        self.text_generation_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.reference_generation_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.text_generation_model_combo.currentTextChanged.connect(self.refresh_generation_controls)
        self.reference_generation_model_combo.currentTextChanged.connect(self.refresh_generation_controls)
        self.text_ratio_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.text_resolution_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.text_ratio_combo.currentTextChanged.connect(self.refresh_generation_price_labels)
        self.text_resolution_combo.currentTextChanged.connect(self.refresh_generation_price_labels)
        self.reference_ratio_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.reference_resolution_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.reference_ratio_combo.currentTextChanged.connect(self.refresh_generation_price_labels)
        self.reference_resolution_combo.currentTextChanged.connect(self.refresh_generation_price_labels)
        self.chk_visible_mark_cleanup.toggled.connect(self.schedule_settings_save)
        self.visible_mark_mode_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.chk_upscale.toggled.connect(self.schedule_settings_save)
        self.chk_upscale_after.toggled.connect(self.schedule_settings_save)
        self.chk_remove_bg.toggled.connect(self.schedule_settings_save)
        self.chk_trim.toggled.connect(self.schedule_settings_save)
        self.chk_unsharp.toggled.connect(self.schedule_settings_save)
        self.chk_export_300_dpi.toggled.connect(self.schedule_settings_save)
        self.chk_edge_shrink.toggled.connect(self.schedule_settings_save)
        self.chk_cleanup_all.toggled.connect(self.schedule_settings_save)
        self.edge_shrink_pixels_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.trim_mode_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.unsharp_amount_spin.valueChanged.connect(self.schedule_settings_save)
        self.unsharp_radius_spin.valueChanged.connect(self.schedule_settings_save)
        self.unsharp_threshold_spin.valueChanged.connect(self.schedule_settings_save)
        self.upscale_provider_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.upscale_after_provider_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.local_realesrgan_dir_input.textChanged.connect(self.schedule_settings_save)
        self.local_realesrgan_profile_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.local_realesrgan_scale_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.local_realesrgan_after_scale_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.kie_upscale_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.kie_upscale_model_combo.currentTextChanged.connect(self.refresh_processing_price_labels)
        self.kie_upscale_after_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.kie_upscale_after_model_combo.currentTextChanged.connect(self.refresh_processing_price_labels)
        self.remove_bg_provider_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.local_rembg_profile_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.local_rembg_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.local_rembg_edge_quality_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.local_ben2_refine_checkbox.toggled.connect(self.schedule_settings_save)
        self.local_ben2_alpha_threshold_spin.valueChanged.connect(self.schedule_settings_save)
        self.local_ben2_edge_softness_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.local_ben2_corner_radius_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.kie_remove_bg_model_combo.currentTextChanged.connect(self.schedule_settings_save)
        self.kie_remove_bg_model_combo.currentTextChanged.connect(self.refresh_processing_price_labels)
        self.radio_run_generate.toggled.connect(self.schedule_settings_save)
        self.radio_run_process.toggled.connect(self.schedule_settings_save)
        self.radio_run_both.toggled.connect(self.schedule_settings_save)

    def schedule_settings_save(self, *_):
        self.settings_save_timer.start()

    def update_visible_mark_controls_state(self, *_):
        enabled = self.chk_visible_mark_cleanup.isChecked()
        self.visible_mark_settings.set_enabled_state(enabled)

    def update_trim_controls_state(self, *_):
        trim_enabled = self.chk_trim.isChecked()
        self.trim_mode_combo.setEnabled(trim_enabled)

    def update_edge_shrink_controls_state(self, *_):
        self.edge_shrink_pixels_combo.setEnabled(self.chk_edge_shrink.isChecked())

    def update_unsharp_controls_state(self, *_):
        unsharp_enabled = self.chk_unsharp.isChecked()
        self.unsharp_amount_spin.setEnabled(unsharp_enabled)
        self.unsharp_radius_spin.setEnabled(unsharp_enabled)
        self.unsharp_threshold_spin.setEnabled(unsharp_enabled)

    def update_upscale_provider_controls_state(self, *_):
        before_is_local = self.upscale_provider_combo.currentData() == "local_realesrgan"
        after_is_local = self.upscale_after_provider_combo.currentData() == "local_realesrgan"
        after_recraft_blocked = bool(
            self.chk_remove_bg.isChecked()
            and self.chk_upscale_after.isChecked()
            and not after_is_local
        )
        recraft_index = self.kie_upscale_after_model_combo.findText("recraft/crisp-upscale")
        if recraft_index >= 0:
            recraft_item = self.kie_upscale_after_model_combo.model().item(recraft_index)
            recraft_item.setEnabled(not after_recraft_blocked)
        if after_recraft_blocked:
            self.upscale_after_note.setText(
                "Recraft Crisp недоступен после удаления фона: модель не поддерживает "
                "прозрачный вход. Используйте Local Real-ESRGAN или включите Recraft Crisp "
                "до удаления фона."
            )
        else:
            self.upscale_after_note.setText(
                "После удаления фона рекомендуется Local Real-ESRGAN, потому что "
                "Recraft Crisp не поддерживает прозрачные входные изображения."
            )
        self.local_realesrgan_dir_input.setEnabled(before_is_local or after_is_local)
        self.local_realesrgan_profile_combo.setEnabled(before_is_local or after_is_local)
        self.local_realesrgan_scale_combo.setEnabled(before_is_local)
        self.local_realesrgan_after_scale_combo.setEnabled(after_is_local)
        self.kie_upscale_model_combo.setEnabled(not before_is_local)
        self.kie_upscale_price_label.setEnabled(not before_is_local)
        self.kie_upscale_after_model_combo.setEnabled(not after_is_local)
        self.kie_upscale_after_price_label.setEnabled(not after_is_local)
        self.update_upscale_total_label()

    def _ui_upscale_pass_factor(self, provider_combo, local_scale_combo, kie_model_combo):
        if provider_combo.currentData() == "local_realesrgan":
            return normalize_local_realesrgan_scale(local_scale_combo.currentData() or 4)
        if provider_combo.currentData() == "fal":
            return normalize_fal_upscale_factor(
                self.config.get("fal_upscale_model", FAL_BRIA_UPSCALE_MODEL_ID),
                self.config.get("fal_upscale_scale", 2),
            )
        model_name = kie_model_combo.currentText().strip()
        if model_name == KIE_TOPAZ_MODEL_ID:
            return normalize_topaz_upscale_factor(
                self.config.get("upscale_factor", 4)
            )
        return 4

    def update_upscale_total_label(self, *_):
        factor = 1
        if self.chk_upscale.isChecked():
            factor *= self._ui_upscale_pass_factor(
                self.upscale_provider_combo,
                self.local_realesrgan_scale_combo,
                self.kie_upscale_model_combo,
            )
        if self.chk_upscale_after.isChecked():
            factor *= self._ui_upscale_pass_factor(
                self.upscale_after_provider_combo,
                self.local_realesrgan_after_scale_combo,
                self.kie_upscale_after_model_combo,
            )
        self.upscale_total_label.setText(f"Итоговый масштаб: {factor}x")

    def update_remove_bg_provider_controls_state(self, *_):
        is_kie = self.remove_bg_provider_combo.currentData() == "kie"
        is_local_rembg = self.remove_bg_provider_combo.currentData() == "local_rembg"
        is_local_ben2 = self.remove_bg_provider_combo.currentData() == "local_ben2"
        self.kie_remove_bg_model_combo.setEnabled(is_kie)
        self.kie_remove_bg_price_label.setEnabled(is_kie)
        self.local_rembg_profile_combo.setEnabled(is_local_rembg)
        self.local_rembg_model_combo.setEnabled(is_local_rembg)
        self.local_rembg_edge_quality_combo.setEnabled(is_local_rembg)
        self.local_ben2_refine_checkbox.setEnabled(is_local_ben2)
        self.local_ben2_alpha_threshold_spin.setEnabled(is_local_ben2)
        self.local_ben2_edge_softness_combo.setEnabled(is_local_ben2)
        self.local_ben2_corner_radius_combo.setEnabled(is_local_ben2)

    def on_mode_changed(self, checked):
        is_process = self.radio_run_process.isChecked()
        if hasattr(self, "tabs"):
            self.tabs.setCurrentIndex(1 if is_process else 0)

    def select_work_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Выбрать рабочую папку")
        if path:
            self.work_dir = path
            self.lbl_work_dir.setText(f"Рабочая папка: {path}")
            os.makedirs(os.path.join(path, "raw"), exist_ok=True)
            os.makedirs(os.path.join(path, "output"), exist_ok=True)
            self.config["last_work_dir"] = path
            self.save_config()
            self.log(f"Созданы/проверены папки raw и output в {path}")

    def restore_last_work_dir(self):
        last_work_dir = str(self.config.get("last_work_dir", "")).strip()
        if not last_work_dir or not os.path.isdir(last_work_dir):
            return
        self.work_dir = last_work_dir
        self.lbl_work_dir.setText(f"Рабочая папка: {last_work_dir}")
        os.makedirs(os.path.join(last_work_dir, "raw"), exist_ok=True)
        os.makedirs(os.path.join(last_work_dir, "output"), exist_ok=True)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выбрать изображения",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All files (*.*)",
        )
        if files:
            self.selected_files = files
            self.lbl_files_count.setText(f"Выбрано файлов: {len(files)}")
            self.log(f"Выбрано файлов: {len(files)}")

    def collect_visible_mark_regions(self):
        confirmed_regions = {}
        for file_path in self.selected_files:
            try:
                dialog = VisibleMarkRegionDialog(file_path, self)
            except Exception as error:
                QMessageBox.warning(
                    self,
                    "Область видимой метки",
                    f"Не удалось открыть {os.path.basename(file_path)}: {error}",
                )
                return None

            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            region = dialog.selected_region()
            if region is not None:
                confirmed_regions[visible_mark_region_key(file_path)] = region
        return confirmed_regions

    def add_prompt_row(self):
        self.generated_prompts.append({"prompt": "", "references": []})
        self.refresh_prompts_table()
        self.save_prompts_storage()
        row_index = len(self.generated_prompts) - 1
        self.table.setCurrentCell(row_index, 0)
        self.table.editItem(self.table.item(row_index, 0))

    def _normalize_prompt_entry(self, entry):
        parsed_entry = entry
        if isinstance(entry, str):
            raw_text = entry.strip()
            if raw_text.startswith("{") and raw_text.endswith("}"):
                for parser in (json.loads, ast.literal_eval):
                    try:
                        candidate = parser(raw_text)
                        if isinstance(candidate, dict):
                            parsed_entry = candidate
                            break
                    except Exception:
                        continue

        if isinstance(parsed_entry, dict):
            prompt_text = str(parsed_entry.get("prompt", "")).strip()
            references = split_references(parsed_entry.get("references", []))
            return {"prompt": prompt_text, "references": references[:MAX_REFERENCES_PER_PROMPT]}

        return {"prompt": str(entry).strip(), "references": []}

    def _pick_reference_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выбрать референсы",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        return [f for f in files if str(f).strip()]

    def _merge_references(self, existing, additions):
        result = []
        for item in split_references(existing) + split_references(additions):
            if item not in result:
                result.append(item)
        if len(result) > MAX_REFERENCES_PER_PROMPT:
            result = result[:MAX_REFERENCES_PER_PROMPT]
        return result

    def _set_row_references(self, row_index, references):
        if not (0 <= row_index < len(self.generated_prompts)):
            return
        current_entry = self.generated_prompts[row_index]
        if not isinstance(current_entry, dict):
            current_entry = {"prompt": str(current_entry), "references": []}
        current_entry["references"] = split_references(references)[:MAX_REFERENCES_PER_PROMPT]
        self.generated_prompts[row_index] = current_entry
        self.refresh_prompts_table()
        self.save_prompts_storage()

    def _get_selected_prompt_rows(self):
        selection_model = self.table.selectionModel()
        if selection_model is None:
            return []
        rows = sorted({index.row() for index in selection_model.selectedRows()})
        return [row for row in rows if 0 <= row < len(self.generated_prompts)]

    def add_references_to_selected_prompts(self):
        if not self.generated_prompts:
            QMessageBox.warning(self, "Референсы", "Список промптов пуст")
            return

        selected_rows = self._get_selected_prompt_rows()
        if not selected_rows:
            QMessageBox.warning(self, "Референсы", "Выделите хотя бы одну строку")
            return

        files = self._pick_reference_files()
        if not files:
            return

        for idx in selected_rows:
            current = self._normalize_prompt_entry(self.generated_prompts[idx])
            current["references"] = self._merge_references(current.get("references", []), files)
            self.generated_prompts[idx] = current

        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Референсы добавлены к строкам: {len(selected_rows)} | Файлов: {len(files)}")

    def clear_references_for_selected_prompts(self):
        if not self.generated_prompts:
            QMessageBox.warning(self, "Референсы", "Список промптов пуст")
            return

        selected_rows = self._get_selected_prompt_rows()
        if not selected_rows:
            QMessageBox.warning(self, "Референсы", "Выделите хотя бы одну строку")
            return

        for idx in selected_rows:
            current = self._normalize_prompt_entry(self.generated_prompts[idx])
            current["references"] = []
            self.generated_prompts[idx] = current

        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Референсы очищены у строк: {len(selected_rows)}")

    def open_prompt_editor(self, row_index):
        if not (0 <= row_index < len(self.generated_prompts)):
            return
        entry = self._normalize_prompt_entry(self.generated_prompts[row_index])
        self.generated_prompts[row_index] = entry

        dialog = PromptReferencesDialog(entry.get("prompt", ""), entry.get("references", []), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        prompt_text, references = dialog.get_data()
        self.generated_prompts[row_index] = {
            "prompt": prompt_text,
            "references": split_references(references),
        }
        self.refresh_prompts_table()
        self.save_prompts_storage()

    def open_prompt_references(self, row_index):
        if not (0 <= row_index < len(self.generated_prompts)):
            return
        entry = self._normalize_prompt_entry(self.generated_prompts[row_index])
        self.generated_prompts[row_index] = entry

        dialog = PromptReferencesDialog(entry.get("prompt", ""), entry.get("references", []), self, refs_only=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        _, references = dialog.get_data()
        entry["references"] = split_references(references)
        self.generated_prompts[row_index] = entry
        self.refresh_prompts_table()
        self.save_prompts_storage()

    def pick_references_for_prompt_row(self, row_index):
        if not (0 <= row_index < len(self.generated_prompts)):
            return
        files = self._pick_reference_files()
        if not files:
            return

        entry = self._normalize_prompt_entry(self.generated_prompts[row_index])
        entry["references"] = self._merge_references(entry.get("references", []), files)
        self.generated_prompts[row_index] = entry
        self.refresh_prompts_table()
        self.save_prompts_storage()

    def replace_references_for_prompt_row(self, row_index):
        if not (0 <= row_index < len(self.generated_prompts)):
            return
        files = self._pick_reference_files()
        if files:
            self._set_row_references(row_index, files)

    def remove_references_for_prompt_row(self, row_index):
        if 0 <= row_index < len(self.generated_prompts):
            self._set_row_references(row_index, [])

    def on_prompt_item_double_clicked(self, item):
        if item.column() in {0, 1}:
            self.open_prompt_editor(item.row())

    def build_prompts(self):
        if not hasattr(self, "master_prompt"):
            self.log("Шаблонный режим промптов отключён в текущем интерфейсе")
            return
        template = self.master_prompt.toPlainText().strip()
        a = self.get_template_values(self.field_a)
        b = self.get_template_values(self.field_b)
        c = self.get_template_values(self.field_c)

        if not template:
            QMessageBox.warning(self, "Ошибка", "Введите Master Prompt")
            return

        self.generated_prompts = []
        max_len = max(len(a), len(b), len(c))
        if max_len == 0:
            self.generated_prompts = [{"prompt": template, "references": []}]
        else:
            for i in range(max_len):
                prompt = template
                if a and i < len(a):
                    prompt = prompt.replace("{A}", a[i])
                if b and i < len(b):
                    prompt = prompt.replace("{B}", b[i])
                if c and i < len(c):
                    prompt = prompt.replace("{C}", c[i])
                self.generated_prompts.append({"prompt": prompt, "references": []})
        self.refresh_prompts_table()

        self.log(f"Создано промптов: {len(self.generated_prompts)}")

    def build_prompts_from_template_inputs(self):
        if not hasattr(self, "master_prompt"):
            return []
        template = self.master_prompt.toPlainText().strip()
        if not template:
            return []

        a = self.get_template_values(self.field_a)
        b = self.get_template_values(self.field_b)
        c = self.get_template_values(self.field_c)

        prompts = []
        max_len = max(len(a), len(b), len(c))
        if max_len == 0:
            prompts = [template]
        else:
            for i in range(max_len):
                prompt = template
                if a and i < len(a):
                    prompt = prompt.replace("{A}", a[i])
                if b and i < len(b):
                    prompt = prompt.replace("{B}", b[i])
                if c and i < len(c):
                    prompt = prompt.replace("{C}", c[i])
                prompts.append(prompt)
        return [p.strip() for p in prompts if p.strip()]

    def get_list_mode_prompts(self):
        entries = []
        for entry in self.generated_prompts:
            normalized_entry = self._normalize_prompt_entry(entry)
            prompt_text = str(normalized_entry.get("prompt", "")).strip()
            references = split_references(normalized_entry.get("references", []))
            if prompt_text or references:
                entries.append({"prompt": prompt_text, "references": references})
        return entries

    def import_prompts_from_template(self):
        if not hasattr(self, "master_prompt"):
            QMessageBox.warning(self, "Ошибка", "Шаблонный режим промптов недоступен")
            return
        raw_text = self.master_prompt.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "Ошибка", "Вставьте список промптов в поле Master Prompt")
            return

        prompts = self._split_prompts_text(raw_text)
        if not prompts:
            QMessageBox.warning(self, "Ошибка", "Не удалось распознать промпты")
            return

        self.generated_prompts = [{"prompt": p, "references": []} for p in prompts]
        self.refresh_prompts_table()
        self.log(f"Импортировано промптов: {len(self.generated_prompts)}")

    def on_table_bulk_paste(self, raw_text):
        prompts = self._split_prompts_text(raw_text)
        self.generated_prompts = [{"prompt": p, "references": []} for p in prompts]
        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Вставлено промптов: {len(self.generated_prompts)}")

    def import_prompts_from_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбрать CSV-файл с промптами",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if not file_path:
            return

        dialog = CsvImportDialog(file_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        imported_entries = dialog.get_entries()
        if not imported_entries:
            QMessageBox.warning(self, "Импорт CSV", "Не найдено ни одной записи для импорта")
            return

        choice_box = QMessageBox(self)
        choice_box.setIcon(QMessageBox.Icon.Question)
        choice_box.setWindowTitle("Импорт CSV")
        choice_box.setText(f"Найдено записей: {len(imported_entries)}")
        choice_box.setInformativeText("Как импортировать список?")
        replace_btn = choice_box.addButton("Заменить текущие", QMessageBox.ButtonRole.AcceptRole)
        append_btn = choice_box.addButton("Добавить к текущим", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = choice_box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        choice_box.setDefaultButton(replace_btn)
        choice_box.exec()

        clicked = choice_box.clickedButton()
        if clicked == cancel_btn or clicked is None:
            return
        if clicked == replace_btn:
            self.generated_prompts = imported_entries
            self.log(f"CSV импорт: заменено записей: {len(imported_entries)}")
        elif clicked == append_btn:
            self.generated_prompts.extend(imported_entries)
            self.log(f"CSV импорт: добавлено записей: {len(imported_entries)}")
        else:
            return

        self.refresh_prompts_table()
        self.save_prompts_storage()

    def _split_prompts_text(self, raw_text):
        text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return []

        if "\t" in text:
            prompts = []
            for line in text.split("\n"):
                for cell in line.split("\t"):
                    item = cell.strip()
                    if item:
                        prompts.append(item)
            if prompts:
                return prompts

        blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
        if blocks:
            return blocks

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) > 1:
            return lines

        return [text]

    def refresh_prompts_table(self):
        self.is_updating_prompts_table = True
        self.table.setRowCount(0)
        for index, entry in enumerate(self.generated_prompts):
            normalized_entry = self._normalize_prompt_entry(entry)
            self.generated_prompts[index] = normalized_entry
            row = self.table.rowCount()
            self.table.insertRow(row)
            prompt_text = str(normalized_entry.get("prompt", ""))
            references_count = len(split_references(normalized_entry.get("references", [])))
            references_text = str(references_count)

            prompt_item = QTableWidgetItem(prompt_text)
            references_item = QTableWidgetItem(references_text)
            references_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            references_item.setFlags(references_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, prompt_item)
            self.table.setItem(row, 1, references_item)

            delete_btn = QPushButton("🗑")
            delete_btn.setToolTip("Удалить запись")
            delete_btn.setMinimumHeight(28)
            delete_btn.clicked.connect(lambda _, r=index: self.remove_prompt_row(r))

            edit_btn = QPushButton("🖼")
            edit_btn.setToolTip("Выбрать файлы референсов")
            edit_btn.setMinimumHeight(28)
            edit_btn.clicked.connect(lambda _, r=index: self.pick_references_for_prompt_row(r))

            replace_btn = QPushButton("🖼↻")
            replace_btn.setToolTip("Заменить референсы")
            replace_btn.setMinimumHeight(28)
            replace_btn.clicked.connect(lambda _, r=index: self.replace_references_for_prompt_row(r))
            remove_ref_btn = QPushButton("🖼−")
            remove_ref_btn.setToolTip("Удалить референсы")
            remove_ref_btn.setMinimumHeight(28)
            remove_ref_btn.clicked.connect(lambda _, r=index: self.remove_references_for_prompt_row(r))
            self.table.setCellWidget(row, 2, edit_btn)
            self.table.setCellWidget(row, 3, replace_btn)
            self.table.setCellWidget(row, 4, remove_ref_btn)
            self.table.setCellWidget(row, 5, delete_btn)
        self.is_updating_prompts_table = False

    def _build_references_tooltip(self, references):
        items = split_references(references)
        if not items:
            return ""
        html_parts = ["<div><b>Референсы:</b></div>"]
        for ref in items[:3]:
            normalized_path = os.path.abspath(ref) if os.path.isfile(ref) else ""
            label = os.path.basename(ref) or ref
            if normalized_path:
                img_src = normalized_path.replace("\\", "/")
                html_parts.append(f"<div style='margin-top:4px;'><div>{label}</div><img src='file:///{img_src}' width='140'></div>")
            else:
                html_parts.append(f"<div style='margin-top:4px;'>{label}</div>")
        if len(items) > 3:
            html_parts.append(f"<div style='margin-top:4px;'>И ещё: {len(items) - 3}</div>")
        return "".join(html_parts)

    def on_prompt_item_changed(self, item):
        if self.is_updating_prompts_table:
            return
        if item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.generated_prompts):
            current_entry = self._normalize_prompt_entry(self.generated_prompts[row])
            current_entry["prompt"] = item.text()
            self.generated_prompts[row] = current_entry
            self.save_prompts_storage()

    def remove_prompt_row(self, row_index):
        if row_index < 0 or row_index >= len(self.generated_prompts):
            return
        del self.generated_prompts[row_index]
        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log(f"Удалена запись. Осталось: {len(self.generated_prompts)}")

    def clear_all_prompts(self):
        self.generated_prompts = []
        self.refresh_prompts_table()
        self.save_prompts_storage()
        self.log("Список записей очищен")

    def export_prompts(self):
        entries = self.get_list_mode_prompts()
        if not entries:
            QMessageBox.warning(self, "Экспорт CSV", "Нет записей для экспорта")
            return

        base_dir = self.work_dir if self.work_dir else os.getcwd()
        default_path = os.path.join(base_dir, "prompts_export.csv")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить CSV с промптами",
            default_path,
            "CSV files (*.csv)",
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".csv"):
            file_path = f"{file_path}.csv"

        try:
            from v3_prompt_csv_import import write_prompt_csv_atomic

            write_prompt_csv_atomic(file_path, entries)
            self.log(f"CSV экспортирован: {file_path}")
            QMessageBox.information(
                self,
                "Экспорт CSV",
                "Файл успешно экспортирован.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Экспорт CSV", f"Не удалось сохранить CSV: {e}")

    def _get_model_label(self, model_id):
        normalized = self._normalize_generation_model_id(model_id)
        for entry in GENERATION_MODELS:
            if entry.get("id") == normalized:
                return str(entry.get("label") or normalized)
        return normalized

    def _is_model_unavailable_error(self, message):
        text = str(message or "").lower()
        markers = [
            "model not supported",
            "not supported",
            "model unavailable",
            "unsupported model",
            "не поддерж",
            "недоступ",
        ]
        return any(marker in text for marker in markers)

    def _select_combo_model_id(self, combo_box, model_id):
        idx = combo_box.findData(model_id)
        if idx >= 0:
            combo_box.setCurrentIndex(idx)
            return True
        return False

    def _is_model_compatible_for_references(self, model_id):
        normalized = self._normalize_generation_model_id(model_id)
        model_meta = GENERATION_MODEL_META.get(normalized, {})
        model_type = model_meta.get("type")
        if model_type in {"image_to_image", "edit"}:
            return True
        return bool(self._get_model_capabilities(normalized)["reference_compatible_text"])

    def _ensure_mode_compatible_model_with_prompt(
        self,
        combo_box,
        selected_model_id,
        fallback_model_id,
        needs_references,
        reason_text,
    ):
        selected_model = self._normalize_generation_model_id(selected_model_id)
        fallback_model = self._normalize_generation_model_id(fallback_model_id)

        compatible = self._is_model_compatible_for_references(selected_model) if needs_references else (
            (GENERATION_MODEL_META.get(selected_model) or {}).get("type") == "text_to_image"
        )
        if compatible:
            return True

        selected_label = self._get_model_label(selected_model)
        fallback_label = self._get_model_label(fallback_model)
        answer = QMessageBox.question(
            self,
            "Модель не подходит для режима",
            (
                f'Модель "{selected_label}" не подходит для текущего режима.\n'
                f"Причина: {reason_text}\n\n"
                f'Заменить на модель по умолчанию "{fallback_label}"?'
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.log("Запуск остановлен: пользователь отказался от замены несовместимой модели")
            return False

        if selected_model == fallback_model:
            QMessageBox.warning(
                self,
                "Модель не подходит для режима",
                f'Модель по умолчанию "{fallback_label}" тоже не подходит. Запуск остановлен.',
            )
            self.log(f"Запуск остановлен: модель по умолчанию '{fallback_label}' не подходит для режима")
            return False

        self.log(
            f"Модель '{selected_label}' не подходит для режима ({reason_text}). "
            f"Переключаемся на '{fallback_label}'."
        )
        self._select_combo_model_id(combo_box, fallback_model)
        return True

    def _probe_model_with_fallback_prompt(
        self,
        combo_box,
        preferred_model_id,
        fallback_model_id,
        ratio,
        headers,
        timeout,
        probe_reference_urls=None,
        runtime_settings=None,
    ):
        selected_model = self._normalize_generation_model_id(preferred_model_id)
        fallback_model = self._normalize_generation_model_id(fallback_model_id)
        if is_fal_generation_model(selected_model):
            # Fal queue requests are paid; availability is checked only by the
            # explicit user-confirmed run, never by an implicit probe.
            self._select_combo_model_id(combo_box, selected_model)
            return True
        probe_settings = dict(runtime_settings or self.config)
        probe_settings["kie_api_key"] = self.secret_settings.get("kie_api_key", "").strip()
        probe_settings["photoroom_api_key"] = self.secret_settings.get("photoroom_api_key", "").strip()
        probe_settings["fal_api_key"] = self.secret_settings.get("fal_api_key", "").strip()
        probe_worker = WorkerThread(
            "mode1_generate_only",
            self.work_dir or os.getcwd(),
            probe_settings,
            selected_files=[],
            generated_prompts=[],
        )

        while True:
            ok, error_message, _ = probe_worker._probe_model_with_ratio(
                selected_model,
                ratio,
                headers,
                timeout,
                reference_urls=probe_reference_urls,
            )
            if ok:
                self._select_combo_model_id(combo_box, selected_model)
                return True

            if probe_reference_urls and self._is_schema_required_error(error_message):
                self.log(
                    "Reference-model preflight skipped: the API requires fields that are only available during the real run."
                )
                return True

            if not self._is_model_unavailable_error(error_message):
                safe_message = safe_error_text(
                    error_message,
                    (probe_settings.get("kie_api_key", ""),),
                )
                self.log(f"Запуск остановлен: проверка модели не завершена ({safe_message})")
                QMessageBox.warning(
                    self,
                    "Проверка модели",
                    "Не удалось безопасно проверить модель. Запуск остановлен, чтобы не дублировать платный запрос.",
                )
                return False

            unavailable_label = self._get_model_label(selected_model)
            fallback_label = self._get_model_label(fallback_model)
            answer = QMessageBox.question(
                self,
                "Модель недоступна",
                (
                    f'Модель "{unavailable_label}" недоступна.\n'
                    f'Заменить на модель по умолчанию "{fallback_label}"?'
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.log("Запуск остановлен: пользователь отказался от замены недоступной модели")
                return False

            if selected_model == fallback_model:
                QMessageBox.warning(
                    self,
                    "Модель недоступна",
                    f'Модель по умолчанию "{fallback_label}" тоже недоступна. Запуск остановлен.',
                )
                self.log(f"Запуск остановлен: модель по умолчанию '{fallback_label}' недоступна")
                return False

            self.log(f"Модель '{unavailable_label}' недоступна. Переключаемся на '{fallback_label}'.")
            selected_model = fallback_model

    def _ensure_models_available_before_run(self, run_mode, prompts, runtime_settings=None):
        if run_mode == "process_only":
            return True

        references_needed = False
        for entry in prompts or []:
            if isinstance(entry, dict) and split_references(entry.get("references", [])):
                references_needed = True
                break

        text_model = self.get_selected_generation_model_id(self.text_generation_model_combo)
        if not self._ensure_mode_compatible_model_with_prompt(
            combo_box=self.text_generation_model_combo,
            selected_model_id=text_model,
            fallback_model_id="gpt-image/1.5-text-to-image",
            needs_references=False,
            reason_text="эта модель работает только с референсным изображением (image-to-image/edit)",
        ):
            return False

        if references_needed:
            reference_model = self.get_selected_generation_model_id(self.reference_generation_model_combo)
            if not self._ensure_mode_compatible_model_with_prompt(
                combo_box=self.reference_generation_model_combo,
                selected_model_id=reference_model,
                fallback_model_id="gpt-image/1.5-image-to-image",
                needs_references=True,
                reason_text="для записей с референсами нужна image-to-image/edit модель",
            ):
                return False

        # Automatic preflight is deliberately local. KIE createTask may spend
        # credits, so a network probe is allowed only through the explicit
        # user action that checks the selected models.
        return True

    def _uses_local_realesrgan_for_run(self, run_mode):
        if run_mode not in {"process_only", "both"}:
            return False
        return (
            self.chk_upscale.isChecked()
            and self.upscale_provider_combo.currentData() == "local_realesrgan"
        ) or (
            self.chk_upscale_after.isChecked()
            and self.upscale_after_provider_combo.currentData() == "local_realesrgan"
        )

    def validate_local_realesrgan_selection(self, run_mode):
        if not self._uses_local_realesrgan_for_run(run_mode):
            return ""
        _, error_message = validate_local_realesrgan_exe(bundled_local_realesrgan_dir())
        return error_message

    def _cleanup_requested_from_ui(self):
        return self.chk_cleanup_all.isChecked()

    def start_work(self):
        if not self.work_dir:
            QMessageBox.warning(self, "Ошибка", "Выберите рабочую папку")
            return

        validation_error = self.validate_generation_selection()
        if validation_error:
            QMessageBox.warning(self, "Ошибка", validation_error)
            return

        self.persist_ui_settings()
        current_api_key = self.secret_settings.get("kie_api_key", "").strip()
        current_photoroom_api_key = self.secret_settings.get("photoroom_api_key", "").strip()
        current_fal_api_key = self.secret_settings.get("fal_api_key", "").strip()
        selected_generation_models = {
            self.get_selected_generation_model_id(self.text_generation_model_combo),
            self.get_selected_generation_model_id(self.reference_generation_model_combo),
        }
        will_process = self.radio_run_process.isChecked() or self.radio_run_both.isChecked()

        needs_kie_api = (
            (
                not self.radio_run_process.isChecked()
                and any(not is_fal_generation_model(model) for model in selected_generation_models)
            )
            or (self.chk_upscale.isChecked() and self.upscale_provider_combo.currentData() == "kie")
            or (
                self.chk_upscale_after.isChecked()
                and self.upscale_after_provider_combo.currentData() == "kie"
            )
            or (
                self.chk_remove_bg.isChecked()
                and self.remove_bg_provider_combo.currentData() == "kie"
            )
        )
        if needs_kie_api and not current_api_key:
            QMessageBox.warning(self, "Ошибка", "Укажите KIE API Key на вкладке «Настройки»")
            return

        needs_fal_api = (
            not self.radio_run_process.isChecked()
            and any(is_fal_generation_model(model) for model in selected_generation_models)
        ) or (
            will_process
            and (
                (self.chk_upscale.isChecked() and self.upscale_provider_combo.currentData() == "fal")
                or (
                    self.chk_upscale_after.isChecked()
                    and self.upscale_after_provider_combo.currentData() == "fal"
                )
                or (
                    self.chk_remove_bg.isChecked()
                    and self.remove_bg_provider_combo.currentData() == "fal"
                )
            )
        )
        if needs_fal_api and not current_fal_api_key:
            QMessageBox.warning(self, "Ошибка", "Укажите Fal.ai API Key на вкладке «Настройки»")
            return
        fal_cost_confirmed = False
        if needs_fal_api:
            answer = QMessageBox.question(
                self,
                "Подтвердите запуск Fal.ai",
                "Для выбранной модели Fal.ai актуальная цена не загружена в приложение. "
                "Сервис может списать средства по своему текущему тарифу. "
                "Продолжить только если вы проверили цену в Fal.ai?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            fal_cost_confirmed = True

        needs_photoroom_api = (
            will_process
            and self.chk_remove_bg.isChecked()
            and self.remove_bg_provider_combo.currentData() == "photoroom"
        )
        if needs_photoroom_api and not current_photoroom_api_key:
            QMessageBox.warning(self, "Ошибка", "Укажите PhotoRoom API Key на вкладке «Настройки»")
            return
        if self.credential_store_error and (needs_kie_api or needs_photoroom_api or needs_fal_api):
            QMessageBox.warning(
                self,
                "Ошибка",
                "Не удалось сохранить секреты в user-data .env. Исправьте доступ к папке и попробуйте снова.",
            )
            return

        runtime_settings = build_runtime_settings(self.config, self.secret_settings)
        runtime_settings["fal_cost_confirmed"] = fal_cost_confirmed
        self.has_generated_output_in_run = False
        active_prompts = []
        visible_mark_confirmed_regions = {}

        run_mode = self.config.get("run_mode", "generate_only")
        if run_mode == "process_only":
            mode = worker_mode_for(run_mode)
            if not self.selected_files:
                QMessageBox.warning(self, "Ошибка", "Для режима обработки выберите файлы")
                return
            if not (
                self.chk_visible_mark_cleanup.isChecked()
                or self.chk_upscale.isChecked()
                or self.chk_upscale_after.isChecked()
                or self.chk_unsharp.isChecked()
                or self.chk_remove_bg.isChecked()
                or self.chk_trim.isChecked()
                or self.chk_edge_shrink.isChecked()
                or self._cleanup_requested_from_ui()
            ):
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    "Включите хотя бы один этап: удаление видимой метки, апскейл, "
                    "удаление фона, trim или очистку файла",
                )
                return
            if (
                self.chk_visible_mark_cleanup.isChecked()
                and self.visible_mark_mode_combo.currentData() == "confirmed_area"
            ):
                visible_mark_confirmed_regions = self.collect_visible_mark_regions()
                if visible_mark_confirmed_regions is None:
                    return
        elif run_mode == "both":
            if (
                self.chk_visible_mark_cleanup.isChecked()
                and self.visible_mark_mode_combo.currentData() == "confirmed_area"
            ):
                QMessageBox.warning(
                    self,
                    "Область видимой метки",
                    "Ручное подтверждение области доступно только для уже выбранных файлов. "
                    "Для создаваемых изображений выберите автоматический режим Gemini.",
                )
                return
            active_prompts = self.get_list_mode_prompts()
            if not active_prompts:
                QMessageBox.warning(self, "Ошибка", "Добавьте хотя бы одну запись")
                return
            self.generated_prompts = active_prompts
            self.refresh_prompts_table()
            mode = worker_mode_for(run_mode)
        else:
            active_prompts = self.get_list_mode_prompts()
            if not active_prompts:
                QMessageBox.warning(self, "Ошибка", "Добавьте хотя бы одну запись")
                return

            self.generated_prompts = active_prompts
            self.refresh_prompts_table()
            mode = worker_mode_for(run_mode)

        local_realesrgan_error = self.validate_local_realesrgan_selection(run_mode)
        if local_realesrgan_error:
            QMessageBox.warning(self, "Ошибка", local_realesrgan_error)
            return

        launch_mode_label = {
            "generate_only": "Только генерация изображений",
            "process_only": "Только обработка файлов",
            "both": "Все вместе",
        }.get(run_mode, run_mode)
        self.log(f"Сценарий запуска: {launch_mode_label}")

        if not self._ensure_models_available_before_run(run_mode, self.generated_prompts, runtime_settings):
            return
        self.persist_ui_settings()
        runtime_settings = build_runtime_settings(
            self.config,
            self.secret_settings,
            visible_mark_confirmed_regions=visible_mark_confirmed_regions,
        )

        self.stop_pending = False
        self.worker = launch_worker(
            WorkerThread,
            mode=mode,
            work_dir=self.work_dir,
            settings=runtime_settings,
            selected_files=self.selected_files,
            generated_prompts=self.generated_prompts,
            on_progress=self.log,
            on_progress_value=self.progress_bar.setValue,
            on_finished=self.on_finished,
            on_error=self.on_error,
        )

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def validate_generation_selection(self):
        text_model = self.get_selected_generation_model_id(self.text_generation_model_combo)
        reference_model = self.get_selected_generation_model_id(self.reference_generation_model_combo)
        text_ratio = self.text_ratio_combo.currentText().strip()
        reference_ratio = self.reference_ratio_combo.currentText().strip()
        text_resolution = self.text_resolution_combo.currentText().strip()
        reference_resolution = self.reference_resolution_combo.currentText().strip()

        text_caps = self._get_model_capabilities(text_model)
        reference_caps = self._get_model_capabilities(reference_model)

        if text_caps["ratios"] and text_ratio not in text_caps["ratios"]:
            return f"Соотношение {text_ratio} недоступно для модели {text_model}"
        if reference_caps["ratios"] and reference_ratio not in reference_caps["ratios"]:
            return f"Соотношение {reference_ratio} недоступно для модели {reference_model}"
        if text_caps["resolutions"] and text_resolution not in text_caps["resolutions"]:
            return f"Размер {text_resolution} недоступен для модели {text_model}"
        if reference_caps["resolutions"] and reference_resolution not in reference_caps["resolutions"]:
            return f"Размер {reference_resolution} недоступен для модели {reference_model}"
        order_error = validate_upscale_after_background_order(
            self.chk_remove_bg.isChecked(),
            self.chk_upscale_after.isChecked(),
            self.upscale_after_provider_combo.currentData(),
            (
                self.fal_upscale_after_model_combo.currentData()
                if self.upscale_after_provider_combo.currentData() == "fal"
                else self.kie_upscale_after_model_combo.currentText()
            ),
        )
        if order_error:
            return order_error
        return ""

    def stop_work(self):
        if not self.worker:
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            return

        if not self.stop_pending:
            self.stop_pending = True
            self.worker.stop()
            self.log("Остановка запрошена...")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self._finish_stop_when_worker_exits()

    def _finish_stop_when_worker_exits(self):
        if self.worker and self.worker.isRunning():
            QTimer.singleShot(100, self._finish_stop_when_worker_exits)
            return

        self.worker = None
        self.stop_pending = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log("Остановлено")
        self.offer_open_output_folder_after_stop()

    def on_finished(self, message):
        if self.stop_pending:
            return
        self.log(message)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100)
        self.offer_open_output_folder(message)

    def offer_open_output_folder(self, message):
        if "Готово" not in (message or ""):
            return
        if not self.work_dir:
            return
        output_dir = os.path.join(self.work_dir, "output")
        if not os.path.isdir(output_dir):
            return
        answer = QMessageBox.question(
            self,
            "Готово",
            f"{message}\n\nОткрыть папку с результатами?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                os.startfile(output_dir)
            except Exception as e:
                self.log(f"Не удалось открыть папку output: {e}")

    def offer_open_output_folder_after_stop(self):
        output_dir = os.path.join(self.work_dir, "output") if self.work_dir else ""
        if not output_dir or not os.path.isdir(output_dir):
            return
        if not self.has_generated_output_in_run:
            return
        answer = QMessageBox.question(
            self,
            "Остановка",
            "Остановка выполнена. Открыть папку с уже готовыми результатами?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                os.startfile(output_dir)
            except Exception as e:
                self.log(f"Не удалось открыть папку output: {e}")

    def on_error(self, err):
        if self.stop_pending:
            return
        self.log(f"Ошибка: {err}")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def log(self, msg):
        if "Итог сохранён:" in (msg or ""):
            self.has_generated_output_in_run = True
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")

    def on_api_key_changed(self, *_):
        self.api_key_mask_timer.start()

    def enforce_api_key_hidden(self):
        if self.api_key_locked:
            self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        if self.fal_api_key_locked:
            self.fal_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

    def toggle_api_key_lock(self):
        self.api_key_locked = not self.api_key_locked
        if self.api_key_locked:
            self.kie_api_key_input.setReadOnly(True)
            self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_api_key_lock.setText("🔒")
            self.btn_api_key_lock.setToolTip("Ключ заблокирован")
            self.log("KIE API Key заблокирован")
            return

        self.kie_api_key_input.setReadOnly(False)
        self.kie_api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        self.btn_api_key_lock.setText("🔓")
        self.btn_api_key_lock.setToolTip("Ключ разблокирован")
        self.log("KIE API Key разблокирован: можно смотреть и редактировать")

    def toggle_fal_api_key_lock(self):
        self.fal_api_key_locked = not self.fal_api_key_locked
        if self.fal_api_key_locked:
            self.fal_api_key_input.setReadOnly(True)
            self.fal_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_fal_api_key_lock.setText("🔒")
            self.btn_fal_api_key_lock.setToolTip("Ключ заблокирован")
            self.log("Fal.ai API Key заблокирован")
            return
        self.fal_api_key_input.setReadOnly(False)
        self.fal_api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        self.btn_fal_api_key_lock.setText("🔓")
        self.btn_fal_api_key_lock.setToolTip("Ключ разблокирован")
        self.log("Fal.ai API Key разблокирован: можно смотреть и редактировать")

    def toggle_photoroom_api_key_lock(self):
        self.photoroom_api_key_locked = not self.photoroom_api_key_locked
        if self.photoroom_api_key_locked:
            self.photoroom_api_key_input.setReadOnly(True)
            self.photoroom_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_photoroom_api_key_lock.setText("🔒")
            self.btn_photoroom_api_key_lock.setToolTip("Ключ заблокирован")
            self.log("PhotoRoom API Key заблокирован")
            return

        self.photoroom_api_key_input.setReadOnly(False)
        self.photoroom_api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        self.btn_photoroom_api_key_lock.setText("🔓")
        self.btn_photoroom_api_key_lock.setToolTip("Ключ разблокирован")
        self.log("PhotoRoom API Key разблокирован: можно смотреть и редактировать")

    def check_generation_model(self):
        api_key = self.kie_api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Ошибка", "Сначала укажите KIE API Key")
            return

        text_model = self.get_selected_generation_model_id(self.text_generation_model_combo)
        reference_model = self.get_selected_generation_model_id(self.reference_generation_model_combo)
        timeout = max(10, int(self.config.get("timeout", 60)))
        text_ratio = self.text_ratio_combo.currentText().strip() or "1:1"
        reference_ratio = self.reference_ratio_combo.currentText().strip() or "1:1"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        reference_model_type = (GENERATION_MODEL_META.get(reference_model) or {}).get("type", "text_to_image")
        sample_image_url = MODEL_PROBE_SAMPLE_IMAGE_URL

        try:
            text_ok, text_msg, text_task_id = self._probe_model_with_ratio(text_model, "1:1", headers, timeout)
            if not text_ok:
                raise RuntimeError(f"Недоступна модель для текстовых промптов: {text_model}. {text_msg}")

            # Если уже проверили 1:1 и выбран тоже 1:1, повторный сетевой запрос не нужен.
            if text_ratio != "1:1":
                ratio_ok, ratio_msg, _ = self._probe_model_with_ratio(text_model, text_ratio, headers, timeout)
                if not ratio_ok:
                    raise RuntimeError(
                        f"Недоступно соотношение {text_ratio} для модели {text_model}. {ratio_msg}"
                    )

            ref_ok, ref_msg, ref_task_id = self._probe_model_with_ratio(
                reference_model,
                "1:1",
                headers,
                timeout,
                reference_urls=[sample_image_url],
            )
            if (
                not ref_ok
                and reference_model == "gpt-image/1.5-image-to-image"
                and "This field is required" in str(ref_msg)
            ):
                self.log(
                    "Проверка image-to-image для gpt-image/1.5-image-to-image пропущена: "
                    "API возвращает schema-ошибку на тестовом запросе, но модель может работать в реальном запуске."
                )
                ref_ok = True
                ref_task_id = "schema-check-skipped"
            elif (
                not ref_ok
                and (reference_model_type in {"image_to_image", "edit"} or self._get_model_capabilities(reference_model)["reference_compatible_text"])
                and self._is_schema_required_error(ref_msg)
            ):
                self.log(
                    "Проверка image-to-image/edit модели переведена в мягкий режим: "
                    "API вернул schema-ошибку на тестовом запросе. Модель будет проверена реальным запуском."
                )
                ref_ok = True
                ref_task_id = "schema-check-skipped"
            if not ref_ok:
                raise RuntimeError(f"Недоступна модель для промптов с референсами: {reference_model}. {ref_msg}")

            if reference_ratio != "1:1":
                ref_ratio_ok, ref_ratio_msg, _ = self._probe_model_with_ratio(
                    reference_model,
                    reference_ratio,
                    headers,
                    timeout,
                    reference_urls=[sample_image_url],
                )
                if (
                    not ref_ratio_ok
                    and reference_model == "gpt-image/1.5-image-to-image"
                    and "This field is required" in str(ref_ratio_msg)
                ):
                    self.log(
                        "Проверка соотношения для gpt-image/1.5-image-to-image пропущена: "
                        "API возвращает schema-ошибку на тестовом запросе."
                    )
                    ref_ratio_ok = True
                elif (
                    not ref_ratio_ok
                    and (reference_model_type in {"image_to_image", "edit"} or self._get_model_capabilities(reference_model)["reference_compatible_text"])
                    and self._is_schema_required_error(ref_ratio_msg)
                ):
                    self.log(
                        "Проверка соотношения для image-to-image/edit модели пропущена: "
                        "API вернул schema-ошибку на тестовом запросе."
                    )
                    ref_ratio_ok = True
                if not ref_ratio_ok:
                    raise RuntimeError(
                        f"Недоступно соотношение {reference_ratio} для модели {reference_model}. {ref_ratio_msg}"
                    )

            self.log(
                (
                    "Проверка моделей успешна. "
                    f"Text→Image: {text_model} (Task ID: {text_task_id}) | "
                    f"Image→Image: {reference_model} (Task ID: {ref_task_id})"
                )
            )
            QMessageBox.information(self, "Проверка моделей", "Обе модели доступны")
        except urlerror.HTTPError as e:
            msg = f"HTTP {e.code}"
            self.log(f"Проверка моделей не пройдена: {msg}")
            QMessageBox.warning(self, "Проверка моделей", f"Проверка не пройдена\n{msg}")
        except Exception as e:
            msg = safe_error_text(e, (self.kie_api_key_input.text().strip(),))
            self.log(f"Проверка моделей не пройдена: {msg}")
            QMessageBox.warning(self, "Проверка моделей", f"Ошибка проверки: {msg}")

    def _is_schema_required_error(self, message):
        return is_schema_required_error_message(message)

    def _extract_credit_value(self, payload):
        priority_keys = [
            "remainingCredits",
            "remainingCredit",
            "remaining_credits",
            "remaining_credit",
            "availableCredits",
            "available_credits",
            "credits",
            "credit",
            "balance",
            "amount",
            "totalCredits",
            "total_credits",
        ]

        def _looks_like_number(value):
            if isinstance(value, (int, float)):
                return True
            if isinstance(value, str):
                text = value.strip().replace(",", ".")
                if not text:
                    return False
                try:
                    float(text)
                    return True
                except Exception:
                    return False
            return False

        if isinstance(payload, dict):
            for key in priority_keys:
                if key in payload:
                    return key, payload.get(key)

            # Частый формат: data = число/строка с числом
            if "data" in payload and _looks_like_number(payload.get("data")):
                return "data", payload.get("data")

            for value in payload.values():
                found = self._extract_credit_value(value)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._extract_credit_value(item)
                if found is not None:
                    return found
        elif _looks_like_number(payload):
            return "value", payload
        return None

    def check_kie_balance(self):
        api_key = self.kie_api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Ошибка", "Сначала укажите KIE API Key")
            return

        timeout = max(10, int(self.config.get("timeout", 60)))
        headers = {
            "Authorization": f"Bearer {api_key}",
            "x-api-key": api_key,
            "Accept": "application/json",
            "User-Agent": APP_USER_AGENT,
        }

        self.btn_check_balance.setEnabled(False)
        self.btn_check_balance.setText("Проверка...")
        try:
            req = request.Request("https://api.kie.ai/api/v1/chat/credit", headers=headers, method="GET")
            protect_secret_headers_from_redirects(req)
            with open_url_secure(req, timeout=timeout, context=build_ssl_context()) as resp:
                raw = read_response_limited(resp, MAX_API_JSON_RESPONSE_BYTES)
            result = json.loads(raw.decode("utf-8"))

            if int(result.get("code", 200)) not in {0, 200}:
                raise RuntimeError(
                    f"KIE balance request failed (code {result.get('code', '-')})"
                )

            extracted = self._extract_credit_value(result)
            if extracted is None:
                self.log("Баланс KIE: поле с кредитами не найдено")
                QMessageBox.information(
                    self,
                    "Баланс KIE",
                    "Запрос выполнен, но поле баланса не распознано.",
                )
                return

            key, value = extracted
            self.log(f"Баланс KIE: {value} кредитов")
            QMessageBox.information(self, "Баланс KIE", f"{value} кредитов")
        except urlerror.HTTPError as e:
            msg = f"HTTP {e.code}"
            self.log(f"Проверка баланса не пройдена: {msg}")
            QMessageBox.warning(self, "Баланс KIE", f"Проверка не пройдена\n{msg}")
        except Exception as e:
            msg = safe_error_text(e, (api_key,))
            self.log(f"Проверка баланса не пройдена: {msg}")
            QMessageBox.warning(self, "Баланс KIE", f"Ошибка проверки: {msg}")
        finally:
            self.btn_check_balance.setEnabled(True)
            self.btn_check_balance.setText("Проверить баланс")

    def check_photoroom_balance(self):
        api_key = self.photoroom_api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "PhotoRoom", "Сначала укажите PhotoRoom API Key")
            return
        self.btn_photoroom_check_balance.setEnabled(False)
        try:
            balance = check_photoroom_balance_api(api_key, timeout=max(10, int(self.config.get("timeout", 60))))
            QMessageBox.information(self, "Баланс PhotoRoom", balance)
        except Exception as error:
            QMessageBox.warning(self, "Баланс PhotoRoom", f"Проверка не пройдена: {safe_error_text(error, (api_key,))}")
        finally:
            self.btn_photoroom_check_balance.setEnabled(True)

    def check_license_key(self):
        license_key = self.license_key_input.text().strip()
        if not license_key:
            QMessageBox.warning(self, "Лицензия", "Введите лицензионный ключ")
            return

        try:
            license_client = self._build_license_client()
            result = license_client.activate(license_key)
            self.license_key_input.clear()
            expires_at = result.expires_at.astimezone().strftime("%d.%m.%Y %H:%M")
            state_text = "Лицензия активирована"
            message = (
                f"{state_text}\n"
                f"Текущая онлайн-проверка действует до: {expires_at}"
            )
            self.log(f"Проверка лицензии успешна: {state_text}")
            QMessageBox.information(self, "Лицензия", message)
        except Exception as e:
            message = safe_error_text(e, (license_key,))
            self.log(f"Проверка лицензии не пройдена: {message}")
            QMessageBox.warning(self, "Лицензия", f"Ошибка проверки: {message}")

    def _probe_model_with_ratio(self, raw_model, ratio, headers, timeout, reference_urls=None):
        probe_settings = dict(self.config)
        probe_settings["kie_api_key"] = self.secret_settings.get("kie_api_key", "").strip()
        probe_settings["photoroom_api_key"] = self.secret_settings.get("photoroom_api_key", "").strip()
        probe_worker = WorkerThread(
            "mode1_generate_only",
            self.work_dir or os.getcwd(),
            probe_settings,
            selected_files=[],
            generated_prompts=[],
        )
        return probe_worker._probe_model_with_ratio(
            raw_model,
            ratio,
            headers,
            timeout,
            reference_urls=reference_urls,
        )

    def _parse_version_tuple(self, version_text):
        parts = str(version_text or "0.0.0").strip().split(".")
        numbers = []
        for part in parts:
            try:
                numbers.append(int(part))
            except Exception:
                numbers.append(0)
        while len(numbers) < 3:
            numbers.append(0)
        return tuple(numbers[:3])

    def _is_newer_version(self, latest, current):
        return self._parse_version_tuple(latest) > self._parse_version_tuple(current)

    def _sha256_file(self, file_path):
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest().lower()

    def _cleanup_update_file(self, installer_path):
        try:
            if installer_path and os.path.isfile(installer_path):
                os.remove(installer_path)
        except Exception:
            pass

    def _validate_update_checksum(self, checksum):
        normalized = str(checksum or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized):
            raise RuntimeError("version.json не содержит корректную SHA-256 сумму обновления")
        return normalized

    def _download_update_installer(self, download_url, expected_sha256=None):
        validate_https_url(download_url, "Update download URL")
        last_error = None
        for attempt in range(1, MAX_UPDATE_DOWNLOAD_RETRIES + 1):
            temp_dir = tempfile.gettempdir()
            retry_suffix = "" if attempt == 1 else f"_{attempt}"
            filename = f"VibixImages-Update-{int(time.time())}{retry_suffix}.exe"
            installer_path = os.path.join(temp_dir, filename)

            try:
                req = request.Request(
                    download_url,
                    headers={
                        "User-Agent": APP_UPDATE_USER_AGENT,
                        "Accept": "application/octet-stream,*/*",
                    },
                    method="GET",
                )
                with open_url_secure(req, timeout=UPDATE_DOWNLOAD_TIMEOUT_SECONDS, context=build_ssl_context()) as resp:
                    get_header = getattr(resp, "getheader", None)
                    if callable(get_header):
                        content_length = get_header("Content-Length")
                    else:
                        content_length = getattr(resp, "headers", {}).get("Content-Length")
                    if content_length:
                        try:
                            total = int(content_length)
                        except Exception:
                            total = -1
                        if total > MAX_UPDATE_INSTALLER_BYTES:
                            raise ResponseLimitError("Скачиваемый файл слишком большой")

                    with open(installer_path, "wb") as f:
                        downloaded = 0
                        while True:
                            chunk = resp.read(UPDATE_DOWNLOAD_CHUNK_BYTES)
                            if not chunk:
                                break
                            downloaded += len(chunk)
                            if downloaded > MAX_UPDATE_INSTALLER_BYTES:
                                raise ResponseLimitError("Скачиваемый файл превысил лимит")
                            f.write(chunk)

                if expected_sha256:
                    actual = self._sha256_file(installer_path)
                    if actual != expected_sha256.lower().strip():
                        MainWindow._cleanup_update_file(self, installer_path)
                        raise RuntimeError("Контрольная сумма обновления не совпала")

                return installer_path

            except ResponseLimitError:
                MainWindow._cleanup_update_file(self, installer_path)
                raise
            except Exception as e:
                last_error = e
                MainWindow._cleanup_update_file(self, installer_path)
                if attempt >= MAX_UPDATE_DOWNLOAD_RETRIES:
                    break
                time.sleep(min(2, attempt))
                logger = getattr(self, "log", None)
                if callable(logger):
                    logger(
                        "Ошибка скачивания апдейта "
                        f"(попытка {attempt}): "
                        f"{safe_error_text(e, getattr(self, '_secret_values', ())) }"
                    )

        raise RuntimeError(
            "Не удалось скачать установщик: "
            f"{safe_error_text(last_error, getattr(self, '_secret_values', ())) }"
        )

    def _run_downloaded_installer(self, installer_path):
        if not os.path.isfile(installer_path):
            raise RuntimeError("Файл установщика не найден")
        os.startfile(installer_path)

    def _build_license_client(self):
        return LicenseClient(
            base_url=LICENSE_SERVICE_BASE_URL,
            state_path=LICENSE_STATE_FILE,
            public_keys=LICENSE_PUBLIC_KEYS,
            product_id=LICENSE_PRODUCT_ID,
            timeout=10,
        )

    def _should_show_updates_expired_notice(self):
        last_notice_raw = str(self.config.get("last_updates_expired_notice_at", "")).strip()
        if not last_notice_raw:
            return True
        try:
            last_notice_at = datetime.fromisoformat(last_notice_raw)
            if last_notice_at.tzinfo is None:
                last_notice_at = last_notice_at.replace(tzinfo=timezone.utc)
        except Exception:
            return True
        return (datetime.now(timezone.utc) - last_notice_at) >= timedelta(days=30)

    def _mark_updates_expired_notice_shown(self):
        self.config["last_updates_expired_notice_at"] = datetime.now(timezone.utc).isoformat()
        self.save_config(include_secrets=bool(self.credential_store_error))

    def _parse_update_manifest(self, raw_bytes):
        raw_text = raw_bytes.decode("utf-8-sig", errors="replace")
        stripped = raw_text.lstrip()

        if "<<<<<<<" in raw_text or "=======" in raw_text or ">>>>>>>" in raw_text:
            raise RuntimeError("version.json содержит маркеры git-конфликта")

        if stripped.startswith("<!DOCTYPE") or stripped.startswith("<html"):
            raise RuntimeError("сервер обновлений вернул HTML вместо JSON")

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Некорректный JSON в version.json: {e}") from e

    def check_for_updates(self, silent=False, auto_apply=False):
        manifest_url = UPDATE_MANIFEST_URL
        if not manifest_url:
            if not silent:
                QMessageBox.warning(self, "Обновления", "Не задан URL version.json")
            return

        try:
            req = request.Request(
                manifest_url,
                headers={
                    "User-Agent": APP_UPDATE_USER_AGENT,
                    "Accept": "application/json",
                },
                method="GET",
            )
            with open_url_secure(req, timeout=20, context=build_ssl_context()) as resp:
                manifest = self._parse_update_manifest(read_response_limited(resp, MAX_UPDATE_MANIFEST_BYTES))

            latest_version = str(manifest.get("latest_version", "")).strip()
            download_url = str(manifest.get("download_url", "")).strip()
            checksum = self._validate_update_checksum(manifest.get("sha256"))

            if not latest_version or not download_url:
                raise RuntimeError("version.json не содержит latest_version/download_url")

            validate_https_url(download_url, "Update download URL")

            # Источник истины о текущей версии — константа в текущей сборке.
            current_version = APP_VERSION
            if not self._is_newer_version(latest_version, current_version):
                if not silent:
                    QMessageBox.information(self, "Обновления", f"У вас актуальная версия: {current_version}")
                return

            if auto_apply:
                self.log(f"Авто-обновление: новая версия {latest_version}, текущая {current_version}")
            else:
                answer = QMessageBox.question(
                    self,
                    "Доступно обновление",
                    (
                        f"Доступна новая версия: {latest_version}\n"
                        f"Текущая версия: {current_version}\n\n"
                        "Установить обновление сейчас?"
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self.log("Обновление отклонено пользователем")
                    return

            self.log(f"Скачивание обновления {latest_version}...")
            installer_path = self._download_update_installer(download_url, expected_sha256=checksum or None)
            self.log(f"Установщик скачан: {installer_path}")

            self._run_downloaded_installer(installer_path)
            if auto_apply:
                QApplication.instance().quit()
                return

            QMessageBox.information(
                self,
                "Обновление",
                "Установщик обновления скачан. После завершения установки закройте приложение и откройте заново.",
            )
            QApplication.instance().quit()
        except Exception as e:
            human_error = str(e)
            if isinstance(e, urlerror.URLError):
                reason = getattr(e, "reason", None)
                if reason is not None and ("11001" in str(reason) or "getaddrinfo" in str(reason).lower()):
                    human_error = "Нет доступа к сети или DNS не может разрешить адрес сервера обновлений"
                elif reason is not None and "certificate_verify_failed" in str(reason).lower():
                    human_error = (
                        "Не удалось проверить SSL-сертификат. Проверьте дату/время Windows, "
                        "обновления корневых сертификатов и доступ к github.com"
                    )
            self.log(f"Проверка обновлений: {human_error}")
            if not silent:
                QMessageBox.warning(self, "Обновления", f"Не удалось проверить обновления: {human_error}")

    def _ratio_to_legacy_size_ui(self, ratio):
        return {
            "1:1": "1024x1024",
            "4:3": "1536x1024",
            "3:4": "1024x1536",
            "16:9": "1536x1024",
            "9:16": "1024x1536",
        }.get(ratio, "1024x1024")

    def persist_ui_settings(self):
        self.config["overwrite_existing"] = self.chk_overwrite_existing.isChecked()
        self.secret_settings["kie_api_key"] = self.config["kie_api_key"] = self.kie_api_key_input.text().strip()
        self.secret_settings["photoroom_api_key"] = self.config["photoroom_api_key"] = self.photoroom_api_key_input.text().strip()
        self.secret_settings["fal_api_key"] = self.config["fal_api_key"] = self.fal_api_key_input.text().strip()
        self.config["text_generation_model"] = self.get_selected_generation_model_id(self.text_generation_model_combo)
        self.config["reference_generation_model"] = self.get_selected_generation_model_id(
            self.reference_generation_model_combo
        )
        self.config["generation_model"] = self.config["text_generation_model"]
        self.config["text_generation_ratio"] = self.text_ratio_combo.currentText()
        self.config["reference_generation_ratio"] = self.reference_ratio_combo.currentText()
        self.config["text_generation_resolution"] = self.text_resolution_combo.currentText()
        self.config["reference_generation_resolution"] = self.reference_resolution_combo.currentText()
        self.config["generation_size"] = self.config["text_generation_ratio"]
        self.config["visible_mark_cleanup_enabled"] = self.chk_visible_mark_cleanup.isChecked()
        self.config["visible_mark_cleanup_mode"] = normalize_visible_mark_cleanup_mode(
            self.visible_mark_mode_combo.currentData()
        )
        self.config["remove_bg"] = self.chk_remove_bg.isChecked()
        self.config["upscale"] = self.chk_upscale.isChecked()
        self.config["upscale_after"] = self.chk_upscale_after.isChecked()
        self.config["trim_enabled"] = self.chk_trim.isChecked()
        self.config["unsharp_enabled"] = self.chk_unsharp.isChecked()
        self.config["unsharp_amount"] = normalize_unsharp_amount(self.unsharp_amount_spin.value())
        self.config["unsharp_radius"] = normalize_unsharp_radius(self.unsharp_radius_spin.value())
        self.config["unsharp_threshold"] = normalize_unsharp_threshold(self.unsharp_threshold_spin.value())
        self.config["export_300_dpi"] = self.chk_export_300_dpi.isChecked()
        self.config["edge_shrink_enabled"] = self.chk_edge_shrink.isChecked()
        self.config["edge_shrink_pixels"] = normalize_edge_shrink_pixels(self.edge_shrink_pixels_combo.currentData() or 1)
        cleanup_all = self.chk_cleanup_all.isChecked()
        self.config["cleanup_remove_exif"] = cleanup_all
        self.config["cleanup_remove_xmp"] = cleanup_all
        self.config["cleanup_remove_iptc"] = cleanup_all
        self.config["cleanup_remove_comments_text"] = cleanup_all
        self.config["cleanup_remove_embedded_thumbnail"] = cleanup_all
        self.config["cleanup_remove_generator_fields"] = cleanup_all
        self.config["cleanup_remove_embedded_c2pa"] = cleanup_all
        self.config["cleanup_remove_all"] = cleanup_all
        self.config["cleanup_preserve_icc"] = True
        self.config["cleanup_preserve_dpi"] = True
        self.config["trim_mode"] = str(self.trim_mode_combo.currentData() or "alpha")
        self.config["upscale_provider"] = str(self.upscale_provider_combo.currentData() or "kie")
        self.config["upscale_after_provider"] = str(
            self.upscale_after_provider_combo.currentData() or "local_realesrgan"
        )
        self.config["local_realesrgan_dir"] = bundled_local_realesrgan_dir()
        self.config["local_realesrgan_profile"] = str(self.local_realesrgan_profile_combo.currentData() or "clipart")
        self.config["local_realesrgan_scale"] = int(self.local_realesrgan_scale_combo.currentData() or 4)
        self.config["local_realesrgan_after_scale"] = int(
            self.local_realesrgan_after_scale_combo.currentData() or 4
        )
        self.config["remove_bg_provider"] = str(self.remove_bg_provider_combo.currentData() or "kie")
        self.config["local_rembg_profile"] = str(self.local_rembg_profile_combo.currentData() or "clipart")
        self.config["local_rembg_model"] = str(self.local_rembg_model_combo.currentData() or "birefnet-general")
        self.config["local_rembg_edge_quality"] = normalize_local_rembg_edge_quality(
            self.local_rembg_edge_quality_combo.currentData()
        )
        self.config["local_ben2_refine_foreground"] = self.local_ben2_refine_checkbox.isChecked()
        self.config["local_ben2_alpha_threshold"] = normalize_ben2_alpha_threshold(
            self.local_ben2_alpha_threshold_spin.value()
        )
        self.config["local_ben2_edge_softness"] = normalize_ben2_edge_softness(
            self.local_ben2_edge_softness_combo.currentData()
        )
        self.config["local_ben2_corner_radius"] = normalize_ben2_corner_radius(
            self.local_ben2_corner_radius_combo.currentData()
        )
        self.config["kie_upscale_model"] = self.kie_upscale_model_combo.currentText()
        self.config["kie_upscale_after_model"] = self.kie_upscale_after_model_combo.currentText()
        self.config["kie_remove_bg_model"] = self.kie_remove_bg_model_combo.currentText()
        self.config["update_manifest_url"] = UPDATE_MANIFEST_URL
        self.config["prompt_input_mode"] = "list"
        if self.radio_run_process.isChecked():
            self.config["run_mode"] = "process_only"
        elif self.radio_run_both.isChecked():
            self.config["run_mode"] = "both"
        else:
            self.config["run_mode"] = "generate_only"
        try:
            self.credential_store.save(self.secret_settings)
            self.credential_store_error = ""
        except Exception as error:
            self.credential_store_error = safe_error_text(error)
            self.log(
                f"Не удалось сохранить секреты в user-data .env: {self.credential_store_error}"
            )
        if self.credential_store_error:
            return
        self.save_config()

    def closeEvent(self, event):
        try:
            self.settings_save_timer.stop()
            self.persist_ui_settings()
            self.save_prompts_storage()
        except Exception:
            pass
        super().closeEvent(event)


def create_v3_application_window():
    from diagnostics import DiagnosticJournal
    from update_client import UpdateClient, current_platform_id
    from v3_components import V3_WINDOW_DEFAULT_SIZE
    from v3_mode_selection import MODE_CARD_SPECS, V3ApplicationView
    from v3_license import OnlineLicenseGate
    from v3_project_state import migrate_v2_config

    config = {}
    try:
        if os.path.isfile(CONFIG_FILE) and os.path.getsize(CONFIG_FILE) <= 2 * 1024 * 1024:
            with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                config = loaded
    except (OSError, UnicodeError, json.JSONDecodeError):
        config = {}
    # V3 uses this raw config directly; keep the bundled local provider available
    # even when the legacy config is absent or predates the provider setting.
    config["local_realesrgan_dir"] = bundled_local_realesrgan_dir()
    secrets = ProviderCredentialStore(
        ENV_FILE,
        os.path.join(USER_DATA_DIR, "fal_api_key.bin"),
    ).load()

    app_data = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    diagnostic_journal = DiagnosticJournal(app_data, app_version=APP_VERSION)
    diagnostic_journal.record(
        "application_started",
        f"{APP_NAME} запущен.",
        details={"current_version": APP_VERSION},
    )
    license_client = LicenseClient(
        base_url=LICENSE_SERVICE_BASE_URL,
        state_path=os.path.join(app_data, "license_state.json"),
        public_keys=LICENSE_PUBLIC_KEYS,
        product_id=LICENSE_PRODUCT_ID,
        timeout=10,
    )
    update_client = UpdateClient(
        license_client,
        current_version=APP_VERSION,
        download_directory=os.path.join(app_data, "updates"),
        platform_id=current_platform_id(),
        timeout=20,
    )
    window = V3ApplicationView(
        runtime_settings_provider=lambda: build_runtime_settings(config, secrets),
        draft_path=os.path.join(app_data, "project_state.json"),
        license_gate=OnlineLicenseGate(license_client),
        diagnostic_journal=diagnostic_journal,
        update_client=update_client,
        legacy_project=migrate_v2_config(config) if config else None,
    )
    diagnostic_journal.record(
        "application_ui_ready",
        "Основной интерфейс подготовлен.",
        screen="mode_selection",
        outcome="success",
    )
    window.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
    window.resize(*V3_WINDOW_DEFAULT_SIZE)
    if len(window.mode_selection.mode_cards) != len(MODE_CARD_SPECS):
        raise RuntimeError("V3 mode selection does not contain all mode cards")
    return window


def create_authorized_v3_application_window(
    *,
    window_factory=None,
    dialog_factory=None,
    unavailable_dialog_factory=None,
):
    """Create the release window only after fresh online authorization."""
    from license_client import LicenseUnavailableError
    from v3_license import LicenseDialog, SavedLicenseUnavailableDialog

    factory = window_factory or create_v3_application_window
    dialog_type = dialog_factory or LicenseDialog
    unavailable_dialog_type = (
        unavailable_dialog_factory or SavedLicenseUnavailableDialog
    )
    window = factory()
    gate = getattr(window, "_license_gate", None)
    journal = getattr(window, "_diagnostic_journal", None)
    if gate is None:
        window.close()
        return None
    while True:
        try:
            gate.authorize_run()
        except LicenseError as error:
            if journal is not None:
                journal.record(
                    "license_validation_failed",
                    "Проверка лицензии при запуске не выполнена.",
                    severity="warning",
                    outcome="failed",
                    details={"error_message": str(error)},
                )

            if gate.has_activation() and isinstance(error, LicenseUnavailableError):
                retry_dialog = unavailable_dialog_type(str(error), parent=window)
                if retry_dialog.exec() == QDialog.DialogCode.Accepted:
                    continue
                window.close()
                return None

            dialog = dialog_type(gate, parent=window)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                continue
            if journal is not None:
                journal.record(
                    "license_activation_cancelled",
                    "Ввод лицензии отменён пользователем.",
                    severity="warning",
                    outcome="cancelled",
                )
            window.close()
            return None

        if journal is not None:
            journal.record(
                "license_validation_succeeded",
                "Лицензия проверена при запуске.",
                outcome="success",
            )
        refresh = getattr(window, "refresh_license_status", None)
        if callable(refresh):
            refresh()
        return window


def install_diagnostic_exception_hook(journal) -> None:
    """Record bounded traceback locations, then preserve the normal Qt/Python hook."""
    if journal is None:
        return
    import traceback

    previous_hook = sys.excepthook

    def diagnostic_hook(error_type, error, trace) -> None:
        frames = traceback.extract_tb(trace)[-8:]
        locations = "; ".join(
            f"{os.path.basename(frame.filename)}:{frame.lineno}:{frame.name}"
            for frame in frames
        )
        journal.record(
            "unhandled_exception",
            "В приложении возникла необработанная ошибка.",
            severity="error",
            outcome="failed",
            details={
                "error_code": getattr(error_type, "__name__", "Exception"),
                "error_message": f"{error}; {locations}",
            },
        )
        previous_hook(error_type, error, trace)

    sys.excepthook = diagnostic_hook


def run_release_entrypoint_smoke(app) -> int:
    from v3_components import ModeCard
    from v3_mode_selection import MODE_CARD_SPECS

    report_path = os.path.join(
        tempfile.gettempdir(), "clipart-release-entrypoint-smoke.txt"
    )
    try:
        window = create_v3_application_window()
    except Exception as error:
        with open(report_path, "w", encoding="utf-8") as report:
            report.write(f"startup_exception={type(error).__name__}: {error}\n")
        return 1
    app.processEvents()
    cards = list(window.mode_selection.mode_cards.values())
    valid = (
        len(cards) == 3
        and all(isinstance(card, ModeCard) for card in cards)
        and all(card.accessibleName() for card in cards)
        and set(window.mode_selection.mode_cards) == set(MODE_CARD_SPECS)
    )
    diagnostic = (
        f"window={type(window).__name__}\n"
        f"cards={len(cards)}\n"
        f"card_types={[type(card).__name__ for card in cards]}\n"
        f"accessible_names={[bool(card.accessibleName()) for card in cards]}\n"
        f"mode_keys={[str(mode) for mode in window.mode_selection.mode_cards]}\n"
        f"expected_keys={[str(mode) for mode in MODE_CARD_SPECS]}\n"
        f"valid={valid}\n"
    )
    with open(report_path, "w", encoding="utf-8") as report:
        report.write(diagnostic)
    window.close()
    return 0 if valid else 1


def run_packaged_entrypoint_check(
    expected_app_version=None,
    *,
    evidence_dir=None,
) -> int:
    from v3_license import LicenseDialog, OnlineLicenseGate
    from v3_mode_selection import (
        MODE_CARD_SPECS,
        V3ApplicationView,
        default_work_directory,
    )

    class SmokeClient:
        @staticmethod
        def has_activation():
            return False

        @staticmethod
        def activate(_license_key):
            raise LicenseError("smoke activation must not run")

        @staticmethod
        def validate():
            raise LicenseError("smoke validation must not run")

    class RejectedDialog:
        def __init__(self, _gate, parent=None):
            self.parent = parent

        @staticmethod
        def exec():
            return QDialog.DialogCode.Rejected

    gate = OnlineLicenseGate(SmokeClient())
    dialog = LicenseDialog(gate)
    license_input_is_safe = (
        dialog.license_key_input.echoMode() == QLineEdit.EchoMode.Password
        and dialog.license_key_input.accessibleName() == "Лицензионный ключ"
    )
    dialog.close()

    packaged_view = V3ApplicationView(license_gate=gate)
    evidence_is_saved = True
    if evidence_dir is not None:
        from v3_project_state import ProjectMode, PromptEntry, StepId

        evidence_root = Path(evidence_dir)
        try:
            evidence_root.mkdir(parents=True, exist_ok=True)
            packaged_view.resize(1366, 900)
            packaged_view.show()
            QApplication.processEvents()
            evidence_is_saved = packaged_view.grab().save(
                str(evidence_root / "mode-selection.png"),
                "PNG",
            )

            packaged_view.mode_selection.mode_cards[
                ProjectMode.CLIPART
            ].start_button.click()
            QApplication.processEvents()
            packaged_view.shell.state.clipart.prompts = [
                PromptEntry(
                    "Watercolor baby fox, isolated on white background",
                    ["C:/smoke/reference-fox.png"],
                ),
                PromptEntry("Watercolor baby bear with wildflowers"),
                PromptEntry("Watercolor woodland rabbit, soft neutral palette"),
            ]
            packaged_view.shell.state.set_step(StepId.PROMPTS)
            packaged_view.shell.refresh()
            QApplication.processEvents()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QApplication.processEvents()
            prompt_review_page = (
                packaged_view.shell.clipart_flow_controller.pages[
                    StepId.PROMPT_REVIEW
                ]
            )
            evidence_is_saved = (
                packaged_view.grab().save(
                    str(evidence_root / "clipart-prompts.png"),
                    "PNG",
                )
                and evidence_is_saved
            )

            packaged_view.shell.state.set_step(StepId.PROMPT_REVIEW)
            packaged_view.shell.refresh()
            QApplication.processEvents()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QApplication.processEvents()
            review_columns_width = (
                prompt_review_page.table.columnWidth(0)
                + prompt_review_page.table.columnWidth(1)
            )
            prompt_review_is_rendered = (
                prompt_review_page.table.rowCount() == 3
                and review_columns_width > 0
                and abs(
                    prompt_review_page.table.columnWidth(0)
                    / review_columns_width
                    - 2 / 3
                )
                <= 0.04
                and packaged_view.shell.state.clipart.prompts[0].references
                == ["C:/smoke/reference-fox.png"]
            )
            evidence_is_saved = (
                packaged_view.grab().save(
                    str(evidence_root / "clipart-prompt-review.png"),
                    "PNG",
                )
                and evidence_is_saved
            )
        except (OSError, RuntimeError, AttributeError):
            evidence_is_saved = False
            prompt_review_is_rendered = False
    else:
        prompt_review_is_rendered = True
    mode_artwork_is_rendered = all(
        card.illustration is not None
        and hasattr(card.illustration, "pixmap")
        and card.illustration.pixmap() is not None
        and not card.illustration.pixmap().isNull()
        for card in packaged_view.mode_selection.mode_cards.values()
    )
    controls_are_present = (
        packaged_view.mode_selection.license_status_label.text()
        == "Лицензия не активирована"
        and packaged_view.mode_selection.license_verification_label.text()
        == "Онлайн-проверка не выполнена"
        and packaged_view.mode_selection.license_button.text()
        == "Сменить лицензию"
        and packaged_view.mode_selection.api_settings_button.text()
        == "Настройки API"
        and packaged_view.mode_selection.diagnostics_button.text()
        == "Диагностика"
    )
    controls_are_connected = (
        packaged_view.mode_selection.receivers(
            packaged_view.mode_selection.license_requested
        )
        == 1
        and packaged_view.mode_selection.receivers(
            packaged_view.mode_selection.api_settings_requested
        )
        == 1
        and packaged_view.mode_selection.receivers(
            packaged_view.mode_selection.diagnostics_requested
        )
        == 1
    )
    default_path = default_work_directory()
    pictures_default_is_safe = (
        default_path.name == APP_NAME
        and os.path.abspath(str(default_path)) != os.path.abspath(os.getcwd())
    )
    packaged_view.close()

    configured_view = create_v3_application_window()
    update_channel_is_connected = (
        configured_view._update_controller is not None
        and configured_view._diagnostic_journal is not None
    )
    configured_view.close()

    smoke_window = QWidget()
    smoke_window._license_gate = gate
    startup_is_blocked = (
        create_authorized_v3_application_window(
            window_factory=lambda: smoke_window,
            dialog_factory=RejectedDialog,
        )
        is None
    )
    smoke_window.deleteLater()
    return 0 if (
        len(MODE_CARD_SPECS) == 3
        and V3ApplicationView
        and mode_artwork_is_rendered
        and evidence_is_saved
        and prompt_review_is_rendered
        and license_input_is_safe
        and controls_are_present
        and controls_are_connected
        and pictures_default_is_safe
        and update_channel_is_connected
        and startup_is_blocked
        and (expected_app_version is None or APP_VERSION == expected_app_version)
    ) else 1


def run_local_processing_entrypoint_check(report_path=None) -> int:
    """Exercise the packaged local runtimes with a tiny rembg inference."""
    def write_report(stage, message):
        if not report_path:
            return
        try:
            Path(report_path).write_text(
                f"stage={stage}\nmessage={safe_error_text(message, limit=300)}\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    _, realesrgan_error = validate_local_realesrgan_exe(bundled_local_realesrgan_dir())
    if realesrgan_error:
        write_report("realesrgan_validation", realesrgan_error)
        return 1
    write_report("rembg_import", "started")
    try:
        new_session, remove = import_rembg_tools()
    except Exception as error:
        write_report("rembg_import", error)
        return 1
    write_report("rembg_session", "started")
    try:
        source = BytesIO()
        Image.new("RGB", (8, 8), "white").save(source, format="PNG")
        session = new_session("u2netp")
    except Exception as error:
        write_report("rembg_session", error)
        return 1
    write_report("rembg_inference", "started")
    try:
        result_data = remove(source.getvalue(), session=session)
        with Image.open(BytesIO(result_data)) as result:
            result.load()
            if result.size != (8, 8) or "A" not in result.getbands():
                write_report("rembg_output", "invalid RGBA output")
                return 1
    except Exception as error:
        write_report("rembg_inference", error)
        return 1
    write_report("ben2_model", "started")
    try:
        ben2_model = load_local_ben2_model()
    except Exception as error:
        write_report("ben2_model", error)
        return 1
    write_report("ben2_inference", "started")
    try:
        ben2_source = Image.new("RGB", (64, 64), "white")
        ben2_source.paste((20, 40, 120), (14, 10, 50, 56))
        ben2_result = ben2_model.inference(ben2_source)
        if (
            not isinstance(ben2_result, Image.Image)
            or ben2_result.size != ben2_source.size
            or "A" not in ben2_result.getbands()
        ):
            write_report("ben2_output", "invalid RGBA output")
            return 1
        alpha_min, alpha_max = ben2_result.getchannel("A").getextrema()
        if alpha_min == alpha_max:
            write_report(
                "ben2_output",
                f"invalid constant alpha mask: {alpha_min}",
            )
            return 1
    except Exception as error:
        write_report("ben2_inference", error)
        return 1
    write_report("complete", "ok")
    return 0


if __name__ == "__main__":
    # Защита от случайного запуска в offscreen-режиме в рабочем терминале.
    if (
        os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
        and "--release-entrypoint-smoke" not in sys.argv
        and "--local-processing-smoke" not in sys.argv
    ):
        os.environ["QT_QPA_PLATFORM"] = "windows"
    app = QApplication(sys.argv)
    configure_application_identity(app)
    if "--release-entrypoint-smoke" in sys.argv:
        expected_version = None
        evidence_dir = None
        for argument in sys.argv:
            if argument.startswith("--expected-app-version="):
                expected_version = argument.split("=", 1)[1]
            elif argument.startswith("--ui-evidence-dir="):
                evidence_dir = argument.split("=", 1)[1]
        sys.exit(
            run_packaged_entrypoint_check(
                expected_version,
                evidence_dir=evidence_dir,
            )
        )
    if "--local-processing-smoke" in sys.argv:
        report_path = None
        for argument in sys.argv:
            if argument.startswith("--local-processing-smoke-report="):
                report_path = argument.split("=", 1)[1]
                break
        smoke_result = run_local_processing_entrypoint_check(report_path)
        # ONNX Runtime can keep native worker threads alive after a successful
        # cold-start inference on macOS. This CLI-only smoke has already written
        # its result, so do not let GUI/native teardown hold the Azure agent.
        os._exit(smoke_result)
    window = create_authorized_v3_application_window()
    if window is None:
        sys.exit(0)
    install_diagnostic_exception_hook(getattr(window, "_diagnostic_journal", None))
    window.show()
    QTimer.singleShot(1200, window.start_update_check)
    sys.exit(app.exec())
