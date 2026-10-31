"""Кисть восстановления открывает чистый цвет, а не мусор из-под прозрачности (жалоба владельца 2026-10-31).

Под alpha == 0 в PNG хранится «спрятанный» RGB: у Bria — что вернула модель, у старых локальных апскейлов —
мозаика из ближайших цветов, у доставки — чёрный. Пока пиксель прозрачен, его не видно; кисть
восстановления делает его видимым, и владелец видел «белеберду из оттенков и цветовых пятен». Редактор
обязан сам подставить под прозрачность чистый цвет предмета (тот же алгоритм, что и в подготовке апскейла).
Видимые пиксели при этом не меняются ни на единицу.
"""
import numpy as np
import pytest
from PIL import Image

from v3_transparency_preview import MaskEditDocument

SUBJECT = (200, 40, 40)
SIZE = 40


def _cutout(hidden):
    """Opaque red 14x14 subject in the middle; everything else alpha 0 with `hidden(x, y)` RGB underneath."""
    pixels = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    for y in range(SIZE):
        for x in range(SIZE):
            pixels[y, x, :3] = hidden(x, y)
    pixels[13:27, 13:27] = (*SUBJECT, 255)
    return Image.fromarray(pixels)


def _mosaic(x, y):
    """The old nearest-colour smear / provider junk: every pixel a different colour."""
    return ((x * 37) % 256, (y * 91) % 256, ((x + y) * 53) % 256)


def _restore(document, centre, radius=6):
    document.begin_stroke()
    document.extend_stroke([centre], radius=radius, hardness=100, action="add")
    document.end_stroke()


def _restored_pixels(document):
    shown = np.asarray(document.corrected_image())
    return shown[shown[:, :, 3] > 0][:, :3], shown


@pytest.mark.parametrize("hidden", [_mosaic, lambda x, y: (0, 0, 0), lambda x, y: (255, 255, 255)],
                         ids=["mosaic", "black", "white"])
def test_restoring_the_background_reveals_one_flat_subject_colour_not_the_hidden_junk(hidden):
    document = MaskEditDocument(_cutout(hidden))
    _restore(document, (5, 5))  # a corner far away from the subject
    shown = np.asarray(document.corrected_image())
    patch = shown[0:11, 0:11]
    assert (patch[:, :, 3] == 255).any(), "the brush must have restored something"
    colours = {tuple(pixel[:3]) for pixel in patch[patch[:, :, 3] == 255]}
    assert colours == {SUBJECT}, colours


def test_visible_pixels_are_not_changed_by_opening_or_saving_the_editor():
    source = _cutout(_mosaic)
    document = MaskEditDocument(source)
    original = np.asarray(source)
    shown = np.asarray(document.corrected_image())
    visible = original[:, :, 3] > 0
    np.testing.assert_array_equal(shown[visible], original[visible])
    np.testing.assert_array_equal(shown[:, :, 3], original[:, :, 3])


def test_soft_edge_pixels_keep_their_own_colour_and_alpha():
    pixels = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    pixels[:, :, :3] = _mosaic(3, 4)
    pixels[13:27, 13:27] = (*SUBJECT, 255)
    pixels[12, 13:27] = (90, 200, 90, 120)  # a soft edge row
    document = MaskEditDocument(Image.fromarray(pixels))
    shown = np.asarray(document.corrected_image())
    assert tuple(shown[12, 20]) == (90, 200, 90, 120)


def test_fully_transparent_image_keeps_working():
    document = MaskEditDocument(Image.new("RGBA", (8, 8), (9, 8, 7, 0)))
    _restore(document, (4, 4), radius=2)
    assert document.corrected_image().size == (8, 8)


def test_image_without_alpha_is_untouched():
    source = Image.new("RGB", (8, 8), (10, 20, 30))
    document = MaskEditDocument(source)
    assert set(document.corrected_image().getdata()) == {(10, 20, 30, 255)}
