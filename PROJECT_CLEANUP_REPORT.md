# Project Cleanup Report

Дата: 2026-07-31
Ветка: `develop/3.0`

## Результат

- Git tracked files сохранены.
- Рабочее дерево на момент аудита было чистым.
- `release/3.x`, `v3.0.0`, `v3.0.0-rc1`, `version.json` и опубликованный Release не изменялись.
- Внешний архив клиентских installers создан и проверен.
- Удаление файлов в рабочем дереве не выполнялось автоматически: неоднозначные кандидаты оставлены до отдельного решения.

## Архив

Постоянный внешний архив:

`D:\WorkOS\ClipartGenerator-Release-Archive`

Содержит:

- `2.0\ClipartGenerator-Setup-2.0.exe` — rollback installer;
- `2.0\ClipartGenerator-macOS-2.0.zip` — исторический macOS artifact;
- `3.0\ClipartGenerator-Setup-3.0.exe`;
- `3.0\ClipartGenerator-macOS-3.0.zip`;
- checksum-файлы 3.0.

SHA-256 финальных 3.0 artifacts совпадает с опубликованным Release:

- Windows: `9256EB4C6A85018D189435387FE0CF557BF9B00AAC2DF987CD853EC08AD0BD54`;
- macOS: `014D4FE502867A0801B74A5A4FEE38305967E1A547031B41F62AFDEB603E2BA8`.

## KEEP

- весь tracked source code, tests, workflows, spec/build scripts и документация;
- tracked release history и `release/VERSION.txt`;
- `third_party` и bundled processing models;
- rollback installer 2.0 и пользовательские backups вне Git;
- финальные 3.0 artifacts во внешнем архиве и GitHub Release.

## REVIEW REQUIRED

- `dist/` — локальная сборка, потенциально воспроизводима CI, но требует проверки перед удалением;
- `.scratch/` — исследовательские SynthID artifacts и virtual environment, не удалять без решения;
- `_updates_repo_tmp/` — временный clone updates workflow, не удалять автоматически;
- `output/`, `raw/` — локальные пользовательские/тестовые данные, не трогать;
- `realesrgan-ncnn-vulkan-20211212-windows/` — локальные runtime binaries/models, используются локальным build/test path;
- старые installers и ZIP в `release/` и `_updates_repo_tmp/`;
- `ai-metla-test-20260719/` — тестовые материалы;
- tracked исторические benchmark/preflight documents — не считать мусором только по возрасту.

## SAFE TEMP CANDIDATES

Следующие ignored candidates можно удалить после отдельного подтверждения окружением:

- `.pytest_cache/`;
- `.ruff_cache/`;
- `__pycache__/` во всех каталогах;
- пустой `build/`;
- `start_clipart_gui_launch.log`.

Они не tracked, не являются backup и не нужны workflow. В рамках текущего аудита они сохранены для обратимости.

## Gitignore

Текущие правила уже покрывают Python caches, virtual environments, `build/`, `dist/`, `raw/`, `output/`, `.scratch/`, локальные binaries, `_updates_repo_tmp/` и launch log. Новые широкие правила не добавлялись, чтобы не скрыть fixtures или документацию.

## Validation

- `git status`: чистое дерево до этого отчёта;
- artifacts archive: создан вне Git;
- SHA-256: проверены после копирования;
- release pipeline, spec, installer и tests: ссылки на рабочие build paths сохранены;
- tracked files: не удалялись и не перемещались.

## Следующее безопасное действие

Отдельно подтвердить список `SAFE TEMP CANDIDATES` для удаления. `REVIEW REQUIRED` объекты удалять только после явного решения по каждому классу.
