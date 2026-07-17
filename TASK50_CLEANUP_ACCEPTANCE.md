# Task 50 - Complete Cleanup Acceptance

Дата: 2026-07-17.

## Вердикт

`PASS` для текущей post-MVP цели очистки без сборки и публикации релиза.

- Metadata cleanup выборочно удаляет поддерживаемые категории и сохраняет
  декодированные пиксели, alpha, выбранные ICC/DPI.
- Local, mixed KIE и PhotoRoom Standard используют общий final cleanup.
- Автоматический Gemini-режим опирается на подтверждённый detector; ручная
  область сообщает только факт обработки и требует визуальной проверки.
- Для SynthID и неизвестных pixel-level markers гарантированное удаление остаётся
  `UNSUPPORTED`. Tasks 43-49 явно пропущены после Task 42 hardware no-go.
- Сборка, тег, GitHub Actions и release не запускались.
- Финальный offline regression: `176/176`; повторное независимое review: `PASS`.

## Проверенное покрытие

| Область | Доказательство |
|---|---|
| Независимые cleanup-галочки | EXIF, XMP, IPTC, comments/text, thumbnail, generator и C2PA проверяются отдельно в `tests.test_metadata_cleanup_acceptance`. |
| Local combined | Все cleanup-галочки вместе с Unsharp, edge shrink и trim; cleanup выполняется один раз и не меняет пиксели финальной стадии. |
| Mixed KIE | Реальный worker-маршрут `Local upscale -> KIE background removal -> cleanup` с подменённым transport, без сети; provider metadata удалены, alpha сохранён. |
| PhotoRoom Standard | Реальный worker-маршрут `PhotoRoom -> cleanup` с подменённым transport; KIE не вызывается, `raw/` и `output/` проверены, ключ не попадает в лог. |
| Legacy/default off | Старый config получает безопасные defaults; выключенный cleanup пропускает inspection и совпадает с прежним writer. |
| Stop/cancellation | GUI не блокируется на `wait()`; текущий файл не публикуется после Stop; уже готовые итоги остаются доступными. |
| Network boundary | Remote API/license transport требует HTTPS; HTTPS redirect не может понизиться до HTTP или содержать credentials; KIE credentials передаются только точным `kie.ai`/`redpandaai.co` host/subdomain и не наследуются redirect-запросом. |
| Provider output | Upload/response имеют byte-лимиты; PNG принимается только после проверки размера, pixel count, single-frame и полной декодируемости; невалидный результат не публикуется. |
| Paid request safety | `POST` не повторяется автоматически после неоднозначного timeout; повтор остаётся только для idempotent GET/HEAD/OPTIONS. |
| Claims | Processing, metadata/C2PA hints и pixel-detector evidence не смешиваются; confirmed-area не заявляет доказанное удаление. |

## Визуальная приёмка

Offline comparison выполнен на принадлежащей проекту доске `1024x1024` с пятью
классами: `photo`, `face`, `illustration`, `clipart + alpha`, `text-heavy`.
Вход содержит `261101` прозрачный пиксель.

Результат:

- source hash unchanged: `true`;
- dimensions match: `true`;
- decoded RGBA pixels match: `true`;
- alpha match: `true`;
- ICC preserved: `true`;
- DPI preserved: `true`;
- выбранные EXIF/XMP/IPTC/comments/thumbnail/generator категории отсутствуют;
- на светлом и тёмном фоне видимых различий нет.

Evidence вне git:

- `C:\Users\belou\Downloads\output\task50-cleanup-acceptance\acceptance.json`
- `C:\Users\belou\Downloads\output\task50-cleanup-acceptance\light-dark-multiclass-comparison.png`
- `C:\Users\belou\Downloads\output\task50-run-cleanup-acceptance.py`

## Проверка UI

Изолированный offscreen config без API keys создал `MainWindow` версии `1.0.2`
размером `1070x1123`. Основная, processing и settings вкладки отрисованы без
перекрытий контролов. Offscreen backend не содержит рабочего Cyrillic font,
поэтому финальная типографика остаётся частью ручного pre-release checklist, а не
этой no-release приёмки.

## Команды

```powershell
python -m unittest tests.test_license_client_security -v
$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_license_client_security tests.test_kie_routing tests.test_photoroom_provider tests.test_main_ui_acceptance -v
$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_kie_routing tests.test_main_ui_acceptance -v
$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -v
python 'C:\Users\belou\Downloads\output\task50-run-cleanup-acceptance.py'
python -m py_compile .\main.py .\license_client.py .\tests\test_license_client_security.py .\tests\test_kie_routing.py .\tests\test_main_ui_acceptance.py .\tests\test_photoroom_provider.py .\tests\test_visible_mark_pipeline.py
$env:QT_QPA_PLATFORM='offscreen'; python -c "import main; app=main.QApplication([]); w=main.MainWindow(); w.show(); app.processEvents(); print('UI_SHOWN_OK', w.windowTitle(), w.size().width(), w.size().height()); w.settings_save_timer.stop(); w.api_key_mask_timer.stop(); w.close(); app.quit()"
git diff --check
```

## Отложенные улучшения

- `config.json` по действующему PRD хранит пользовательские API keys локально в
  открытом виде и маскирует их только в UI. Шифрование at rest требует отдельного
  продуктового решения и миграции.
- Запись `config.json` пока не имеет отдельного recovery-файла после внезапного
  отключения питания. Это не блокирует Task 50 и не изменялось в cleanup-задаче.
- Ручные release-проверки `TEST_CHECKLIST.md` sections 10-11 остаются открытыми
  до прямой команды пользователя на выпуск.
