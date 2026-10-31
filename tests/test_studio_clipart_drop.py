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


def test_explicit_target_wins_over_the_file_name():
    items = [item(), item(), item()]
    source = Path("utka_03_ready.png")
    assert drop.resolve_position(source, items, target_index=0) == 0
    assert drop.resolve_position(source, items, target_index=None) == 2  # из имени _03_ready


def test_name_hint_never_leaves_the_set():
    assert drop.suggest_position("utka_03_ready.png", 6) == 2
    assert drop.suggest_position("utka_03_ready_2.png", 6) == 2   # копия коллизии — та же позиция
    assert drop.suggest_position("utka.PNG", 6) is None           # чужое имя: цифры нет
    assert drop.suggest_position("utka_09_ready.png", 6) is None  # номер вне диапазона
    assert drop.suggest_position("utka_03_ready.png", 0) is None


# --- дубликат «позиция уже показывает файл» ----------------------------------------


def test_duplicate_by_path_is_rejected(tmp_path):
    positioned = png(tmp_path / "utka_03_ready.png")
    items = [item(), item(str(positioned.resolve())), item()]
    planned, rejects = drop.plan_attachments([positioned], items, {positioned: 2})
    assert planned == [] and rejects == ["Эта картинка уже стоит на позиции 2"]


def test_duplicate_by_content_is_rejected(tmp_path):
    positioned = png(tmp_path / "utka_03_ready.png")
    copy = tmp_path / "копия utka (1).png"
    copy.write_bytes(positioned.read_bytes())
    items = [item(), item(str(positioned.resolve())), item()]
    planned, rejects = drop.plan_attachments([copy], items, {copy: 2})
    assert planned == [] and rejects == ["Эта картинка уже стоит на позиции 2"]


def test_same_file_content_by_path_and_by_bytes(tmp_path):
    first = png(tmp_path / "a.png")
    Image.new("RGBA", (30, 30), (10, 200, 60, 255)).save(tmp_path / "c.png")
    other = tmp_path / "c.png"
    assert drop.same_file_content(first, first.resolve())
    assert not drop.same_file_content(first, other)


def test_free_and_busy_positions_are_planned_in_order(tmp_path):
    first = png(tmp_path / "new_01.png")
    second = png(tmp_path / "utka_03_ready.png")
    items = [item(""), item(str(tmp_path / "other_02_ready.png")), item("")]
    planned, rejects = drop.plan_attachments([first, second], items, {first: 1, second: 3})
    assert rejects == []
    assert [(plan.number, plan.busy) for plan in planned] == [(1, False), (3, False)]


def test_busy_position_needs_the_replace_question(tmp_path):
    source = png(tmp_path / "utka.png")
    Image.new("RGBA", (40, 40), (30, 90, 200, 255)).save(tmp_path / "old_01_ready.png")
    items = [item(str((tmp_path / "old_01_ready.png").resolve()))]
    planned, _rejects = drop.plan_attachments([source], items, {source: 1})
    assert planned == [drop.PlannedAttachment(source=source, number=1, busy=True)]


def test_unknown_position_is_a_programmer_error(tmp_path):
    with pytest.raises(ValueError):
        drop.plan_attachments([png(tmp_path / "a.png")], [item()], {Path(tmp_path / "a.png"): 5})


def test_source_without_a_chosen_position_is_not_planned(tmp_path):
    source = png(tmp_path / "a.png")
    planned, _rejects = drop.plan_attachments([source], [item()], {})
    assert planned == []  # позицию не выбрали (отмена диалога) — файл не подключается


# --- имя копии и копирование в папку результата -------------------------------------


def test_copy_name_follows_the_position_template():
    assert drop.position_copy_name("duckling", 4) == "duckling_04_ready.png"
    assert drop.position_copy_name("utka_03_ready.png", 5) == "utka_03_ready_05_ready.png"


