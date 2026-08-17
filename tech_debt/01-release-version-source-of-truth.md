# P0 — единый production surface, версия и release contract

Status: Done (2026-08-17)

Evidence: `release_contract.py`, `tests/test_release_contract.py`, строгий
`main.py` version loading, согласованные `build.ps1` и Windows workflow.
Локальный `version.json` остаётся историческим манифестом legacy-канала и не
используется защищённым V3 update service; его публикация не менялась.

## Проблема и evidence

- `release/VERSION.txt` содержит `3.0`, `installer.iss` и `build.ps1` имеют
  собственные defaults, а `version.json` всё ещё указывает latest `2.0` и старый
  download URL.
- README одновременно описывает source 3.0 и packaging metadata 2.0.
- `main.resolve_app_version()` имеет fallback `3.0`, то есть отсутствие/ошибка
  файла маскируется вместо явного build failure.
- Workflow умеет передавать версию, но не проверяет согласованность manifest,
  installer name, app identity и update contract до публикации.
- `README.md` запускает `run_clipart_gui_v3.py`, который открывает V3 view
  напрямую; защищённый startup/license path находится в `main.py`. Это разные
  production surfaces с разным updater/diagnostics/license поведением.
- `build.ps1` строит `dist\\Vibix Images`, а workflow ищет
  `dist\\Clipart Generator\\Clipart Generator.exe`; это конкретный packaging
  contract mismatch.

## Цель

Одна версия должна проходить из release input в runtime, installer, checksum и
update manifest; устаревший manifest должен быть невозможен в CI.

## Минимальная реализация

1. Выбрать `release/VERSION.txt` единственным source of truth для source build;
   workflow input разрешить только как явный override.
2. Вынести чистые функции `parse_version`, `resolve_release_version` и
   `validate_release_contract` без Qt/GUI.
3. Добавить проверки: version format, artifact filename, manifest latest version,
   URL, checksum filename и expected packaged version.
4. Синхронизировать README/KNOWN_LIMITATIONS только после фактического состояния;
   не обещать публикацию, если revision ещё draft.
5. Выбрать один поддерживаемый production launcher. Dev-only launcher должен
   явно называться так и не обходить license gate; app name, executable name,
   PyInstaller dist path, installer path и update artifact name должны быть одной
   проверяемой матрицей.

## TDD и acceptance

- Сначала тесты на `3.0`, `3.0.1`, whitespace/invalid/missing version.
- Тест на несоответствие manifest `2.0` должен падать до исправления и проходить
  после него.
- Acceptance: source smoke, installer smoke и manifest contract сообщают одну
  и ту же версию; отсутствие `version.json`/невалидная версия дают понятный
  non-zero результат.
- Launcher parity test подтверждает: startup authorization, updater,
  diagnostics и V3 routes доступны из поддерживаемого launcher; workflow ищет
  реально созданный executable.
- Не запускать release workflow без отдельного разрешения пользователя.

## Подводные камни

- Не менять автоматически опубликованный update service и не выкатывать draft.
- Сохранить совместимость с `3.0` и `3.0.1`, не требовать семантического patch
  номера там, где существующий workflow допускает `3.0`.
- Не зашивать конкретный URL updates repository в несколько модулей.

## Зависимости и размер

Зависит от решения по текущему update manifest. Средний объём: 3–6 файлов и
focused release tests.
