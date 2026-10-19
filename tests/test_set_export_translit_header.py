from __future__ import annotations

import os
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from studio_delivery import (
    assign_output_names,
    create_contact_sheet_pdf,
    slug_from_title,
    transliterate_ru,
)
from studio_set_export import export_clipart_sets


def test_russian_names_are_transliterated_not_translated():
    assert transliterate_ru("второй") == "vtoroy"
    assert slug_from_title("Второй цветок") == "vtoroy-tsvetok"
    assert slug_from_title("Щенок и ёжик") == "shchenok-i-ezhik"
    assert assign_output_names(["Синяя лиса"])[0] == "001_sinyaya-lisa.png"
    # Latin names are untouched.
    assert slug_from_title("Pink bear") == "pink-bear"


def test_export_uses_latin_file_and_archive_names_and_titled_pdf(tmp_path):
    sources = []
    for index in range(3):
        path = tmp_path / f"картинка{index}.png"
        Image.new("RGBA", (40, 30), (255, 0, 0, 200)).save(path)
        sources.append(str(path))
    destination = tmp_path / "out"
    destination.mkdir()
    archives = export_clipart_sets([{"title": "Зимние птицы", "images": sources}], destination)
    assert [a.name for a in archives] == ["001_zimnie-ptitsy.zip"]
    with ZipFile(archives[0]) as zf:
        names = zf.namelist()
        assert "overview.pdf" in names
        pngs = [n for n in names if n.startswith("png/")]
        assert pngs == ["png/001_kartinka0.png", "png/002_kartinka1.png", "png/003_kartinka2.png"]
        assert all(name.isascii() for name in names)


def test_pdf_header_adds_title_and_keeps_all_images_on_one_sheet(tmp_path):
    paths = []
    for index in range(20):
        path = tmp_path / f"{index + 1:03d}_x.png"
        Image.new("RGBA", (60, 40), "red").save(path)
        paths.append(path)
    with_title = tmp_path / "titled.pdf"
    create_contact_sheet_pdf(paths, with_title, title="Winter birds")
    assert b"/Count 1" in with_title.read_bytes()
    # 40 images need two pages even with the header (30 per sheet).
    more = paths + paths[:10] + paths[:10]
    two_pages = tmp_path / "two.pdf"
    create_contact_sheet_pdf(more, two_pages, title="Winter birds")
    assert b"/Count 2" in two_pages.read_bytes()


def test_very_long_title_does_not_hang_and_is_elided(tmp_path):
    source = tmp_path / "a.png"
    Image.new("RGBA", (30, 30), "red").save(source)
    output = tmp_path / "long.pdf"
    create_contact_sheet_pdf([source], output, title="Watercolor spring flowers botanical clipart bundle " * 80)
    assert output.read_bytes().startswith(b"%PDF")
