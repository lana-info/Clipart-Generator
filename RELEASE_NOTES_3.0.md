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

- Упаковочные metadata и существующие артефакты всё ещё `2.0`; 3.0 installer
  нельзя считать опубликованным.
- Реальные provider-backed запросы не выполнялись и требуют отдельного
  одобрения стоимости.
- Installer, подписи, macOS notarization и clean-machine smoke не подтверждены.
- SynthID removal и RunPod/cloud pipeline не входят в подтверждённый scope.
- WorkerThread/legacy и Qt teardown остаются техническим долгом.

См. [CHANGELOG.md](CHANGELOG.md) для исторических изменений и
[RELEASE_PROCESS.md](RELEASE_PROCESS.md) для операционного процесса публикации.
