# Клиентская поставка Vibix Images 3.0

## Что получает пользователь

Проверенный Windows installer `VibixImages-Setup-3.0.exe` и один macOS ZIP с arm64 `.app` версии 3.0, необходимыми runtime-компонентами, моделями и лицензиями. Пакеты должны работать без Git, Python, исходников проекта и ручной подготовки папок.

## Что не входит

Не входят `output`, `cache`, `logs`, временные изображения, тестовые данные, `scratch`, служебные документы разработки, git-метаданные, `.env` с секретами и файлы старых релизов.

## Текущее состояние

macOS-поставка поддерживает только Apple Silicon (M1, M2, M3, M4 и новее). Intel Mac не поддерживается в 3.0. `version.json` описывает опубликованный 2.0 update-канал.

Версия 3.0 распространяется вручную через закрытый клиентский чат. Автоматическое обновление отключено. Приватный Release `v3.0.0` в `lana-info/Clipart-Generator` используется как официальный внутренний архив релиза; публичный updates-репозиторий не используется.

Windows installer устанавливается поверх версии 2.0; подтверждено, что пользовательские настройки и пользовательские данные сохраняются.

Публичный репозиторий `Clipart-Generator-Updates`, `version.json` версии 2.0 и существующие публичные релизы не изменяются.
## Verified delivery scope

- Windows x64 installer: manually verified, including upgrade and Processing.
- macOS Apple Silicon arm64 ZIP: build and packaging verified; real Mac GUI smoke pending.
- Intel Mac is unsupported.
- macOS package is unsigned and not notarized.
- RunPod SynthID and automatic updates are deferred.
