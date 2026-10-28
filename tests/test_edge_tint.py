"""Key-ward colour cast on the soft edge is pulled back to the neighbouring subject colour, nothing else moves."""
import cv2
import numpy as np
from PIL import Image

from edge_tint import suppress_key_tint

CREAM = (230, 200, 160)


def _lab(rgb):
    return cv2.cvtColor(np.array([[rgb]], np.float32) / 255.0, cv2.COLOR_RGB2Lab)[0, 0]


def _disc(colour_for, size=100, radius=34):
    """RGBA disc: opaque inside, a 2 px partial rim; colour_for(x, y, rim) gives the pixel colour."""
    image = np.zeros((size, size, 4), np.uint8)
    for y in range(size):
        for x in range(size):
            distance = np.hypot(x - size / 2, y - size / 2)
            if distance <= radius:
                image[y, x] = (*colour_for(x, y, False), 255)
            elif distance <= radius + 2:
                image[y, x] = (*colour_for(x, y, True), 128)
    return Image.fromarray(image, "RGBA")


def _chroma_error(pixel, target):
    return float(np.hypot(*(_lab(pixel)[1:] - _lab(target)[1:])))


def test_lilac_rim_of_cream_fur_gets_the_fur_hue_back():
    lilac = (150, 120, 170)  # cream mixed with the blue key
    image = _disc(lambda x, y, rim: lilac if rim else CREAM)

    result = suppress_key_tint(image, "blue")

    before, after = image.getpixel((85, 50)), result.getpixel((85, 50))
    assert before[3] == 128 and after[3] == 128
    assert _chroma_error(after[:3], CREAM) < 0.4 * _chroma_error(before[:3], CREAM)


def test_spots_of_key_cast_just_inside_the_edge_are_corrected_too():
    grey_blue = (170, 175, 205)
    image = _disc(lambda x, y, rim: grey_blue if (x, y) == (80, 50) else CREAM)

    result = suppress_key_tint(image, "blue")

    assert _chroma_error(result.getpixel((80, 50))[:3], CREAM) < 0.5 * _chroma_error(grey_blue, CREAM)


def test_edge_pixels_between_two_different_subject_colours_are_left_alone():
    """A green leaf tip beside a red berry: the neighbourhood is not one colour, so there is no reference."""
    red, green = (200, 40, 40), (60, 140, 60)

    def colour(x, y, rim):
        side = green if x >= 50 else red
        return tuple(int(v * 0.7) for v in side) if rim else side

    image = _disc(colour)
    result = suppress_key_tint(image, "blue")

    for x in (53, 56, 46):
        before, after = np.array(image.getpixel((x, 16))), np.array(result.getpixel((x, 16)))
        assert np.abs(before - after).max() <= 8, (x, before, after)


def test_interior_far_from_the_edge_and_unknown_key_are_untouched():
    image = _disc(lambda x, y, rim: (150, 120, 170) if rim else CREAM)

    result = suppress_key_tint(image, "blue")

    assert result.getpixel((50, 50)) == image.getpixel((50, 50))
    assert result.getpixel((0, 0)) == image.getpixel((0, 0))
    assert suppress_key_tint(image, "magenta") is image
