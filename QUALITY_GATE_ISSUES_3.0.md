# Quality Gate issues 3.0

## Current release state

Manual smoke for Clipart, Pinterest and Processing was completed successfully.
User-facing issues found during that smoke are closed and covered by targeted
regression. Only the native Qt teardown blocker and explicitly deferred release
items remain below.

| ID | Criticality | Reproduction | Status |
|---|---|---|---|
| QG-001 | High | Запустить полный Qt smoke с созданием V3ApplicationView и дождаться завершения процесса | Open: native Qt/offscreen teardown зависает/завершается с кодом 1; точка после создания и перехода режима, до lifecycle teardown |
| QG-002 | Medium | Запустить полный набор pytest | Open: часть Qt-наборов не завершается стабильно; non-Qt/targeted suites проходят |
| QG-003 | Medium | Проверить сборку release artifact Windows/macOS | Open: installer/build не подтверждены |
| QG-004 | Medium | Проверить production path запуска V3 | Open: V3 controllers используют legacy WorkerThread из main.py |
| QG-005 | Medium | Сверить TASKS/PRD с фактическими проверками | Open: есть преждевременные Done и deferred release checks |
| QG-006 | High | Pinterest: перетащить строку промпта с прикреплённым референсом | Fixed: reorder теперь меняет только порядок исходных PromptEntry; targeted tests 12 passed |
