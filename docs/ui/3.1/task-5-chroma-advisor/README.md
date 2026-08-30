# Task 5 — Chroma Key помощник

Утверждённый макет: `approved-mockup.png`.

Статус: утверждён пользователем 2026-08-29. Этот screen применяется в Clipart
для одиночного prompt и генератора серии; CSV не получает Chroma controls.
Цветовые controls и материалы расположены слева; compact helper находится
справа и не содержит длинных объяснений.

## Реализация

- [`implemented-ready-prompt-1120x780.png`](implemented-ready-prompt-1120x780.png)
  — готовый многострочный prompt, три цветовые кнопки, материалы и раскрытый
  helper.
- [`implemented-series-1120x780.png`](implemented-series-1120x780.png) — тот же
  Chroma contract в конструкторе серии.
- [`implemented-ready-prompt-980x700.png`](implemented-ready-prompt-980x700.png)
  — evidence best-effort меньшего окна. На Linux offscreen
  при 980×700 страница имеет `140 px` горизонтального overflow: третья кнопка
  источника и правая часть helper не видны одновременно без прокрутки. По
  решению владельца это не release blocker: supported target — 1120×780 при
  Windows scaling 100%; меньшие окна/scaling выше 100% допускают прокрутку.

Предсборочный аудит обнаружил, что в интегрированном checkpoint helper не был
подключён, а цвет оставался выпадающим списком. Исправление добавлено через
падающие UI tests: helper виден только в двух Clipart-источниках, цвета показаны
тремя кнопками, материалы переносятся компактной сеткой и не расширяют страницу
при 1120×780. Remote Desktop не поддерживается и не входит в acceptance.
