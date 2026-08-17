# P2 — рудименты, артефакты и документационная консолидация

Status: Done (2026-08-17)

Evidence: `docs/maintenance/artifact-inventory.md`, the short-pointer update in
`TECHNICAL_DEBT.md`, explicit Windows/macOS delivery scope in
`CLIENT_DELIVERY.md`, and `tests/test_documentation_hygiene.py`. No historical
or generated artifacts were deleted.

## Проблема и evidence

- В корне есть `main_restored.py` с invalid/non-text bytes, исторические
  benchmark JSON/HTML и release artifacts; часть может быть нужна, часть только
  увеличивает ambiguity.
- Документы `TECHNICAL_DEBT.md`, `PROJECT_CLEANUP_REPORT.md`, `README.md`,
  `STATE.md`, `TASKS*.md` описывают пересекающиеся статусы и иногда разные
  версии/ветки.
- `run_error.log` и database-like files требуют явной classification policy.
- В `v3_processing_flow.py` есть пользовательские сообщения, повреждённые до
  буквальных `????????`; это нужно исправить как encoding/runtime-message debt,
  а не оставлять при уборке документов.
- `CLIENT_DELIVERY.md` одновременно описывает macOS package как поставку, а
  workflow macOS job отключён; supported-platform matrix должна быть однозначной.

## Цель

Каждый tracked artifact имеет owner/purpose/lifecycle, а developer docs дают
один актуальный status без удаления полезной истории.

## Минимальная реализация

1. Составить inventory tracked/ignored/generated files с KEEP/ARCHIVE/DELETE
   decision; не удалять автоматически.
2. Пометить `main_restored.py`, старые benchmarks и release copies как
   historical/experimental или вынести в утверждённый archive.
3. Свести технический долг в `tech_debt/`, а `TECHNICAL_DEBT.md` оставить коротким
   указателем.
4. Удалить только доказанные дубликаты после явного решения и проверить ссылки.
5. Провести UTF-8 audit пользовательских строк и исправить только подтверждённые
   повреждения; добавить тест на отсутствие таких placeholder strings в runtime.
6. Явно выбрать, поддерживается ли macOS в текущем release scope; старые ZIP не
   удалять, а классифицировать как historical, если platform support снят.

## TDD/verification и acceptance

- `rg` по ссылкам показывает отсутствие broken developer links.
- `git ls-files` policy check не считает пользовательские outputs source.
- Python compile/import не затрагивает исторические бинарные/invalid files.
- Release history и third-party notices сохраняются.

## Подводные камни

- Не удалять по дате или названию.
- Не перемещать артефакты между репозиториями без согласования backup/ownership.
- Не переписывать project history только ради чистого корня.
