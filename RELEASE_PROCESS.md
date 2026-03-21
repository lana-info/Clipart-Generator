## Процесс выпуска версии

В проекте используется двойная схема: **Clipart-Generator** хранит код и собирает артефакты, **Clipart-Generator-Updates** публикует только `version.json` и `ClipartGenerator-Setup-*.exe` для автообновления. Эти шаги можно выполнять вручную или запускать скрипты.

### Шаг 1. Собрать релиз в `Clipart-Generator`
1. Убедитесь, что все изменения закоммичены в `main`. Обновите `version.json` через `update_version.ps1`: `powershell -ExecutionPolicy Bypass -File .\update_version.ps1 -AppVersion 0.25`.
2. Запустите GitHub Action `Release Multi Platform` ( `.github/workflows/release-multi-platform.yml` ) с нужным `app_version` (например `0.25`). Он соберёт и выдаст Windows setup и macOS ZIP как артефакты.
3. После успешного выполнения скачайте из артефактов `ClipartGenerator-Setup-0.25.exe` и `ClipartGenerator-macOS-0.25.zip`, и разместите их в `release/`.

### Шаг 2. Подготовка GitHub Release
1. Создайте release на GitHub с тегом `v0.25`.
2. Загрузите Windows setup и macOS zip как assets.
3. Скопируйте `version.json` и все артефакты локально в `_updates_repo_tmp`.

### Шаг 3. Обновление репозитория `Clipart-Generator-Updates`
1. Перейдите в папку `_updates_repo_tmp` (клонированный публичный репозиторий).
2. Запустите скрипт `scripts/refresh_updates_repo.ps1` из приватного репозитория: `powershell -ExecutionPolicy Bypass -File .\scripts\refresh_updates_repo.ps1 -PrivateRepoPath ".." -UpdatesRepoPath "..\Clipart-Generator-Updates" -SetupName "ClipartGenerator-Setup-0.25.exe"`.
3. Скрипт очистит публичное репо, оставит только `version.json` и `.exe`, затем сделает `git commit` и `git push` туда.

### Шаг 4. Финальный чек
1. Убедитесь, что GitHub release содержит только нужные assets (удалите лишнее).
2. Проверьте, что `Clipart-Generator-Updates` (в GitHub) показывает `version.json` и `.exe` и что ссылка соответствует новой версии (0.25).
3. Протестируйте автообновление в приложении: запустите и убедитесь, что `version.json` скачивается без ошибок.

Если нужен автоматический скрипт (PowerShell или .cmd), можно взять вышеописанный `scripts/refresh_updates_repo.ps1` как основу, добавить флаг `-DryRun`, логирование и запуск сборки до копирования.