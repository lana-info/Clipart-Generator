# ADR-003: Prompt translation is explicit and separate from creative rewrite

Status: Accepted for the current phase

## Decision

Structured prompt values remain the source of truth. Rendering section labels
in English does not count as translating Russian values. Until a translation
backend is selected and its privacy, cost, timeout, offline and fallback
behavior are documented, the application uses an explicit no-op translation
backend that reports `translated: false` and preserves the original values.

Translation and creative prompt rewriting are separate operations. The base
generation path does not make an additional AI request automatically.

## Consequences

- Russian users can safely review the exact text they entered.
- The application does not falsely promise an English provider prompt when no
  translation is available.
- A future backend can implement the same structured-fields contract without
  changing saved Clipart or Pinterest data.
- Choosing and integrating that backend remains a separate task with an
  explicit cost/privacy decision.
