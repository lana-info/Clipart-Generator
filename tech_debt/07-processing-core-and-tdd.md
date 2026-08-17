# P1 — тестируемое ядро processing pipeline

Status: Done (2026-08-17)

Evidence: `processing_contract.py`, `tests/test_processing_contract.py`, the
V3 processing request boundary and legacy final publication/raw workspace
integration. Independent review scored the first pass 3/10; one corrective
pass added immutable runtime context seams, provider protocol, cancellation/
event contracts, secret-safe failure classification, output-adjacent run
workspace and shared atomic publication. Full provider/UI matrix remains a
follow-up because Qt/Pillow are unavailable in this environment.

## Проблема и evidence

- `WorkerThread` в `main.py` занимает примерно 2.4k строк и одновременно
  владеет orchestration, subprocess Real-ESRGAN, rembg/BEN2/PhotoRoom/KIE,
  progress, cancellation, temp files и final save.
- `_run_processing_pipeline` и provider methods напрямую зависят от mutable
  worker fields и Qt signals.
- Acceptance tests есть, но значительная часть provider/failure matrix остаётся
  implicit через worker и filesystem.

## Цель

Получить pure orchestration contract и provider adapters, которые можно менять
через TDD без запуска полного GUI и без сети.

## Минимальная реализация

1. Зафиксировать pipeline plan как ordered immutable steps: upscale before,
   unsharp, background, upscale after, edge shrink, trim, metadata, export.
2. Ввести narrow `ProcessingContext`/result contract с paths, cancellation и
   event sink; не переносить сразу всю реализацию.
3. Каждый provider получает adapter interface и fake в тестах.
4. Первыми вынести pure normalization, order, path naming и failure classification;
   затем по одному provider adapter.

## TDD и acceptance

- Matrix tests для before/after/both upscale, alpha/RGB, local/KIE/mixed,
  skip/failure/cancel и metadata-only runs.
- Нет network/subprocess в unit tests; integration smoke явно opt-in.
- Критические invariants: atomic final publication, raw/output separation,
  alpha preservation, no output on failed step, no secret in event text.
- Regression на stale workspace: intermediates создаются относительно
  разрешённого run/output workspace, а не случайно под `state.common.work_dir`;
  source не изменяется.
- Existing local/mixed acceptance and KIE routing remain green.

## Подводные камни

- Не менять фактический порядок и не делать provider abstraction ради абстракции.
- Не скрывать partial failure и не превращать cancellation в success.
- Real-ESRGAN/rembg models и third-party binaries остаются runtime dependencies,
  не копируются в test fixtures.
