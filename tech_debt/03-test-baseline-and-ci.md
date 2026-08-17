# P0 — воспроизводимый test и CI baseline

Status: Done (2026-08-17)

Evidence: `pyproject.toml`, `.github/workflows/ci.yml`,
`docs/testing/ci-baseline.md` and explicit `network` marker assignments.

## Проблема и evidence

- README рекомендует `python -m pytest`, а release workflow запускает только
  отдельный unittest-набор.
- `requirements-dev.txt` содержит pytest, но нет единого pytest config, coverage
  threshold, marker policy или тестового job для обычного push/PR.
- Основные entrypoints и Qt lifecycle проверяются разными наборами; Linux
  offscreen не заменяет Windows packaged smoke.

## Цель

Одна команда даёт честный быстрый baseline, а CI отдельно показывает syntax,
unit/contract, offscreen UI и release-only проверки.

## Минимальная реализация

1. Зафиксировать pytest как основной runner либо явно разделить unittest legacy и
   pytest, не оставляя два неполных источника истины.
2. Добавить `pyproject.toml` только для pytest markers/options и coverage
   configuration, если это не конфликтует с текущей упаковкой.
3. Разделить тесты на быстрые pure/contract и Qt offscreen; paid/network tests
   должны быть opt-in и по умолчанию не запускаться.
4. Добавить CI job на обычные изменения: compile/import, fast tests, offscreen
   startup, `git diff --check`; release job оставить manual.
5. Отдельно документировать Windows-only checks и artifact smoke.

Уже найденный пример для этого слоя: два contract tests создают loopback
`ThreadingHTTPServer`/socket и не могут выполняться в текущем sandbox с
`EPERM`. Их нужно запускать в разрешённом CI job или заменить transport-level
fake там, где настоящий socket не является предметом проверки; нельзя просто
пометить весь license contract skipped.

## TDD и acceptance

- Новая команда запускается в чистой среде с `python3`/Windows `python`.
- Полный локальный baseline не делает внешних платных вызовов и не зависит от
  пользовательского config.
- CI failure виден по конкретному классу: syntax, unit, UI или packaging.
- Отдельная проверка на test discovery ловит тесты, которые просто импортируются
  и не выполняют assertions.

## Подводные камни

- Не поднимать coverage threshold искусственно: сначала baseline и hotspots.
- Не запускать в каждом PR тяжёлые onnx/model/runtime tests.
- PyQt native teardown может давать Windows-specific access violation; зафиксировать
  process-isolated smoke, а не скрывать сообщение.
