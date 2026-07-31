# Known Limitations 3.0

Этот документ описывает ограничения, которые нельзя скрывать в клиентском
релизе. Он не является списком будущих идей — идеи находятся в
[PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md).

## Релизные blockers

- Source-ветка называется 3.0, но `APP_VERSION`, `installer.iss`, `build.ps1`,
  `version.json`, `release/VERSION.txt` и существующие установочные артефакты
  всё ещё имеют `2.0`. Публичный 3.0 installer/release не подтверждён.
- Полный provider-backed smoke Clipart/Pinterest не выполнен: он требует
  реальных ключей и платных запросов.
- Windows/macOS installer для 3.0 не собран и не подписан.

## Не поддерживается или не обещается

- Автоматическое удаление SynthID не гарантируется; это research-only область.
- Cloud GPU/RunPod не являются подтверждённым локальным production-сценарием.
- Пользовательские файлы не должны загружаться во внешние сервисы без явного
  выбора соответствующей операции.
- Нельзя считать локальный fallback видимой марки доказанным универсальным
  удалением watermark.

## Работает экспериментально или с оговорками

- Локальный confirmed-area cleanup зависит от доступности MI-GAN/ONNX; при
  проблеме native runtime используется ограниченный OpenCV fallback.
- Автообновление зависит от внешнего `version.json`, доступности updates
  repository и корректного checksum/download URL.
- Legacy `WorkerThread` остаётся production seam для части V3 маршрутов.

## Требует ручной проверки

- Установщик Windows и оба macOS-архива 3.0 на чистых системах.
- Подпись/notarization macOS.
- Полный ручной Clipart/Pinterest run с одобренным provider budget.
- Native teardown полного legacy Qt smoke и отсутствие diagnostic при закрытии.

## Не вошло в 3.0

- Выделение WorkerThread из `main.py`.
- Полноценный installer/release automation cleanup.
- Большие UX-улучшения Results: zoom, comparison slider, фильтры очереди.
- Production SynthID pipeline и cloud watermark research.

См. [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md) для внутренних причин и
[RELEASE_NOTES_3.0.md](RELEASE_NOTES_3.0.md) для краткого описания релиза.
