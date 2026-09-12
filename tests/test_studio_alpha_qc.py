import hashlib
from pathlib import Path

from PIL import Image

from studio_alpha_qc import inspect_alpha_png


def _save(path: Path, image: Image.Image) -> Path:
    image.save(path, format='PNG')
    return path


def test_valid_transparent_png_passes_without_mutating_bytes(tmp_path):
    path = tmp_path / 'good.png'
    image = Image.new('RGBA', (40, 40), (0, 0, 0, 0))
    for y in range(10, 30):
        for x in range(10, 30):
            image.putpixel((x, y), (180, 120, 80, 255))
    _save(path, image)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    report = inspect_alpha_png(path)

    assert report.status == 'ok'
    assert report.issues == ()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_rgb_or_fully_opaque_png_blocks_as_missing_transparency(tmp_path):
    rgb = _save(tmp_path / 'rgb.png', Image.new('RGB', (32, 32), (20, 30, 40)))
    opaque = _save(tmp_path / 'opaque.png', Image.new('RGBA', (32, 32), (20, 30, 40, 255)))

    for path in (rgb, opaque):
        report = inspect_alpha_png(path)
        assert report.status == 'block'
        assert report.issues[0].code == 'no_transparency'
        assert 'прозрач' in report.issues[0].message.casefold()


def test_nearly_empty_png_blocks_with_specific_reason(tmp_path):
    path = tmp_path / 'empty.png'
    image = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    image.putpixel((50, 50), (120, 80, 40, 255))
    _save(path, image)

    report = inspect_alpha_png(path)

    assert report.status == 'block'
    assert any(issue.code == 'nearly_empty' for issue in report.issues)
    assert any('почти пуст' in issue.message.casefold() for issue in report.issues)


def test_subject_touching_canvas_edge_is_review_not_block(tmp_path):
    path = tmp_path / 'touching.png'
    image = Image.new('RGBA', (50, 50), (0, 0, 0, 0))
    for y in range(10, 40):
        for x in range(0, 25):
            image.putpixel((x, y), (100, 80, 60, 255))
    _save(path, image)

    report = inspect_alpha_png(path)

    assert report.status == 'review'
    issue = next(issue for issue in report.issues if issue.code == 'touches_edge')
    assert 'кра' in issue.message.casefold()
    assert issue.action


def test_residual_uniform_color_fringe_is_review_when_internal_hint_is_known(tmp_path):
    path = tmp_path / 'fringe.png'
    image = Image.new('RGBA', (60, 60), (0, 0, 0, 0))
    # Solid warm object.
    for y in range(15, 45):
        for x in range(15, 45):
            image.putpixel((x, y), (190, 120, 70, 255))
    # Semi-transparent saturated fringe, deliberately separated from the subject colour.
    for x in range(14, 46):
        image.putpixel((x, 14), (0, 0, 255, 150))
        image.putpixel((x, 45), (0, 0, 255, 150))
    for y in range(14, 46):
        image.putpixel((14, y), (0, 0, 255, 150))
        image.putpixel((45, y), (0, 0, 255, 150))
    _save(path, image)

    report = inspect_alpha_png(path, residue_hint='#0000FF')

    assert report.status == 'review'
    issue = next(issue for issue in report.issues if issue.code == 'color_fringe')
    assert 'цветн' in issue.message.casefold()
    assert '#0000ff' not in issue.message.casefold()
    assert 'син' not in issue.message.casefold()


def test_unreadable_file_blocks_with_plain_language_reason(tmp_path):
    path = tmp_path / 'broken.png'
    path.write_bytes(b'not a png')

    report = inspect_alpha_png(path)

    assert report.status == 'block'
    assert report.issues[0].code == 'unreadable'
    assert 'прочитать' in report.issues[0].message.casefold()


def test_too_many_semitransparent_subject_pixels_are_review_with_specific_reason(tmp_path):
    path = tmp_path / 'too-translucent.png'
    image = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    for y in range(25, 75):
        for x in range(25, 75):
            image.putpixel((x, y), (160, 110, 70, 100))
    _save(path, image)

    report = inspect_alpha_png(path)

    assert report.status == 'review'
    issue = next(issue for issue in report.issues if issue.code == 'too_translucent')
    assert 'полупрозрач' in issue.message.casefold()
    assert issue.action


def test_expected_interior_opening_accepts_clear_frame_center(tmp_path):
    path = tmp_path / 'frame.png'
    image = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    for y in range(20, 80):
        for x in range(20, 80):
            if not (35 <= x < 65 and 35 <= y < 65):
                image.putpixel((x, y), (120, 90, 60, 255))
    _save(path, image)

    report = inspect_alpha_png(path, expect_interior_opening=True)

    assert not any(issue.code == 'missing_interior_opening' for issue in report.issues)


def test_expected_interior_opening_reviews_filled_center(tmp_path):
    path = tmp_path / 'filled-wreath.png'
    image = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    for y in range(20, 80):
        for x in range(20, 80):
            image.putpixel((x, y), (120, 90, 60, 255))
    _save(path, image)

    report = inspect_alpha_png(path, expect_interior_opening=True)

    issue = next(issue for issue in report.issues if issue.code == 'missing_interior_opening')
    assert report.status == 'review'
    assert 'внутрен' in issue.message.casefold()
    assert 'отверст' in issue.message.casefold() or 'простран' in issue.message.casefold()
    assert issue.action


def test_expected_interior_opening_accepts_center_space_connected_to_outer_background(tmp_path):
    path = tmp_path / 'open-wreath.png'
    image = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    for y in range(20, 80):
        for x in range(20, 80):
            if not (35 <= x < 65 and 35 <= y < 65):
                image.putpixel((x, y), (120, 90, 60, 255))
    # Open a narrow channel from the center to the outside, like an intentionally open wreath.
    for y in range(0, 36):
        for x in range(48, 52):
            image.putpixel((x, y), (0, 0, 0, 0))
    _save(path, image)

    report = inspect_alpha_png(path, expect_interior_opening=True)

    assert not any(issue.code == 'missing_interior_opening' for issue in report.issues)
