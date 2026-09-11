"""Generate a contact-sheet acceptance fixture using only synthetic images.

Usage: QT_QPA_PLATFORM=offscreen python scripts/preview_studio_delivery.py /tmp/demo
Never reads user images or calls a provider.
"""
from pathlib import Path
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio_delivery import create_contact_sheet_pdf, output_filename


def main():
    folder = Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    titles = ["pink bear", "blue flower", "gold star", "green leaves", "red balloon",
              "розовый медвежонок", "small golden crown", "spring flower", "little blue bird",
              "pastel ribbon"]
    for index in range(31):
        path = folder / output_filename(index + 1, titles[index % len(titles)])
        if path.exists():
            raise FileExistsError(path)
        image = Image.new("RGBA", (480, 360), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        colors = ["#efa0b6", "#7298cf", "#e5b753", "#6aa480", "#d96f71"]
        color = colors[index % len(colors)]
        if index % 3 == 0:
            draw.ellipse((130, 35, 205, 110), fill=color)
            draw.ellipse((275, 35, 350, 110), fill=color)
            draw.ellipse((145, 70, 335, 255), fill=color)
            draw.ellipse((202, 156, 278, 216), fill="#fff0df")
        elif index % 3 == 1:
            for box in [(180, 40, 300, 150), (100, 105, 240, 215), (240, 105, 380, 215), (180, 170, 300, 280)]:
                draw.ellipse(box, fill=color)
            draw.ellipse((204, 122, 276, 194), fill="#ffe4ac")
        else:
            draw.regular_polygon((240, 160, 118), 5, fill=color)
        image.save(path)
        paths.append(path)
    print(create_contact_sheet_pdf(paths, folder / "clipart-contact-sheet-letter.pdf"))


if __name__ == "__main__":
    main()
