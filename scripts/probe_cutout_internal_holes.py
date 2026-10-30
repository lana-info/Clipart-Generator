"""Holes inside the subject: pixels the engine kept opaque and key-dominant, dropped by the final chain."""
import sys
import numpy as np
from PIL import Image

REPO = sys.argv[1]
sys.path.insert(0, REPO)
import chroma_key as ck
from chroma_matting import matte_edges
from alpha_cleanup import DEBRIS_MIN_GAP, clean_alpha
from edge_tint import suppress_key_tint

print(REPO)
total_old = total_bright = 0
for name in ("rough_01", "rough_02", "rough_03", "rough_04", "rough_05"):
    with Image.open(f"/tmp/edge_control/{name}_generated.png") as opened:
        source = opened.convert("RGBA")
    engine = ck.finish_rim_cleanup(ck.remove_chroma_key_automatic(source, "blue", subject_profile="opaque_clipart"), "opaque_clipart")
    final = suppress_key_tint(clean_alpha(matte_edges(source, engine, "blue"), island_min_gap=DEBRIS_MIN_GAP), "blue")
    rgb = np.asarray(source.convert("RGB"), np.float32) / 255.0
    key = np.array(ck._measured_border_key(source), np.float32) / 255.0
    e_alpha = np.asarray(engine)[..., 3]
    f_alpha = np.asarray(final)[..., 3]
    others = np.maximum(rgb[..., 0], rgb[..., 1])
    key_lead = rgb[..., 2] - others
    # exactly the candidate conditions of _enclosed_shaded_key before its width test
    candidate = (e_alpha > 0) & (rgb[..., 2] > 1.6 * others) & (key_lead > 40.0 / 255.0)
    holes = candidate & (e_alpha == 255) & (f_alpha == 0)
    bright = holes & (rgb[..., 2] > 0.7 * key[2])   # bright key-hued: the contract's 1-px details
    dark = int(holes.sum()) - int(bright.sum())     # genuinely shaded (<= 70 %): a real gap
    total_old += int(holes.sum()); total_bright += int(bright.sum())
    print(f"  {name}: engine-opaque key-dominant pixels dropped by the final chain: {int(holes.sum())} "
          f"(из них ярких, контрактных: {int(bright.sum())}; тёмных швов: {dark})")
print(f"  ИТОГО: {total_old} px, из них контрактных ярких {total_bright} px")
