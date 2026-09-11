from pathlib import Path

import pytest
from PIL import Image

from studio_delivery import assign_output_names, create_contact_sheet_pdf, output_filename, slug_from_title


def test_stable_names_are_ordinal_and_short_even_when_completion_is_reordered():
    assert assign_output_names(["Pink bear", "Синяя лиса", "Object: a very long prompt"])[0] == "001_pink-bear.png"
    assert assign_output_names(["Pink bear", "Синяя лиса", "Object: a very long prompt"])[1].startswith("002_")
    assert len(assign_output_names(["😀" * 100])[0]) < 160


def test_slug_is_safe_and_variant_is_explicit():
    slug = slug_from_title("../CON: розовая, медведица! / scene")
    assert "/" not in slug and "\\" not in slug and slug.startswith("item-con")
    assert output_filename(1, "Pink bear", variant=2) == "001_pink-bear-2.png"


def test_collision_gets_suffix_without_overwriting():
    assert output_filename(1, "Pink bear", existing_names=["001_pink-bear.png"]) == "001_pink-bear-2.png"


def _images(folder: Path, count: int):
    paths = []
    for index in range(count):
        path = folder / f"{index + 1:03d}_тест.png"
        Image.new("RGBA", (80 + index, 60), (255, 0, 0, 120)).save(path)
        paths.append(path)
    return paths


def test_contact_sheet_has_five_columns_and_expected_page_count(tmp_path):
    paths = _images(tmp_path, 31)
    output = tmp_path / "sheet.pdf"
    create_contact_sheet_pdf(paths, output)
    data = output.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"/Count 2" in data
    assert b"/MediaBox [0 0 612.000000 792.000000]" in data


def test_invalid_input_is_atomic_and_source_is_not_lost(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGBA", (10, 10), "red").save(source)
    output = tmp_path / "sheet.pdf"
    output.write_bytes(b"old pdf")
    with pytest.raises(ValueError):
        create_contact_sheet_pdf([source], source)
    assert source.exists()
    assert output.read_bytes() == b"old pdf"
    with pytest.raises(FileNotFoundError):
        create_contact_sheet_pdf([tmp_path / "missing.png"], output)
    assert output.read_bytes() == b"old pdf"


def test_existing_pdf_requires_explicit_overwrite_and_geometry_is_validated(tmp_path):
    source = _images(tmp_path, 1)[0]
    output = tmp_path / "sheet.pdf"
    output.write_bytes(b"old pdf")
    with pytest.raises(FileExistsError):
        create_contact_sheet_pdf([source], output)
    with pytest.raises(ValueError):
        create_contact_sheet_pdf([source], tmp_path / "other.pdf", margin=float("nan"))
    with pytest.raises(ValueError):
        create_contact_sheet_pdf([source], tmp_path / "other.pdf", rows=True)
    assert output.read_bytes() == b"old pdf"
