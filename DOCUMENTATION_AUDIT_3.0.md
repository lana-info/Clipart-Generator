# Documentation Structure Audit 3.0

Проверка выполнена без удаления файлов. Ниже предложения, а не автоматические
операции.

## Дубли и возможная консолидация

- `PRD.md` и `PRD_3.0.ru.md`: общий legacy PRD и локализованный 3.0 PRD;
  выбрать canonical entry point и оставить ссылку на исторический документ.
- `TASKS.md`, `TASKS_3.0.ru.md`, `TASKS_AI_CLEANUP_3.0.ru.md`: разделить
  active 3.0 evidence, historical tasks и research appendix.
- `RELEASE.md`, `RELEASE_PROCESS.md`, `RELEASE_PLAN_0.2.4.md`,
  `AUTHOR_STEP_BY_STEP.md`: объединить актуальный process с архивными планами.
- `USER_INSTALL_GUIDE.md` и `CLIENT_MAC_INSTALL_SHORT.md`: сделать один
  пользовательский guide и короткую ссылку на него.
- `M1_REVERSE_SYNTHID_PILOT_2026-07-26.md`, `M1_GEMINI_HANDOFF.ru.md`,
  `SYNTHID_3_METHOD_BENCHMARK.ru.md`: пометить как research archive.

## Устаревшие или требующие явной пометки

- `RELEASE_PLAN_0.2.4.md` содержит историческую версию и не должен выглядеть
  как текущий release plan.
- `BASELINE_2.0_2026-07-25.md` и текущие `2.0` packaging metadata могут
  вводить в заблуждение без ссылки на 3.0 blocker.
- Старые benchmark/task документы должны иметь status/date в заголовке.
- `ROADMAP_3.1.md` остаётся roadmap; `PRODUCT_BACKLOG.md` теперь отдельный
  полный каталог идей.

## TODO и инструкции

- Провести отдельный grep TODO/FIXME по исходникам и классифицировать каждую
  запись; в рамках этой документационной работы код не изменялся.
- Проверить `.agents`, `AGENTS.md` и локальные instructions на соответствие
  текущей ветке и release policy.
- Проверить ссылки после будущей консолидации; сейчас исторические файлы
  намеренно не удаляются.

## Рекомендованный порядок после 3.0

1. Зафиксировать canonical user/release docs.
2. Архивировать исторические документы в отдельный каталог только отдельным
   согласованным изменением.
3. Синхронизировать version metadata и только затем публиковать installer.
