"""Shaded key pockets: the generator's shaded key inside a narrow gap is background.

The gap between two subject parts is filled with a darkened sample of the key
(ambient occlusion in a crevice); the source also draws thin dark stems and
flat key-like detail patches that are opaque subject. These tests pin the
ground truth of the synthetic fixture and the post-upscale delivery alpha.
"""
import numpy as np
import pytest
from PIL import Image

from scripts.chroma_shaded_gap_synth import DETAIL_MINIMUMS, ELEMENTS, build, measure, shade


@pytest.mark.parametrize("blue", [253, 150])
@pytest.mark.parametrize("width", [4, 8])
def test_shaded_gap_core_is_transparent_and_details_survive(blue, width):
    """The delivered chain (engine + matting + clean) is what ships, so it is what
    is pinned here; the shade at a gap mouth within 2 px of the open background is
    deliberately left to the matting stage (see the engine's clearance rule)."""
    key, rgb, subject, gap, details = build(blue, width, enclosed=True)
    rgb = shade(key, rgb, subject, gap)
    core_max, core_violations, values, *_ = measure(rgb, subject, gap, details)
    assert core_max <= 10, f"the shaded gap keeps visible film {core_max:.0f} at the key level {blue}"
    assert core_violations == 0
    for name, minimum in DETAIL_MINIMUMS.items():
        assert values[name] >= minimum, f"{name} lost: alpha {values[name]:.0f} < {minimum}"
    # The 1-px cream wisp is a free-floating speck and is dropped as debris by
    # policy in both the pre-fix and the fixed chain; it is measured, not asserted.
    assert set(values) == set(ELEMENTS)


@pytest.mark.parametrize("blue", [253, 80])
def test_plain_gap_of_the_same_geometry_stays_background(blue):
    # Unshaded gaps (open and enclosed) must keep working: any failure here means the
    # new pocket rule is eating plain background or subject detail.
    for enclosed in (False, True):
        for width in (2, 4, 8):
            key, rgb, subject, gap, details = build(blue, width, enclosed=enclosed)
            core_max, core_violations, values, *_ = measure(rgb, subject, gap, details)
            assert core_max == 0, f"blue={blue} gap={width} enclosed={enclosed}: film {core_max:.0f}"
            for name, minimum in DETAIL_MINIMUMS.items():
                assert values[name] >= minimum, f"blue={blue} {name} lost: {values[name]:.0f}"


def test_delivery_alpha_after_local_upscale_keeps_the_gap_transparent(tmp_path):
    """The post-upscale delivery matte (_restore_upscaled_alpha) must not bring the
    crevice film back: the engine result is upscaled 2x with the real resampler."""
    import main
    from scripts import chroma_shaded_gap_synth as synth

    key, rgb, subject, gap, details = build(253, 8, enclosed=True)
    rgb = shade(key, rgb, subject, gap)
    raw = tmp_path / "raw"
    raw.mkdir()
    source_path = tmp_path / "source.png"
    Image.fromarray(np.clip(np.rint(rgb), 0, 255).astype(np.uint8), "RGB").save(source_path)
    worker = main.WorkerThread("mode2_process", str(tmp_path), {
        "upscale": False,
        "remove_bg": True, "remove_bg_provider": "local_chroma_key", "chroma_key_color": "blue",
        "upscale_after": True, "upscale_after_provider": "local_realesrgan",
        "local_realesrgan_after_scale": 2, "trim_enabled": False, "trim_mode": "alpha",
    })
    def reject(*_args, **_kwargs):
        raise AssertionError("Network/provider call forbidden in this offline test")

    for name in ("_kie_upload_file", "_download_file", "_fal_source_url", "_download_precleanup_result"):
        setattr(worker, name, reject)
    calls = []

    def upscale(input_path, output_path, scale):
        with Image.open(input_path) as opened:
            actual_input = opened.convert("RGBA")
        size = (actual_input.width * scale, actual_input.height * scale)
        Image.new("RGB", size, (101, 121, 141)).save(output_path)
        worker._restore_upscaled_alpha(output_path, actual_input.getchannel("A"))
        calls.append(input_path)

    worker._run_local_realesrgan = upscale
    result_path = worker._run_processing_pipeline(
        str(source_path), None, str(raw), 1, "case", chroma_key_color="blue", result_kind="clipart",
    )
    assert len(calls) == 1
    with Image.open(result_path) as opened:
        final = opened.convert("RGBA")
    alpha = np.asarray(final)[..., 3].astype(float)
    scale = 2
    core = np.zeros((final.height, final.width), bool)
    core[(synth.TOP * scale + 2):(synth.BOTTOM - 40) * scale - 2,
         (140 + 2) * scale:(148 - 2) * scale] = True
    assert alpha[core].max() == 0, "the upscaled delivery alpha keeps film in the shaded gap"
    for name, minimum in DETAIL_MINIMUMS.items():
        big = np.asarray(Image.fromarray(details[name].astype(np.uint8) * 255).resize(
            final.size, Image.Resampling.NEAREST)) > 0
        assert alpha[big].min() >= minimum * 0.5, f"{name} weakened after the upscale: {alpha[big].min():.0f}"
