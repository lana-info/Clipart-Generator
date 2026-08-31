# Windows acceptance checklist — Vibix Images 3.1.1

Этот чек-лист проверяет replacement-кандидат 3.1.1 перед публикацией. Успешная
сборка создаёт только временный GitHub artifact: она не публикует обновление и
не загружает installer на license server. Платные provider-запросы требуют
отдельного разрешения.

Статусы ручных пунктов: `PASS`, `FAIL` или `SKIP` с объяснением.

## 1. Идентификация

- [x] Source branch: `develop/3.1`.
- [x] Source commit: `dee4fac526a5418b607140d21e683dd2fb3bd4d2`;
  GitHub Actions run: `33350465599`.
- [x] Artifact: `windows-3.1.1`, ID `9743579624`, expires
  `2026-09-03T02:31:52Z`; локальная серверная копия сохранена.
- [x] Installer: `VibixImages-Setup-3.1.1.exe`, `231576030` байт.
- [x] SHA-256 совпадает с `.sha256` и `build-provenance.json`:
  `1c89a48d4050322e5e5e62dcb881636784070c4cb68ce102029495b1b1c02946`.
- [x] Приложенный `release/VERSION.txt` содержит `3.1.1`.

## 2. Автоматические Windows gates

- [x] DPAPI round-trip Fal.ai key прошёл на Windows, не `skipped`.
- [x] Installer-lock contract прошёл на Windows, не `skipped`.
- [x] License/run gates, compilation и sensitive scan прошли.
- [x] PyInstaller executable сообщает версию 3.1.1.
- [x] Inno Setup, установленный startup/UI smoke и Local Real-ESRGAN smoke
  завершились успешно.
- [x] Release contract, checksum и provenance прошли.
- [x] Artifact содержит Windows screenshots: `mode-selection.png`,
  `clipart-prompts.png`, `clipart-prompt-review.png`.

## 3. Установка и обновление

- [ ] Чистая установка завершается без ошибки; ярлыки имеют имя Vibix Images.
- [ ] Приложение запускается и закрывается без зависшего процесса.
- [ ] Обновление поверх проверенной 3.0.7 сохраняет настройки, лицензию и
  выбранные рабочие папки.
- [ ] Повторная установка 3.1.1 не повреждает приложение.
- [ ] Проверенный предыдущий installer сохранён для rollback.

## 4. Интерфейс — 1120×780, scaling 100%

- [ ] Проверка выполняется локально, не через Remote Desktop.
- [ ] Clipart, Pinterest и Processing открываются без зависания и наложений.
- [ ] Видны три chroma-кнопки: синяя, красная и зелёная; оранжевой нет.
- [ ] Обычная и reference-генерация имеют отдельные model/ratio/resolution;
  количество вариантов общее.
- [ ] Есть отдельная бирюзовая кнопка `CSV` в группе `Экспорт:`.
- [ ] Стоимость показана строками KIE/Fal.ai/PhotoRoom и итогом; обновление
  Fal.ai не скрывает уже известную стоимость KIE.
- [ ] В Clipart и Processing виден `Экспорт 300 DPI`.
- [ ] Апскейл до удаления фона доступен; апскейл после удаления фона скрыт.
- [ ] Вверху справа одна кнопка `Диагностика`, дублирующей кнопки в Results нет.

## 5. Провайдеры и журнал

- [ ] Один контролируемый Fal.ai smoke больше не получает общий HTTP 405;
  lifecycle показывает submit, polling и result по provider URL.
- [ ] Неуспешный KIE/Fal item отображается как ошибка, а не как успешное
  `item_finished` уровня «информация».
- [ ] После перезапуска pending task продолжает polling без повторного POST.
- [ ] Fal.ai key переживает полный перезапуск и не появляется в журнале,
  config, screenshot или diagnostics archive.
- [ ] Журнал ограничен по размеру/числу записей и сохраняет позднюю ошибку и
  итог запуска.

## 6. Workspace и отсутствие дублей

- [ ] В новой папке созданы `rough/`, `output/` и уникальная `.run/<run-id>`.
- [ ] Один prompt + один variant создают ровно один provider Task ID и один
  `_ready` PNG в `output/`.
- [ ] В `rough/` один provider result публикуется как один `*_generated`;
  metadata/existing-alpha копии не маскируются под новые генерации.
- [ ] Файлы предыдущего запуска не публикуются повторно; collisions не
  перезаписывают существующие файлы.
- [ ] Старый literal path `output` безопасно нормализуется в parent.

## 7. Chroma и прозрачность

- [ ] Blue/red/green presets проверены на тонких линиях, отверстиях, near-key
  деталях и полупрозрачных материалах.
- [ ] Точный выбранный key внутри предмета считается фоном; для такого предмета
  пользователь выбирает другой preset.
- [ ] Уже прозрачный provider PNG сохраняется без повторного Chroma-removal, а
  журнал явно показывает `already_alpha`/skipped.
- [ ] Редактор прозрачности открывается из Processing/Results; работают кисть,
  hardness, undo/redo/reset, pan и масштаб до 300%.
- [ ] Изображение выше 40 Мп отклоняется понятным сообщением.

## 8. Лицензия и итог

- [ ] Qualifying outage использует только ранее подтверждённый offline grace;
  denial/revocation/expiry/tampering/clock rollback остаются fail-closed.
- [ ] Все обязательные пункты имеют `PASS` либо принятое объяснение.
- [ ] Installer, checksum, provenance, screenshots и заполненный checklist
  сохранены вместе.
- [ ] Получено отдельное подтверждение перед публикацией 3.1.1 пользователям.

До последнего пункта 3.1.1 остаётся непубличным acceptance artifact.
