"""Локальный апскейл не оставляет светлой каймы на тёмном фоне (приёмка под-альфы, 2026-10-31).

Приёмка #195 смотрела на светлом фоне. На тёмном видна обратная беда: спрятанный под прозрачностью
светлый RGB (Bria, старые апскейлы) растягивается апскейлером в мягкую кайму вокруг тёмного предмета.
Real-ESRGAN офлайн недоступен — вместо него плоское увеличение Lanczos: оно так же смешивает соседние
пиксели, а проверяется именно подготовка RGB (`_prepare_upscale_rgb`) и возврат альфы (`_restore_upscaled_alpha`).
"""
import cv2
import numpy as np
import pytest
from PIL import Image

import main

SIZE = 48
SCALE = 2
SUBJECT = np.array((30, 40, 90), dtype=float)  # тёмно-синий предмет
DARK_BACKGROUND = np.array((12, 12, 12), dtype=float)


def _cutout(hidden_rgb, hard=False):
    """Dark disc; `hard` is a binary matte (Bria, hard cut-out), otherwise a 3 px soft edge."""
    yy, xx = np.mgrid[:SIZE, :SIZE]
    radius = np.hypot(xx - SIZE / 2, yy - SIZE / 2)
    alpha = np.clip((16 - radius) / 3.0, 0.0, 1.0)
    if hard:
        alpha = (alpha >= 0.5).astype(float)
    pixels = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    pixels[..., :3] = hidden_rgb
    inside = alpha > 0
    pixels[inside, :3] = SUBJECT
    pixels[..., 3] = np.rint(alpha * 255).astype(np.uint8)
    return Image.fromarray(pixels)


def _upscale_and_composite(tmp_path, cutout, prepare):
    rgb = prepare(cutout)
    big = rgb.resize((SIZE * SCALE, SIZE * SCALE), Image.Resampling.LANCZOS).convert("RGBA")
    path = tmp_path / "upscaled.png"
    big.save(path)
    worker = main.WorkerThread("mode2_process", str(tmp_path), {})
    worker._restore_upscaled_alpha(str(path), cutout.getchannel("A"))
    with Image.open(path) as result:
        shown = np.asarray(result.convert("RGBA"), dtype=float)
    alpha = shown[..., 3:4] / 255.0
    return shown[..., :3] * alpha + DARK_BACKGROUND * (1 - alpha), shown[..., 3]


def _brightest_edge_excess(composite, alpha):
    """How much brighter than the subject the visible outline gets (a light halo on a dark background).

    The outline is the visible pixels within two pixels of the edge: for a hard matte it is fully
    opaque, for a soft one it also holds the partially transparent ring.
    """
    visible = alpha > 0
    inner = cv2.erode(visible.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2) > 0
    outline = visible & ~inner
    assert outline.any()
    return float(composite[outline].max() - SUBJECT.max())


@pytest.mark.parametrize("hard", [True, False], ids=["hard-matte", "soft-matte"])
@pytest.mark.parametrize("hidden", [(255, 255, 255), (250, 230, 40), (0, 255, 0)],
                         ids=["white", "yellow", "green"])
def test_light_hidden_colour_does_not_become_a_halo_on_a_dark_background(tmp_path, hidden, hard):
    composite, alpha = _upscale_and_composite(
        tmp_path, _cutout(hidden, hard), main.WorkerThread._prepare_upscale_rgb)
    assert _brightest_edge_excess(composite, alpha) <= 1, "светлая кайма вокруг тёмного предмета"


def test_the_halo_is_real_without_the_preparation(tmp_path):
    """Контроль самого теста: без подготовки RGB белый мусор даёт кайму (иначе проверка ничего не доказывает)."""
    composite, alpha = _upscale_and_composite(
        tmp_path, _cutout((255, 255, 255), hard=True), lambda image: image.convert("RGB"))
    assert _brightest_edge_excess(composite, alpha) >= 5


def test_the_subject_interior_is_not_recoloured(tmp_path):
    composite, alpha = _upscale_and_composite(tmp_path, _cutout((255, 255, 255)),
                                              main.WorkerThread._prepare_upscale_rgb)
    inner = alpha == 255
    assert inner.any()
    assert np.abs(composite[inner] - SUBJECT).max() <= 2
