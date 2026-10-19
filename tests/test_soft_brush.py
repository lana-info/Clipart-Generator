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
    assert partial(soft) >= 7          # soft edge: wide gradual transition
    # Overlapping stamps must not accumulate into a hard edge on the soft stroke.
    assert soft[0] == 255 and soft[8] < 200


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
