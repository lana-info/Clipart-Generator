"""Контракт приёма перетаскиваемых PNG — модуль studio_clipart_drop (макет 2026-10-30).

Макет-контракт: docs/ui/3.2/drag-drop-png-20261030/README.md (семантика и тексты отказов).
Негативные контроли: обход валидации в модуле обязан ронять эти тесты (см. описание PR-1).
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtWidgets import QApplication

import studio_clipart_drop as drop


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def png(path: Path):
    Image.new("RGBA", (24, 24), (200, 40, 40, 255)).save(path)
    return path


def item(output: str = ""):
    return SimpleNamespace(output_path=output)


# --- валидация одного дропа (таблица «Откуда принимаем» макета) ----------------------


def test_real_png_is_accepted(tmp_path):
    accepted, reasons = drop.validate_dropped_files([png(tmp_path / "utka_03_ready.png")])
    assert accepted == [tmp_path / "utka_03_ready.png"] and reasons == []


def test_wrong_extension_rejected_with_plain_text(tmp_path):
    """Расширение не .png — отказ, даже если внутри настоящий PNG (макет: utka.jpg)."""
    source = png(tmp_path / "utka.png")
    disguised = tmp_path / "utka.jpg"
    os.replace(source, disguised)
    accepted, reasons = drop.validate_dropped_files([disguised])
    assert accepted == []
    assert reasons == ["utka.jpg — это не PNG. Перетащите файл с расширением .png"]


def test_renamed_foreign_file_rejected_by_signature(tmp_path):
    """Расширение .png, внутри другой формат — «переименованный другой файл»."""
    fake = tmp_path / "utka.png"
    fake.write_bytes(b"\xff\xd8\xff\xe0 jpeg pretend" * 8)
    accepted, reasons = drop.validate_dropped_files([fake])
    assert accepted == [] and reasons == ["utka.png — внутри не PNG (переименованный другой файл)"]


def test_symlink_is_never_accepted(tmp_path):
    outside = png(tmp_path / "outside.png")
    link = tmp_path / "link.png"
    link.symlink_to(outside)
    accepted, reasons = drop.validate_dropped_files([link])
    assert accepted == [] and reasons == ["link.png недоступен (ярлык или ссылка)"]


def test_folder_is_rejected_without_unpacking(tmp_path):
    folder = tmp_path / "album"
    folder.mkdir()
    png(folder / "deep_01_ready.png")
    accepted, reasons = drop.validate_dropped_files([folder])
    assert accepted == [] and reasons == ["Папки не принимаются — перетащите PNG-файлы"]


def test_over_64mb_rejected(tmp_path):
    big = tmp_path / "huge.png"
    with open(big, "wb") as handle:
        handle.write(drop.PNG_SIGNATURE)
        handle.truncate(drop.MAX_DROP_BYTES + 5 * 1024 * 1024)
    accepted, reasons = drop.validate_dropped_files([big])
    assert accepted == [] and reasons == ["huge.png слишком большой (69 МБ) — лимит 64 МБ"]


def test_more_than_eight_files_knock_out_the_extras(tmp_path):
    nine = [png(tmp_path / f"file_{number:02d}.png") for number in range(1, 10)]
    accepted, reasons = drop.validate_dropped_files(nine)
    assert accepted == nine[:8]
    assert reasons == ["За раз можно 8 файлов — лишние (1) не приняты"]


def test_limit_reason_sits_where_the_extras_started(tmp_path):
    """Причина лимита идёт по порядку дропа: причины файлов до неё — раньше, после — позже."""
    files = [png(tmp_path / f"good_{number}.png") for number in range(8)]
    files.insert(4, tmp_path / "mid.png")  # не существует — отказ в середине дропа
    files.extend(png(tmp_path / f"extra_{number}.png") for number in (9, 10, 11))
    accepted, reasons = drop.validate_dropped_files(files)
    assert len(accepted) == 8
    assert reasons == [
        "mid.png недоступен (ярлык или ссылка)",
        "За раз можно 8 файлов — лишние (3) не приняты",
    ]


def test_uppercase_extension_accepted_but_missing_file_explained(tmp_path):
    good = png(tmp_path / "Utka.PNG")
    accepted, reasons = drop.validate_dropped_files([good, tmp_path / "missing.png"])
    assert accepted == [good]
    assert reasons == ["missing.png недоступен (ярлык или ссылка)"]


# --- выбор позиции: явная цель > имя файла > диалог ---------------------------------


# --- дубликат «позиция уже показывает файл» ----------------------------------------


def test_same_file_content_by_path_and_by_bytes(tmp_path):
    first = png(tmp_path / "a.png")
    Image.new("RGBA", (30, 30), (10, 200, 60, 255)).save(tmp_path / "c.png")
    other = tmp_path / "c.png"
    assert drop.same_file_content(first, first.resolve())
    assert not drop.same_file_content(first, other)


# --- имя копии и копирование в папку результата -------------------------------------


def test_copy_lands_in_the_result_folder_and_keeps_the_source(tmp_path):
    source = png(tmp_path / "duckling.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    copied = drop.copy_for_position(source, output_dir, 4)
    assert copied == output_dir / "duckling_04_ready.png"
    assert copied.read_bytes() == source.read_bytes()
    assert source.is_file()  # файл из «Загрузок» не изменяется и не переносится


def test_copy_collision_gets_a_suffix_like_the_workers(tmp_path):
    source = png(tmp_path / "duckling.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    first = drop.copy_for_position(source, output_dir, 1)
    second = drop.copy_for_position(source, output_dir, 1)
    assert first.name == "duckling_01_ready.png"
    assert second.name == "duckling_01_ready_2.png"
    assert drop.same_file_content(first, second)


# --- лимиты --------------------------------------------------------------------------


def test_module_limit_constants_match_the_mock():
    assert drop.MAX_DROP_FILES == 8 and drop.MAX_DROP_BYTES == 64 * 1024 * 1024
    assert drop.DROP_MB_LIMIT == 64


def test_copy_name_follows_the_position_template(tmp_path):
    source = png(tmp_path / "duckling.png")
    assert drop.copy_for_position(source, tmp_path, 4).name == "duckling_04_ready.png"


def test_copy_name_keeps_cyrillic_and_strips_forbidden_characters(tmp_path):
    source = png(tmp_path / "утка золотая осень.png")
    named = drop.copy_for_position(source, tmp_path, 2).name
    assert named.endswith("_02_ready.png") and "утка" in named and "осень" in named


def test_copy_name_never_loses_the_position_suffix_on_a_long_stem(tmp_path):
    source = png(tmp_path / ("у" * 100 + ".png"))
    named = drop.copy_for_position(source, tmp_path, 7).name
    assert named.endswith("_07_ready.png")
    assert len(named) <= 240
