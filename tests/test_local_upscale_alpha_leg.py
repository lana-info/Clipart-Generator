"""Alpha-aware alpha leg of the local Real-ESRGAN upscale (prototype AC-C1, path C).

The old restore stretched the cut-out matte bilinearly to the x4 grid: on the owner's
files (rough2/rough1, artifacts ac-c1-owner-20261030) that multiplied the faint key
remnants x178 (the grey film). The leg now resizes the alpha with Lanczos, drops the
sub-tau film, closes interior holes under 32 px and never touches the transparent
periphery or the intentional soft alpha above the tau (fur, watercolour washes).

Characterization of the old bilinear leg on the fixture below (x4): remnants 1..63
865 px, the alpha-20 haze speck stayed alive on 64 px, the 2x2 interior hole stayed
open, the gradient median was 108. With the leg: haze 0, hole closed, gradient
median 107. The gates are load-bearing: test_negative_without_the_gates_... reverts
them and watches the film and the open hole come back.
"""
import time

import numpy as np
import pytest
from PIL import Image

import alpha_upscale
import main
from alpha_upscale import REMNANT_TAU, REMNANT_TAU_STRICT, count_interior_holes, upscale_alpha
from tests.test_local_processing_acceptance import worker_settings


def build_fixture():
    """Solid body + intentional soft gradient + micro-haze specks + interior holes."""
    w, h = 32, 24
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = 200, 150, 80
    a = np.zeros((h, w), dtype=np.uint8)
    a[4:16, 8:28] = 255                                    # solid interior
    for x, value in zip(range(4, 8), (64, 96, 128, 192)):  # intentional soft gradient band
        a[4:16, x] = value
    a[20:22, 2:4] = 20                                     # micro-haze specks: the "film"
    a[20, 13] = 38
    a[12, 29] = 30                                         # haze at the solid rim
    a[8, 16:18] = 0                                        # small interior hole (L of 3 px)
    a[8:10, 16] = 0                                        # its x4 core is 24 px < 32 -> closed
    a[8:14, 20:26] = 0                                     # large interior hole (6x6) that stays open
    rgba[..., 3] = a
    return Image.fromarray(rgba)


def fur_alpha():
    """A soft "fur" matte: its tips live entirely in the 48..80 alpha band."""
    a = np.zeros((16, 24), dtype=np.uint8)
    a[2:8, 4:20] = 255                                     # body
    for row, value in zip(range(8, 12), (80, 64, 56, 48)):  # wide soft tips
        a[row, 4:20] = value
    return Image.fromarray(a)


def make_worker(tmp_path, scale, monkeypatch):
    settings = worker_settings(local_realesrgan_dir=str(tmp_path), local_realesrgan_scale=scale)
    worker = main.WorkerThread("mode2_process", str(tmp_path), settings)
    exe = tmp_path / "realesrgan-ncnn-vulkan.exe"
    exe.write_bytes(b"")
    model = main.get_local_realesrgan_model_name(worker.local_realesrgan_profile, scale)
    (tmp_path / "models").mkdir(exist_ok=True)
    for suffix in (".bin", ".param"):
        (tmp_path / "models" / (model + suffix)).write_bytes(b"")
    monkeypatch.setattr(main, "validate_local_realesrgan_exe", lambda _dir: (str(exe), None))
    monkeypatch.setattr(main, "validate_local_realesrgan_output_size", lambda *_args: None)
    inputs = []

    def execute(_exe, input_path, output_path, _model, scale_):
        with Image.open(input_path) as opened:
            rgb = opened.convert("RGB")
        inputs.append(rgb.copy())
        rgb.resize((rgb.width * scale_, rgb.height * scale_), Image.Resampling.NEAREST).save(output_path)

    worker._execute_realesrgan = execute
    worker.inputs = inputs
    return worker


def run_local_upscale(tmp_path, monkeypatch, scale=4, fixture=None):
    worker = make_worker(tmp_path, scale, monkeypatch)
    source = tmp_path / "source.png"
    (fixture or build_fixture()).save(source)
    output = tmp_path / "output.png"
    worker._run_local_realesrgan(str(source), str(output), scale=scale)
    with Image.open(output) as opened:
        result = opened.convert("RGBA")
    return np.asarray(result.getchannel("A")), np.asarray(result.convert("RGB")), worker


