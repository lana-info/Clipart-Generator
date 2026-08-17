# P1 — lifecycle license/update service

Status: Done (2026-08-17)

Evidence: `license_update_contract.py`, `tests/test_license_update_contract.py`
and `docs/security/license-update-lifecycle.md`. The contract fixes endpoint
versioning, bounded timeout, outage/revoke/tamper fail-closed semantics, clock
skew and overlapping trust-root rotation. Live service behavior and key
material were not changed.

## Проблема и evidence

- Клиент зависит от hard-coded license service URL, product id и public signing
  key; startup и каждый run зависят от online validation.
- Signed update flow требует согласованных manifest, delegation key, revocation и
  installer artifact, но operational contract не описывает outage, key rotation,
  protocol compatibility и recovery.
- API keys хранятся в plaintext `.env`, а device private key — в
  `license_state.json`; для Windows не зафиксирована policy ACL/DPAPI/Credential
  Manager.

## Минимальная реализация

1. Написать короткий contract: endpoint versioning, timeout/outage behavior,
   revocation semantics, clock skew, key rotation, old-client compatibility и
   recovery после смены endpoint/key.
2. Зафиксировать trust-root rotation strategy: overlapping public keys или
   signed keyset; не менять ключ вручную в коде без migration plan.
3. Для Windows принять security decision по `.env` и device state: допустимый
   plaintext с ACL или OS-backed protection; покрыть decision тестами и docs.
4. Добавить offline/endpoint outage contract tests без реального сервиса и
   manual checklist для staged update.

## Acceptance

- Старый клиент fail-closed предсказуемо при revoke/tampered manifest и не
  превращает outage в бессрочный доступ.
- Rotation не требует одновременного выпуска несовместимого клиента.
- Ни license key, private device key, provider key, nonce или response body не
  попадает в обычный config/log/diagnostic export.

## Не делать сейчас

Не менять live service, не публиковать update и не выбирать DPAPI/credential
manager без отдельного security/product решения.
