# Windows acceptance checklist — Vibix Images 3.1.0

Этот чек-лист проверяет кандидат 3.1.0 перед публикацией. Успешная сборка сама
по себе не разрешает загружать installer на сервер обновлений. Платные запросы
и публикация выполняются только после отдельного подтверждения владельца.

Статусы: `PASS`, `FAIL`, `SKIP` с обязательным объяснением.

## 1. Идентификация кандидата

- [x] Source branch: `codex/release-3.1.0-final-candidate`.
- [x] Source commit записан: `8c8c51cc95c8e3e61657988d0641f7a010b48f75`.
- [x] GitHub Actions run записан: `33323775508`.
- [x] Artifact: `windows-3.1.0`.
- [x] Installer: `VibixImages-Setup-3.1.0.exe`.
- [x] Размер installer записан: `231576596` байт.
- [x] SHA-256 из artifact записан и повторно вычислен локально:
  `421aae337715057bbd44a808c0078d08689c04443225b2b1b1a19269a85b7f80`.
- [x] `release/build-provenance.json` указывает тот же commit, а приложенный
  `release/VERSION.txt` — версию 3.1.0.
- [x] Использован новый artifact этого run, а не старая ветка или прежний файл.

## 2. Автоматические Windows gates

- [x] Нативный DPAPI round-trip Fal.ai key: `1 passed`, не `skipped`.
- [x] Нативная блокировка installer: `1 passed`, не `skipped`.
- [x] License/run gates, compilation и sensitive scan прошли.
- [x] PyInstaller executable сообщает версию 3.1.0.
- [x] Inno Setup завершился успешно с закреплённой версией 6.7.1.
- [x] Microsoft Visual C++ runtime имеет действительную подпись Microsoft.
- [x] Установка в чистую временную папку и packaged startup smoke прошли.
- [x] Installed local-processing smoke с bundled Real-ESRGAN прошёл.
- [x] В artifact есть `mode-selection.png`, `clipart-prompts.png` и
  `clipart-prompt-review.png` с нативным Windows rendering.
- [x] Release contract, installer checksum и build provenance прошли.

