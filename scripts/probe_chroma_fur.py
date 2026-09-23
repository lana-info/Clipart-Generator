"""Offline known-truth fur/irregular-edge probe; never calls image providers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chroma_key import KEY_COLORS, remove_chroma_key_automatic


def fixture(textured: bool, size: int = 384) -> Image.Image:
    scale = 4
    side = size * scale
    mask = Image.new('L', (side, side))
    draw = ImageDraw.Draw(mask)
    rng = np.random.default_rng(227)
    # High-resolution opaque fibres; downsampling adds only boundary coverage.
    for cx, cy, rx, ry in ((.46, .61, .28, .25), (.58, .32, .17, .17)):
        draw.ellipse(tuple(int(v * side) for v in (cx-rx, cy-ry, cx+rx, cy+ry)), fill=255)
        for angle in np.linspace(0, 2*np.pi, 380, endpoint=False):
            length = rng.uniform(.006, .040)
            a = ((cx + rx*.96*np.cos(angle))*side, (cy + ry*.96*np.sin(angle))*side)
            b = ((cx + (rx+length)*np.cos(angle+.015))*side,
                 (cy + (ry+length)*np.sin(angle+.015))*side)
            draw.line((a, b), fill=255, width=int(rng.integers(2, 9)))
    draw.polygon([(int(x*side), int(y*side)) for x,y in
                  ((.70,.30),(.85,.36),(.70,.40))], fill=255)
    alpha = np.array(mask.resize((size,size), Image.Resampling.BOX))
    y,x = np.indices((size,size))
    rgb = np.full((size,size,3), (240,210,45), dtype=np.uint8)
    if textured:
        shade = 10*np.sin(x*.19+y*.11) + 7*np.cos(y*.37-x*.09)
        rgb = np.clip(rgb.astype(float)+shade[...,None],0,255).astype(np.uint8)
        # Genuine warm strands at several depths, not contamination from key.
        stripes = (np.sin(x*.16+y*.10) > .94) & (y > size*.42)
        rgb[stripes] = (180,145,35)
    rgb[(x > size*.70) & (y > size*.30) & (y < size*.40)] = (235,125,30)
    rgb[(x-size*.62)**2+(y-size*.29)**2 < (size*.012)**2] = (30,25,20)
    return Image.fromarray(np.dstack((rgb,alpha)))


def measure(actual: Image.Image, expected: Image.Image) -> dict:
    a = np.array(actual).astype(float)
    e = np.array(expected).astype(float)
    opaque = e[...,3] == 255
    depth = cv2.distanceTransform(opaque.astype(np.uint8),cv2.DIST_L2,5)
    error = np.max(np.abs(a[...,:3]-e[...,:3]),axis=2)
    damaged_rgb = opaque & (error > 20) & (a[...,3] > 0)
    damaged_alpha = opaque & (a[...,3] < 235)
    partial = (e[..., 3] > 0) & (e[..., 3] < 255)
    composites = {}
    for name, value in [('white', 255), ('black', 0)]:
        actual_preview = a[..., :3]*a[..., 3:]/255 + value*(1-a[..., 3:]/255)
        expected_preview = e[..., :3]*e[..., 3:]/255 + value*(1-e[..., 3:]/255)
        difference = np.abs(actual_preview-expected_preview)[partial]
        composites[name] = {
            'mean_channel_error': float(difference.mean()) if difference.size else None,
            'p95_channel_error': float(np.percentile(difference, 95)) if difference.size else None,
            'pixels_over_20': int(np.count_nonzero(np.max(difference, axis=1) > 20)),
        }
    return {
        'opaque_pixels': int(opaque.sum()),
        'opaque_rgb_error_over_20': int(damaged_rgb.sum()),
        'opaque_alpha_loss_over_20': int(damaged_alpha.sum()),
        'deepest_rgb_damage_px': float(depth[damaged_rgb].max(initial=0)),
        'deepest_alpha_damage_px': float(depth[damaged_alpha].max(initial=0)),
        'alpha_mae': float(np.abs(a[...,3]-e[...,3]).mean()),
        'partial_pixels': int(partial.sum()),
        'partial_composites': composites,
    }


def composite(image: Image.Image, color: tuple) -> Image.Image:
    return Image.alpha_composite(Image.new('RGBA',image.size,(*color,255)),image).convert('RGB')


def run(output: Path) -> dict:
    output.mkdir(parents=True,exist_ok=False)
    report = {}
    rows = []
    for textured in (False,True):
        truth = fixture(textured)
        for key in ('blue','green','red'):
            name = ('textured' if textured else 'plain')+'-'+key
            folder = output / name
            folder.mkdir()
            truth.save(folder/'expected.png')
            source = composite(truth,KEY_COLORS[key])
            source.save(folder/'source.png')
            stages = {}
            def observe(stage, image):
                stages[stage] = measure(image,truth)
                image.save(folder/(stage+'.png'))
            result = remove_chroma_key_automatic(source,key,subject_profile='opaque_clipart',stage_observer=observe)
            result.save(folder/'result.png')
            report[name] = stages
            row = Image.new('RGB',(384*4,414),'#eeeeee')
            for index,(label,img) in enumerate((('source',source),('expected / white',composite(truth,(255,255,255))),
                                                ('actual / white',composite(result,(255,255,255))),
                                                ('actual / black',composite(result,(0,0,0))))):
                row.paste(img,(index*384,30))
                ImageDraw.Draw(row).text((index*384+8,8),name+' '+label,fill='black')
            row.save(folder/'comparison.png')
            rows.append(row)
    sheet = Image.new('RGB',(1536,414*len(rows)))
    for index,row in enumerate(rows):
        sheet.paste(row,(0,index*414))
    sheet.save(output/'comparison.png')
    (output/'metrics.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.output),indent=2))
