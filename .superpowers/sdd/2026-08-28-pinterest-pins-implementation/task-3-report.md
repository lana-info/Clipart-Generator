# Task 3 — protected product compositing and fidelity guards

Дата: 2026-08-28

## Изменения

- Добавлен `pinterest_pin_composer.py` с неизменяемым `ProductLayer`: RGB всегда
  берётся из исходного файла, а rembg, BEN2 и внешний adapter могут передать
  только alpha-маску.
- Уже прозрачный источник не требует provider; отсутствующий provider и
  некорректная маска завершаются безопасной ошибкой без раскрытия пути к файлу.
- Композитинг ограничен canvas 1000×1500, использует детерминированный LANCZOS
  resize и Pillow alpha composite; продукт не проходит image-to-image обработку.
- Добавлены SHA-256 digest слоя, fidelity guard с количеством и максимум пятью
  координатами несовпадений, а также атомарный PNG/WebP export. JPEG отклоняется,
  потому что не сохраняет alpha.

## TDD evidence

- RED 1: новый `tests/test_pinterest_pin_composer.py` — `7 failed` из-за
  отсутствующего модуля.
- GREEN 1: `7 passed` после минимальной реализации загрузки, композитинга,
  guard и экспорта.
- RED 2: локальные rembg/BEN2 routes — `2 failed`, оба были недоступны.
- GREEN 2: `9 passed` после lazy alpha-only adapter’ов.
- RED 3: digest — `1 failed` (`product_layer_digest` отсутствовал).
- GREEN 3 и финальный focused run: `10 passed`.

## Проверки

- `/root/projects/Clipart Generator/commit-worktree/.venv/bin/python -m pytest tests/test_pinterest_pin_composer.py -q` — `10 passed`.
- `/root/projects/Clipart Generator/commit-worktree/.venv/bin/python -m py_compile pinterest_pin_composer.py tests/test_pinterest_pin_composer.py` — exit 0.
- `git diff --check` — без замечаний.

## Ограничения

- Реальные rembg/BEN2 inference не запускались: это могло бы скачать модель или
  занять ресурсы. Их alpha-only boundary проверен изолированными adapter-тестами;
  контролируемый интеграционный прогон остаётся задачей следующей стадии.

## Review remediation — 2026-08-28

- `ProductLayer` теперь сохраняет normalised RGB и alpha как immutable bytes и
  возвращает defensive Pillow copies. Внешняя мутация `rgba` или `alpha_mask`
  больше не изменяет digest либо композитинг.
- Shadow строится на полном canvas и вырезается по финальной области любого
  product alpha `> 0`, поэтому не меняет RGB или alpha даже полупрозрачного
  товара.
- Fidelity guard использует сохранённый только в памяти детерминированный
  reference product region, проверяет RGB и alpha всех transformed pixels с
  alpha `> 0`, а сообщения содержат лишь count и максимум пять координат.
- Export теперь принимает PNG, JPG и JPEG. JPEG детерминированно flatten’ится
  на белую подложку в RGB; TIFF и остальные неподдерживаемые форматы отклоняются.
- Provider/load/export error paths больше не chain’ят сырые причины с путями,
  сообщениями provider’а или секретами; наружу выдаются только safe domain errors.

### Regression evidence

- RED: после добавления review-тестов — `6 failed, 9 passed`: raw provider
  cause, mutation `ProductLayer`, shadow overlap, two partial-alpha guard cases
  и JPG export.
- После минимальной реализации временно оставалось четыре guard failure:
  evidence записывал digest resize-layer вместо protected source. Поток был
  проверен отдельным digest probe; исправлено место записи evidence.
- GREEN: `15 passed` в focused composer suite.
