from __future__ import annotations

import json
import os
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image

import studio_name_translation as snt
from studio_set_export import archive_basename, export_clipart_sets
from studio_text_errors import TextGenerationError


class _Response:
    def __init__(self, payload, status=200):
        self.status_code, self._raw = status, json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, size):
        yield self._raw


def _chat(names):
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"names": names})}}]}


def test_all_names_are_translated_with_one_request():
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        sent = json.loads(kwargs["json"]["messages"][-1]["content"])["names"]
        return _Response(_chat([f"EN {index}" for index, _ in enumerate(sent)]))

    result = snt.translate_names(["Маленький гусёнок", "Персонажи", "Маленький гусёнок", "Кот"],
                                 provider="openrouter", model="google/gemini-3.8-flash", api_key="k", post=post)
    assert len(calls) == 1
    assert result == {"Маленький гусёнок": "EN 0", "Персонажи": "EN 1", "Кот": "EN 2"}


def test_bad_or_mismatched_translation_is_rejected():
    for payload in (_chat(["only one"]), _chat(["", ""]), {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}):
        with pytest.raises(TextGenerationError):
            snt.translate_names(["а", "б"], provider="openrouter", model="google/gemini-3.8-flash",
                                api_key="k", post=lambda *a, **k: _Response(payload))
    with pytest.raises(TextGenerationError):
        snt.translate_names(["а"], provider="openrouter", model="google/gemini-3.8-flash",
                            api_key="k", post=lambda *a, **k: _Response({}, status=500))


def test_archive_name_is_project_set_set_name():
    names = {"Маленький гусёнок": "Little Goose", "Персонажи": "Characters"}
    assert archive_basename("017 Clipart Маленький гусёнок", "Персонажи",
                            {"017 Clipart Маленький гусёнок": "017 Clipart Little Goose Garden Party",
                             "Персонажи": "Characters"}, count=42) == "017-clipart-little-goose-garden-party-set-characters-42"
    assert archive_basename("", "Set 1") == "set-1"
    assert archive_basename("Project", "Set Full Bundle") == "project-set-full-bundle"
    assert names  # keep fixture used


def test_export_uses_translated_names_and_unique_archives(tmp_path):
    sources = []
    for index in range(2):
        path = tmp_path / f"кот{index}.png"
        Image.new("RGBA", (30, 30), (255, 0, 0, 255)).save(path)
        sources.append(str(path))
    dest = tmp_path / "out"
    dest.mkdir()
    names = {"Проект Гуси": "Goose Project", "Персонажи": "Characters", "кот0": "cat0", "кот1": "cat1"}
    sets = [{"title": "Персонажи", "images": sources}, {"title": "Персонажи", "images": sources[:1]}]
    archives = export_clipart_sets(sets, dest, project_name="Проект Гуси", names=names)
    # The archive carries the bare picture count at the end (owner 2026-10-29), and the
    # published folder is exactly «clipart set».
    assert [a.name for a in archives] == ["goose-project-set-characters-1.zip", "goose-project-set-characters-2.zip"]
    assert {a.parent.name for a in archives} == {"clipart set"}
    with ZipFile(dest / "clipart set" / "goose-project-set-characters-2.zip") as zf:
        assert sorted(n for n in zf.namelist() if n.startswith("png/")) == ["png/001_cat0.png", "png/002_cat1.png"]
    # A repeated export never overwrites the published folder.
    again = export_clipart_sets(sets, dest, project_name="Проект Гуси", names=names)
    assert {a.parent.name for a in again} == {"clipart set 2"}
    assert (dest / "clipart set" / "goose-project-set-characters-2.zip").is_file()


def test_images_label_is_english_singular_plural():
    assert snt.images_label(1) == "1 image"
    assert snt.images_label(2) == "2 images"


def test_non_english_answers_and_cancel_are_handled():
    answer = lambda *a, **k: _Response(_chat(["Little Goose", "小鹅"]))
    result = snt.translate_names(["Гусёнок", "Гусь"], provider="openrouter", model="google/gemini-3.8-flash",
                                 api_key="k", post=answer)
    assert result == {"Гусёнок": "Little Goose"}  # non-ASCII answer ignored -> transliteration later
    with pytest.raises(TextGenerationError):
        snt.translate_names(["а"], provider="openrouter", model="google/gemini-3.8-flash", api_key="k",
                            post=lambda *a, **k: _Response(_chat(["a"])), cancelled=lambda: True)


def test_long_project_name_keeps_set_part_readable():
    name = archive_basename("Word " * 40, "Characters")
    assert name.endswith("-set-characters") and len(name) < 100
    assert archive_basename("Word " * 40, "Characters", count=12).endswith("-set-characters-12")
