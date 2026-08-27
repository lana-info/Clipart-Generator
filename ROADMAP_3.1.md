# Roadmap 3.1

Статус: планирование после стабилизации 3.0.

Ветка `release/3.x` предназначена только для исправлений стабильной 3.0.
Ветка `develop/3.0` используется для подготовки 3.1. Этот документ не меняет
код и не включает задачи в обязательный scope без отдельного решения.

## Обязательный кандидатный scope 3.1

### R31-01 — Отделить WorkerThread от `main.py`

- Пользовательская ценность: меньше регрессий между legacy 2.0 и V3, более
  предсказуемые ошибки и запуск.
- Риск: высокий; можно нарушить генерацию, обработку, отмену и прогресс.
- Зависимости: стабильные run-plan контракты, structured progress events,
  integration tests для всех трёх режимов.
- Критерии приёмки: V3 запускается через отдельный worker-модуль; `main.py`
  не импортируется рабочим V3-путём; генерация, обработка, cancel, progress и
  error сценарии проходят regression.
- Приоритет: P0.

### R31-02 — Улучшить RunPod UX

- Пользовательская ценность: понятная настройка endpoint, ссылка на аккаунт и
  баланс, видимый статус подключения и стоимость cloud-запуска.
- Риск: средний/высокий; возможны неожиданные сетевые расходы и передача файлов.
- Зависимости: RunPod API key и endpoint пользователя, политика приватности,
  timeout/retry/cancel contract.
- Критерии приёмки: настройки объясняют каждое поле; есть безопасная проверка
  конфигурации; ошибки не раскрывают ключ; запуск cloud-пути явно показывает
  provider, endpoint и статус.
- Приоритет: P1.

### R31-03 — Field-level validation

- Пользовательская ценность: ошибка показывается рядом с конкретным полем, а не
  одной общей строкой внизу экрана.
- Риск: средний; можно создать противоречивые состояния формы.
- Зависимости: единый validation contract и mapping `field -> message`.
- Критерии приёмки: каждое обязательное поле имеет визуальное состояние,
  accessible name и понятное сообщение; переход «Далее» блокируется только
  соответствующей ошибкой; тесты покрывают empty, invalid и valid cases.
- Приоритет: P1.

### R31-04 — Installer Windows/macOS

- Пользовательская ценность: запуск без ручной настройки Python и зависимостей.
- Риск: высокий; размер ML-зависимостей, native DLL, секреты и права установки.
- Зависимости: решение о provider/runtime packaging, smoke на чистых системах,
  список разрешённых ресурсов.
- Критерии приёмки: повторяемая сборка Windows и macOS; приложение стартует на
  чистом окружении; ключи не вшиты; uninstall/upgrade не удаляют пользовательские
  данные.
- Приоритет: P1 после WorkerThread.

### R31-05 — Legacy cleanup

- Пользовательская ценность: меньше устаревших экранов и неоднозначных путей.
- Риск: средний; legacy-функции 2.0 могут быть ещё нужны пользователям.
- Зависимости: usage audit, migration tests, подтверждённый replacement для
  каждой удаляемой функции.
- Критерии приёмки: каждый legacy-модуль имеет owner/status; неиспользуемый код
  удалён только после regression; legacy fallback явно документирован.
- Приоритет: P2.

### R31-06 — Улучшить error handling

- Пользовательская ценность: понятные причины, безопасные сообщения и действия
  для восстановления.
- Риск: средний; широкие перехваты могут скрыть настоящую ошибку.
- Зависимости: structured error taxonomy, progress/run queue и logging policy.
- Критерии приёмки: ошибки разделены на input/provider/network/cancel/internal;
  ключи, пути и промпты не попадают в UI/лог; retry/cancel доступны там, где
  безопасны; failure одного файла не скрывает успешные результаты.
- Приоритет: P1.

### R31-07 — Архитектурно отделить V3 от V2

- Пользовательская ценность: V3 развивается независимо и не ломает стабильную
  ветку 3.0/legacy 2.0.
- Риск: высокий; затрагивает state migration, worker, providers и тесты.
- Зависимости: R31-01, integration contract, migration fixtures и release branch.
- Критерии приёмки: V3 имеет собственные state/run/provider seams; V2 остаётся
  доступной через совместимый adapter; dependency graph не ведёт из V3 UI в
  monolithic `main.py`; полный regression трёх режимов проходит.
- Приоритет: P0.

## Research: SynthID (не обязательный scope 3.1)

SynthID — невидимый сигнал происхождения, который может быть встроен в
изображение Google. Исследовательская задача должна определить, можно ли
надёжно обнаружить и изменить такой сигнал, не повредив изображение.

Что это может дать:

- локальный или cloud-эксперимент с before/after evidence;
- оценку того, меняются ли пиксели, лица, текст и прозрачность;
- понятный статус `detected / not detected / unknown`.

Чего это не обещает:

- гарантированного удаления SynthID;
- подтверждения «изображение создано человеком»;
- универсальной работы с любыми генераторами;
- автоматической проверки через ZeroGPT: ZeroGPT оценивает вероятность AI-
  генерации и не является официальным SynthID detector.

Перед включением в продукт нужно отдельно решить: нужен ли cloud GPU, какие
файлы можно передавать, какой бюджет допустим и какое официальное evidence
считается достаточным. До этого SynthID остаётся research-only и не блокирует
обычную генерацию, обработку или экспорт.

## Release-ветки

- `release/3.x` — стабильная 3.0, только исправления ошибок.
- `develop/3.0` — дальнейшая разработка и подготовка 3.1.
- `v3.0.0-rc1` — зафиксированная точка, к которой всегда можно вернуться.

## Results UX backlog

- **R31-08 — Preview inspection:** add zoom-to-fit/zoom-in, a before/after
  comparison slider, and a focused preview mode without changing the single
  selected-item model.
- **R31-09 — Large-batch navigation:** add filtering by status, compact
  grouping, and an optional thumbnail strip for 20–100 item runs while keeping
  the main preview singular.
- **R31-10 — Run performance details:** expose per-file duration and throughput
  in the details/log view, not in the primary completion summary.

## Next product phase after 3.1 acceptance

The detailed execution source of truth is the `NEXT-TASK-*` section in
`TASKS_3.0.ru.md`, with requirements in the `Next Product Phase` section of
`PRD.md`. This phase is not a replacement for the P0 architecture work above.
The initial workflow and prompt-foundation tasks may start after the current
product acceptance tasks; Fal.ai integration additionally requires the
provider-neutral lifecycle gate.

Its order is: workflow/page definition layer, structured prompt and
localization foundation, translation-backend decision, Clipart prompt
generator, provider-neutral generation/lifecycle contract, Fal.ai
model/provider integration, controlled acceptance, and only then a separate
Pinterest prompt generator. Patterns, mockups,
Invitations/Canva, and commercial module licensing remain future scope.
