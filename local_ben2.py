import hashlib
import os
import ssl
from pathlib import Path
from urllib.request import Request, urlopen


BEN2_MODEL_REVISION = "e48a20765fb421d19dcdb0bf3cc61e802ca5ec8f"
BEN2_MODEL_FILENAME = "BEN2_Base.onnx"
BEN2_MODEL_SIZE = 222_932_053
BEN2_MODEL_SHA256 = "22cea62108ff53b7ccc20f7a008bf30494228d84b1687f29ecbe76936a998101"
BEN2_MODEL_URL = (
    "https://huggingface.co/PramaLLC/BEN2/resolve/"
    f"{BEN2_MODEL_REVISION}/{BEN2_MODEL_FILENAME}"
)


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_cached_model(
    path,
    *,
    expected_size=BEN2_MODEL_SIZE,
    expected_sha256=BEN2_MODEL_SHA256,
):
    model_path = Path(path)
    if not model_path.is_file():
        raise RuntimeError("Модель BEN2 не найдена.")
    actual_size = model_path.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(
            f"Неверный размер модели BEN2: {actual_size} вместо {expected_size}."
        )
    if _sha256(model_path).lower() != expected_sha256.lower():
        raise RuntimeError("Контрольная сумма модели BEN2 не совпадает.")
    return model_path


def ensure_ben2_model(cache_dir, *, progress=None, cancel_check=None):
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    model_path = cache_path / BEN2_MODEL_FILENAME
    if model_path.exists():
        try:
            return validate_cached_model(model_path)
        except RuntimeError:
            model_path.unlink(missing_ok=True)

    partial_path = model_path.with_suffix(model_path.suffix + ".part")
    partial_path.unlink(missing_ok=True)
    request = Request(BEN2_MODEL_URL, headers={"User-Agent": "Vibix Images"})
    try:
        with urlopen(request, timeout=60, context=ssl.create_default_context()) as response:
            declared_size = response.headers.get("Content-Length")
            if declared_size and int(declared_size) != BEN2_MODEL_SIZE:
                raise RuntimeError("Сервер вернул неожиданный размер модели BEN2.")
            downloaded = 0
            last_percent = -1
            with partial_path.open("wb") as output:
                while True:
                    if cancel_check is not None:
                        cancel_check()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > BEN2_MODEL_SIZE:
                        raise RuntimeError("Загрузка модели BEN2 превысила ожидаемый размер.")
                    output.write(chunk)
                    percent = int(downloaded * 100 / BEN2_MODEL_SIZE)
                    if progress is not None and percent >= last_percent + 5:
                        progress(f"  BEN2: загрузка модели {percent}%")
                        last_percent = percent
        validate_cached_model(partial_path)
        os.replace(partial_path, model_path)
        return model_path
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise


class LocalBen2OnnxModel:
    def __init__(self, session):
        self.session = session
        self.input_name = session.get_inputs()[0].name

    @staticmethod
    def _refine_foreground(image, mask, radius=90):
        import cv2
        import numpy as np
        from PIL import Image

        rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
        alpha = np.asarray(mask, dtype=np.float32) / 255.0
        alpha_3d = alpha[:, :, None]

        def estimate(source, foreground, background, blur_radius):
            blurred_alpha = cv2.blur(alpha_3d, (blur_radius, blur_radius))[:, :, None]
            blurred_foreground = cv2.blur(foreground * alpha_3d, (blur_radius, blur_radius))
            blurred_foreground /= blurred_alpha + 1e-5
            blurred_background = cv2.blur(
                background * (1.0 - alpha_3d),
                (blur_radius, blur_radius),
            )
            blurred_background /= (1.0 - blurred_alpha) + 1e-5
            estimated = blurred_foreground + alpha_3d * (
                source
                - alpha_3d * blurred_foreground
                - (1.0 - alpha_3d) * blurred_background
            )
            return np.clip(estimated, 0.0, 1.0), blurred_background

        foreground, background = estimate(rgb, rgb, rgb, radius)
        foreground, _ = estimate(rgb, foreground, background, 6)
        return Image.fromarray((foreground * 255.0).astype(np.uint8))

    def inference(self, image, refine_foreground=False):
        import numpy as np
        from PIL import Image

        source = image.convert("RGB")
        resized = source.resize((1024, 1024), Image.Resampling.BILINEAR)
        tensor = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))[None, ...]
        outputs = self.session.run(None, {self.input_name: tensor})
        mask = np.asarray(outputs[0], dtype=np.float32).squeeze()
        if mask.ndim != 2:
            raise RuntimeError(f"BEN2 вернул маску неверной формы: {mask.shape!r}")
        mask_image = Image.fromarray(mask).resize(
            source.size,
            Image.Resampling.BILINEAR,
        )
        mask = np.asarray(mask_image, dtype=np.float32)
        minimum = float(mask.min())
        maximum = float(mask.max())
        if maximum > minimum:
            mask = (mask - minimum) / (maximum - minimum)
        else:
            mask = np.zeros_like(mask)
        alpha = Image.fromarray((mask * 255.0).astype(np.uint8))
        foreground = (
            self._refine_foreground(source, alpha)
            if refine_foreground
            else source
        )
        result = foreground.convert("RGBA")
        result.putalpha(alpha)
        return result


def load_local_ben2_onnx_model(cache_dir, *, progress=None, cancel_check=None):
    try:
        import onnxruntime
    except (ImportError, OSError) as exc:
        raise RuntimeError(f"Local BEN2 ONNX недоступен: {exc}") from exc

    model_path = ensure_ben2_model(
        cache_dir,
        progress=progress,
        cancel_check=cancel_check,
    )
    try:
        session_options = onnxruntime.SessionOptions()
        session_options.enable_cpu_mem_arena = False
        session_options.enable_mem_pattern = False
        session_options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        session_options.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_ENABLE_BASIC
        )
        session_options.intra_op_num_threads = 1
        session_options.inter_op_num_threads = 1
        session = onnxruntime.InferenceSession(
            str(model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
    except Exception as exc:
        raise RuntimeError(f"Не удалось загрузить модель BEN2 ONNX: {exc}") from exc
    return LocalBen2OnnxModel(session)
