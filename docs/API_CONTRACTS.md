# Реестр API-контрактов Vibix Images

Последняя сверка: **2026-08-26**.

Этот документ отвечает на два вопроса для каждого внешнего сервиса:

1. Что требует официальная документация.
2. Что сейчас отправляет и принимает Vibix Images.

Проверка контрактов выполняется локальными тестами без платных запросов. Живой
запрос допустим только после отдельного решения владельца. Никогда не вставляйте
API-ключи, лицензионные ключи, промпты или подписанные URL в этот документ.

## Общий KIE Market API

| Операция | Текущий вызов | Официальная документация | Диагностика |
|---|---|---|---|
| Загрузка файла | `POST https://kieai.redpandaai.co/api/file-stream-upload`; multipart `file`, `uploadPath` | [Upload File Stream](https://docs.kie.ai/file-upload-api/upload-file-stream/) | `provider_upload_started`, `provider_upload_finished` |
| Создание задачи | `POST https://api.kie.ai/api/v1/jobs/createTask`; JSON `model`, `input` | [Market Quickstart](https://docs.kie.ai/market/quickstart) | `provider_task_submitted`, `provider_task_failed` |
| Состояние задачи | `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...` | [Get Task Details](https://docs.kie.ai/market/common/get-task-detail) | `provider_task_polled`, `provider_task_succeeded`, `provider_task_failed` |
| Баланс | `GET https://api.kie.ai/api/v1/chat/credit` | [Get Account Credits](https://docs.kie.ai/common-api/get-account-credits) | только пользовательский результат проверки баланса |

Авторизация выполняется через `Authorization: Bearer ...`. Ключ, заголовки,
полные ответы, `resultJson` и URL результатов в диагностику не попадают.
Сохраняются только HTTP-статус, `taskId`, `state`, `failCode`, безопасный
`failMsg`, номер опроса, длительность и количество результатов.

## Модели генерации KIE

| Модель в приложении | Поля запроса | Документация и ограничения | Текущее состояние |
|---|---|---|---|
| `gpt-image/1.5-text-to-image` | `prompt`, `aspect_ratio`, `quality` | [GPT Image 1.5](https://kie.ai/gpt-image-1.5); 1:1, 2:3, 3:2; medium/high | Соответствует |
| `gpt-image/1.5-image-to-image` | `input_urls`, `prompt`, `aspect_ratio`, `quality` | [GPT Image 1.5](https://kie.ai/gpt-image-1.5); до 16 JPEG/PNG/WEBP, 10 МБ на файл | Поля соответствуют; интерфейс намеренно ограничен пятью референсами |
| `gpt-image-2` → `gpt-image-2-text-to-image` / `gpt-image-2-image-to-image` | `prompt`, `aspect_ratio`, `resolution`, при необходимости `input_urls` | [GPT Image 2 text](https://docs.kie.ai/market/gpt/gpt-image-2-text-to-image), [GPT Image 2 image](https://docs.kie.ai/market/gpt/gpt-image-2-image-to-image); 1K/2K/4K, расширенный набор пропорций, до 16 референсов по 30 МБ | Соответствует; ограничения пропорций для 2K/4K проверяются локально |
| `nano-banana-2` | `prompt`, `image_input`, `aspect_ratio`, `resolution`, `output_format` | [Nano Banana 2](https://docs.kie.ai/market/google/nanobanana2); до 14 референсов по 30 МБ | Соответствует; интерфейс ограничен пятью референсами |
| `nano-banana-pro` | `prompt`, `image_input`, `aspect_ratio`, `resolution`, `output_format` | [Nano Banana Pro](https://kie.ai/nano-banana-pro); до 8 референсов по 30 МБ | Соответствует; интерфейс ограничен пятью референсами |
| `qwen-image-2` → `qwen2/text-to-image` / `qwen2/image-edit` | `prompt`, `image_size`, `output_format`, при редактировании один строковый `image_url` | [Qwen Image 2 text](https://docs.kie.ai/market/qwen2/text-to-image), [Qwen Image 2 edit](https://docs.kie.ai/market/qwen2/image-edit); text и edit имеют разные пропорции, edit принимает один URL | Соответствует; endpoint, payload, пропорции и один локальный референс до 10 МБ проверяются до загрузки |
| `flux-2/pro-text-to-image`, `flux-2/flex-text-to-image` | `prompt`, `aspect_ratio`, `resolution` | [FLUX.2 Pro](https://docs.kie.ai/market/flux2/pro-text-to-image), [FLUX.2 Flex](https://docs.kie.ai/market/flux2/flex-text-to-image); `auto` не разрешён для text-to-image; промпт 3–5000 символов | Соответствует; `auto` отсутствует, длина проверяется локально |
| `flux-2/pro-image-to-image`, `flux-2/flex-image-to-image` | `prompt`, `input_urls`, `aspect_ratio`, `resolution` | [FLUX.2](https://kie.ai/flux-2); `auto` разрешён; до 8 референсов по 10 МБ | Соответствует; интерфейс ограничен пятью референсами, лимиты проверяются до загрузки |

Для генерации журнал записывает номер промпта, число символов и количество
референсов. Точный текст промпта не записывается.

## Обработка изображений KIE

| Модель | Текущий payload | Официальная документация | Текущее состояние |
|---|---|---|---|
| `topaz/image-upscale` | `image_url`, строковый `upscale_factor` 1/2/4 | [Topaz Image Upscale](https://docs.kie.ai/market/topaz/image-upscale); JPEG/PNG/WEBP, 10 МБ, результат до 20 000 px | Соответствует; проверяется до загрузки |
| `recraft/crisp-upscale` | `image` | [Recraft Crisp Upscale](https://docs.kie.ai/market/recraft/crisp-upscale); JPEG/PNG/WEBP, 10 МБ | Соответствует; недокументированные ограничения размеров не применяются |
| `recraft/remove-background` | `image` | [Recraft Remove Background](https://docs.kie.ai/market/recraft/remove-background); JPEG/PNG/WEBP, 5 МБ, до 16 MP, сторона 256–4096 px | Соответствует; provider-specific проверка выполняется до загрузки |

Недоступность Recraft у провайдера не скрывает модель из интерфейса. Ошибка
показывается с реальным безопасным `failCode`/`failMsg`; автоматической замены
модели и дополнительного платного запроса быть не должно.

## PhotoRoom

| Операция | Текущий вызов | Документация | Состояние |
|---|---|---|---|
| Удаление фона | `POST https://sdk.photoroom.com/v1/segment`; multipart `image_file`, `format=png`, `channels=rgba`, `size=full`, `crop=false`, `despill=false` | [API Reference](https://docs.photoroom.com/api-reference-openapi), [форматы и размеры](https://docs.photoroom.com/remove-background-api-basic-plan/file-size-resolution-and-format) | Соответствует; приложение принимает декодируемое подмножество PNG/JPEG/WEBP и проверяет 50 МБ и сторону 6000 px до запроса. HEIC провайдер поддерживает, но приложение не заявляет без пакетного декодера |
| Баланс/аккаунт | `GET https://image-api.photoroom.com/v2/account` | [PhotoRoom API](https://docs.photoroom.com/api-reference-openapi) | Соответствует |

Диагностика сохраняет HTTP-статус, длительность, размер ответа и параметры
проверенного PNG/RGBA. Бинарный ответ и ключ не сохраняются.

## RunPod Serverless

| Операция | Текущий вызов | Документация | Состояние |
|---|---|---|---|
| Запуск | `POST https://api.runpod.ai/v2/{endpoint_id}/run`; `{"input": ...}` | [Endpoint Operations](https://docs.runpod.io/serverless/endpoints/operation-reference) | Базовый контракт соответствует; схема `input` определяется пользовательским worker endpoint |
| Состояние | `GET https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}` | [Endpoint Operations](https://docs.runpod.io/serverless/endpoints/operation-reference) | Соответствует |

Клиент поддерживает безопасный диагностический callback. Payload worker-а,
API-ключ и endpoint URL в события не копируются.

## Лицензирование и обновления

Базовый URL: `https://services.etsyneuroclub.com/licenses`.

| Назначение | Контракт клиента |
|---|---|
| Активация | `POST /api/v1/licenses/activate` |
| Проверка лицензии | `POST /api/v1/licenses/validate` |
| Получение ключа проверки обновлений | `GET /api/v1/releases/key` |
| Подписанный манифест | `POST /api/v1/releases/manifest` |
| Частное скачивание | `GET /downloads/{token}` |

Контракт сверяется с соседним репозиторием `license-service/API_CONTRACT.md`.
Клиент проверяет подпись, nonce, продукт, устройство, срок, размер и SHA-256.
Старый GitHub `version.json` остаётся неактивным compatibility-кодом.

Административная панель использует логин `admin` и пароль. TOTP-код является
дополнительным вторым фактором; публичной регистрации и сброса привязки
пользователем нет.

## Устранённые расхождения — 2026-08-26

1. Обычный запуск больше не создаёт тестовую KIE-задачу. Живой тест модели
   остаётся только отдельным явным действием пользователя.
2. GPT Image 2 поддерживает документированные пропорции и условные ограничения
   разрешений 2K/4K.
3. Qwen Image 2 использует точные endpoint `qwen2/text-to-image` и
   `qwen2/image-edit`, разные пропорции и один строковый `image_url`.
4. FLUX.2 text-to-image не предлагает `auto` и проверяет 3–5000 символов.
5. Количество и размер локальных референсов проверяются по выбранной модели до
   загрузки провайдеру.
6. Recraft Crisp принимает документированный предел 10 МБ без исторических
   ограничений по пикселям или сторонам.
7. Recraft Remove Background и PhotoRoom получили предварительную проверку
   формата, размера файла и геометрии изображения.

Для ссылочных референсов приложение может проверить количество, но не скачивает
файл только ради определения его размера. Ограничение размера такого URL
окончательно контролирует провайдер.

## Как обновлять реестр

При изменении модели или API одновременно:

1. открыть официальную ссылку и записать дату сверки;
2. обновить model/endpoint/payload и ограничения в коде;
3. добавить или изменить локальный contract test;
4. проверить диагностические события успеха и ошибки;
5. выполнить полный offline-набор тестов;
6. не выполнять платный запрос без отдельного разрешения владельца.
