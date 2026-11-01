"""Prompt wording of the A/B-tested variant D (report 2026-11-01): what the text asks of the generator."""
import pytest

from chroma_key import chroma_key_prompt_block
from studio_commercial_prompt_guidance import prompt_guidance_for_role


def _text(role, language):
    guidance = prompt_guidance_for_role(role, language=language)
    return " ".join((guidance["consistency"], *guidance["restrictions"]))


@pytest.mark.parametrize("key,banned,allowed", (
    ("blue", "blue, navy, cyan or teal", ("green", "red")),
    ("green", "green, lime, mint or olive", ("blue", "red")),
    ("red", "red, crimson, scarlet or hot pink", ("blue", "green")),
))
def test_colour_ban_follows_the_chosen_key(key, banned, allowed):
    block = chroma_key_prompt_block(key)
    assert f"Use no saturated {banned} in the subject" in block
    assert "anywhere" not in block
    assert f"any {key} part the brief asks for is painted pale and muted" in block
    assert f"clearly different from the {key} background" in block
    for other in allowed:
        assert f"Use no saturated {other}" not in block


def test_colour_ban_comes_after_the_background_rules_and_before_the_opaque_rule():
    block = chroma_key_prompt_block("blue")
    assert block.index("No white or cream backing") < block.index("Use no saturated blue") < block.index("fully opaque and solid")


def test_custom_key_has_no_colour_ban():
    assert "Use no" not in chroma_key_prompt_block("#123456")


def test_backing_rule_is_not_limited_to_flowers():
    block = chroma_key_prompt_block("blue")
    assert "behind or between parts of the subject" in block
    assert "flowers, leaves and twigs" not in block


def test_edge_standard_asks_for_hard_edges_not_hairs():
    block = chroma_key_prompt_block("blue", edge_quality=True)
    assert "Crisp hard edges, everything in sharp focus" in block
    assert "hairs" not in block and "wisps" not in block and "fluffy" not in block
    assert "one continuous closed silhouette" in block


@pytest.mark.parametrize("language,marker", (("ru", "5-8 крупных"), ("en", "5-8 large")))
@pytest.mark.parametrize("role", ("wreath", "border"))
def test_flower_rules_stay_for_wreaths_and_borders(language, marker, role):
    assert marker in _text(role, language)


@pytest.mark.parametrize("language,marker", (("ru", "5-8 крупных"), ("en", "5-8 large")))
@pytest.mark.parametrize("role", ("hero", "composition", "decor"))
def test_flower_rules_are_absent_for_other_subjects(language, marker, role):
    assert marker not in _text(role, language)
    assert "near-white" not in _text(role, language) and "почти белые" not in _text(role, language)


@pytest.mark.parametrize("language", ("ru", "en"))
def test_backing_restriction_names_no_flowers_or_twigs(language):
    text = _text("hero", language)
    for word in ("twigs", "веточ", "цветами"):
        assert word not in text
