# Клиентская поставка Vibix Images 3.0

## Что получает пользователь

Проверенный Windows installer `VibixImages-Setup-3.0.exe`. macOS Apple
Silicon package остаётся experimental/internal: real Mac GUI smoke, signing и
notarization не завершены, поэтому macOS не считается поддержанной публичной
поставкой 3.0.

## Что не входит

Не входят `output`, `cache`, `logs`, временные изображения, тестовые данные, `scratch`, служебные документы разработки, git-метаданные, `.env` с секретами и файлы старых релизов.

## Текущее состояние

macOS-поставка поддерживает только Apple Silicon (M1, M2, M3, M4 и новее). Intel Mac не поддерживается в 3.0. `version.json` описывает опубликованный 2.0 update-канал.

Версия 3.0 распространяется вручную через закрытый клиентский чат. Автоматическое обновление отключено. Приватный Release `v3.0.0` в `lana-info/Clipart-Generator` используется как официальный внутренний архив релиза; публичный updates-репозиторий не используется.

Windows installer устанавливается поверх версии 2.0; подтверждено, что пользовательские настройки и пользовательские данные сохраняются.

Публичный репозиторий `Clipart-Generator-Updates`, `version.json` версии 2.0 и существующие публичные релизы не изменяются.
## Verified delivery scope

- Windows x64 installer: manually verified, including upgrade and Processing.
- macOS Apple Silicon ZIPs are historical/internal artifacts only; they are not
  supported delivery targets for 3.0 because real Mac GUI smoke, signing and
  notarization are incomplete.
- Intel Mac is unsupported.
- RunPod SynthID and automatic updates are deferred.
