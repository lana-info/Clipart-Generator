"""Замер загрузки окна проверки PNG (владелец 2026-10-30).

Строит настоящую панель проверки с N картинками и мерит, за сколько появляются все миниатюры.
Запуск: python measure.py <repo> [<число картинок>]

Замеры на VDS (Ubuntu, 6 CPU), 2026-10-30, back-to-back на одном состоянии машины:

| Набор | По одной (было) | Несколько потоков (стало) | Выигрыш |
| --- | ---: | ---: | ---: |
| 47 × 2048 px | 2,70 с (57 мс/шт) | 1,00 с (21 мс/шт) | 2,7× |
| 12 × 4096 px | 4,01 с (334 мс/шт) | 1,33 с (111 мс/шт) | 3,0× |
| 47 × 2048 px (машина под нагрузкой) | 14,3 с | 4,1 с | 3,5× |

Повторный заход на тот же экран с прогретым кешем миниатюр — 0,4–0,7 с в обоих вариантах.
"""
import os, sys, tempfile, time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1])
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 47

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from PIL import Image, ImageDraw
from studio_set_export_ui import SetExportDialog

work = Path(tempfile.mkdtemp())
out = work / 'output'
out.mkdir(parents=True, exist_ok=True)
paths = []
for n in range(COUNT):
    path = out / f'result_{n:02d}.png'
    image = Image.new('RGBA', (2048, 2048), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((150, 150, 1900, 1900), fill=(250, 240, 220, 255))
    draw.ellipse((1200, 600, 1600, 1000), fill=(245, 170, 80, 255))
    image.save(path)
    paths.append(path)

loader = lambda path: SimpleNamespace(  # то же, что подаёт модуль Авто-клипарт
    path=str(Path(path).resolve()), status='ok', issues=(), width=0, height=0,
    transparent_fraction=0.0, content_fraction=0.0)

start = time.monotonic()
panel = SetExportDialog([], review_paths=paths, quality_reports=(),
                        workspace=work, embedded=True, quality_loader=loader)
panel.enable_marks({str(p.resolve()): 'unchecked' for p in paths})
panel._show_quality_review()
while panel._qc_pending and time.monotonic() - start < 300:
    app.processEvents()
    time.sleep(0.002)
total = time.monotonic() - start
print(f'все миниатюры готовы: {total:.2f} с ({total / COUNT * 1000:.0f} мс на картинку)')
start2 = time.monotonic()
panel.deleteLater()
panel2 = SetExportDialog([], review_paths=paths, quality_reports=(),
                         workspace=work, embedded=True, quality_loader=loader)
panel2.enable_marks({str(p.resolve()): 'unchecked' for p in paths})
panel2._show_quality_review()
while panel2._qc_pending and time.monotonic() - start2 < 300:
    app.processEvents()
    time.sleep(0.002)
print(f'повторный заход (кеш на диске): {time.monotonic() - start2:.2f} с')
sys.stdout.flush()
os._exit(0)
