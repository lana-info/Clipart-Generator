# Матрица очистки метаданных и маркеров

Дата проверки источников: 2026-07-13.

## Назначение

Этот документ фиксирует реализованный контракт metadata/C2PA cleanup и границы будущих экспериментов. Основное правило: файловые метаданные можно инспектировать и выборочно удалять. Пиксельные сигналы можно пытаться разрушить полной перегенерацией изображения, но такой режим должен быть отдельным и экспериментальным: он меняет все пиксели и не равен metadata cleanup.

Статусы:

- `INSPECT`: можно локально обнаружить и показать без изменения файла;
- `REMOVE`: можно удалить конкретную файловую структуру из нового экспортируемого файла;
- `DETECT/REPORT`: можно только проверить или сообщить, часто через внешний официальный сервис;
- `EXPERIMENTAL REGENERATE`: можно перегенерировать пиксели всего изображения и затем проверить результат, но нельзя обещать точечное или гарантированное удаление;
- `UNSUPPORTED`: надежного общего метода нет, функцию в приложение не добавляем.

## Поддерживаемые форматы

| Область | Решение для первой версии |
|---|---|
| Вход | Обычные однокадровые `PNG` и `JPEG`. Формат определяется по содержимому, а не только по расширению. |
| Выход | Новый `PNG`; исходный файл никогда не перезаписывается. Пиксели, размеры и alpha не меняются при metadata-only очистке. |
| C2PA detection | `PNG` и `JPEG`: спецификация определяет `caBX` для PNG и `APP11` для JPEG. |
| Не поддерживаем | APNG/анимации, HEIC/HEIF, TIFF, PSD, SVG, WebP и произвольные контейнеры до отдельных тестов и ТЗ. |

