# Quality Gate issues 3.0

## Current release state

Final Windows upgrade smoke is **VERIFIED/PASS**: installed 3.0 launches V3,
all three modes work, two-file Processing completes without `\\raw`, selected
output is respected, sources remain unchanged, preferences restore after
restart, and SynthID Deferred does not block ordinary work. No paid API calls
were made.

Targeted regression, local Processing acceptance checks, and a manual GUI
smoke through the native file picker are green. The end-to-end Processing
scenario is now VERIFIED using test copies and a separate output directory.

## Stabilization update after Windows V3 upgrade

- KIE balance responses now use a typed parser and reject unknown schemas.
- V3 production runtime merges persisted `.env` credentials into its runtime snapshot.
- SynthID/deep-watermark consent is required only for that optional operation.
- The mandatory Processing evidence step was removed from the blocking route.
- Access-denied failures now use a visible error state and a user-facing recovery message.

| ID | Criticality | Reproduction | Status |
|---|---|---|---|
| QG-001 | High | Запустить полный Qt smoke с созданием V3ApplicationView и дождаться завершения процесса | Open: отдельный smoke проходит; расширенный V3 набор также завершился (`32 passed`, `8 subtests`, 51.76 s), но legacy MainWindow/offscreen lifecycle still needs separate closure |
| QG-002 | Medium | Запустить полный набор pytest | Open: full suite now passes (`418 passed`, `61 subtests`, 245.87 s); Windows still prints a non-fatal `onnxruntime` access-violation diagnostic while the optional MI-GAN backend falls back to OpenCV |
| QG-003 | Medium | Проверить сборку release artifact Windows/macOS | Open: installer/build не подтверждены |
| QG-004 | Medium | Проверить production path запуска V3 | Open: V3 controllers используют legacy WorkerThread из main.py |
| QG-005 | Medium | Сверить TASKS/PRD с фактическими проверками | Open: есть преждевременные Done и deferred release checks |
| QG-006 | High | Pinterest: перетащить строку промпта с прикреплённым референсом | Fixed: reorder теперь меняет только порядок исходных PromptEntry; targeted tests 12 passed |
| QG-007 | High | Processing: ошибка файла визуально не отличается от технических строк | Fixed: native Results smoke confirmed distinct success/failure presentation, explicit reason, and Processing-specific user status |
| QG-008 | High | Processing: политика конфликта одинаковых output-имён не видна до запуска | Fixed: native Processing smoke used a separate output folder; collision policy is covered by targeted regression and surfaced in the Results flow |
| QG-009 | High | Processing: действия и навигация находятся внутри scroll area | Fixed: native Results smoke confirmed usable fixed action bar with folder/log/report actions and result navigation |
| QG-010 | High | Processing: «Готово» и повторный запуск не имеют подтверждённого общего контракта | Fixed: native Results smoke plus targeted behavior tests confirm Done and Process-more contracts |

## Results UX audit — 2026-07-31

First-time-user review at 980×700 identified the following issues, ordered by
impact:

1. **High — action bar overflow.** Six actions in one row forced the Results
   page wider than the supported window and clipped actions for large queues.
   Fixed by separating workflow and utility actions into two keyboard-ordered
   rows.
2. **High — weak completion hierarchy.** The top message did not clearly
   distinguish running, successful, partial, and failed runs. Fixed with a
   plain-language heading and compact counts for processed, errors, skipped,
   total, output folder, and elapsed time.
3. **High — technical stage language.** Internal stage names could appear next
   to the current file. Fixed with user-facing Russian stage descriptions.
4. **High — insufficient keyboard/screen-reader context.** Before/after
   previews lacked accessible names. Fixed with explicit names; action buttons
   retain their visible labels as accessible names.
5. **Medium — preview inspection.** No zoom, comparison slider, or enlarged
   preview mode for detailed visual inspection.
6. **Medium — large-batch navigation.** The list-plus-single-selection model
   scales to 20–100 files, but filtering, grouping, and a stronger selected-row
   summary would reduce navigation cost.
7. **Low — richer timing.** Only total elapsed time is shown; per-file timing
   and throughput are not exposed.

Critical/High items are implemented and covered by targeted UI regression plus
the 980×700 rendered review. Medium/Low items are tracked in `ROADMAP_3.1.md`.

## Current evidence — Processing

| Check | Status | Evidence |
|---|---|---|
| Processing request keeps the selected output directory | VERIFIED | `tests/test_v3_processing_flow.py::test_processing_request_preserves_selected_output_directory` |
| Processing queue uses `processing`, not `generation` | VERIFIED | `tests/test_v3_run_queue.py::test_processing_item_start_is_not_reported_as_generation` |
| Missing input receives an explicit failure reason | VERIFIED | `tests/test_v3_run_queue.py::test_missing_processing_file_is_marked_failed` |
| `README.jpg` is processed together with neighboring JPEGs | VERIFIED | `tests/test_v3_processing_flow.py::test_real_local_pipeline_processes_readme_jpg_in_batch` |
| Local worker creates a new output and preserves the source | VERIFIED | `tests/test_v3_processing_flow.py::test_real_local_pipeline_creates_new_file_without_touching_source` |
| Real GUI selection → run → output verification | VERIFIED | Manual native-file-picker smoke: files added, Processing stage shown, separate output used, results saved there, README.jpg handled or explicitly failed, remaining files continued, sources unchanged, no paid API started |
| Credential storage, secret redaction and provider contracts | VERIFIED | Focused mock/security regression: `8 passed`, `5 subtests`; no real provider request or key exposure |

## Current evidence — macOS Apple Silicon

| Check | Status | Evidence |
|---|---|---|
| Single macOS client artifact | VERIFIED | Workflow produces one `ClipartGenerator-macOS-3.0.zip` |
| Bundle version | VERIFIED | `Info.plist` contains version `3.0` |
| Apple Silicon architecture | VERIFIED | Audited artifact contains 378 Mach-O binaries, all `arm64` |
| Intel Mac compatibility | DEFERRED | Intel Mac and Universal 2 are outside the 3.0 product decision |
## Stabilization update — Processing intermediate paths

- Исправлен Critical defect: промежуточные файлы Processing больше не строятся из устаревшего workspace-пути `\\raw`.
- Для каждого запуска создаётся изолированный временный каталог; итоговый файл по-прежнему сохраняется только в выбранную output-папку.
- Добавлены regression-тесты для корневого/устаревшего workspace, custom output и сохранения исходника.
- Output-пути теперь хранятся отдельно для Clipart, Pinterest и Processing в project draft.
- Processing consent сохраняется как пользовательская настройка и восстанавливается при загрузке draft.
- Старые draft-файлы без новых полей продолжают загружаться с безопасными defaults.
- RunPod SynthID принят как Deferred/Research и не является блокером релиза 3.0.
- SynthID в клиентском UI отключён с коротким объяснением; обычная обработка не требует CUDA или RunPod.
