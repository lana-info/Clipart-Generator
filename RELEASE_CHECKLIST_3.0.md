# Release checklist 3.0

## Final Windows client smoke

- [x] Installer установлен поверх существующей 3.0 без uninstall.
- [x] Приложение запускается в V3.
- [x] Clipart, Pinterest и Processing доступны.
- [x] Processing обработал два файла без ошибки `\\raw`.
- [x] Результаты сохранены в выбранную output-папку.
- [x] Исходные файлы не изменились.
- [x] Output-папки, custom recipe и consent восстановились после перезапуска.
- [x] SynthID Deferred не блокирует обычную обработку.
- [x] Платные API не запускались.

Windows upgrade smoke: **PASS**. Windows clean-install smoke и macOS GUI smoke остаются отдельными ограничениями среды.

## Release readiness review

Verdict: **READY WITH MINOR RISKS**.

The Windows client path is verified. macOS Apple Silicon GUI smoke remains
manual pending; Intel Mac/Universal 2, signing/notarization, public updates
repository, and GitHub Release publication are outside this preparation step.

Статус текущей проверки: **NOT READY**. Публичная публикация в `Clipart-Generator-Updates` не выполняется.

## Версия и метаданные

- [x] `main.py`, `build.ps1`, `installer.iss`, workflow и `release/VERSION.txt` используют `3.0`.
- [ ] `version.json` обновлён только вместе с реальным 3.0 installer и его SHA-256.
- [ ] Версия проверена в собранном executable и About/заголовке.
- [ ] Changelog и release notes согласованы с фактически поставляемым артефактом.

## Сборка и поставка

- [ ] PyInstaller завершился успешно и создал полный пакет.
- [ ] Inno Setup создал `ClipartGenerator-Setup-3.0.exe`.
- [x] macOS workflow создал единственный ZIP с arm64 `.app`.
- [x] Главный executable и обязательные native dependencies содержат `arm64`.
- [x] Клиентское ограничение явно указано: Intel Mac не поддерживается.
- [ ] SHA-256 installer рассчитан и перепроверен.
- [ ] SHA-256 macOS-пакета рассчитан и перепроверен.
- [ ] Пакет запущен из чистого временного каталога.
- [ ] Проверены первый запуск, папки, настройки, DLL, модели и ресурсы.
- [ ] Нет платных API-вызовов без явного действия пользователя.

## Состав пакета

Разрешены только executable, runtime-библиотеки, модели/ресурсы, лицензии и пользовательская инструкция. Не включать `output`, `cache`, `logs`, временные изображения, тестовые файлы, `scratch`, внутренние документы, git-метаданные и исходники.

## Финал

- [ ] Вердикт изменён на READY или READY WITH MINOR RISKS после закрытия блокеров.
- [ ] Публикация выполняется только в согласованном канале поставки.
- [x] GitHub Actions workflow работает в build-only режиме и не создаёт GitHub Release.
- [ ] Не изменены `release/3.x` и `v3.0.0-rc1`.
