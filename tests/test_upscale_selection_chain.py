"""The upscale that runs is the one the user selected (owner 2026-10-31: «проверь что апскейлит именно тот апскейл»).

The chain under test: page controls -> saved project state -> run settings -> worker -> the call that
reaches the provider. Backends are recorded, nothing is paid. Expected values come from
``provider_upscale_contract`` (what each model really accepts), never from the code being checked.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import itertools
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QApplication

import main
from provider_upscale_contract import (
    FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
    FAL_BRIA_UPSCALE_MODEL_ID,
    FAL_RECRAFT_CRISP_MODEL_ID,
    FAL_TOPAZ_PRECISION_MODEL_ID,
    FAL_TOPAZ_TRANSPARENT_MODEL_ID,
    KIE_TOPAZ_MODEL_ID,
    normalize_fal_upscale_factor,
)
from v3_clipart_flow import ClipartProcessingPage
from v3_image_worker_settings import build_image_run_settings
from v3_processing_flow import ProcessingPipelinePage
from v3_project_state import ProjectMode, ProjectState

KIE_RECRAFT = "recraft/crisp-upscale"
FAL_MODELS = (
    FAL_BRIA_UPSCALE_MODEL_ID,
    FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
    FAL_TOPAZ_TRANSPARENT_MODEL_ID,
    FAL_TOPAZ_PRECISION_MODEL_ID,
    FAL_RECRAFT_CRISP_MODEL_ID,
)
STAGES = ("before", "after")


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def _set_stage(operations, stage, provider, *, kie_model=KIE_TOPAZ_MODEL_ID, fal_model=FAL_BRIA_UPSCALE_MODEL_ID,
               fal_scale=4, local_scale=4, topaz_factor=None):
    """Select one stage the way the page would and leave the other stage as it is."""
    if stage == "before":
        operations.upscale_before = True
        operations.upscale_before_provider = provider
        operations.kie_upscale_model = kie_model
        operations.fal_upscale_model = fal_model
        operations.fal_upscale_scale = fal_scale
        operations.local_realesrgan_scale = local_scale
    else:
        operations.upscale_after = True
        operations.upscale_after_provider = provider
        operations.kie_upscale_after_model = kie_model
        operations.fal_upscale_after_model = fal_model
        operations.fal_upscale_after_scale = fal_scale
        operations.local_realesrgan_after_scale = local_scale
    if topaz_factor is not None:
        operations.upscale_factor = topaz_factor


def _fresh_operations(mode=ProjectMode.CLIPART):
    state = ProjectState(mode=mode)
    operations = (state.clipart if mode is ProjectMode.CLIPART else state.processing).operations
    operations.upscale_before = False
    operations.upscale_after = False
    operations.remove_background = False
    return state, operations


def _run_chain(tmp_path, state, mode=ProjectMode.CLIPART):
    """Run the real processing pipeline from the saved state; return what reached each provider backend."""
    restored = ProjectState.from_dict(state.to_dict())
    data = restored.clipart if mode is ProjectMode.CLIPART else restored.processing
    settings = build_image_run_settings(restored.runtime, restored.clipart.generation, data.operations,
                                        run_mode="process_only")
    settings.update({"kie_api_key": "", "fal_api_key": "fal-test-secret", "fal_concurrency": 1})
    source = tmp_path / "source.png"
    image = Image.new("RGBA", (32, 32), (255, 255, 255, 255))  # opaque: Recraft Crisp refuses transparency
    ImageDraw.Draw(image).ellipse((6, 6, 26, 26), fill=(200, 90, 50, 255))
    image.save(source)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    worker = main.WorkerThread("mode2_process", str(tmp_path), settings, selected_files=[str(source)])
    calls = []

    def write_result(path):
        result = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        ImageDraw.Draw(result).ellipse((24, 24, 104, 104), fill=(200, 90, 50, 255))
        result.save(path)

    def fal_process(_self, image_url, *, operation, model_id, scale=2, parameters=None):
        calls.append(("fal", model_id, scale))
        return "https://cdn.example/fal-result.png"

    def kie_task(_self, model, image_url, extra_input=None, **_kwargs):
        factor = None if not extra_input else int(extra_input.get("upscale_factor", extra_input.get("scale", 0)))
        calls.append(("kie", model, factor))
        return "https://cdn.example/kie-result.png"

    def local_step(self, input_path, raw, idx, prefix, step_name):
        calls.append(("local", "realesrgan", self._active_local_realesrgan_scale))
        output = Path(raw) / f"{prefix}_{step_name}_{idx:03d}.png"
        write_result(output)
        return str(output)

    def download(_self, _url, output_path):
        write_result(output_path)

    for name, replacement in {
        "_fal_process_image": fal_process,
        "_kie_run_model_task": kie_task,
        "_local_realesrgan_pipeline_step": local_step,
        "_download_file": download,
        "_fal_source_url": lambda _self, *_a, **_k: "https://cdn.example/source.png",
        "_ensure_kie_url": lambda _self, url, _path: url or "https://cdn.example/kie-source.png",
        "_kie_upload_file": lambda _self, _path: "https://cdn.example/kie-source.png",
        "_remember_paid_image_input": lambda _self, *_a, **_k: None,
        "_emit_diagnostic": lambda _self, *_a, **_k: None,
    }.items():
        setattr(worker, name, replacement.__get__(worker))
    worker._run_processing_pipeline(str(source), None, str(raw_dir), 1, "file")
    return calls


def _expected_fal(model, selected_scale):
    return ("fal", model, normalize_fal_upscale_factor(model, selected_scale))


SINGLE_STAGE_CASES = (
    [("kie", dict(kie_model=KIE_TOPAZ_MODEL_ID, topaz_factor=factor), ("kie", KIE_TOPAZ_MODEL_ID, factor))
     for factor in (2, 4)]
    + [("kie", dict(kie_model=KIE_RECRAFT), ("kie", KIE_RECRAFT, None))]
    + [("fal", dict(fal_model=model, fal_scale=scale), _expected_fal(model, scale))
       for model, scale in itertools.product(FAL_MODELS, (2, 4))]
    + [("local_realesrgan", dict(local_scale=scale), ("local", "realesrgan", scale)) for scale in (2, 4)]
)


@pytest.mark.parametrize("mode", [ProjectMode.CLIPART, ProjectMode.PROCESSING])
@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("provider,choice,expected", SINGLE_STAGE_CASES,
                         ids=[f"{p}-{sorted(c.items())}" for p, c, _e in SINGLE_STAGE_CASES])
def test_selected_upscale_is_the_only_one_that_reaches_the_provider(tmp_path, mode, stage, provider, choice,
                                                                    expected):
    state, operations = _fresh_operations(mode)
    _set_stage(operations, stage, provider, **choice)
    assert _run_chain(tmp_path, state, mode) == [expected]


MIXED_PAIRS = (
    # before, after, expected calls in running order. Every pair mixes providers and scales so a value
    # leaking from one stage into the other (a shared scale, a shared model) changes the result.
    (("fal", dict(fal_model=FAL_TOPAZ_PRECISION_MODEL_ID, fal_scale=2)), ("local_realesrgan", dict(local_scale=4)),
     [("fal", FAL_TOPAZ_PRECISION_MODEL_ID, 2), ("local", "realesrgan", 4)]),
    (("local_realesrgan", dict(local_scale=2)), ("fal", dict(fal_model=FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
                                                              fal_scale=4)),
     [("local", "realesrgan", 2), ("fal", FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID, 4)]),
    (("fal", dict(fal_model=FAL_TOPAZ_PRECISION_MODEL_ID, fal_scale=4)),
     ("fal", dict(fal_model=FAL_TOPAZ_PRECISION_MODEL_ID, fal_scale=2)),
     [("fal", FAL_TOPAZ_PRECISION_MODEL_ID, 4), ("fal", FAL_TOPAZ_PRECISION_MODEL_ID, 2)]),
    (("fal", dict(fal_model=FAL_BRIA_UPSCALE_MODEL_ID)), ("fal", dict(fal_model=FAL_TOPAZ_TRANSPARENT_MODEL_ID,
                                                                        fal_scale=2)),
     [("fal", FAL_BRIA_UPSCALE_MODEL_ID, 2), ("fal", FAL_TOPAZ_TRANSPARENT_MODEL_ID, 4)]),
    (("local_realesrgan", dict(local_scale=4)), ("local_realesrgan", dict(local_scale=2)),
     [("local", "realesrgan", 4), ("local", "realesrgan", 2)]),
    (("fal", dict(fal_model=FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID, fal_scale=2)),
     ("kie", dict(kie_model=KIE_TOPAZ_MODEL_ID, topaz_factor=2)),
     [("fal", FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID, 2), ("kie", KIE_TOPAZ_MODEL_ID, 2)]),
    (("kie", dict(kie_model=KIE_RECRAFT)), ("local_realesrgan", dict(local_scale=2)),
     [("kie", KIE_RECRAFT, None), ("local", "realesrgan", 2)]),
)


@pytest.mark.parametrize("mode", [ProjectMode.CLIPART, ProjectMode.PROCESSING])
@pytest.mark.parametrize("before,after,expected", MIXED_PAIRS)
def test_before_and_after_each_run_their_own_selection(tmp_path, mode, before, after, expected):
    state, operations = _fresh_operations(mode)
    _set_stage(operations, "before", before[0], **before[1])
    _set_stage(operations, "after", after[0], **after[1])
    assert _run_chain(tmp_path, state, mode) == expected


@pytest.mark.parametrize("stage", STAGES)
def test_disabled_stage_never_reaches_a_provider_even_with_a_paid_provider_selected(tmp_path, stage):
    state, operations = _fresh_operations()
    _set_stage(operations, stage, "fal", fal_model=FAL_TOPAZ_PRECISION_MODEL_ID, fal_scale=2)
    if stage == "before":
        operations.upscale_before = False
    else:
        operations.upscale_after = False
    assert _run_chain(tmp_path, state) == []


# --- the controls the user sees must be the controls that decide the run -------------------------------

PAGES = [(ClipartProcessingPage, ProjectMode.CLIPART), (ProcessingPipelinePage, ProjectMode.PROCESSING)]


def _page(page_class, mode, stage, provider, fal_model):
    state, operations = _fresh_operations(mode)
    _set_stage(operations, stage, provider, fal_model=fal_model)
    return page_class(state, lambda: None), state


def _scale_is_decided_by_the_user(model):
    return normalize_fal_upscale_factor(model, 2) != normalize_fal_upscale_factor(model, 4)


@pytest.mark.parametrize("page_class,mode", PAGES)
@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("fal_model", FAL_MODELS)
def test_fal_scale_control_is_visible_exactly_when_the_worker_obeys_it(page_class, mode, stage, fal_model):
    """A hidden scale that still decides the run would silently upscale 2x where the page shows nothing."""
    page, _state = _page(page_class, mode, stage, "fal", fal_model)
    control = page.operation_widgets["fal_upscale_scale" if stage == "before" else "fal_upscale_after_scale"]
    assert (not control.isHidden()) is _scale_is_decided_by_the_user(fal_model)
    page.close()


@pytest.mark.parametrize("page_class,mode", PAGES)
@pytest.mark.parametrize("stage", STAGES)
def test_page_choices_arrive_in_the_state_the_run_is_built_from(page_class, mode, stage):
    state, operations = _fresh_operations(mode)
    operations.upscale_before = operations.upscale_after = True
    page = page_class(state, lambda: None)
    widgets = page.operation_widgets
    suffix = "" if stage == "before" else "_after"
    provider = widgets[f"upscale_{stage}_provider"]
    provider.setCurrentIndex(provider.findData("fal"))
    model = widgets[f"fal_upscale{suffix}_model"]
    model.setCurrentIndex(model.findData(FAL_TOPAZ_PRECISION_MODEL_ID))
    scale = widgets[f"fal_upscale{suffix}_scale"]
    scale.setCurrentIndex(scale.findData(2))
    restored = ProjectState.from_dict(state.to_dict())
    settings = build_image_run_settings(restored.runtime, restored.clipart.generation,
                                        (restored.clipart if mode is ProjectMode.CLIPART
                                         else restored.processing).operations, run_mode="process_only")
    key = "" if stage == "before" else "_after"
    assert settings["upscale" + ("" if stage == "before" else "_after")] is True
    assert settings["upscale" + ("_provider" if stage == "before" else "_after_provider")] == "fal"
    assert settings[f"fal_upscale{key}_model"] == FAL_TOPAZ_PRECISION_MODEL_ID
    assert settings[f"fal_upscale{key}_scale"] == 2
    page.close()
