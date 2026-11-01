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


@pytest.mark.parametrize("automatic", (False, True))
@pytest.mark.parametrize("subject", ("Yellow flowers with green leaves", "Жёлтые цветы с зелёными листьями"))
@pytest.mark.parametrize("enabled", (False, True))
def test_final_prompt_contains_cutout_rules_once(automatic, subject, enabled):
    from clipart_prompt_generator import generate_clipart_prompt_series
    from studio_clipart_objects import compile_objects, fill_recipe
    from studio_clipart_recipe import ClipartRecipe
    from v3_project_state import PromptGeneratorData

    data = PromptGeneratorData(subjects=[subject], chroma_key_enabled=enabled)
    if automatic:
        recipe = ClipartRecipe(theme=subject)
        recipe.select(1)
        recipe.objects = fill_recipe([], recipe.counts)
        recipe.objects[0]['name'] = subject
        entry = compile_objects(recipe, data)[0]
    else:
        entry = generate_clipart_prompt_series(data)[0]

    clauses = (
        "Flat clean background: no gradients, shadows or textures",
        "background color must be absent from the subject",
        "never yellow or green beside yellow or green details",
        "Wide empty margins; separate elements must not touch each other or frame edges",
        "Crisp contours: no blur, glow, halo or soft shadows",
        "Omit nonessential threads and hairs; essential ones must be thick, bright and continuous",
        "No tiny detached fragments, confetti, splinters or splashes",
        "Fully opaque subject; no background color inside its solid parts",
        "Prefer fewer clean elements over dense ornament",
    )
    for clause in clauses:
        assert entry.prompt.count(clause) == int(enabled)
    assert subject in entry.prompt
    assert entry.chroma_key_color == ("blue" if enabled else "")


def _flatten(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _flatten(item)]
    return [text for item in value for text in _flatten(item)]
