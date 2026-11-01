import pytest

from chroma_key import chroma_key_prompt_block
from studio_commercial_prompt_guidance import commercial_planning_hints, prompt_guidance_for_role


@pytest.mark.parametrize("language,marker", (("ru", "без белой или кремовой подложки"), ("en", "no white or cream backing")))
@pytest.mark.parametrize("role", ("wreath", "border", "hero"))
def test_every_role_forbids_white_backing(language, role, marker):
    assert marker in " ".join(_flatten(prompt_guidance_for_role(role, language=language)))


@pytest.mark.parametrize("language,marker", (("ru", "5-8 крупных"), ("en", "5-8 large")))
def test_consistency_caps_flowers_for_wreaths_and_borders(language, marker):
    assert marker in " ".join(_flatten(prompt_guidance_for_role("wreath", language=language)))


def test_planner_prefers_quality_over_lushness():
    policy = commercial_planning_hints()["detail_policy"]
    assert "outranks lushness" in policy and "tiny blossoms" in policy


def test_chroma_block_forbids_white_backing():
    assert "No white or cream backing" in chroma_key_prompt_block("blue")


def test_chroma_block_keeps_gaps_as_bright_as_the_background():
    # The generator painted dark shade pockets in gaps between parts, which the cutter kept as subject.
    for key in ("blue", "green"):
        block = chroma_key_prompt_block(key)
        assert "never a darker or black shade" in block
        assert "ambient-occlusion" in block


def _flatten(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _flatten(item)]
    return [text for item in value for text in _flatten(item)]
