# P0 — граница секретов и чувствительных артефактов

Status: Done (2026-08-17)

Evidence: `security_redaction.py`, `tests/test_security_redaction.py`,
`docs/security/secret-storage-policy.md`, POSIX mode enforcement in
`api_credentials.py`, `scripts/check_sensitive_artifacts.py` and the CI syntax
step. The legacy local `licenses.db` is no longer tracked; the scanner remains
fail-closed for any local copy.

## Проблема и evidence

- Локальный `licenses.db` может содержать чувствительное состояние лицензий,
  поэтому он остаётся ignored и не отслеживается Git.
- Legacy `main.py`, `api_credentials.py`, `runtime_settings.py`, `license_client.py`
  и V3 settings имеют разные пути и правила хранения credentials.
- В проекте есть `.env.example`, но нет единого проверяемого inventory полей,
  redaction policy и pre-commit/CI guard для accidental secret leakage.
- API keys сохраняются в plaintext user `.env`, а device private key — в
  `license_state.json`; для Windows пока не зафиксирована ACL/DPAPI/Credential
  Manager policy.

## Цель

Секреты, license state и пользовательские данные не попадают в tracked source,
логи, exception text и тестовые fixtures; публичный контракт приложения при этом
не меняется.

## Минимальная реализация

1. Провести read-only inventory tracked sensitive paths без вывода содержимого.
2. Зафиксировать policy: что хранится в `.env`, что в user-data, что в server DB;
   добавить безопасный placeholder/fixture вместо реальных данных.
3. Ввести единый redaction helper и проверить им UI log, diagnostics, update,
   license и provider errors.
4. Добавить CI test/scan, который ловит имена ключей, PEM/private material,
   database dumps и credential-like values в новых tracked files.
5. Не добавлять `licenses.db` обратно в Git; резервные копии и server-side
   состояние хранить вне source repository.
6. Добавить threat-model decision для plaintext user state: либо явная policy
   ACL с ограничением scope, либо OS-backed protection; не выбирать механизм
   молча в рамках extraction.

## TDD и acceptance

- Тесты проверяют redaction для разных key names, query/header/body и nested errors.
- Тесты проверяют, что runtime settings не мутируют исходный config и не пишут
  secrets в обычный config.
- CI проверяет отсутствие запрещённых tracked artifacts; false positives должны
  разрешаться allowlist для документации/тестовых фикстур.

## Подводные камни

- Не печатать реальные `.env`, `licenses.db` или user config даже при диагностике.
- Не ломать старые пользовательские config; миграция должна быть read-compatible.
- Не считать `SECRET_CONFIG_KEYS` полной моделью: проверить RunPod, license,
  update signing и любые будущие provider keys.

## Зависимости и размер

Частично пересекается с 09; сначала определить policy, затем вынести общий
primitive. Средний/большой объём, внешнее удаление tracked DB — отдельное решение.