Evidence: [GitHub Actions run 33323775508](https://github.com/lana-info/Clipart-Generator/actions/runs/33323775508),
artifact ID `9735781326`, срок хранения до `2026-09-02T17:06:52Z`.
Автоматические screenshots сняты runner'ом при размере меньше поддерживаемого
1120×780 и подтверждают только наличие/rendering; visual acceptance раздела 4
остаётся ручным.

Команда для повторения двух нативных тестов на целевом Windows-компьютере:

```powershell
python -m pytest -q `
  tests/test_api_credentials.py::ApiCredentialKeysTests::test_fal_key_round_trips_through_dpapi_after_store_restart `
  tests/test_update_client.py::UpdateClientTests::test_verified_installer_is_immutable_until_protected_context_closes
```

Ожидаемый результат: `2 passed`, `0 skipped`.

## 3. Проверка файла и установка

- [ ] Локальный SHA-256 совпадает с `.sha256` из artifact.
- [ ] Повреждённая копия installer не используется и не принимается как
  проверенный кандидат.
- [ ] SmartScreen/UAC показали ожидаемое поведение; приложен screenshot.
- [ ] Чистая установка в стандартную папку завершается без ошибки.
- [ ] Ярлыки меню «Пуск» и рабочего стола используют имя **Vibix Images**.
- [ ] Приложение запускается из меню «Пуск» и закрывается без зависшего процесса.
- [ ] Повторная установка 3.1.0 не повреждает приложение.
- [ ] Обновление поверх последней проверенной 3.0.7 сохраняет настройки,
  лицензионное состояние и выбранные рабочие папки.
- [ ] После удаления 3.1.0 предыдущий проверенный installer остаётся доступен
  для rollback; повторная установка предыдущей версии возможна.

## 4. Интерфейс — 1120×780, Windows scaling 100%

- [ ] Проверка выполняется локально, не через Remote Desktop.
- [ ] Tasks 2, 3 и 5 соответствуют implemented screenshots: нет наложений,
  обрезанных обязательных controls и недостижимой навигации.
- [ ] В Chroma helper видны три кнопки: синяя, красная и зелёная.
- [ ] Действие Gemini подписано `Удалить водяной знак Gemini`.
- [ ] Clipart, Pinterest и Processing открываются и переключаются без зависания.
- [ ] Обычная/reference генерация показывают раздельные model/ratio/resolution;
  количество вариантов остаётся общим.
- [ ] Меньшее окно или scaling выше 100% проверены только best-effort и не
  считаются release blocker, пока controls достижимы через прокрутку.

## 5. Редактор прозрачности

- [ ] Открывается кнопкой `Проверить прозрачность` из Processing/Results.
- [ ] Мышью работают add/remove, continuous stroke, radius и hardness.
- [ ] Работают Fit/50/100/150/200/300%, pan с пробелом и focus mode.
- [ ] Работают undo/redo/reset и предупреждение о несохранённых изменениях.
- [ ] Переключение файлов не смешивает маски.
- [ ] Corrected PNG и alpha-mask сохраняются согласованной парой; DPI сохранён.
- [ ] Изображение выше pixel cap отклоняется понятным сообщением без зависания.
- [ ] Стилус проверяется только если он используется на целевом устройстве.

## 6. Workspace, имена и отсутствие дублей

- [ ] В новой пустой выбранной папке созданы `rough/`, `output/` и уникальная
  `.run/<run-id>` без отдельной миграционной страницы.
- [ ] Старый сохранённый literal path `output` безопасно нормализуется в parent.
- [ ] В `output/` попадают только `_ready` файлы текущего запуска; intermediates
  остаются в `rough/`.
- [ ] Повторяющиеся имена получают collision-safe suffix и не перезаписываются.
- [ ] Длинные/русские имена укладываются в Windows-safe path budget.
- [ ] Файлы предыдущего запуска не публикуются повторно.
- [ ] После отмены или сбоя не остаётся ложных ready-файлов и незавершённых
  CSV/PNG/mask транзакций.

## 7. Chroma quality

- [ ] Blue/red/green presets дают прозрачный фон на representative images.
- [ ] Проверены тонкие линии, отверстия, enclosed near-key details и цветной
  spill без подтверждённой потери предмета.
- [ ] Проверены несколько реальных полупрозрачных материалов.
- [ ] Подтверждено правило: точный выбранный key-цвет внутри предмета
  неотличим от фона; для такого предмета выбирается другой preset.
- [ ] Результат сравнен на шахматном, белом, чёрном и контрастном фоне.

## 8. Credentials и лицензия

- [ ] Fal.ai key сохраняется, приложение полностью закрывается и после нового
  запуска key восстанавливается без повторного ввода.
- [ ] Fal.ai key не появляется в config, журнале, screenshot или отчёте.
- [ ] Первая активация без сети остаётся fail-closed.
- [ ] Ранее успешно проверенная тестовая лицензия при qualifying outage
  показывает offline grace, дату последней проверки и крайний срок.
- [ ] Denial/revocation/expiry/tampering/clock rollback остаются fail-closed.
- [ ] После восстановления сети проходит новая signed online validation.

## 9. KIE duplicate audit — отдельный платный gate

Не выполнять без отдельного подтверждения владельца.

- [ ] Разрешение на один платный запуск получено либо риск явно принят.
- [ ] Один prompt + один variant создали один KIE Task ID.
- [ ] В `output/` создан ровно один ready PNG.
- [ ] Сохранены filename, SHA-256 и privacy-safe diagnostic journal.
- [ ] Stage-копии в `rough/` соответствуют ожидаемым этапам, а не дублям ready.

## 10. Итог и публикация

- [ ] Все обязательные пункты имеют `PASS` либо явно принятое объяснение.
- [ ] Все `FAIL` имеют воспроизведение, severity и решение fix/accept/defer.
- [ ] Installer, checksum, provenance, screenshots и заполненный checklist
  сохранены вместе.
- [ ] Идеи следующей версии не потеряны: Task 27 фиксирует zoom/brush shortcuts,
  базовый «Умный контур» и последующее отключаемое магнитное притягивание.
- [ ] Получено отдельное подтверждение на публикацию 3.1.0 пользователям.

До последнего пункта кандидат остаётся непубличным acceptance artifact.
