# Clipart Generator 3.0 — Release Notes

Статус: стабильный клиентский релиз 3.0. Windows x64 прошёл ручную клиентскую
проверку; macOS arm64 доступен как неподписанный preview с ручным GUI smoke pending.

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
- Автоматический update-канал не включён; клиентам предоставляются прямые ссылки на assets Release.
- macOS-клиент 3.0 выпускается одним ZIP только для Apple Silicon (arm64); Intel Mac и Universal 2 отложены.
- Реальные provider-backed запросы не выполнялись и требуют отдельного
  одобрения стоимости.
- Windows installer подтверждён ручным upgrade smoke; macOS signing, notarization и clean-machine smoke не подтверждены.
- SynthID removal и RunPod/cloud pipeline отложены и не блокируют обычный Processing.
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
