# P1 — проактивный аудит межкомпонентных контрактов

Дата: 2026-08-17

## Подтверждённые исправления

- `v3_run_queue.py`: generated-path trust теперь соответствует runtime-контракту
  `output_dir/.run`, а не устаревшему `work_dir/raw`.
- `v3_run_queue.py`: stop-after-current обрабатывает stop-marker после уже
  сохранённого результата; pending items получают `cancelled`, run становится
  terminal.
- `v3_evidence_center.py`: неполные inspection-ответы дают `unknown`/`None`, а
  не ложные `not_present`/`0`.
- `licenses.db`: локальная копия сохранена, но удалена из Git tracking; scanner
  больше не получает blocked sensitive path из tracked source.

## Состояние проверки

- `CLOUD_OK`: offline fixtures, Qt offscreen, provider routing, license/update
  contract parsing и полный локальный pytest suite.
- `WINDOWS_REQUIRED`: packaged entrypoint, DPI/visual layout, real account,
  Windows filesystem/installer/UAC/SmartScreen и native QThread teardown.
- `BLOCKED`: live provider/API balance и license-service calls не выполнялись;
  sandbox не разрешает реальные сети и платные операции.

## Остаточные риски

- Legacy `WorkerThread` и V3 queue всё ещё связаны текстовым progress adapter;
  migration на typed native runner остаётся отдельной задачей 12/13.
- Исторический `main_restored.py` удалён из рабочего дерева; его содержимое
  остаётся доступным в Git history, поэтому source tree больше не содержит
  этот compile-blocking backup.
