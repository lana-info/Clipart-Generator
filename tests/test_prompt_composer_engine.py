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
    templates = first["templates"]
    legacy = [item for item in templates if item.get("legacy")]
    scenes = [item for item in templates if item.get("reusable") and not item.get("direction")]
    nested = [item for item in templates if item.get("direction")]
    assert len(templates) == len({item["id"] for item in templates}) == 319
    assert len(nested) == 250
    assert len(legacy) == 21
    assert len(scenes) == 48
    assert {item["id"] for item in legacy} == {
        "tw_morning_look", "tw_man_at_work", "tw_mature_audience",
        "tw_living_portrait", "tw_product_in_life", "tw_unboxing",
        "tw_character_micro_story", "image_paper_podium", "image_botanical_still_life",
        "image_pet_window", "image_greeting_card", "image_handmade_texture",
        "image_workshop_portrait", "image_backlit_dessert", "reels_cup_turn",
        "reels_fabric_window", "reels_petal_fall", "reels_cocoa_stir",
        "reels_brush_paper", "reels_cat_blink", "reels_bottle_drop",
    }
    assert first["categories"] == [
        {"id": "people", "label": "Люди"},
        {"id": "products", "label": "Товары"},
        {"id": "food", "label": "Еда и напитки"},
        {"id": "spaces", "label": "Интерьеры и архитектура"},
        {"id": "animals", "label": "Животные"},
        {"id": "nature", "label": "Природа и путешествия"},
    ]
    for mode in ("image", "reels"):
        assert sum(item["draft"]["mode"] == mode for item in scenes) == 24
        for category in first["categories"]:
            expected = 6 if category["id"] in ("people", "products") else 3
            assert sum(item["category"] == category["id"] and item["draft"]["mode"] == mode
                       for item in scenes) == expected
    for item in templates:
        assert validate_draft(item["draft"]) == item["draft"]
        assert apply_template(item["id"]) == item["draft"]
        for pair in item["draft"]["fields"].values():
            assert pair["ru"].strip() and pair["en"].strip(), item["id"]
    first["templates"][0]["draft"]["name"] = "tampered"
    first["categories"][0]["label"] = "tampered"
    first["options"]["style"][0]["en"] = "tampered"
    assert catalogue()["templates"][0]["draft"]["name"] != "tampered"
    assert catalogue()["categories"][0]["label"] == "Люди"
    assert catalogue()["options"]["style"][0]["en"] != "tampered"
    copied = apply_template(scenes[0]["id"])
    copied["fields"]["subject"]["en"] = "tampered"
    assert apply_template(scenes[0]["id"])["fields"]["subject"]["en"] == "person"


def test_reusable_scene_recipes_have_neutral_subjects_and_detailed_bilingual_fields() -> None:
    subjects = {
        "people": ("человек", "person"), "products": ("товар", "product"),
        "food": ("блюдо или напиток", "dish or drink"), "spaces": ("помещение", "space"),
        "animals": ("животное", "animal"), "nature": ("пейзаж", "landscape"),
    }
    for item in catalogue()["templates"]:
        if not item.get("reusable") or item.get("direction"):
            continue
        draft = item["draft"]
        fields = draft["fields"]
        subject = ("здание", "building") if "_exterior_" in item["id"] else subjects[item["category"]]
        assert fields["subject"] == {"ru": subject[0], "en": subject[1]}
        assert draft["locks"] == []
        assert not {"wardrobe", "appearance", "color", "material"} & fields.keys()
        assert item["id"].startswith(f"scene_{item['category']}_")
        assert item["id"].endswith("_" + draft["mode"])
        assert not item.get("legacy")
        for key in ("style", "lighting", "location", "shot", "angle", "camera", "exclusions"):
            for language in ("ru", "en"):
                assert len(fields[key][language].split()) >= 3, (item["id"], key, language)
        if draft["mode"] == "reels":
            assert fields["duration"] == {"ru": "8 секунд", "en": "8 seconds"}
            assert all(len(fields["action"][language].split()) >= 5 for language in ("ru", "en"))
        else:
            assert "duration" not in fields


def test_scene_cards_match_approved_titles_and_descriptions() -> None:
    from pathlib import Path
    outline_path = Path(__file__).resolve().parents[1] / "docs/ui/3.1/composer-directions-20261007/scenario-outline.json"
    outline = json.loads(outline_path.read_text(encoding="utf-8"))
    scenes = [item for item in catalogue()["templates"] if item.get("reusable") and not item.get("direction")]
    for category, approved in outline["scenes"].items():
        for mode, description_index in (("image", 1), ("reels", 2)):
            actual = [(item["label"], item["description"]) for item in scenes
                      if item["category"] == category and item["draft"]["mode"] == mode]
            assert actual == [(row[0], row[description_index]) for row in approved]


def test_scene_variations_are_isolated_bilingual_relative_options() -> None:
    scenes = [item for item in catalogue()["templates"] if item.get("reusable")]
    for mode in ("image", "reels"):
        signatures = [item["draft"]["fields"]["style"]["en"] for item in scenes
                      if item["draft"]["mode"] == mode]
        assert len(signatures) == len(set(signatures)) == 149
    sizes = {"style": 1, "time": 1, "camera": 1, "shot": 4, "angle": 3, "lighting": 3}
    for item in scenes:
        pools = item["variation_options"]
        assert set(pools) == sizes.keys()
        assert item["draft"]["locks"] == []
        for key, size in sizes.items():
            assert len(pools[key]) == size
            assert pools[key][0] == {"ru": "", "en": ""}
            assert len({(pair["ru"], pair["en"]) for pair in pools[key]}) == size
            for pair in pools[key][1:]:
                assert set(pair) == {"ru", "en"}
                assert all(pair[language].startswith(", ") and len(pair[language].split()) >= 3
                           for language in ("ru", "en"))
        pools["style"][0]["en"] = "tampered"
        assert pools["camera"][0]["en"] == ""
        assert catalogue()["templates"][-1]["variation_options"]["style"][0]["en"] == ""
        assert apply_template(item["id"])["fields"]["style"] == item["draft"]["fields"]["style"]


def test_image_scenes_capture_actions_without_video_camera_movement() -> None:
    for item in catalogue()["templates"]:
        if not item.get("reusable") or item["draft"]["mode"] != "image":
            continue
        fields = item["draft"]["fields"]
        video_fields = apply_template(item["id"].removesuffix("image") + "reels")["fields"]
        assert fields["action"] != video_fields["action"]
        assert fields["action"]["ru"] and fields["action"]["en"]
        assert "duration" not in fields
        assert all(word not in fields["camera"]["en"] for word in ("moves", "tracks", "pans", "approaches"))
        for variant in generate_variants(item["draft"])["variants"]:
            assert fields["action"]["ru"] in variant["ru"]
            assert fields["action"]["en"] in variant["en"]
    expectations = {
        "scene_products_on_person_image": "a person",
        "scene_products_ugc_hands_image": "hands",
        "scene_products_ugc_unboxing_image": "packaging open",
        "scene_food_preparation_image": "stirring movement",
    }
    for identifier, expected in expectations.items():
        assert expected in apply_template(identifier)["fields"]["action"]["en"]


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
