## Процесс выпуска версии

В проекте используется двойная схема: **Clipart-Generator** хранит код и собирает артефакты, **Clipart-Generator-Updates** публикует только `version.json` и `ClipartGenerator-Setup-*.exe` для автообновления. Эти шаги можно выполнять вручную или запускать скрипты.

### Шаг 1. Собрать релиз в `Clipart-Generator`
1. Убедитесь, что все изменения закоммичены в `main`. Скрипт `scripts/refresh_updates_repo.ps1` теперь вызывает `Release Multi Platform`, обновляет `version.json`, скачивает готовые `.exe` и `.zip` и копирует артефакты в `_updates_repo_tmp`.
2. Запустите `powershell -ExecutionPolicy Bypass -File .\scripts\refresh_updates_repo.ps1 -PrivateRepoPath .. -UpdatesRepoPath ..\Clipart-Generator-Updates` и передайте `-AppVersion` если нужен конкретный тег (по умолчанию берётся из `release/VERSION.txt`). Скрипт сам ждёт GitHub Action, скачивает артефакты и копирует их.

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