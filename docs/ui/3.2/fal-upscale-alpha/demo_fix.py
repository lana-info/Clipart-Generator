"""Прогон правки на реальном файле владельца: возвращаем прозрачность апскейленному PNG.

Вход: opaque-результат Fal-апскейла (как пришёл владельцу) и исходник до апскейла (его матте).
Операция ровно та же, что теперь делает конвейер: alpha из исходника, растянутая до размера
результата. Ничего не платим, ничего не генерируем.

Запуск: python -I demo_fix.py <upscaled.png> <source-before-upscale.png> <out.png>
"""
import sys
from pathlib import Path

from PIL import Image

upscaled_path, source_path, out_path = (Path(arg) for arg in sys.argv[1:4])

with Image.open(source_path) as source:
    alpha = source.convert("RGBA").getchannel("A")
    has_soft = any(alpha.histogram()[1:255])
    resample = Image.Resampling.BILINEAR if has_soft else Image.Resampling.NEAREST

with Image.open(upscaled_path) as result_img:
    result = result_img.convert("RGBA")
    before = result.getchannel("A")
    print(f'до правки: alpha min={before.getextrema()[0]} max={before.getextrema()[1]} — прозрачности нет')
    restored = alpha.resize(result.size, resample)
    result.putalpha(restored)
    result.save(out_path, format="PNG")
    after = result.getchannel("A")
    print(f'после правки: alpha min={after.getextrema()[0]} max={after.getextrema()[1]}'
          f'; прозрачных пикселей {after.histogram()[0]}, размер {result.size}')

    # лист сравнения: «было» — как пришло (непрозрачное), «стало» — с возвращённой прозрачностью
    bound = 900
    tile = result.copy()
    tile.thumbnail((bound, bound), Image.Resampling.LANCZOS)
    opaque = Image.new("RGBA", tile.size, (255, 255, 255, 255))
    opaque.alpha_composite(result_img.convert("RGBA").resize(tile.size, Image.Resampling.LANCZOS))
    checker = Image.new("RGBA", tile.size, (255, 255, 255, 255))
    step = 24
    for y in range(0, tile.height, step):
        for x in range(0, tile.width, step):
            if (x // step + y // step) % 2:
                checker.paste((214, 220, 228, 255), (x, y, x + step, y + step))
    checker.alpha_composite(tile)
    sheet = Image.new("RGB", (checker.width * 2 + 24, checker.height), (23, 33, 49))
    sheet.paste(opaque.convert("RGB"), (0, 0))
    sheet.paste(checker.convert("RGB"), (checker.width + 24, 0))
    sheet_path = out_path.with_name("до-после-прозрачность-" + out_path.name)
    sheet.save(sheet_path, format="PNG")
    print(f'лист сравнения: {sheet_path}')
