# ADR-001: SynthID остаётся research-only, без production integration

## Status

Accepted

## Date

2026-07-28

## Context

В backlog 3.0 были выполнены три исследования по pixel-watermark / SynthID:

- M1: `reverse-SynthID V4`
- M2: `noai-watermark CtrlRegen`
- M3: `Synthid-Bypass V2`

Итог по имеющимся свидетельствам:

- M1 дал локально воспроизводимый результат и secure repeat совпал точно, но
  официальный input/output detector evidence не был получен;
- M1 помечен как research-only, а коммерческая интеграция upstream-лицензией не
  разрешена;
- M2 и M3 остановлены на preflight из-за отсутствия CUDA на текущей машине и
  отсутствия согласованного cloud/provider контракта;
- `PIXEL_WATERMARK_STATUS_CONTRACT.md` прямо разделяет processing,
  pixel_evidence, file_hints и verification_handoff, а также запрещает
  заявлять `removed` без отдельного detector evidence.

Нам нужно выбрать одно из четырёх состояний:

- `adopt_local_experimental`
- `adopt_worker_experimental`
- `research_only`
- `reject`

## Decision

Выбрано `research_only`.

Это означает:

- SynthID / provenance tooling остаётся только исследовательским направлением;
- production UI, generation, processing и export не зависят от SynthID;
- в пользовательском интерфейсе не появляется рабочая «перегенерация ради
  удаления SynthID» как обещанная функция;
- online upload отсутствует, provenance tool опционален и не блокирует
  основной pipeline;
- при появлении новых официальных доказательств можно открыть отдельную
  implementation task, но не раньше.

## Alternatives Considered

### adopt_local_experimental

Отклонено: M1 не даёт официального detector evidence, а лицензия upstream
ограничивает коммерческую интеграцию. Локальный research result не равен
production-ready capability.

### adopt_worker_experimental

Отклонено: M2 и M3 упёрлись в отсутствие CUDA и неподписанный provider/budget
контракт. Для текущего workstation profile это не готовый путь.

### reject

Отклонено как слишком сильное формулирование: у нас есть полезные
исследовательские результаты и контракт статуса, которые стоит сохранить для
будущей проверки. Но эти результаты не поднимаются до уровня production
feature.

## Consequences

- Генерация, обработка и экспорт продолжают работать без SynthID gate.
- UI не обещает гарантированное удаление или «человеческое происхождение».
- Любой будущий detector/provenance workflow должен быть отдельной task и
  отдельным gated capability.
- Следующие implementation tasks по SynthID не создаются, пока не появится
  новое официальное evidence или иной согласованный контур поставки.

## Evidence

- [PIXEL_WATERMARK_STATUS_CONTRACT.md](../../PIXEL_WATERMARK_STATUS_CONTRACT.md)
- [M1_REVERSE_SYNTHID_PILOT_2026-07-26.md](../../M1_REVERSE_SYNTHID_PILOT_2026-07-26.md)
- [benchmark_synthid_m1.pilot.json](../../benchmark_synthid_m1.pilot.json)
- [benchmark_synthid_m2.preflight.json](../../benchmark_synthid_m2.preflight.json)
- [benchmark_synthid_m3.preflight.json](../../benchmark_synthid_m3.preflight.json)
- [benchmark_synthid_3_methods.preflight.json](../../benchmark_synthid_3_methods.preflight.json)

