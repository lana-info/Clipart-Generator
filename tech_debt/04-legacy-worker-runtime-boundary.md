# P1 — единый runtime adapter вместо скрытого legacy seam

Status: Done (2026-08-17)

Evidence: `v3_runtime_adapter.py`, adapter-owned legacy stage parser,
controller dependency injection in Clipart/Pinterest/Processing, and
`tests/test_worker_runtime.py`. `WorkerThread` remains the explicit temporary
implementation behind `LegacyWorkerRuntimeAdapter`.

## Проблема и evidence

- `v3_clipart_flow.py` и `v3_processing_flow.py` импортируют
  `_read_legacy_runtime_settings` и `_legacy_worker_factory`.
- Factory динамически импортирует `main.WorkerThread`; V3 controllers фактически
  зависят от монолита.
- `v3_run_queue.py` адаптирует legacy text progress по строковым префиксам, рядом
  с новым `ProgressEvent` contract.

## Цель

V3 зависит от узкого runtime protocol, а legacy worker становится временной
реализацией этого protocol, а не скрытой архитектурной зависимостью.

## Минимальная реализация

1. Описать protocol: run request, progress event, error, finished, cancel,
   lifecycle и secret-safe message.
2. Сделать один `LegacyWorkerRuntimeAdapter` в отдельном модуле; controllers
   получают его через dependency injection.
3. Перенести parser legacy text → structured event в adapter и покрыть все
   используемые stage markers.
4. Добавить feature flag/diagnostic assertion, показывающий, когда ещё используется
   legacy path; не удалять WorkerThread в этой задаче.

## TDD и acceptance

- Contract tests запускаются на fake runtime без Qt thread.
- Каждый legacy message из `_STAGE_PREFIXES` имеет предсказуемый stage/status;
  неизвестное сообщение не теряется.
- Cancel/finished/error доставляются ровно один раз.
- Clipart, Pinterest и Processing проходят существующие acceptance tests без
  изменения UX и payload.

## Подводные камни

- Не переносить 2.4k строк целиком и не менять порядок processing.
- Не делать новый adapter ещё одним god-object: только protocol translation и
  lifecycle wiring.
- Сохранить patch seams, которыми пользуются текущие тесты, на переходный период.

## Зависимости и размер

Основа для 07 и отдельной задачи 12. Средний объём.
