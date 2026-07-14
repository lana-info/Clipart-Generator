# База знаний проекта Clipart Generator

_Последнее обновление: 2026-05-07_

## Кратко

Clipart Generator — это настольное приложение для генерации и последующей обработки изображений/клипарта. Основной код живёт в `main.py`, интерфейс собран на PyQt6, а работа с изображениями завязана на KIE API и локальные файлы пользователя.

## Назначение проекта

- Генерация изображений по промптам.
- Обработка и постобработка локальных файлов.
- Поддержка сценариев с загрузкой референсов, апскейлом, удалением фона и экспортом результатов.
- Поставка Windows-сборки и обновлений через отдельный public repo `Clipart-Generator-Updates`.

## Текущая схема репозиториев

1. Этот репозиторий хранит исходный код, сборку и внутренние инструкции.
2. Репозиторий `Clipart-Generator-Updates` хранит только `version.json` и готовые release-артефакты для автообновления.

## Основные файлы

- [`main.py`](./main.py) - главное приложение, GUI и бизнес-логика.
- [`build.ps1`](./build.ps1) - локальная сборка через PyInstaller.
- [`update_version.ps1`](./update_version.ps1) - генерация `version.json` с `download_url` и `sha256`.
- [`scripts/refresh_updates_repo.ps1`](./scripts/refresh_updates_repo.ps1) - синхронизация release-артефактов в `_updates_repo_tmp`.
- [`version.json`](./version.json) - публичный манифест для автообновления.
- [`release/VERSION.txt`](./release/VERSION.txt) - текущая версия релиза.
- [`license_server.py`](./license_server.py), [`license_client.py`](./license_client.py), [`license_admin.py`](./license_admin.py) - лицензирование.
- [`PROGRESS.md`](./PROGRESS.md) - история выполненных изменений.
- [`RELEASE_PROCESS.md`](./RELEASE_PROCESS.md) - процесс выпуска.
- [`TEST_CHECKLIST.md`](./TEST_CHECKLIST.md) - ручной чеклист перед релизом.

## Архитектура приложения

- UI написан на PyQt6.
- Основная рабочая логика вынесена в `WorkerThread`.
- В `main.py` есть отдельные режимы генерации и обработки файлов.
- Для апдейтов используется `UPDATE_MANIFEST_URL` на GitHub raw content.
- Пользовательские данные хранятся вне репозитория в `%LOCALAPPDATA%\Clipart Generator`.

## Пользовательские данные

Приложение использует отдельную папку данных:

- `config.json` - настройки приложения.
- `prompts.json` - сохранённые промпты.
- `license_cache.json` - кэш лицензии.

Это важно: при проверке багов не искать эти файлы внутри репозитория, они лежат в пользовательском профиле.

## Поддерживаемые сценарии

- Text-to-image.
- Image-to-image.
- Edit.
- Загрузка референсов.
- Независимый апскейл до и после удаления фона с отображением общей кратности.
- Удаление фона.
- PhotoRoom Standard как отдельный платный провайдер удаления фона с собственным API key.
- Экспорт готовых файлов.

## Актуальные модели в меню

Сейчас в приложении оставлены только выбранные модели:

| Модель | Режим | Примечание |
| --- | --- | --- |
| `gpt-image/1.5-text-to-image` | text-to-image | Базовая текстовая генерация |
| `gpt-image/1.5-image-to-image` | image-to-image | Базовая генерация по референсу |
| `gpt-image-2` | text-to-image, image-to-image | Поддерживает `aspect_ratio`, `resolution` |
| `nano-banana-2` | text-to-image, image-to-image | Поддерживает `aspect_ratio`, `resolution`, `image_input` |
| `nano-banana-pro` | text-to-image, image-to-image | Поддерживает `aspect_ratio`, `resolution`, `image_input` |
| `qwen-image-2` | text-to-image, edit/reference | Поддерживает `image_size`, `output_format`, `nsfw_checker` |
| `flux-2/flex-text-to-image` | text-to-image | `aspect_ratio` + `resolution` |
| `flux-2/pro-text-to-image` | text-to-image | `aspect_ratio` + `resolution` |
| `flux-2/flex-image-to-image` | image-to-image | `aspect_ratio` + `resolution` |
| `flux-2/pro-image-to-image` | image-to-image | `aspect_ratio` + `resolution` |