def test_copy_name_keeps_cyrillic_and_strips_forbidden_characters():
    named = drop.position_copy_name('утка: "золотая"/осень?', 2)
    assert named.endswith("_02_ready.png")
    for forbidden in (":", "/", '"', "?"):
        assert forbidden not in named
    assert "утка" in named and "золотая" in named and "осень" in named


def test_copy_name_never_loses_the_position_suffix_on_a_long_stem():
    named = drop.position_copy_name("у" * 400 + ".png", 7)
    assert named.endswith("_07_ready.png")
    assert len(named) <= 240  # бюджет полного имени — output_naming (UTF-16 единицы)


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


def test_no_new_positions_ever(tmp_path):
    """Позиции = промптам: планировщик не создаёт позиции вне набора (README, решение 3)."""
    source = png(tmp_path / "extra.png")
    with pytest.raises(ValueError):
        drop.plan_attachments([source], [item(), item()], {source: 3})


# --- диалог «Куда поставить …?» (макет «проверка-выбор-позиции») --------------------


def test_position_options_carry_current_pictures_and_exclusions(tmp_path):
    busy = png(tmp_path / "vetok_02_ready.png")
    items = [item(str(busy.resolve())), item("")]
    options = drop.position_options(items, is_excluded=lambda path: path.endswith("02_ready.png"))
    assert options == [
        drop.PositionOption(number=1, path=str(busy.resolve()), excluded=True),
        drop.PositionOption(number=2, path="", excluded=False),
    ]


def test_dialog_shows_all_positions_and_returns_the_choice(app, tmp_path):
    picture = png(tmp_path / "venok_01_ready.png")
    options = [
        drop.PositionOption(number=1, path=str(picture.resolve())),
        drop.PositionOption(number=2, path=""),
        drop.PositionOption(number=3, path="", excluded=True),
        drop.PositionOption(number=4, path=""),
    ]
    dialog = drop.PositionPickerDialog("duckling.png", options)
    assert dialog.windowTitle() == "Куда поставить duckling.png?"
    assert dialog.grid.count() == 4
    assert not dialog.apply_button.isEnabled()  # без выбора кнопка «Поставить» мертва
    dialog.grid.setCurrentRow(1)
    assert dialog.apply_button.isEnabled()
    assert dialog.chosen_number() == 2
    dialog.accept()
    assert dialog.result() == 1  # выбор принят


def test_dialog_cancel_discards_the_choice(app):
    dialog = drop.PositionPickerDialog("duckling.png", [drop.PositionOption(number=1)])
    dialog.grid.setCurrentRow(0)
    dialog.cancel_button.click()
    assert dialog.result() == 0  # отмена —Rejected, номер никому не сообщается


def test_select_position_reports_choice_or_none(app, tmp_path, monkeypatch):
    options = [drop.PositionOption(number=number) for number in (1, 2, 3)]
    dialog = drop.PositionPickerDialog("duckling.png", options)
    dialog.grid.setCurrentRow(2)
    monkeypatch.setattr(dialog, "exec", lambda: 1)  # QDialog.DialogCode.Accepted
    assert dialog.select_position() == 3
    monkeypatch.setattr(dialog, "exec", lambda: 0)  # Rejected
    assert dialog.select_position() is None


def test_ask_builds_the_dialog_and_returns_its_choice(app, monkeypatch):
    class SpyDialog(drop.PositionPickerDialog):
        seen = ()

        def __init__(self, source_name, options, parent=None):
            SpyDialog.seen = (source_name, options, parent)
            super().__init__(source_name, options, parent)

        def select_position(self):
            return 6

    monkeypatch.setattr(drop, "PositionPickerDialog", SpyDialog)
    options = [drop.PositionOption(number=2)]
    assert drop.PositionPickerDialog.ask("duckling.png", options) == 6
    assert SpyDialog.seen[:2] == ("duckling.png", options)


def test_module_limit_constants_match_the_mock():
    assert drop.MAX_DROP_FILES == 8 and drop.MAX_DROP_BYTES == 64 * 1024 * 1024
    assert drop.DROP_MB_LIMIT == 64