Источники: [Pillow: image formats](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html), [PNG Third Edition](https://www.w3.org/TR/png-3/), [C2PA 2.4: embedding manifests](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html#_embedding_manifests_into_non_bmff_based_assets).

## Реализованный контракт Tasks 24-30

- В UI доступны независимые действия: `Удалить EXIF`, `Удалить XMP`, `Удалить IPTC`, `Удалить комментарии/текст`, `Удалить встроенную миниатюру`, `Удалить данные генератора`, `Удалить встроенный C2PA`.
- `Сохранить ICC-профиль` и `Сохранить DPI` включены по умолчанию. Включённый `Экспорт для печати (300 DPI)` имеет приоритет и задаёт итоговые 300 DPI.
- Очистку можно запускать как единственное действие в process-only без KIE API key. Generate-only, generate-and-process, process-only, local и mixed workflows используют один final-save путь.
- Порядок финала: выбранные пиксельные действия -> `Trim` -> read-only inspection -> выбранная очистка -> повторная проверка -> атомарная публикация в `output/`.
- Исходник и файлы в `raw/` не изменяются. Ошибка очистки не публикует новый частичный результат и не заменяет существующий итог.
- Metadata-only стадия сохраняет размеры, декодированные пиксели и alpha относительно входа этой стадии. Апскейл, Unsharp Mask, удаление фона, edge shrink и Trim могут намеренно изменить изображение до неё.
- Поддерживаемые входные режимы metadata-only core: `1`, `L`, `LA`, `P`, `RGB`, `RGBA`, `I;16`. Лимиты: до 512 MiB, до 70 000 000 пикселей и до 32 768 px по одной стороне.
- PNG/JPEG metadata ограничены 64 MiB на контейнерный scan; один PNG metadata chunk ограничен 16 MiB. Число PNG chunks или JPEG segments ограничено 100 000.
- Невыбранные EXIF/XMP/comments/thumbnail/known-generator данные сохраняются, если не удаляется содержащая их категория и новый PNG может представить их безопасно. Binary IPTC IIM из JPEG не обещается к сохранению в PNG и явно отмечается как unsupported, если его удаление не выбрано.
- Значения metadata, prompts, API keys и secrets в обычный лог не выводятся: только безопасные названия категорий и итог действия.
- Все удаления выключены для старых config-файлов; при полностью выключенной очистке inspection не запускается и используется прежнее поведение финального writer.

## Матрица возможностей

| Категория | Что ищем | Статус | Действие / подпись в UI | Ограничения | Источник |
|---|---|---|---|---|---|
| Обычные метаданные | EXIF, включая GPS и встроенную миниатюру | `INSPECT` + `REMOVE` | `Удалить EXIF` | Для PNG и JPEG. Удаление выполняется только в новом файле. | [Pillow: JPEG/PNG EXIF](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html), [PNG eXIf](https://www.w3.org/TR/png-3/#11eXIf) |
| Обычные метаданные | XMP | `INSPECT` + `REMOVE` | `Удалить XMP` | Показывать наличие, размер и безопасно разобранные поля. Не выполнять XML как код. | [Pillow `getxmp()`](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.getxmp), [IPTC/XMP formats](https://iptc.org/standards/photo-metadata/iptc-standard/) |
| Обычные метаданные | IPTC IIM и IPTC-поля внутри XMP | `INSPECT` + `REMOVE` | `Удалить IPTC` | Binary IIM актуален прежде всего для JPEG; IPTC в XMP очищается вместе с выбранной XMP-категорией. | [IPTC Photo Metadata Standard 2025.1](https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2025.1.html) |
| Обычные метаданные | PNG `tEXt`/`zTXt`/`iTXt`, JPEG comments | `INSPECT` + `REMOVE` | `Удалить комментарии и текстовые данные` | Значения считаются недоверенными; в лог выводятся категории и размеры, а не полное содержимое. | [PNG text chunks](https://www.w3.org/TR/png-3/#11textinfo), [Pillow JPEG comment/PNG text](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html) |
| Экспортные данные | ICC color profile | `INSPECT`; preserve by default | `Сохранить ICC-профиль` | Не считать мусором. Удалять только отдельным явным выбором пользователя. | [Pillow PNG/JPEG `icc_profile`](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html) |
| Экспортные данные | DPI/pHYs/JFIF density | `INSPECT`; preserve by default | `Сохранить DPI` | Не считать маркером нейросети. При экспорте 300 DPI итоговое значение задает существующая настройка приложения. | [Pillow PNG/JPEG DPI](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html) |
| AI/service metadata | Известные названия генератора, модели или редактора в EXIF/XMP/PNG text | `INSPECT` + `REMOVE` | `Удалить данные генератора` | Работает как проверяемый allowlist поверх обычных метаданных. Неизвестное поле нельзя автоматически объявлять AI-маркером. | [Google: metadata отличается от pixel watermark](https://support.google.com/gemini/answer/16722517), [IPTC metadata fields](https://iptc.org/standards/photo-metadata/iptc-standard/) |
| Provenance | Встроенный C2PA/Content Credentials manifest | `INSPECT` + ограниченный `REMOVE` | `Удалить встроенный C2PA` | Инспектор показывает наличие и `not_validated`; проверка подписи не выполняется. Удаление локальных байтов не означает удаления удаленной записи или всех Content Credentials. | [C2PA 2.4](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html), [C2PA FAQ](https://c2pa.org/faqs/), [c2patool usage](https://opensource.contentauthenticity.org/docs/c2patool/docs/usage/) |
| Provenance | Remote/sidecar C2PA manifest reference | `INSPECT` + ограниченный `REMOVE` | Та же галочка `Удалить встроенный C2PA` удаляет только поддерживаемую ссылку из нового PNG | Remote manifest, sidecar и копии у третьих сторон не удаляются и не запрашиваются по сети. | [c2patool external/remote manifests](https://opensource.contentauthenticity.org/docs/c2patool/docs/usage/#generating-a-remote-manifest), [Adobe: deletion limits](https://helpx.adobe.com/creative-cloud/apps/adobe-content-authenticity/content-credentials/manage-content-credentials.html) |
| Pixel-level watermark | Google SynthID в Nano Banana/Gemini images | `DETECT/REPORT` + `EXPERIMENTAL REGENERATE` | `Проверить SynthID через Gemini`; отдельно `Перегенерировать изображение (экспериментально)` | Все изображения Nano Banana API содержат SynthID. Официальная проверка доступна через Gemini, но отсутствие результата не доказывает отсутствие AI. Экспериментальная перегенерация меняет все пиксели и требует повторной внешней проверки. | [Gemini image generation](https://ai.google.dev/gemini-api/docs/image-generation), [Google SynthID](https://deepmind.google/models/synthid/), [Gemini verification](https://support.google.com/gemini/answer/16722517) |
| Pixel-level watermark | Неизвестные невидимые watermark/fingerprint/steganography | `UNSUPPORTED` для гарантированного удаления; `EXPERIMENTAL REGENERATE` без гарантии | Только общий экспериментальный режим перегенерации | Нет универсального надежного детектора или метода удаления. C2PA soft bindings могут переживать удаление manifest и обычные преобразования. | [C2PA soft bindings](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html#_soft_bindings), [C2PA FAQ](https://c2pa.org/faqs/) |
| Видимая метка | Логотип/значок в пикселях | `PROTOTYPE ONLY` | Интеграция только после go/no-go Task 34 | Не путать с SynthID. Автоматическое универсальное удаление не обещать; тестировать только на собственных или лицензированных изображениях. | [Google: visible watermark experiment and invisible SynthID](https://blog.google/products-and-platforms/products/gemini/image-editing/) |

`REMOVE` для C2PA подтверждён bounded PNG/JPEG fixtures Tasks 25, 27 и 30 только для локальных `caBX`/APP11 JUMBF structures и поддерживаемых XMP references в новом PNG. Это не означает удаление remote manifest, sidecar, подписи у третьей стороны или pixel-level soft binding.

## Оценка готовых кандидатов

| Кандидат | Что реально даёт | Решение |
|---|---|---|
| [`lana-info/remove-ai-watermarks`](https://github.com/lana-info/remove-ai-watermarks) | Apache-2.0 код для metadata/C2PA, локализации известных видимых меток и inpainting; отдельный тяжёлый режим полной diffusion-перегенерации через SDXL/ControlNet/Qwen | Использовать как референс и кандидат для прототипа, не копировать целиком в основной процесс. Проверить отдельно visible, metadata и invisible режимы. Учесть лицензии загружаемых моделей и обязательную атрибуцию Apache-2.0. |
| KIE | В документации есть масочное редактирование через 4o Image и image-to-image через GPT Image 2, FLUX Kontext/FLUX.2; отдельного документированного удалителя скрытых image-watermark не найдено. KIE предлагает специализированный remover только для Sora 2 video. | Проверить как облачный fallback для видимой метки и полной перегенерации. Не считать результат очищенным от скрытой метки без отдельной проверки. |
| OpenRouter | Унифицированный Image API поддерживает image-to-image/reference editing для доступных image models; отдельной подтверждённой операции удаления скрытого watermark нет. | Проверить только в сравнительном прототипе. Не использовать Google/Nano Banana как remover SynthID: новый Google output сам получает SynthID. |

Источники: [лицензия remove-ai-watermarks](https://github.com/lana-info/remove-ai-watermarks/blob/main/LICENSE), [KIE 4o Image mask editing](https://docs.kie.ai/4o-image-api/quickstart), [KIE GPT Image 2 image-to-image](https://docs.kie.ai/market/gpt/gpt-image-2-image-to-image), [KIE FLUX Kontext editing](https://docs.kie.ai/flux-kontext-api/generate-or-edit-image/), [KIE Sora 2 video remover](https://docs.kie.ai/cn/market/sora2/sora-watermark-remover), [OpenRouter Image API](https://openrouter.ai/docs/guides/overview/multimodal/image-generation), [OpenRouter image models](https://openrouter.ai/collections/image-models).

## Принятые продуктовые решения

1. Первая реализация очистки работает только с новым экспортируемым `PNG`; исходник остается неизменным.
2. Галочки независимы: `EXIF`, `XMP`, `IPTC`, `Комментарии/текст`, `Встроенная миниатюра`, `Данные генератора`, `Встроенный C2PA`.
3. `Сохранить ICC-профиль` и `Сохранить DPI` включены по умолчанию и не объединяются с удалением метаданных.
4. Перед очисткой выполняется read-only inspection. После сохранения файл проверяется повторно, а лог сообщает только категории и результат.
5. Для C2PA формулировка ограничивается встроенным manifest/ссылкой. Нельзя писать «полностью удалить Content Credentials».
6. Для SynthID приложение сначала предлагает официальную проверку. Полная перегенерация допускается отдельным экспериментальным режимом для любых принадлежащих пользователю изображений, а не только для клипарта.
7. Неизвестные пиксельные маркеры нельзя объявлять гарантированно удалёнными. Экспериментальная перегенерация сообщает только факт выполнения и результат доступной проверки.
8. Видимые метки остаются отдельным исследовательским этапом и не входят в metadata cleanup.

## Ограничения владения и безопасности

- Очистка разрешена только для собственных изображений пользователя или файлов, лицензия которых явно допускает изменение.
- Приложение не должно удалять чужие авторские логотипы, фотобанковские водяные знаки или помогать обходить проверку происхождения.
- Все новые опции выключены для старых конфигураций, кроме безопасного сохранения ICC и DPI.
- Полное содержимое metadata не попадает в обычный лог: только безопасное название категории и итог действия.
- Сетевой поиск remote manifests или SynthID verification выполняется только после отдельного согласия пользователя.

## Решение для следующих задач

- Tasks 24-30 выполнены: локально инспектируют и выборочно очищают поддерживаемые PNG/JPEG metadata/C2PA только в final save, с проверкой pixels/alpha/ICC/DPI и без сетевого запроса.
- Tasks 31-37: отдельно проверить detector, local inpainting и KIE mask editing для видимых меток; интегрировать только после go/no-go.
- Tasks 38-41: определить status contract и сначала проверить KIE, затем при необходимости OpenRouter.
- Tasks 42-47: запускать local/GPU serverless/VPS gateway только если managed API не проходит quality gate.
- Tasks 48-49: добавить только одобренный режим перегенерации и выполнять повторную инспекцию результата.
