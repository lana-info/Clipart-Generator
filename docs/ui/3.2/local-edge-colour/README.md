# Локальная коррекция цветной каймы: макет управления

Владелец поручил реализовать предложенный ручной инструмент. Эти экраны
показывают размещение и состояния управления; владелец ответил «Продолжай» после показанного макета, подключение разрешено.
В макете используется только синтетическая чашка. Проверка эффекта на настоящих
рисунках хранится отдельно в private artifacts и не подменяется этой иллюстрацией.

Работа: нажать «Убрать цветную кайму», обвести проблемный край рамкой,
посмотреть До/После на белом/тёмном фоне и выбрать Отмена или Применить.
Изменяется цвет выбранного края; alpha и форма сохраняются. Настоящая выбранная
обводка тоже может изменить цвет. Применение даёт один шаг Undo; автоматическая
обработка инструмент не вызывает. Ползунка силы нет.

| Состояние | Экран |
| --- | --- |
| Прежний редактор | [current](proposal/current.png) |
| Готовность новой кнопки | [ready](proposal/ready.png) |
| Выделение рамкой; только отмена до расчёта | [selecting](proposal/selecting.png) |
| Расчёт; можно отменить | [busy](proposal/busy.png) |
| До на белом фоне | [preview-before](proposal/preview-before.png) |
| После на белом фоне | [preview-after](proposal/preview-after.png) |
| После на тёмном фоне | [preview-dark](proposal/preview-dark.png) |
| Пустой редактор, действие выключено | [empty](proposal/empty.png) |
| Нет подходящей опоры; ничего не применено | [no-op](proposal/no-op.png) |

Цель1120×780,100% scaling. В режиме коррекции кисть/перо и история заблокированы;
их подробные настройки временно скрыты. Фон, масштаб и Отмена доступны. Apply
применяет После даже при просмотре До. Смена файла закрывает только preview;
применённые RGB/alpha должны сохраняться в черновике. Существующая политика
редактора не сохраняет Undo/Redo историю при смене файла; её глобальный редизайн
сюда не включён. RGB draft хранит изменённый участок без повышения его до saved
baseline; page lifecycle подключён и проверен.

`render_proposal.py` использует существующую страницу с временными Qt-элементами
только при снятии mockup. Production UI подключается отдельно от mockup renderer.
`proposal/notes.json` содержит перечень состояний и подтверждение продолжения владельцем.


## Проверка реализованного экрана

Главный агент просмотрел8 actual screenshots и сравнил с показанным макетом.
Размер1120×780, darktheme и расположение controls сохранены; новая кнопка,
Before/After и footer доступны без прокрутки. В состоянии no-op настоящая рамка
показывает проверенную пустую область, а не illustrative edge selection макета.
Кнопка коррекции остаётся checked и доступна для отмены, как в макете.
До и После используют реальный RGB proposal, не synthetic clean replacement.
Busy-state снят с held Future в настоящем integrated UI; остальные calculations
выполнены production worker. Это Linux/offscreen acceptance, не Windows build.

| Состояние | Макет | Реальный Qt экран |
| --- | --- | --- |
| ready | [proposal](proposal/ready.png) | [actual](actual/ready.png) |
| selecting | [proposal](proposal/selecting.png) | [actual](actual/selecting.png) |
| busy | [proposal](proposal/busy.png) | [actual](actual/busy.png) |
| preview-before | [proposal](proposal/preview-before.png) | [actual](actual/preview-before.png) |
| preview-after | [proposal](proposal/preview-after.png) | [actual](actual/preview-after.png) |
| preview-dark | [proposal](proposal/preview-dark.png) | [actual](actual/preview-dark.png) |
| empty | [proposal](proposal/empty.png) | [actual](actual/empty.png) |
| no-op | [proposal](proposal/no-op.png) | [actual](actual/no-op.png) |

Доказательство доступности/состояний: [actual verification](actual/verification.json).
Qt Save As, A→B→A, failed save, stale/cancel и keyboard scenarios проверены в
`tests/test_edge_colour_editor.py`; результаты вSTATE.md. Private actual owner
images остаются внеdocs/UI: `../artifacts/local-edge-colour-editor-20261003/ui-flow/`.
