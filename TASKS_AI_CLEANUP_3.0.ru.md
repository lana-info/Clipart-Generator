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

Status: Todo

Goal: сгруппировать metadata, visible mark и optional invisible cleanup в одной карточке.

Acceptance:
- [ ] одна основная кнопка очистки метаданных;
- [ ] optional invisible cleanup явно помечен как экспериментальный;
- [ ] обычная обработка не требует experimental consent.
- [ ] видимая метка имеет понятный confidence/fallback статус.

Verification:
- [ ] offscreen widget tests.

## Task 4: Улучшить сообщения прогресса

Key: `CG3-AI-TASK-004`

Status: Todo

Acceptance:
- [ ] видны текущий этап, файл, процент и итоговый путь;
- [ ] неуспех одного optional этапа не скрывает основной результат.

## Task 5: Проверки и ссылки

Key: `CG3-AI-TASK-005`

Status: Todo

Acceptance:
- [ ] ZeroGPT и официальный SynthID остаются отдельными ссылками;
- [ ] приложение не отправляет файлы автоматически.
- [ ] обе ссылки открываются системным браузером и не блокируют pipeline.

## Task 6: Regression, review и security

Key: `CG3-AI-TASK-006`

Status: Todo

Verification:
- [ ] полный test suite;
- [ ] code review loop;
- [ ] security review uploads/subprocess/env;
- [ ] refactor только при необходимости.

## Traceability

| PRD requirement | Task | Evidence |
|---|---|---|
| `CG3-AI-AC-001` cleanup order and originals | `CG3-AI-TASK-001` | contract tests |
| `CG3-AI-AC-002` optional backend safety | `CG3-AI-TASK-002` | adapter security tests |
| `CG3-AI-AC-003` unified UI | `CG3-AI-TASK-003` | offscreen UI tests |
| `CG3-AI-AC-004` progress and links | `CG3-AI-TASK-004/005` | queue/browser tests |
