r"""Run BEN2 background removal on sample images.

This is an evaluation helper, not part of the app runtime.
Install BEN2 dependencies in a separate environment before running:

    python -m pip install torch torchvision transformers pillow
    python -m pip install git+https://github.com/PramaLLC/BEN2.git

Example:

    python scripts/test_ben2_background.py "C:\path\image.png" --output-dir "C:\path\ben2-test"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image


MODEL_ID = "PramaLLC/BEN2"


def safe_print_path(label: str, path: Path) -> None:
    message = f"{label}: {path}"
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode(sys.stdout.encoding or "utf-8", errors="backslashreplace").decode(sys.stdout.encoding or "utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test BEN2 background removal on local images.")
    parser.add_argument("images", nargs="+", help="Input image paths.")
    parser.add_argument(
        "--output-dir",
        default="ben2-test-output",
        help="Directory for BEN2 PNG results and dark previews.",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=("cpu", "cuda"),
        help="Torch device. Use cuda only when PyTorch CUDA is installed.",
    )
    parser.add_argument(
        "--no-refine",
        action="store_true",
        help="Disable BEN2 refine_foreground output refinement when supported.",
    )
    return parser.parse_args()


def load_ben2_model(device: str):
    try:
        import torch
        from ben2 import AutoModel
    except ImportError as exc:
        raise SystemExit(
            "BEN2 test dependencies are missing. Install them first:\n"
            "python -m pip install torch torchvision transformers pillow\n"
            "python -m pip install git+https://github.com/PramaLLC/BEN2.git"
        ) from exc

    model = AutoModel.from_pretrained(MODEL_ID)
    model.to(torch.device(device))
    model.eval()
    return model


def run_ben2(model, image_path: Path, output_dir: Path, refine: bool) -> Path:
    with Image.open(image_path) as img:
        source = img.convert("RGB")
        try:
            result = model.inference(source, refine_foreground=refine)
        except TypeError:
            result = model.inference(source)

    if not isinstance(result, Image.Image):
        raise RuntimeError(f"BEN2 returned unsupported result type for {image_path}: {type(result)!r}")

    output_path = output_dir / f"{image_path.stem}_ben2.png"
    result.convert("RGBA").save(output_path)
    return output_path


def save_dark_preview(image_path: Path) -> Path:
    preview_path = image_path.with_name(f"{image_path.stem}_dark_preview.png")
    with Image.open(image_path) as img:
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (24, 24, 24, 255))
        Image.alpha_composite(background, rgba).save(preview_path)
    return preview_path


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    model = load_ben2_model(args.device)
    refine = not args.no_refine
    created = []

    for raw_path in args.images:
        image_path = Path(raw_path).expanduser().resolve()
        if not image_path.is_file():
            print(f"Skip missing file: {image_path}", file=sys.stderr)
            continue
        result_path = run_ben2(model, image_path, output_dir, refine)
        preview_path = save_dark_preview(result_path)
        created.append((result_path, preview_path))
        safe_print_path("BEN2", result_path)
        safe_print_path("Dark preview", preview_path)

    if not created:
        print("No images processed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
