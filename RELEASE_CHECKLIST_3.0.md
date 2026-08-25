# Release checklist 3.0

## Final client status

- [x] Windows x64 installation and 2.0 → 3.0 upgrade verified.
- [x] Windows V3, Clipart, Pinterest and Processing verified.
- [x] Windows data preservation, output folders, recipes and preferences verified.
- [x] Windows Processing verified without `\\raw` and without source changes.
- [x] SynthID Deferred does not block ordinary Processing.
- [x] No paid API calls during smoke.
- [x] macOS arm64 artifact and packaging verified.
- [ ] macOS Apple Silicon real-device GUI smoke.

Release readiness: **READY FOR WINDOWS CLIENT RELEASE**; **READY FOR MACOS APPLE SILICON RELEASE WITH MACOS MANUAL-PENDING DISCLOSURE**.

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

## UI и установщик Vibix Images

- [x] Стартовый экран содержит три постоянные карточки: «Создать клипарт»,
  «Создать Pinterest-пины» и «Обработать изображения».
- [x] Каждая карточка использует локальную HQ PNG-иллюстрацию из `assets/` и
  доступное текстовое описание; иллюстрации включены в Windows и macOS PyInstaller-пакеты.
- [x] Windows Inno Setup использует `assets/installer-wizard-hq.png`, а приветственный
  и финальный тексты перечисляют те же три режима и шаг активации лицензии.
- [ ] После следующей сборки проверить визуально карточки на Windows и macOS.
- [ ] После следующей Windows-сборки проверить изображение и текст на экранах
  приветствия и завершения Inno Setup.

Не удалять эти ресурсы при рефакторинге стартового экрана или упаковки. При
добавлении нового режима обновить карточку, SVG-ресурс, тексты установщика,
PyInstaller-параметры и этот чеклист одновременно.

## Финал

- [ ] Вердикт изменён на READY или READY WITH MINOR RISKS после закрытия блокеров.
- [ ] Публикация выполняется только в согласованном канале поставки.
- [x] GitHub Actions workflow работает в build-only режиме и не создаёт GitHub Release.
- [ ] Не изменены `release/3.x` и `v3.0.0-rc1`.