def test_local_upscale_suppresses_the_film_and_keeps_the_intentional_soft_alpha(tmp_path, monkeypatch):
    for scale in (4, 2):
        with monkeypatch.context() as patch:
            alpha, _rgb, _worker = run_local_upscale(tmp_path, patch, scale)
        n = scale
        haze20 = alpha[20 * n:22 * n, 2 * n:4 * n]
        haze38 = alpha[20 * n:21 * n, 13 * n:14 * n]
        haze_rim = alpha[12 * n:13 * n, 29 * n:30 * n]
        gradient = alpha[4 * n:16 * n, 4 * n:8 * n]
        # The film: the old bilinear restore kept the alpha-20 speck alive on 64 px at x4.
        assert haze20.max() == 0 and haze38.max() == 0 and haze_rim.max() == 0, scale
        # The intentional gradient survives: the drawn 128-column keeps its value,
        # the sub-tau pixels left at the x4 grid are a rounding shoulder, not a veil.
        assert int(np.median(gradient)) in range(96, 145), np.unique(gradient)
        assert (gradient > 200).mean() < 0.15, scale      # the drawn wash is not painted solid
        if scale == 4:
            # 862 remnants on the base bilinear path; 82 with the leg - only the
            # 40..63 shoulder of the drawn gradient and of the contour, never the specks.
            assert int(((alpha > 0) & (alpha < 64)).sum()) <= 128
        solid = alpha[9 * n:11 * n, 9 * n:15 * n]
        assert (solid == 255).mean() == 1.0               # the body stays exactly solid


def test_characterization_the_old_bilinear_restore_multiplies_the_film(tmp_path, monkeypatch):
    """The restore this leg replaces kept the film alive — the defect C fixes (owner 2026-10-30).

    The old helper still serves the chroma delivery paths; it is driven here the exact
    way ``_run_local_realesrgan`` called it before the alpha-aware leg.
    """
    worker = make_worker(tmp_path, 4, monkeypatch)
    output = tmp_path / "old_path.png"
    Image.new("RGB", (32 * 4, 24 * 4), (200, 150, 80)).save(output)
    worker._restore_upscaled_alpha(str(output), build_fixture().getchannel("A"))
    with Image.open(output) as opened:
        restored = np.asarray(opened.convert("RGBA").getchannel("A"))
    n = 4
    # The bilinear stretch turns every contour into a 1..63 ramp: the grey film.
    assert int(((restored > 0) & (restored < 64)).sum()) >= 800
    assert (restored[20 * n:22 * n, 2 * n:4 * n] > 0).sum() == 64   # the alpha-20 speck lives
    assert int(np.median(restored[4 * n:16 * n, 4 * n:8 * n])) == 108
    assert (restored[9 * n:11 * n, 9 * n:15 * n] == 255).mean() == 1.0


def test_alpha_leg_tolerates_an_off_grid_esrgan_frame(tmp_path, monkeypatch):
    """A Real-ESRGAN frame padded by tile rounding keeps its alpha leg (putalpha guard)."""

    def execute(_exe, input_path, output_path, _model, scale_):
        with Image.open(input_path) as opened:
            rgb = opened.convert("RGB")
        rgb.resize((rgb.width * scale_ + 8, rgb.height * scale_), Image.Resampling.NEAREST).save(output_path)

    worker = make_worker(tmp_path, 4, monkeypatch)
    worker._execute_realesrgan = execute
    source = tmp_path / "source.png"
    build_fixture().save(source)
    output = tmp_path / "output.png"
    worker._run_local_realesrgan(str(source), str(output), scale=4)
    with Image.open(output) as opened:
        result = opened.convert("RGBA")
    assert result.size == (32 * 4 + 8, 24 * 4)
    alpha = np.asarray(result.getchannel("A"))
    assert alpha[20 * 4:22 * 4, 2 * 4:4 * 4].max() == 0             # the film is still dropped
    assert (alpha[9 * 4:11 * 4, 9 * 4:15 * 4] == 255).mean() == 1.0  # the body stays solid
    assert result.getpixel((0, 0))[:3] == (200, 150, 80)             # the RGB leg is untouched


def test_small_interior_holes_are_closed_and_the_transparent_periphery_is_untouched(tmp_path, monkeypatch):
    alpha, _rgb, _worker = run_local_upscale(tmp_path, monkeypatch, 4)
    assert alpha[34, 66] == 255                       # the 3-px hole (x4 core 24 px) is filled
    assert count_interior_holes(alpha) == 0           # no sub-32 px interior hole is left
    assert alpha[11 * 4, 23 * 4] == 0                 # the 6x6 hole stays open
    assert (alpha[22 * 4:, :] == 0).all()             # the peripheral band is untouched


