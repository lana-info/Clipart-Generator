# Прогресс

## 2026-03-19

## 2026-03-20

### Цели
- Подготовить копию репозитория обновлений внутри проекта для будущих релизов.

### Что сделано
- `main.py`: убрана зависимость проверки обновлений от статуса лицензии; удалены сообщения о «недоступности обновлений из-за лицензии».
- `main.py`: автопроверка обновлений при старте выполняется в «тихом» режиме (без сообщений, если обновлений нет), но при наличии новой версии показывается диалог с подтверждением.
- Обнаружена проблема кодировок: в `main.py` присутствуют строки вида `"Ð..."`, `"â€..."` (mojibake).
- Реализован PowerShell-скрипт `scripts/refresh_updates_repo.ps1`, который запускает GitHub Action `Release Multi Platform`, дожидается завершения и скачивает Windows и macOS артефакты, копирует их с `version.json` в `_updates_repo_tmp` и подсказывает дальнейшие шаги.
- Обновлена инструкция релиза (`RELEASE_PROCESS.md`), теперь шаг сборки и копирования автоматизирован через новый скрипт и включает запуск workflow.

### Текущее состояние / блокеры
- `main.py` по-прежнему содержит множество mojibake-последовательностей. Автоматическая конвертация требует аккуратной реализации, чтобы не повредить emoji/не-CP1252 символы.

## 2026-03-20

### Цели
- Подготовить копию репозитория обновлений внутри проекта для будущих релизов.

### Что сделано
- Добавлен PowerShell-скрипт `scripts/refresh_updates_repo.ps1`, который очищает `_updates_repo_tmp`, копирует `version.json` и свежий `.exe`, а затем делает commit и push в репозиторий обновлений.
- Запущен скрипт: `_updates_repo_tmp` теперь содержит только нужные артефакты, а репозиторий `Clipart-Generator-Updates` обновлён через `git push`.
- Создана папка `_updates_repo_tmp` и в неё клонирован `Clipart-Generator-Updates`.

- Привести GitHub Release `Clipart-Generator-Updates` в соответствие с актуальным `version.json`: проверить `download_url` и `sha256` на совпадение.
- Поддерживать инструкцию по использованию `scripts/refresh_updates_repo.ps1`, чтобы будущие релизы можно было быстро синхронизировать.

## 2026-03-21

### Цели
- Завершить ревизию интеграции KIE API и убрать недокументированные fallback-схемы в основных сценариях.

### Что сделано
- `main.py`: основной путь генерации уже переведён на единичный документированный payload вместо перебора guess/fallback-полей.
- `main.py`: upload через `file-stream-upload` приоритизирован на `https://kieai.redpandaai.co/api/file-stream-upload`, что соответствует найденной документации KIE по upload API.
- `main.py`: увеличен timeout stream upload до `max(60, self.timeout)` для снижения ложных timeout на загрузке референсов.
- `main.py`: для `gpt-image/1.5-text-to-image` и `gpt-image/1.5-image-to-image` добавены документированные ограничения по `aspect_ratio` (`1:1`, `2:3`, `3:2`) и `quality` (`medium`, `high`).
- `main.py`: probe-проверки для image/edit моделей упрощены — вместо legacy-набора альтернативных payload-схем теперь используется один документированный payload.
- `target_probe.py`: исправлен поиск `config.json` — теперь сначала используется `KIE_API_KEY`, затем пользовательский конфиг из `%LOCALAPPDATA%\Clipart Generator\config.json`, и только потом локальный `config.json` рядом со скриптом.
- Подтверждено по локальной документации:
  - `gpt-image/1.5-text-to-image` — поля `prompt`, `aspect_ratio`, `quality`.
  - `gpt-image/1.5-image-to-image` — поля `input_urls`, `prompt`, `aspect_ratio`, `quality`.
  - `recraft/remove-background` — обязательное поле `image`.
  - upload URL API — `https://kieai.redpandaai.co/api/file-url-upload`, только для публичных `http/https` URL.

### Текущее состояние / блокеры
- Полная документальная верификация по всем моделям KIE ещё не завершена: для ряда моделей в проекте есть только косвенное подтверждение через страницы сайта KIE, без локально сохранённых OpenAPI-схем.
- Основные сценарии после последних правок ещё требуют прогонки реальными запросами: `text-to-image`, `image-to-image`, `remove background`, `upload reference`.

### Дополнение по массовой проверке моделей
- Массовый `target_probe.py` показал, что KIE сейчас принимает задачи для следующих моделей UI: `gpt-image/1.5-*`, `z-image`, `google/imagen4*`, `google/nano-banana*`, `flux-2/*`, `grok-imagine/*`, `qwen/*`.
- `ideogram/character-edit`, `ideogram/character-remix`, `ideogram/character` требовали другие имена полей входа; схема в коде скорректирована по сообщениям API (`image_url`, `reference_image_urls`).
- `black-forest-labs/flux-kontext-pro`, `black-forest-labs/flux-kontext-max`, `seedream`, `seedream-v4-text-to-image`, `4.5-text-to-image`, `google/pro-image-to-image`, `seedream-v4-edit`, `4.5-edit` сейчас возвращают `model not supported` в KIE и должны считаться недоступными для UI до появления подтверждённой схемы/активной поддержки.

### Обновление по документации KIE от 2026-03-22
- `main.py`: `4.5-text-to-image` удалена из списка моделей приложения, а не только скрыта фильтром UI.
- `main.py`: `google/pro-image-to-image` заменена на документированную модель `nano-banana-pro` с подписью `Google Nano Banana Pro`.
- По странице `https://docs.kie.ai/market/google/pro-image-to-image` подтверждено, что это страница `Google - Nano Banana Pro`; в примере запроса используется `model: "nano-banana-pro"`.
- `main.py` и `target_probe.py`: для `nano-banana-pro` выставлен документированный payload через `POST /api/v1/jobs/createTask` с `input = { prompt, image_urls, aspect_ratio }`.
- `main.py` и `target_probe.py`: для `gpt4o-image` удалены guess/fallback payload-варианты; теперь используется один документированный запрос `POST /api/v1/gpt4o-image/generate` с телом `{ prompt, size }`.
- По странице `https://docs.kie.ai/4o-image-api/generate-4-o-image` подтверждено, что для `gpt4o-image` в примере запроса поле `size` передаётся в формате соотношения (`"1:1"`), а не в legacy-формате пикселей (`1024x1024`).
- По решению пользователя все модели `Ideogram` удалены из приложения и из `target_probe.py`, чтобы не тратить дополнительные кредиты на их дальнейшую доводку и тестирование.
- По решению пользователя из приложения и из `target_probe.py` также удалены все модели, которые после повторной проверки стабильно возвращали `422 model not supported`: `black-forest-labs/flux-kontext-pro`, `black-forest-labs/flux-kontext-max`, `seedream`, `seedream-v4-text-to-image`, `seedream-v4-edit`, `4.5-edit`.
