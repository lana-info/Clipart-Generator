"""Known-truth opaque botanical details, independent of generation providers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chroma_key import remove_chroma_key_automatic
from scripts.probe_chroma_fur import composite, measure


def fixture(size: int = 256) -> Image.Image:
    scale = 4
    factor = size * scale / 256
    canvas = Image.new('RGBA', (size * scale, size * scale))
    draw = ImageDraw.Draw(canvas)

    def line(points, width, color):
        draw.line([(round(x*factor), round(y*factor)) for x, y in points],
                  fill=(*color, 255), width=max(1, round(width*factor)))

    def ellipse(cx, cy, rx, ry, color):
        draw.ellipse(tuple(round(v*factor) for v in (cx-rx, cy-ry, cx+rx, cy+ry)),
                     fill=(*color, 255))

    # Opaque stems of several widths and small leaves; no soft painting filter.
    for index, (cx, cy, radius) in enumerate([(36, 48, 5), (88, 66, 9), (150, 80, 15), (208, 65, 24)]):
        line([(cx, cy), (cx-7, 205)], 1+index*.5, (65, 115, 40))
        for offset in (35, 65):
            y = cy+offset
            line([(cx-3, y+10), (cx-14, y)], 1, (65, 115, 40))
            ellipse(cx-14, y, 6, 2.5, (100, 150, 45))
        for angle in np.linspace(0, 2*np.pi, 6, endpoint=False):
            ellipse(cx+radius*.7*np.cos(angle), cy+radius*.7*np.sin(angle),
                    radius*.43, radius*.43, (245, 205, 50))
        ellipse(cx, cy, radius*.25, radius*.25, (145, 65, 25))
    return canvas.resize((size, size), Image.Resampling.BOX)


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    report = {}
    for size in (256, 512):
        truth = fixture(size)
        for name, key in [('blue', (0, 0, 255)), ('offblue', (20, 45, 240))]:
            name = f'{size}-{name}'
            folder = output / name
            folder.mkdir()
            source = composite(truth, key)
            result = remove_chroma_key_automatic(source, 'blue', subject_profile='opaque_clipart')
            metrics = measure(result, truth)
            expected_alpha, actual_alpha = np.array(truth)[..., 3], np.array(result)[..., 3]
            opaque = expected_alpha == 255
            rgb_error = np.abs(np.array(result)[..., :3].astype(int)-np.array(truth)[..., :3].astype(int))
            metrics['opaque_alpha_changed'] = int(np.count_nonzero(opaque & (actual_alpha != 255)))
            metrics['opaque_rgb_changed'] = int(np.count_nonzero(opaque & (np.max(rgb_error, axis=2) > 0)))
            metrics['opaque_max_rgb_error'] = int(rgb_error[opaque].max(initial=0))
            metrics['background_pixels_made_visible'] = int(np.count_nonzero((expected_alpha == 0) & (actual_alpha > 0)))
            metrics['opaque_pixels_removed'] = int(np.count_nonzero((expected_alpha == 255) & (actual_alpha == 0)))
            report[name] = metrics
            images = [('source', source), ('expected', truth), ('vibix', result)]
            sheet = Image.new('RGB', (size*3, (size+24)*2), '#eeeeee')
            for label, image in images:
                image.save(folder / f'{label}.png')
            for row, bg in enumerate([(255, 255, 255), (0, 0, 0)]):
                for col, (label, image) in enumerate(images):
                    sheet.paste(composite(image.convert('RGBA'), bg), (col*size, row*(size+24)+24))
                    ImageDraw.Draw(sheet).text((col*size+4, row*(size+24)+4), label, fill='black')
            sheet.save(folder / 'comparison.png')
    (output / 'metrics.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(json.dumps(run(parser.parse_args().output), indent=2))
