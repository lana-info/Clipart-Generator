# P2 — lifecycle, cancellation и единый run event contract

Status: Done (2026-08-17)

Evidence: `run_lifecycle.py`, `tests/test_run_lifecycle.py`, lifecycle
integration and terminal guards in `v3_run_queue.py`, and the Windows checklist
in `docs/testing/windows-lifecycle-checklist.md`. The lifecycle contract is
pure for unit testing while queue/report compatibility remains unchanged.

## Проблема и evidence

- Legacy `WorkerThread(QThread)`, V3 queue, updater workers и timers имеют разные
  модели остановки и завершения.
- Legacy progress — текстовые строки; V3 `ProgressEvent` восстанавливает stage
  через prefix matching.
- В `TECHNICAL_DEBT.md` уже отмечен Windows native teardown risk.

## Цель

У каждого run есть однообразные states/events и проверяемый lifecycle: start,
progress, cancel requested, cancelled/failed/succeeded, cleanup.

## Минимальная реализация

1. Расширить event contract typed stage/status/error code, сохранив legacy text
   adapter на переходный период.
2. Определить idempotent finish/cancel semantics и owner cleanup для threads,
   temp files, timers и dialogs.
3. Добавить process-isolated offscreen smoke и Windows manual checklist.

## TDD и acceptance

- Fake runtime проверяет порядок и отсутствие duplicate terminal events.
- Cancel в каждом pipeline stage не публикует неполный final output как success.
- Repeated start/close не оставляет running QThread/timer.
- Existing queue report and progress UI remain compatible.

## Подводные камни

- Не делать durable queue в этой задаче; это отдельная 13.
- Не считать отсутствие crash на Linux доказательством Windows safety.
