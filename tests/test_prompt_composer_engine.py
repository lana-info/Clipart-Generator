"""Contract tests for the offline prompt composer."""

from __future__ import annotations

from copy import deepcopy
import json
import socket

import pytest
from studio_asset_api import AssetHandle

from prompt_composer import (
    apply_template, catalogue, draft_fingerprint, generate_variants,
    new_draft, rendered_text, validate_draft,
)
from prompt_composer.model import FIELD_KEYS


def test_catalogue_is_bilingual_stable_and_isolated() -> None:
    first = catalogue()
    assert len(first["templates"]) == 21
    assert len({item["id"] for item in first["templates"]}) == 21
    assert len([item for item in first["templates"] if item["id"].startswith("image_")]) == 7
    assert len([item for item in first["templates"] if item["id"].startswith("reels_")]) == 7
    for item in first["templates"]:
        validated = validate_draft(item["draft"])
        assert validated["fields"]["subject"]["en"]
        assert validated["fields"]["subject"]["ru"]
    first["templates"][0]["draft"]["name"] = "tampered"
    assert catalogue()["templates"][0]["draft"]["name"] != "tampered"


def test_blank_start_and_every_template_produce_seven_offline_pairs() -> None:
    assert len(generate_variants(new_draft())["variants"]) == 7
    for template in catalogue()["templates"]:
        result = generate_variants(apply_template(template["id"]))
        assert result["status"] == "complete", template["id"]
        assert len(result["variants"]) == 7, template["id"]
        assert all(item["en"] and item["ru"] for item in result["variants"])
        if template["draft"]["mode"] == "reels":
            assert all(not item["warnings"] for item in result["variants"]), template["id"]


@pytest.mark.parametrize("mode,id", [("image", "image_paper_podium"), ("reels", "reels_cup_turn")])
def test_seven_repeatable_unique_variants_and_snapshots(mode: str, id: str) -> None:
    draft = apply_template(id)
    original = deepcopy(draft)
    result = generate_variants(draft)
    assert result["status"] == "complete"
    assert len(result["variants"]) == 7
    assert draft == original
    assert generate_variants(draft) == result
    later = deepcopy(draft)
    later["selection_seed"] = result["next_seed"]
    next_result = generate_variants(later)
    assert {item["en"] for item in result["variants"]}.isdisjoint(
        {item["en"] for item in next_result["variants"]}
    )
    assert len({tuple((key, item["draft"]["fields"].get(key, {}).get("en", ""))
                      for key in ("style", "lighting", "time", "camera", "shot", "angle"))
                for item in result["variants"]}) == 7
    for item in result["variants"]:
        saved = json.loads(json.dumps(item["draft"], ensure_ascii=False))
        assert validate_draft(saved) == saved
        assert item["en"] == saved["base_en"] == rendered_text(saved)
        assert item["ru"] == saved["base_ru"] == rendered_text(saved, "ru")
        assert item["source"] == "local"
        assert item["warnings"] == []
        assert "subject" in saved["fields"]
        assert saved["fields"]["subject"] == draft["fields"]["subject"]
        if mode == "image":
            assert "duration" not in item["en"]
            assert "action" not in item["en"]
        else:
            assert item["en"].startswith("One continuous short video scene:")
            assert item["en"].count("location:") == 1
            assert item["en"].count("action:") == 1
    # A catalogue edit or a later working-draft edit cannot alter a saved result.
    restored = deepcopy(result["variants"][3]["draft"])
    draft["fields"]["subject"] = {"ru": "другое", "en": "different"}
    assert restored["base_en"] == result["variants"][3]["en"]
    assert restored["fields"]["subject"]["en"] != draft["fields"]["subject"]["en"]


def test_pins_identity_exclusions_and_insufficient_capacity() -> None:
    draft = apply_template("image_paper_podium")
    draft["fields"]["exclusions"] = {"ru": "неон", "en": "neon"}
    draft["fields"]["shot"] = {"ru": "кадр по пояс", "en": "waist-up framing"}
    draft["locks"] = ["subject", "lighting", "style", "time", "camera", "angle"]
    result = generate_variants(draft)
    assert len(result["variants"]) == 7  # current shot plus six catalogue choices
    assert all(item["draft"]["fields"]["subject"] == draft["fields"]["subject"] for item in result["variants"])
    assert all(item["draft"]["fields"]["lighting"] == draft["fields"]["lighting"] for item in result["variants"])
    assert all(item["draft"]["fields"]["exclusions"] == draft["fields"]["exclusions"] for item in result["variants"])
    draft["locks"] = list(FIELD_KEYS)
    one = generate_variants(draft)
    assert one["status"] == "insufficient"
    assert len(one["variants"]) == 1
    assert "Освободите" in one["reason"]
    draft["selection_seed"] = one["next_seed"]
    none = generate_variants(draft)
    assert none["status"] == "insufficient" and none["variants"] == []


def test_exclusions_detect_fixed_conflicts_and_filter_unlocked_choices() -> None:
    draft = apply_template("image_paper_podium")
    draft["fields"]["exclusions"] = {"ru": "без оконного света", "en": "no window light"}
    draft["locks"] = ["lighting"]
    pinned = generate_variants(draft)
    assert pinned["status"] == "insufficient" and pinned["variants"] == []
    assert "lighting" in pinned["reason"]
    draft["locks"] = []
    filtered = generate_variants(draft)
    assert filtered["status"] == "complete"
    assert all("window" not in item["draft"]["fields"]["lighting"]["en"] for item in filtered["variants"])
    draft["fields"]["exclusions"] = {"ru": "без матового флакона", "en": "no matte serum bottle"}
    identity = generate_variants(draft)
    assert identity["status"] == "insufficient" and "subject" in identity["reason"]


