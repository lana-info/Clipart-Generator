import types

import studio_name_translation as snt
from main import WorkerThread


def _worker():
    return types.SimpleNamespace(progress=types.SimpleNamespace(emit=lambda text: None))


def test_russian_subjects_are_translated_once_and_latin_ones_are_skipped(monkeypatch):
    seen = []

    def translator(names):
        seen.append(list(names))
        return {name: "Little Goose" for name in names}

    monkeypatch.setattr(snt, "build_name_translator", lambda: translator)
    entries = [{"prompt": "Объект: Гусёнок. Сцена: зима."}, {"prompt": "Object: fox."},
               {"prompt": "Объект: Гусёнок. Сцена: лето."}]
    assert WorkerThread._english_file_subjects(_worker(), entries) == {"Гусёнок": "Little Goose"}
    assert seen == [["Гусёнок"]]


def test_translation_failure_falls_back_to_transliteration(monkeypatch):
    def broken():
        raise RuntimeError("no key")

    monkeypatch.setattr(snt, "build_name_translator", broken)
    assert WorkerThread._english_file_subjects(_worker(), [{"prompt": "Объект: Гусёнок."}]) == {}