def test_negative_without_the_gates_the_film_and_the_hole_come_back(tmp_path, monkeypatch):
    """Reverting the tau gate and the hole gate must fail the two green tests above."""
    monkeypatch.setattr(alpha_upscale, "REMNANT_TAU", 1)
    monkeypatch.setattr(alpha_upscale, "MIN_INTERIOR_HOLE_PIXELS", 0)
    alpha, _rgb, _worker = run_local_upscale(tmp_path, monkeypatch, 4)
    n = 4
    assert 0 < alpha[20 * n:22 * n, 2 * n:4 * n].max() < 64       # the film speck is alive again
    assert alpha[32:39, 64:71].min() == 0                         # the 24-px hole core is open again
    assert alpha[34, 66] != 255                                   # the ghost hole is not filled


def test_rgb_leg_stays_byte_identical(tmp_path, monkeypatch):
    _alpha, rgb, worker = run_local_upscale(tmp_path, monkeypatch, 4)
    expected_rgb = worker.inputs[0].resize((32 * 4, 24 * 4), Image.Resampling.NEAREST)
    assert np.array_equal(rgb, np.asarray(expected_rgb))          # the alpha leg never rewrites colour


def test_fur_soft_tips_survive_the_default_tau_and_the_strict_tau_dries_them():
    scale = 4
    n = scale
    default = np.asarray(upscale_alpha(fur_alpha(), scale))
    strict = np.asarray(upscale_alpha(fur_alpha(), scale, tau=REMNANT_TAU_STRICT))

    band_default = default[8 * n:12 * n, 4 * n:20 * n]    # the 80..64..56..48 rows at x4
    band_strict = strict[8 * n:12 * n, 4 * n:20 * n]
    # Default tau 40 (~HAZE_FLOOR 0.16): even the faintest 48-row keeps its alpha.
    assert band_default[3 * n:, :].max() >= 40
    assert (band_default > 0).mean() > 0.9
    # Strict tau 64 (~0.25) zeroes the 48/56 rows: exactly how a hard default would
    # dry fur - the reason the product default stays REMNANT_TAU (40).
    assert band_strict[3 * n:, :].max() == 0
    assert (band_strict > 0).sum() < (band_default > 0).sum()


def test_matted_cutout_still_draws_its_soft_matte_bounded_by_the_new_leg(tmp_path, monkeypatch):
    worker = make_worker(tmp_path, 2, monkeypatch)
    worker._item_context.edge_matted = True
    source = tmp_path / "matted.png"
    matted = Image.new("RGBA", (20, 12), (0, 0, 255, 0))
    matted.paste((200, 150, 80, 255), (6, 2, 20, 10))
    matted.paste((200, 150, 80, 100), (4, 2, 6, 10))
    matted.save(source)
    output = tmp_path / "out.png"

    worker._run_local_realesrgan(str(source), str(output), 2)

    assert len(worker.inputs) == 2                        # colour and network matte legs
    with Image.open(output) as opened:
        rgba = opened.convert("RGBA")
    assert rgba.getchannel("A").getpixel((9, 9)) in (99, 100, 101)   # the soft matte value passes
    assert rgba.getchannel("A").getpixel((1, 1)) == 0     # network noise never rings outside the leg


@pytest.mark.perf
def test_alpha_leg_is_not_minutes_on_a_four_megapixel_frame():
    # Wall clock of the alpha leg at 4 MP x4. The bilinear leg cost 0.17 s here and the
    # ESRGAN colour leg of the same step takes minutes; measured 2026-10-30: ~1.5 s
    # (Lanczos + gates + hole closing) - under 2 % of the step it belongs to.
    rng = np.random.default_rng(7)
    img = np.zeros((2000, 2000), dtype=np.uint8)
    yy, xx = np.mgrid[0:2000, 0:2000]
    img[((xx - 1000) ** 2 + (yy - 1000) ** 2) < 690_000] = 255
    rim = (np.abs((xx - 1000) + (yy - 1000)) % 64 < 24) & (img == 0)
    img[rim] = rng.integers(20, 200, size=int(rim.sum()))

    started = time.perf_counter()
    leg = upscale_alpha(Image.fromarray(img), 4)
    elapsed = time.perf_counter() - started

    assert leg.size == (8000, 8000)
    assert elapsed < 30.0, elapsed


# Remnant counter used by the prototype metrics (0<alpha<64) as a module-level sanity gate.
def test_remnant_constants_match_the_prototype_and_haze_floor():
    assert REMNANT_TAU == 40 and 0.15 < REMNANT_TAU / 255 < 0.17      # ≈ alpha_cleanup.HAZE_FLOOR 0.16
    assert REMNANT_TAU_STRICT == 64 and abs(REMNANT_TAU_STRICT / 255 - 0.25) < 0.01
    assert alpha_upscale.MIN_INTERIOR_HOLE_PIXELS == 32               # prototype AC-C1: N=32
    assert alpha_upscale.OPAQUE_SNAP == 200                           # prototype: alpha>200 -> 255