def test_exclusions_that_empty_a_choice_pool_are_explained() -> None:
    draft = apply_template("image_paper_podium")
    draft["fields"]["exclusions"] = {"ru": "без плана", "en": "no framing"}
    result = generate_variants(draft)
    assert result["status"] == "insufficient" and result["variants"] == []
    assert "shot" in result["reason"]


def test_image_captures_action_without_video_duration() -> None:
    draft = apply_template("tw_man_at_work")
    assert draft["fields"]["action"] == {
        "ru": "обрабатывает деталь руками", "en": "works on a small piece by hand",
    }
    result = generate_variants(draft)
    assert result["status"] == "complete"
    assert all("works on a small piece by hand" in item["en"] for item in result["variants"])
    assert all("обрабатывает деталь руками" in item["ru"] for item in result["variants"])
    assert all("duration" not in item["en"] for item in result["variants"])


def test_reels_reject_explicit_cuts_and_warns_on_ambiguous_sequence() -> None:
    draft = apply_template("reels_cup_turn")
    draft["fields"]["action"] = {"ru": "поворот чашки, затем монтаж", "en": "turn the cup, then cut to a new scene"}
    result = generate_variants(draft)
    assert result["status"] == "insufficient" and result["variants"] == []
    assert "одну непрерывную сцену" in result["reason"]
    draft["fields"]["action"] = {"ru": "поворачивает чашку, затем наклоняет её", "en": "turns the cup, then tilts it"}
    caution = generate_variants(draft)
    assert len(caution["variants"]) == 7
    assert all(item["warnings"] for item in caution["variants"])


def test_exactly_six_and_cursor_exhaustion() -> None:
    draft = apply_template("image_paper_podium")
    draft["fields"]["shot"] = {"ru": "крупный план", "en": "close-up framing"}
    draft["locks"] = [key for key in FIELD_KEYS if key != "shot"]
    result = generate_variants(draft)
    assert result["status"] == "insufficient"
    assert len(result["variants"]) == 6
    assert len({item["en"] for item in result["variants"]}) == 6
    draft["selection_seed"] = result["next_seed"]
    assert generate_variants(draft)["variants"] == []


def test_free_form_pair_is_saveable_but_missing_english_blocks_local_generation() -> None:
    draft = apply_template("image_pet_window")
    draft["fields"]["material"] = {"ru": "шерсть особой фактуры", "en": ""}
    assert validate_draft(draft) == draft
    with pytest.raises(ValueError, match="material.*английского"):
        generate_variants(draft)
    draft["fields"]["material"]["en"] = "wool with a distinctive texture"
    assert "distinctive texture" in generate_variants(draft)["variants"][0]["en"]


def test_manual_text_and_unknown_catalog_values_survive_validation() -> None:
    draft = new_draft()
    draft["fields"]["subject"] = {"ru": "старый товар", "en": "legacy product"}
    draft["fields"]["style"] = {"ru": "старый стиль", "en": "legacy style"}
    draft["catalog_version"] = 42
    draft["base_en"] = "built text"
    draft["manual_en"] = "my edited text"
    draft["translation_stale"] = True
    saved = validate_draft(draft)
    assert rendered_text(saved) == "my edited text"
    assert rendered_text(saved, "ru") == ""
    assert saved["fields"]["style"]["en"] == "legacy style"
    assert draft_fingerprint(saved) == draft_fingerprint(json.loads(json.dumps(saved)))
    with pytest.raises(ValueError, match="ручной текст"):
        generate_variants(saved)
    saved["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        validate_draft(saved)


def test_reference_must_be_a_stable_path_free_asset_handle() -> None:
    draft = new_draft()
    digest = "a" * 64
    handle = AssetHandle(digest, digest, 64, "reference.png", "image/png").to_dict()
    draft["references"] = [handle]
    assert validate_draft(draft)["references"] == [handle]
    draft["references"] = [{**handle, "path": "/tmp/reference.png"}]
    with pytest.raises(ValueError, match="AssetHandle"):
        validate_draft(draft)
    draft["references"] = [{**handle, "sha256": "b" * 64}]
    with pytest.raises(ValueError, match="AssetHandle"):
        validate_draft(draft)


def test_generation_never_uses_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network must never be accessed")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    assert len(generate_variants(apply_template("reels_cat_blink"))["variants"]) == 7


def test_ai_preflight_rejects_positive_multi_scene_but_allows_negation():
    from prompt_composer.engine import preflight_ai
    draft = apply_template('reels_cup_turn')
    draft['fields']['action'] = {'en': 'montage of two scenes', 'ru': 'монтаж двух сцен'}
    with pytest.raises(ValueError, match='Reels'):
        preflight_ai(draft)
    draft['fields']['action'] = {'en': 'turn the cup slowly, no montage', 'ru': 'повернуть чашку, без монтажа'}
    preflight_ai(draft)
    for action in ('turn the cup slowly in one shot, without any cuts to another scene',
                   'turn the cup slowly with no sudden montage'):
        draft['fields']['action'] = {'en': action, 'ru': 'медленно повернуть чашку одним кадром, без резких склеек'}
        preflight_ai(draft)
        assert len(generate_variants(draft)['variants']) == 7
    draft['fields']['camera'] = {'en': 'montage', 'ru': 'монтаж'}
    with pytest.raises(ValueError, match='Reels'):
        preflight_ai(draft)
