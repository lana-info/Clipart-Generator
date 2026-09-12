# Auto set export UI, approved 2026-09-11

Owner approved the summary-first export flow with these final refinements:

- show unique PNG count and number of sets only; no inclusion-count metric;
- no confirmation checkbox and no redundant Close button;
- plain-language delivery text: PNG, preview sheet and file list;
- primary action is always `Создать наборы`;
- `Изменить состав наборов` opens a separate matrix editor;
- matrix set headers and checkboxes are centered;
- filename hover shows a PNG preview beside the mouse pointer;
- `К наборам` is sized so its text is fully visible;
- problem state explains that nothing was auto-selected and offers `Проверить сейчас`;
- missing or ambiguous results block export;
- UI supports a dynamic number of set columns/cards, not a fixed four.

Historical proposal renders are retained for comparison. Final real Qt 1120x780
proofs are `final-summary-1120x780.png`, `final-review-1120x780.png`, and
`final-manual-1120x780.png`. Hover behavior is covered by the Qt acceptance test
because a static screenshot cannot demonstrate cursor-relative placement.
