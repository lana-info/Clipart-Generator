"""Run the bundled MI-GAN model on a bounded image mask."""

from functools import lru_cache
import hashlib
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


MODEL_SHA256 = "593eba0b7e04730f1b61c0a3cbca68d97d8d6a7ff5c6a44a7b9d7fcd880fc5ae"


@lru_cache(maxsize=1)
def _session():
    model_path = Path(__file__).with_name("migan.onnx")
    if not model_path.is_file():
        raise RuntimeError("Bundled MI-GAN model is missing")
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        raise RuntimeError("Bundled MI-GAN model failed its integrity check")
    return ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])


def _crop_box(mask, image_shape):
    ys, xs = np.where(mask > 0)
    if xs.size == 0:
        return None
    height, width = image_shape[:2]
    mark_size = max(int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
    padding = max(256, mark_size * 2)
    return (
        max(0, int(xs.min()) - padding),
        max(0, int(ys.min()) - padding),
        min(width, int(xs.max()) + 1 + padding),
        min(height, int(ys.max()) + 1 + padding),
    )


def inpaint_bgr(image_bgr, mask):
    """Inpaint ``mask`` locally while keeping every unmasked pixel exact."""
    if image_bgr is None or image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("MI-GAN requires a three-channel BGR image")
    if mask is None or mask.shape != image_bgr.shape[:2]:
        raise ValueError("MI-GAN mask dimensions do not match the image")

    box = _crop_box(mask, image_bgr.shape)
    if box is None:
        return image_bgr.copy()
    x1, y1, x2, y2 = box
    crop = np.ascontiguousarray(image_bgr[y1:y2, x1:x2])
    crop_mask = np.asarray(mask[y1:y2, x1:x2], dtype=np.uint8)

    session = _session()
    inputs = session.get_inputs()
    image_name, mask_name = inputs[0].name, inputs[1].name
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    image_input = np.transpose(rgb, (2, 0, 1))[None].astype(np.uint8)
    known_input = ((crop_mask <= 127).astype(np.uint8) * 255)[None, None]
    output = session.run(
        None,
        {image_name: image_input, mask_name: known_input},
    )[0]

    output_rgb = np.transpose(np.asarray(output)[0], (1, 2, 0))
    if output_rgb.dtype != np.uint8:
        if output_rgb.size and float(output_rgb.max()) <= 1.5:
            output_rgb = output_rgb * 255.0
        output_rgb = np.clip(output_rgb, 0, 255).astype(np.uint8)
    if output_rgb.shape[:2] != crop.shape[:2]:
        output_rgb = cv2.resize(
            output_rgb,
            (crop.shape[1], crop.shape[0]),
            interpolation=cv2.INTER_LINEAR,
        )

    generated = cv2.cvtColor(output_rgb, cv2.COLOR_RGB2BGR)
    result = image_bgr.copy()
    result_crop = result[y1:y2, x1:x2]
    hole = crop_mask > 127
    result_crop[hole] = generated[hole]
    result[y1:y2, x1:x2] = result_crop
    return result
