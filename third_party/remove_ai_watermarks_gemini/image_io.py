"""Minimal Unicode-safe image helpers required by the vendored detector."""

from pathlib import Path

import cv2
import numpy as np


def imread(path, flags=None):
    if flags is None:
        flags = cv2.IMREAD_COLOR
    try:
        data = np.fromfile(str(Path(path)), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def to_bgr(image):
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if image.ndim == 3 and image.shape[2] == 3:
        return image
    raise ValueError(f"Unsupported image shape: {image.shape}")
