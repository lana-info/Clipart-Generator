# Контракт статусов скрытых пиксельных меток

Этот контракт используется будущими KIE, OpenRouter и GPU-провайдерами. Он не
добавляет удаление в текущий pipeline и не смешивает пиксельную проверку с
metadata/C2PA cleanup.

## Статусы свидетельства

- `detected`: выбранная проверка обнаружила конкретную пиксельную метку.
- `not_detected`: выбранная проверка не обнаружила конкретную метку. Это не
  доказывает, что изображение создано человеком или что другая AI-метка отсутствует.
- `not_verified`: после обработки пиксельная метка не проверялась.
- `unsupported`: для этого типа метки нет поддерживаемой проверки.

Статуса `removed` в контракте нет. Успешная обработка означает только, что выбранный
процесс завершился и сохранил валидный результат. Удаление нельзя заявлять без
отдельного detector evidence.

## Разделение данных

Отчет имеет четыре независимые ветки:

1. `processing`: `not_run`, `succeeded`, `failed` или `cancelled`.
2. `pixel_evidence`: detector status/source, обязательный `input`/`output` stage
   для фактической проверки и ограниченная интерпретация результата.
3. `file_hints`: metadata и C2PA hints; `affects_pixel_evidence` всегда `false`.
4. `verification_handoff`: следующий официальный или ручной шаг проверки.

Наличие/отсутствие EXIF, XMP, generator fields или C2PA не меняет
`pixel_evidence.status`.

## SynthID handoff

Если SynthID не проверялся, приложение должно показать handoff
`official_gemini`. Пользователь загружает один файл в Gemini и просит проверить,
был ли он создан или изменен Google AI. Результат `not_detected` относится только
к Google AI/SynthID и не исключает другие AI-системы. Google также допускает
неопределенный результат для слишком простого изображения или слишком малого
изменения.

Официальные источники:

- [Gemini Apps Help: verification flow and result limits](https://support.google.com/gemini/answer/16722517?hl=en)
- [Google DeepMind: SynthID overview](https://deepmind.google/models/synthid/)

Для неизвестной пиксельной метки используется `manual_review`, пока конкретный
внешний detector не прошел отдельный quality gate.

## Безопасный лог

`format_pixel_watermark_status()` выводит только allowlisted статусы. Пути,
provider responses, metadata values, prompts, API keys и произвольные сообщения в
лог не включаются. Строка всегда заканчивается формулировкой
`удаление=не заявлено`.
