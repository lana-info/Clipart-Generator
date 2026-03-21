## Процесс выпуска версии

В проекте используется двойная схема: **Clipart-Generator** хранит код и собирает артефакты, **Clipart-Generator-Updates** публикует только `version.json` и `ClipartGenerator-Setup-*.exe` для автообновления. Эти шаги можно выполнять вручную или запускать скрипты.

### Шаг 1. Собрать релиз в `Clipart-Generator`
1. Убедитесь, что все изменения закоммичены в `main`. Скрипт `scripts/refresh_updates_repo.ps1` находит проект по пути `D:\Projects\Clipart Generator`, вызывает `Release Multi Platform`, обновляет `version.json`, скачивает готовые `.exe` и `.zip` и копирует артефакты в `_updates_repo_tmp`.
2. Запустите `powershell -ExecutionPolicy Bypass -File .\scripts\refresh_updates_repo.ps1 -PrivateRepoPath .. -UpdatesRepoPath ..\Clipart-Generator-Updates` внутри `D:\Projects\Clipart Generator`, при необходимости добавьте `-AppVersion <версия>` (по умолчанию берётся из `release/VERSION.txt`). Скрипт сам ждёт GitHub Action, скачивает артефакты и копирует их.
    - Пример пошагового запуска:
      1. Откройте PowerShell.
      2. Введите `cd "D:\Projects\Clipart Generator"` и нажмите Enter.
      3. Выполните команду `powershell -ExecutionPolicy Bypass -File .\scripts\refresh_updates_repo.ps1 -PrivateRepoPath .. -UpdatesRepoPath ..\Clipart-Generator-Updates` (при необходимости добавьте `-AppVersion 0.25`).
      4. Дождитесь, пока скрипт напишет "Готово" и подскажет, какие действия сделать дальше.
        - Если вам нужно только скачать уже созданные артефакты, добавьте `-Mode copy` и укажите `-AppVersion`, чтобы команда загрузила `.exe` и `.zip` без повторной сборки.
        - Если сборка уже выполнена локально и файлы лежат в `release/`, используйте `-Mode post-build` (в этом режиме скрипт пропускает workflow/загрузку и просто копирует файлы).

### Шаг 2. Подготовка GitHub Release
1. Создайте release на GitHub с тегом `v0.25`.
2. Загрузите Windows setup и macOS zip как assets.

### Шаг 3. Обновление репозитория `Clipart-Generator-Updates`
1. Перейдите в папку `_updates_repo_tmp` (клонированный публичный репозиторий).
2. Запустите скрипт `scripts/refresh_updates_repo.ps1` из приватного репозитория: `powershell -ExecutionPolicy Bypass -File .\scripts\refresh_updates_repo.ps1 -PrivateRepoPath ".." -UpdatesRepoPath "..\Clipart-Generator-Updates" [-AppVersion <версия>]`.
   - Скрипт:
     1. Обновляет `version.json` через `update_version.ps1`.
     2. Запускает GitHub Action `Release Multi Platform` и ждёт завершения сборки macOS и Windows.
     3. Скачивает артефакты `.exe` и `.zip` из GitHub Release.
     4. Копирует `version.json`, Windows setup и macOS zip в `_updates_repo_tmp`.
     5. Выдаёт рекомендации: `git status`, добавление файлов, коммит/пуш и обновление релиза в `Clipart-Generator-Updates`.
3. Сделайте `git commit` и `git push` в `Clipart-Generator-Updates`.

### Шаг 4. Финальный чек
1. Убедитесь, что GitHub release содержит только нужные assets (удалите лишнее).
2. Проверьте, что `Clipart-Generator-Updates` (в GitHub) показывает `version.json` и `.exe` и что ссылка соответствует новой версии (0.25).
3. Протестируйте автообновление в приложении: запустите и убедитесь, что `version.json` скачивается без ошибок.

Если нужен автоматический скрипт (PowerShell или .cmd), можно взять вышеописанный `scripts/refresh_updates_repo.ps1` как основу, добавить флаг `-DryRun`, логирование и запуск сборки до копирования.