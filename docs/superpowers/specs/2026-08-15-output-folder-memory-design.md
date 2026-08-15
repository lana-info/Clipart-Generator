# Output-folder memory design

## Goal

New projects must start in a user-owned image folder rather than the installed program directory, and the application must reuse the last folders selected for work and results.

## Behavior

- The first default working directory is the platform Pictures location plus `Clipart Generator`.
- The directory is created when a new project starts; if creation fails, the path remains visible and existing validation reports that it is unavailable.
- `preferences.json` stores `last_work_dir` and `last_output_dir` in addition to existing per-mode preferences.
- Clipart and Pinterest continue to write results below `<last_work_dir>/output`.
- Processing restores its last explicit result directory and uses `<last_work_dir>/output` until one is selected.
- A missing or unwritable remembered work directory falls back to the Pictures default.
- No default or browse action depends on `os.getcwd()`, so an installed application does not suggest `Program Files`.

## Verification

Regression tests patch the platform Pictures path, prove the default is created outside the process directory, then reopen the application and prove both selected work and processing-result folders are restored.
