# P1 — минимальный сетевой и security contract

Status: Done (2026-08-17)

Evidence: `network_security.py`, `provider_clients.py`, shared legacy
redirect-handler integration in `main.py` and `tests/test_network_security.py`.
Independent review scored the first pass 4/10; one corrective pass added
shared legacy transport usage, strict downgrade/host/port/credential redirect
blocking and response-limit tests. License/update transports remain covered by
the separate task 17 lifecycle contract.

## Проблема и evidence

- `main.py` содержит HTTPS redirect handling, SSL context, bounded response
  reads, URL/image validation и redaction рядом с UI/worker.
- `update_client.py`, `license_client.py`, `v3_api_settings.py` реализуют
  пересекающиеся network/security правила своими способами.
- `provider_clients.py` использует обычный `urllib.request.urlopen` для
  credential-bearing calls, поэтому no-downgrade/no-redirect policy не является
  общей гарантией.
- Update, license, KIE и PhotoRoom имеют разные lifecycle/error surfaces.

## Цель

Один небольшой security module гарантирует HTTPS-only redirects, size/time
limits, safe headers, response validation и redaction; domain clients используют
его через narrow interfaces.

## Минимальная реализация

1. Сначала snapshot contract tests текущих security invariants.
2. Первым проходом закрыть credential-bearing provider calls: HTTPS-only,
   redirect policy, timeout, bounded response и redaction.
3. Вынести чистые validators/limit readers/redactor без Qt; общий transport
   framework не строить заранее.
4. UI получает typed domain errors, а не raw exceptions/response payload.

## TDD и acceptance

- Redirect с HTTPS на HTTP/credential-bearing URL блокируется.
- Response size, image dimensions/pixels, timeout и malformed JSON ограничены.
- Secrets не появляются в URL, headers after redirect, logs и user-facing error.
- License/update signature/hash checks остаются обязательными.

## Подводные камни

- Не менять доверенный certificate policy без отдельного security решения.
- Не логировать request body для отладки.
- Не объединять transport clients так широко, чтобы потерять provider-specific
  status/error semantics.