Остальные модели оставлены в коде, но скрыты из меню выбора.

## Таблица параметров и цен

Ниже сводка по текущим страницам Kie.ai. Где на странице показан только долларовый эквивалент, в таблице также указан кредитный эквивалент по сетке Kie.

| Модель | Ввод | Доступные пропорции / размеры | Цена |
| --- | --- | --- | --- |
| `gpt-image/1.5-text-to-image` | только текст | `1:1`, `2:3`, `3:2`; `quality`: `medium`, `high` | `4` credits (`$0.02`) medium; `22` credits (`$0.11`) high; эффективная цена после топ-апов: около `$0.018` / `$0.10` |
| `gpt-image/1.5-image-to-image` | текст + референс | `1:1`, `2:3`, `3:2`; `quality`: `medium`, `high` | `4` credits (`$0.02`) medium; `22` credits (`$0.11`) high; эффективная цена после топ-апов: около `$0.018` / `$0.10` |
| `gpt-image-2` | текст + референс | `aspect_ratio`: `auto`, `1:1`, `9:16`, `16:9`, `4:3`, `3:4`; `resolution`: `1K`, `2K`, `4K`; важно: `auto` и `1:1` ограничивают доступные режимы 4K | `6` credits (`$0.03`) 1K; `10` credits (`$0.05`) 2K; `16` credits (`$0.08`) 4K; после топ-апов около `$0.015` / `$0.025` / `$0.040` |
| `nano-banana-2` | текст + референс | `aspect_ratio`: `1:1`, `1:4`, `1:8`, `2:3`, `3:2`, `3:4`, `4:1`, `4:3`, `4:5`, `5:4`, `8:1`, `9:16`, `16:9`, `21:9`, `auto`; `resolution`: `1K`, `2K`, `4K`; `output_format`: `JPG`, `PNG` | `8` credits (`$0.04`) 1K; `12` credits (`$0.06`) 2K; `18` credits (`$0.09`) 4K; после топ-апов около `$0.036` / `$0.054` / `$0.081` |
| `nano-banana-pro` | текст + референс | `aspect_ratio`: `auto`, `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`; `resolution`: `1K`, `2K`, `4K`; `output_format`: `PNG`, `JPG` | `18` credits (`$0.09`) 1K/2K; `24` credits (`$0.12`) 4K; после топ-апов около `$0.082` / `$0.11` |
| `qwen-image-2` | текст + референс | `image_size`: `1:1`, `4:3`, `3:4`, `16:9`, `9:16`; `output_format`: `png`, `jpeg`; `seed`; `nsfw_checker` | около `6` credits (`$0.03`) за изображение; после топ-апов около `$0.027` |
| `flux-2/flex-text-to-image` | только текст | `aspect_ratio`: `1:1`, `4:3`, `3:4`, `16:9`, `9:16`, `3:2`, `2:3`, `auto`; `resolution`: `1K`, `2K` | `14` credits (`$0.07`) 1K; `24` credits (`$0.12`) 2K; после топ-апов около `$0.063` / `$0.108` |
| `flux-2/pro-text-to-image` | только текст | `aspect_ratio`: `1:1`, `4:3`, `3:4`, `16:9`, `9:16`, `3:2`, `2:3`, `auto`; `resolution`: `1K`, `2K` | `5` credits (`$0.025`) 1K; `7` credits (`$0.035`) 2K; после топ-апов около `$0.0225` / `$0.0315` |
| `flux-2/flex-image-to-image` | текст + референс | `aspect_ratio`: `1:1`, `4:3`, `3:4`, `16:9`, `9:16`, `3:2`, `2:3`, `auto`; `resolution`: `1K`, `2K` | `14` credits (`$0.07`) 1K; `24` credits (`$0.12`) 2K; после топ-апов около `$0.063` / `$0.11` |
| `flux-2/pro-image-to-image` | текст + референс | `aspect_ratio`: `1:1`, `4:3`, `3:4`, `16:9`, `9:16`, `3:2`, `2:3`, `auto`; `resolution`: `1K`, `2K` | `5` credits (`$0.025`) 1K; `7` credits (`$0.035`) 2K; после топ-апов около `$0.023` / `$0.032` |

## Модельные ограничения

В коде есть документированные ограничения для некоторых моделей, например для `gpt-image/1.5-text-to-image` и `gpt-image/1.5-image-to-image`:

