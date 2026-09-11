"""Local-only analysis of downloaded KIE probe images; no quality certification."""
from pathlib import Path
import json
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chroma_key import remove_chroma_key_automatic, ChromaKeyAmbiguousError
from native_alpha import preserve_native_alpha


def analyze(folder):
    report = {}
    board = Image.new("RGB", (1200, 1280), "#d8d8d8")
    draw = ImageDraw.Draw(board)
    for row, subject in enumerate(("flowers", "wreath")):
        for column, route in enumerate(("native", "chroma")):
            path = folder / f"{subject}-{route}.png"
            with Image.open(path) as source:
                start = time.monotonic()
                try:
                    output = (preserve_native_alpha(source) if route == "native" else
                              remove_chroma_key_automatic(source, "blue", subject_profile="opaque_clipart"))
                    status = "processed_not_certified"
                except ChromaKeyAmbiguousError as error:
                    output = source.convert("RGBA")
                    status = "review_" + type(error).__name__
                elapsed = time.monotonic() - start
            with (folder / f"{subject}-{route}-processed.png").open("xb") as stream:
                output.save(stream, "PNG")
            alpha = np.asarray(output.getchannel("A"))
            visible = alpha > 0
            report[f"{subject}-{route}"] = {
                "status": status, "seconds": elapsed,
                "alpha_bins_pixels": {name: int(np.count_nonzero(mask)) for name, mask in (
                    ("zero", alpha == 0), ("1_to_15", (alpha > 0) & (alpha < 16)),
                    ("16_to_239", (alpha >= 16) & (alpha < 240)),
                    ("240_to_254", (alpha >= 240) & (alpha < 255)), ("255", alpha == 255))},
                "visible_alpha_percentiles": np.percentile(alpha[visible], [5, 50, 95]).tolist() if visible.any() else [],
            }
            # Four columns: native white/black, chroma white/black. Each source
            # is composited before resizing; hidden RGB cannot affect this view.
            for offset, background in enumerate(("white", "black")):
                tile = Image.new("RGBA", output.size, background)
                tile.alpha_composite(output)
                x, y = (column * 2 + offset) * 300, row * 640
                draw.text((x + 4, y + 4), f"{subject} {route} / {background}", fill="black")
                board.paste(tile.convert("RGB").resize((300, 300)), (x, y + 25))
                # Fixed central region crop, same image coordinates per route.
                crop = tile.crop((400, 100, 700, 400)).convert("RGB")
                board.paste(crop, (x, y + 335))
    with (folder / "analysis.json").open("x") as stream:
        json.dump(report, stream, indent=2)
    board.save(folder / "comparison-white-black.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    analyze(Path(sys.argv[1]))
