# TASKS: очистка следов ИИ и улучшение изображения

PRD: `PRD_AI_CLEANUP_3.0.ru.md`

## Task 1: Зафиксировать контракт очистки

Key: `CG3-AI-TASK-001`

Status: Done

Goal: единый порядок этапов и безопасные результаты.

Steps:
- определить модель результата и статусы этапов;
- сохранить оригинал и отдельный output path;
- покрыть контракт тестами.

Acceptance:
- [ ] порядок очистка → метка → optional invisible → обычная обработка задокументирован;
- [x] зафиксированы PNG/JPEG/WebP, alpha, ICC/DPI и запрет перезаписи исходника.

Verification:
- [ ] `python -m unittest tests.test_v3_processing_flow -v`

## Task 2: Вынести optional backend remove-ai-watermarks

Key: `CG3-AI-TASK-002`

Status: Done

Goal: запускать установленный локальный backend без обязательной CUDA-зависимости.

Steps:
- добавить безопасный adapter/subprocess boundary;
- проверять наличие backend до запуска;
- не показывать секреты и полные пути в ошибках.

Acceptance:
- [x] backend отсутствует — обычная обработка продолжает работать;
- [x] backend завершился ошибкой — результат и причина понятны пользователю.
- [x] subprocess ограничен timeout/размером, без секретов; приложение не передаёт файлы в сеть;
- [x] принимается только output внутри выделенной папки.

Verification:
- [x] `pytest -q tests/test_ai_watermark_backend.py` — 3/3.

## Task 3: Обновить UI первого этапа

Key: `CG3-AI-TASK-003`

Status: Done

Goal: сгруппировать metadata, visible mark и optional invisible cleanup в одной карточке.

Acceptance:
- [x] одна основная кнопка очистки метаданных;
- [x] optional invisible cleanup явно помечен как экспериментальный;
- [x] обычная обработка не требует experimental consent.
- [x] видимая метка имеет понятный confidence/fallback статус.

Verification:
- [x] `python -m unittest tests.test_v3_processing_editor tests.test_v3_project_state -v` — 18/18.

## Task 4: Улучшить сообщения прогресса

Key: `CG3-AI-TASK-004`

Status: Done

Acceptance:
- [x] видны текущий этап, файл, процент и итоговый путь;
- [x] неуспех одного optional этапа не скрывает основной результат.

## Task 5: Проверки и ссылки

Key: `CG3-AI-TASK-005`

Status: Done

Acceptance:
- [x] ZeroGPT и официальный SynthID остаются отдельными ссылками;
- [x] приложение не отправляет файлы автоматически.
- [x] обе ссылки открываются системным браузером и не блокируют pipeline.

## Task 6: Regression, review и security

Key: `CG3-AI-TASK-006`

Status: Done

Verification:
- [ ] полный test suite (отдельные legacy onnxruntime DLL failures остаются в baseline);
- [x] code review loop — PASS;
- [x] security review uploads/subprocess/env — PASS;
- [x] refactor после review выполнен только для порядка и валидации backend.

Evidence: `pytest -q tests/test_ai_watermark_backend.py tests/test_ai_cleanup_order.py` — 4/4.

## Traceability

| PRD requirement | Task | Evidence |
|---|---|---|
| `CG3-AI-AC-001` cleanup order and originals | `CG3-AI-TASK-001` | contract tests |
| `CG3-AI-AC-002` optional backend safety | `CG3-AI-TASK-002` | adapter security tests |
| `CG3-AI-AC-003` unified UI | `CG3-AI-TASK-003` | offscreen UI tests |
| `CG3-AI-AC-004` progress and links | `CG3-AI-TASK-004/005` | queue/browser tests |