- `aspect_ratio`: `1:1`, `2:3`, `3:2`
- `quality`: `medium`, `high`

Для новых моделей в документации и коде зафиксированы такие диапазоны:

- `gpt-image-2`: `aspect_ratio` = `auto`, `1:1`, `4:3`, `3:4`, `9:16`, `16:9`; `resolution` = `1K`, `2K`, `4K`
- `nano-banana-2`: `aspect_ratio` = `auto`, `1:1`, `1:4`, `1:8`, `2:3`, `3:2`, `3:4`, `4:1`, `4:3`, `4:5`, `5:4`, `8:1`, `9:16`, `16:9`, `21:9`; `resolution` = `1K`, `2K`, `4K`
- `nano-banana-pro`: `aspect_ratio` = `auto`, `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`; `resolution` = `1K`, `2K`, `4K`
- `qwen-image-2`: `image_size` = `1:1`, `4:3`, `3:4`, `16:9`, `9:16`

Также в коде есть список поддерживаемых модельных ID и shortlist референс-моделей. При добавлении новых моделей это нужно сверять с кодом и документацией API, а не угадывать.

## Сборка

Локальная сборка идёт через:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -AppVersion 1.0.0
```

Что делает скрипт:

- ставит зависимости из `requirements.txt` и `requirements-dev.txt`;
- очищает `build/` и `dist/`;
- собирает приложение через PyInstaller;
- пишет `release/VERSION.txt`.

## Обновления

`update_version.ps1`:

- берёт версию из аргумента;
- считает `sha256` для setup-файла, если он уже существует;
- пишет `version.json` с `latest_version`, `download_url`, `sha256`.

`scripts/refresh_updates_repo.ps1`:

- обновляет `version.json`;
- запускает workflow `release-multi-platform.yml`;
- скачивает Windows setup и macOS zip-артефакты;
- копирует их в `_updates_repo_tmp`.

## Release-процесс

Ключевая идея:

1. Собрать релиз.
2. Обновить `version.json`.
3. Залить артефакты в GitHub Release.
4. Синхронизировать public update repo.

Для проверки релиза важны:

- `version.json` и GitHub Release должны совпадать по `download_url` и `sha256`;
- `download_url` для Windows-апдейта должен вести на публичный asset в `Clipart-Generator-Updates`, а не на приватный `Clipart-Generator`, иначе приложение получит `404` при скачивании без авторизации;
- в public update repo не должно быть лишних файлов;
- автообновление должно видеть новый `version.json`.

## Лицензирование

В проекте есть отдельный локальный сервер лицензий и клиентская часть. Судя по документации, сервер можно поднимать локально, а ключи генерировать через `license_admin.py`.

При правках лицензирования важно не ломать:

- хранение ключа;
- проверку активации;
- поведение UI с блокировкой/разблокировкой поля ключа.

## Проверка и тестирование

Базовый минимум перед выдачей:

- запуск приложения без ошибок;
- проверка выбора рабочей папки;
- проверка сценария генерации;
- проверка остановки генерации;
- проверка режима обработки файлов;
- проверка сохранения настроек;
- smoke-тест импорта и базовой инициализации.

См. также [`TEST_CHECKLIST.md`](./TEST_CHECKLIST.md).

## Границы изменений

- Не трогать user data внутри `%LOCALAPPDATA%` без явной причины.
- Не добавлять новые зависимости без пользы.
- Не раздувать регенерацию изображений, если задача про минимальную правку.
- Не путать основной репозиторий с `Clipart-Generator-Updates`.

## Где смотреть при следующих задачах

- Логика приложения: [`main.py`](./main.py)
- Сборка: [`build.ps1`](./build.ps1)
- Версионирование: [`update_version.ps1`](./update_version.ps1), [`version.json`](./version.json)
- Обновления: [`scripts/refresh_updates_repo.ps1`](./scripts/refresh_updates_repo.ps1)
- Процесс релиза: [`RELEASE_PROCESS.md`](./RELEASE_PROCESS.md)
- Чеклист: [`TEST_CHECKLIST.md`](./TEST_CHECKLIST.md)

## Что стоит добавить потом

- Схему экранов и режимов интерфейса.
- Таблицу ошибок и типовых причин падений.
- Краткий FAQ по лицензиям и обновлениям.
- Примеры типовых рабочих сценариев для поддержки.
