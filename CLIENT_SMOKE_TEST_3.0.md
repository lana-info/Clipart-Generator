# CLIENT SMOKE TEST 3.0

Статус: **WINDOWS GUI FAIL / MACOS MANUAL PENDING**. Установка Windows 3.0 поверх 2.0 выполнена вручную после постоянного backup; окно `Clipart Generator v3.0` появилось, но ожидаемые режимы отсутствуют.

## Артефакты

- Windows: `ClipartGenerator-Setup-3.0.exe`, run `30655673927`, SHA-256 `25a38056c6c311f36fa69a90bc40dcbd9accf898c8d0f205af8fedbc45c3f07a`.
- macOS: `ClipartGenerator-macOS-3.0.zip`, run `30655673927`, arm64, SHA-256 `52b148dc7a03d5451525af584f64665e757dadfb53e09954206913bff8760323`.
- Проверенная macOS-платформа: Apple Silicon; Intel Mac не поддерживается в 3.0.

## Windows clean install

Статус: **FAIL** — clean install не проверялся; разрешённый upgrade 2.0 → 3.0 выполнен на рабочем ноутбуке.

| Шаг | Ожидаемый результат | Фактический результат | Скриншот | Влияние на данные |
|---|---|---|---|---|
| Проверить SHA-256 | Хэш совпадает с release record | MANUAL PENDING | — | Нет |
| Запустить installer | Установщик открывается без ошибки | MANUAL PENDING | — | Нет |
| Проверить версию | Отображается 3.0 | MANUAL PENDING | — | Нет |
| Проверить путь | Установка в `{autopf}\Clipart Generator` | MANUAL PENDING | — | Нет |
| Проверить ярлык | Start Menu; desktop только при выборе | MANUAL PENDING | — | Нет |
| Первый запуск | Главное окно открывается, создаётся user data | MANUAL PENDING | — | Создаётся `%LOCALAPPDATA%\Clipart Generator` |
| Открыть Clipart/Pinterest/Processing | Все три режима доступны | MANUAL PENDING | — | Нет |
| Сохранить API-настройки | Секреты сохраняются в user-data `.env`, обычный config без секретов | MANUAL PENDING | — | Меняется только user data |
| Закрыть и запустить снова | Настройки и режим восстанавливаются | MANUAL PENDING | — | Нет |
| Обработать безопасное локальное изображение | Создаётся результат в выбранном output | MANUAL PENDING | — | Исходник не меняется |
| Проверить output | Результат существует и читается | MANUAL PENDING | — | Только output |
| Проверить исходник | Размер/хэш исходника не изменились | MANUAL PENDING | — | Данные защищены |
| Uninstall | Удаляется установленное приложение | MANUAL PENDING | — | Проверить отдельно |
| После uninstall | Зафиксировать фактическое поведение user data/projects | MANUAL PENDING | — | Не удалять вручную до фиксации |

## Windows upgrade from 2.0

Статус: **FAIL** — registry и окно показывают 3.0, но Clipart/Pinterest/Processing не представлены в интерфейсе. Uninstall и rollback не выполнялись.

Статический анализ:

- `AppId` 3.0 совпадает с текущим `installer.iss` и предназначен для upgrade-пути Inno Setup.
- Программа устанавливается в `{autopf}\Clipart Generator`.
- Пользовательские данные хранятся отдельно в `%LOCALAPPDATA%\Clipart Generator`:
  `config.json`, `.env`, `prompts.json`, `license_cache.json`.
- Проекты и output выбираются пользователем и не должны удаляться installer-ом, но это требует smoke-проверки.
- Перед upgrade нужен backup user-data и проектов.
- Не подтверждено, что uninstall 2.0 не удалит user-data после upgrade.

Фактический результат: registry показывает 3.0 и путь не изменился; `.env`, `config.json`, `prompts.json` сохранились; окно `Clipart Generator v3.0` появилось после более длительного запуска. Пользователь сообщил, что режимы Clipart/Pinterest/Processing отсутствуют. Processing не запускался.

Безопасный сценарий для повторной проверки: отдельная VM/Sandbox или тестовый компьютер → установить 2.0 → создать тестовые настройки/проект → сделать backup → установить 3.0 поверх → проверить данные → проверить uninstall только после копии.

## macOS Apple Silicon

Статус: **BLOCKED / MANUAL PENDING** — реального Mac Apple Silicon в текущем окружении нет.

1. Проверить SHA-256.
2. Распаковать `ClipartGenerator-macOS-3.0.zip`.
3. Переместить `Clipart Generator.app` в Applications.
4. Выполнить первый запуск.
5. Если Gatekeeper блокирует: Control-click → Open; при необходимости Privacy & Security → Open Anyway.
6. Проверить версию 3.0.
7. Открыть Clipart, Pinterest и Processing.
8. Сохранить API-настройки и перезапустить приложение.
9. Обработать безопасное изображение.
10. Проверить output и неизменность исходника.
11. Удалить `.app` и проверить сохранение пользовательских данных.

GUI smoke нельзя объявлять VERIFIED без реального Apple Silicon Mac.

## Release blockers

| Severity | Root cause | Workaround | Исправление обязательно до релиза |
|---|---|---|---|
| High | Нет подтверждённой изолированной Windows среды | Windows Sandbox/VM/отдельный компьютер | Да, для clean install verdict |
| High | Нет реального Mac Apple Silicon | Тестовый Mac Apple Silicon | Да, для macOS GUI verdict |
| Medium | Upgrade 2.0 → 3.0 не проверен | Backup + изолированная копия 2.0 | Да, если заявляется upgrade |
| Informational | macOS unsigned/notarization skipped | Правый клик → Open | Нет для unsigned manual release, но ограничение раскрыть |

## Data safety

Не устанавливать поверх рабочей 2.0, не удалять user data/projects и не менять публичный update channel без отдельного подтверждения.
