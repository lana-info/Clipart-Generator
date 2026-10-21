from PIL import Image

from background_mask import paint_mask_path
from v3_transparency_preview import MaskEditDocument


def _row(mask, y):
    return [mask.getpixel((x, y)) for x in range(mask.width)]


def test_soft_brush_has_wide_gradual_edge_unlike_hard():
    results = {}
    for name, hardness in (("hard", 100), ("soft", 0)):
        mask = Image.new("L", (80, 40), 0)
        paint_mask_path(mask, [(20, 20), (60, 20)], radius=12, action="add", hardness=hardness)
        results[name] = mask
    # Cross-section through the stroke middle (x = 40), walking up from the centre.
    hard = [results["hard"].getpixel((40, 20 - d)) for d in range(0, 14)]
    soft = [results["soft"].getpixel((40, 20 - d)) for d in range(0, 14)]
    partial = lambda col: sum(1 for v in col if 20 < v < 235)
    assert partial(hard) <= 2          # hard edge: nearly all-or-nothing
    assert partial(soft) >= 3          # soft edge: gradual transition in the outer band
    # Overlapping stamps must not accumulate into a hard edge on the soft stroke.
    assert soft[0] >= 250 and soft[6] >= 250 and soft[12] < 60   # core stays solid, same outer width


def test_document_stroke_in_several_moves_matches_single_stroke():
    image = Image.new("RGBA", (80, 40), (255, 0, 0, 0))
    document = MaskEditDocument(image)
    document.begin_stroke()
    for chunk in (((20, 20), (30, 20)), ((30, 20), (45, 20)), ((45, 20), (60, 20))):
        document.extend_stroke(chunk, radius=12, action="add", hardness=0)
    document.end_stroke()
    single = Image.new("L", (80, 40), 0)
    paint_mask_path(single, [(20, 20), (30, 20), (45, 20), (60, 20)], radius=12, action="add", hardness=0)
    assert list(document.mask.getdata()) == list(single.getdata())
    document.undo()
    assert document.mask.getextrema() == (0, 0)


def _edge_wobble(points, radius=10, size=(160, 80)):
    """Largest deviation of the stroke's top edge from a straight/smooth line."""
    mask = Image.new("L", size, 0)
    paint_mask_path(mask, points, radius=radius, action="add", hardness=100)
    tops = []
    for x in range(30, size[0] - 30):
        column = [mask.getpixel((x, y)) for y in range(size[1])]
        coverage = sum(column) / 255.0
        tops.append(coverage)
    return max(tops) - min(tops)


def test_subpixel_diagonal_stroke_has_even_thickness():
    # Integer-rounded stamps wobble along a shallow diagonal; sub-pixel ones do not.
    points = [(20 + i * 0.37, 20 + i * 0.11) for i in range(0, 330)]
    assert _edge_wobble(points) < 0.6


def test_smoothing_curve_rounds_a_sharp_corner_and_ends_at_midpoint():
    from v3_transparency_preview import TransparencyCanvas

    start, corner, end = (0.0, 0.0), (10.0, 0.0), (10.0, 10.0)
    curve = TransparencyCanvas._smooth_curve(start, corner, end)
    assert curve[-1] == end
    # A straight polyline would pass through the corner; the curve cuts it.
    assert min(((x - corner[0]) ** 2 + (y - corner[1]) ** 2) ** 0.5 for x, y in curve) > 2.0
    assert len(curve) >= 7


def test_single_pixel_brush_stays_hard_and_small_brushes_can_be_soft():
    from background_mask import soft_feather_width
    def stroke(radius, hardness):
        mask = Image.new("L", (80, 40), 0)
        paint_mask_path(mask, [(20, 20), (60, 20)], radius=radius, action="add", hardness=hardness)
        return mask
    assert list(stroke(0, 0).getdata()) == list(stroke(0, 100).getdata())
    for radius in (1, 3):  # 3 px and 6 px brushes (owner decision 2026-10-21)
        soft, hard = stroke(radius, 0), stroke(radius, 100)
        assert list(soft.getdata()) != list(hard.getdata())
        assert soft.getpixel((40, 20)) == 255                      # core stays solid
        assert all(abs(a - b) <= 1 for a, b in zip(soft.getbbox(), hard.getbbox()))  # same outer width (rim pixel may fade out)
        assert 0 < sum(1 for v in soft.getdata() if 0 < v < 255)    # a real soft transition
    # Feather width: a quarter of the diameter, 1 px minimum, 10 px maximum, none at hardness 100.
    assert soft_feather_width(3, 100) == 0
    assert 1.0 <= soft_feather_width(3, 0) <= 1.75
    assert soft_feather_width(8, 0) == 4.25 and soft_feather_width(32, 0) == 10.0
    assert soft_feather_width(100, 0) == 10.0
    assert soft_feather_width(32, 50) == 5.0
    wide = Image.new("L", (160, 100), 0)
    paint_mask_path(wide, [(40, 50), (120, 50)], radius=32, action="add", hardness=0)
    profile = [wide.getpixel((80, 50 - d)) for d in range(0, 33)]
    assert all(a >= b for a, b in zip(profile, profile[1:]))      # monotonic, no bumps
    steps = [a - b for a, b in zip(profile, profile[1:])]
    assert max(steps) < 45                                         # gradual: no hard step
    # Same width as the hard brush: solid across most of the radius, fading only near the rim.
    assert profile[0] >= 250 and profile[16] >= 250 and profile[28] < 170 and profile[-1] <= 2
