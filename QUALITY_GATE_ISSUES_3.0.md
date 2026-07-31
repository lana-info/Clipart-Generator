# Quality Gate issues 3.0

## Current release state

Targeted regression, local Processing acceptance checks, and a manual GUI
smoke through the native file picker are green. The end-to-end Processing
scenario is now VERIFIED using test copies and a separate output directory.

| ID | Criticality | Reproduction | Status |
|---|---|---|---|
| QG-001 | High | Запустить полный Qt smoke с созданием V3ApplicationView и дождаться завершения процесса | Open: native Qt/offscreen teardown зависает/завершается с кодом 1; точка после создания и перехода режима, до lifecycle teardown |
| QG-002 | Medium | Запустить полный набор pytest | Open: часть Qt-наборов не завершается стабильно; non-Qt/targeted suites проходят |
| QG-003 | Medium | Проверить сборку release artifact Windows/macOS | Open: installer/build не подтверждены |
| QG-004 | Medium | Проверить production path запуска V3 | Open: V3 controllers используют legacy WorkerThread из main.py |
| QG-005 | Medium | Сверить TASKS/PRD с фактическими проверками | Open: есть преждевременные Done и deferred release checks |
| QG-006 | High | Pinterest: перетащить строку промпта с прикреплённым референсом | Fixed: reorder теперь меняет только порядок исходных PromptEntry; targeted tests 12 passed |

## Current evidence — Processing

| Check | Status | Evidence |
|---|---|---|
| Processing request keeps the selected output directory | VERIFIED | `tests/test_v3_processing_flow.py::test_processing_request_preserves_selected_output_directory` |
| Processing queue uses `processing`, not `generation` | VERIFIED | `tests/test_v3_run_queue.py::test_processing_item_start_is_not_reported_as_generation` |
| Missing input receives an explicit failure reason | VERIFIED | `tests/test_v3_run_queue.py::test_missing_processing_file_is_marked_failed` |
| `README.jpg` is processed together with neighboring JPEGs | VERIFIED | `tests/test_v3_processing_flow.py::test_real_local_pipeline_processes_readme_jpg_in_batch` |
| Local worker creates a new output and preserves the source | VERIFIED | `tests/test_v3_processing_flow.py::test_real_local_pipeline_creates_new_file_without_touching_source` |
| Real GUI selection → run → output verification | VERIFIED | Manual native-file-picker smoke: files added, Processing stage shown, separate output used, results saved there, README.jpg handled or explicitly failed, remaining files continued, sources unchanged, no paid API started |
