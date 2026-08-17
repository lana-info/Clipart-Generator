# P1 — schema-first конфигурация и миграции

Status: Done (2026-08-17)

Evidence: `config_schema.py`, `tests/test_config_schema.py` and V3
`preferences.json` integration in `v3_mode_selection.py`. Preferences are
versioned, migrated, secret-stripped and atomically replaced. Independent
review scored the first pass 4/10; one corrective pass added strict malformed
value handling, legacy key mapping and future-version fallback. Full Qt tests
remain environment-blocked because `PyQt6`/`Pillow` are not installed.

## Проблема и evidence

- `MainWindow.load_config`, `persist_ui_settings`, autosave и сбор значений из
  Qt widgets находятся в одном классе.
- Legacy defaults, normalization и новые processing fields смешаны с UI wiring.
- V3 `ProjectState` уже имеет dataclass/schema-подобный слой, но legacy config
  и V3 draft state не имеют единой явной migration boundary.

## Цель

Разделить persisted data, migration/normalization и UI adapter; старый config
остаётся читаемым, а новые поля добавляются одним местом.

## Минимальная реализация

1. Зафиксировать versioned config schema и defaults в pure module.
2. Реализовать `load -> migrate -> validate -> runtime snapshot` и обратное
   `UI state -> persisted config` без QApplication.
3. Сделать migration table для legacy keys, unknown keys и malformed values.
4. UI оставляет только binding widgets к schema object; secrets передаются через
   отдельный credential store.

## TDD и acceptance

- Fixtures: минимальный старый config, текущий config, config с неизвестными
  полями, malformed values и отсутствующими новыми keys.
- Round-trip не теряет поддерживаемые значения и не пишет secrets в config.
- Defaults детерминированы и не зависят от реальной user directory.
- Existing UI save/load tests и V3 draft tests проходят.
- Preferences сохраняются атомарно и versioned; текущий прямой `write_text`
  path в V3 должен быть закрыт regression-тестом на partial write/corrupt tail.
- Явно зафиксирован контракт `work_dir`/`output_dir`: валидный доступный
  `output_dir` не должен быть отвергнут только потому, что legacy `work_dir`
  указывает на корень/устаревшее место; при этом нельзя разрешать запись в
  произвольное невалидное место.

## Подводные камни

- Не мигрировать V3 `ProjectState` в legacy config одним большим шагом.
- Не использовать `dict.get` в десятках мест после появления schema object.
- Не менять пользовательские значения при чтении только ради нормализации: явно
  различать display fallback и persisted migration.
