# Clipart Generator 3.0 — Release Notes

Статус: source release candidate `v3.0.0-rc1`; публичная упаковка 3.0 ещё не
подтверждена. Для точного статуса см. [KNOWN_LIMITATIONS_3.0.md](KNOWN_LIMITATIONS_3.0.md).

## Что нового

- Единый V3 wizard для Clipart, Pinterest и Processing.
- Локальная обработка файлов с отдельной папкой результатов и сохранением
  исходников.
- Processing Results с понятной сводкой, статусами файлов, повтором ошибок,
  продолжением обработки и техническим логом.
- Draft/state сохранение и восстановление между навигацией и перезапуском.

## Что изменилось

- Processing отделён от generation в пользовательских статусах.
- Добавлены явные правила collision/overwrite и безопасное именование output.
- Пользовательские причины ошибок отделены от технических событий.
- Clipart и Pinterest используют согласованные модели, пропорции и preflight
  boundaries.
- Проверки безопасности, secret redaction и network-free mocks расширены.

## Что исправлено

- Выбранная output-папка действительно используется.
- `README.jpg` обрабатывается в batch или получает явную причину failure.
- Исходные файлы не перезаписываются локальным Processing pipeline.
- Results action bar больше не зависит от прокрутки и не расширяет окно на
  больших очередях.
- `Done` и «Обработать ещё файлы» имеют общий предсказуемый контракт.

## Известные ограничения

- Релизные источники версии приложения и сборки переведены на `3.0`.
- 3.0 installer и публичный update-канал пока не подтверждены; см. `CLIENT_DELIVERY.md`.
- macOS-клиент 3.0 выпускается одним ZIP только для Apple Silicon (arm64); Intel Mac и Universal 2 отложены.
- Реальные provider-backed запросы не выполнялись и требуют отдельного
  одобрения стоимости.
- Installer, подписи, macOS notarization и clean-machine smoke не подтверждены.
- SynthID removal и RunPod/cloud pipeline не входят в подтверждённый scope.
- WorkerThread/legacy и Qt teardown остаются техническим долгом.

См. [CHANGELOG.md](CHANGELOG.md) для исторических изменений и
[RELEASE_PROCESS.md](RELEASE_PROCESS.md) для операционного процесса публикации.
## Стабилизация

- Раздельное сохранение output-папок и пользовательских processing preferences по режимам.
- SynthID/RunPod обозначен как Deferred и не блокирует обычный Processing workflow.
- Убрано лишнее Pinterest-предупреждение.
## Final client verification

Windows x64 was manually installed over the previous version and verified:
V3 startup, all three modes, Processing, output preservation, source safety,
preferences, recipe restoration, metadata cleanup and restart behavior pass.

macOS Apple Silicon packaging is verified. Real-device GUI smoke is pending;
the build is unsigned/not notarized and Intel Mac is unsupported.
