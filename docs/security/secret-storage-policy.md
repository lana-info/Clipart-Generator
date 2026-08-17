# Secret storage policy

## Scope

Provider API keys and license device state are user data, not application
configuration or source artifacts. They must never be copied to tracked files,
ordinary logs, diagnostics exports, prompts, or exception text.

## Storage

- Provider keys are stored in the per-user `.env` under the application data
  directory. New files are written atomically with mode `0600` on POSIX. On
  Windows the accepted threat-model decision is the user-profile ACL boundary:
  the file is created only below the current user's application-data directory;
  DPAPI/Credential Manager is intentionally out of scope until a separate
  Windows security change adds migration and recovery rules.
- License device state, including its private device key, is stored separately in
  the per-user `license_state.json` with the same atomic/`0600` baseline.
- `licenses.db` is server-side state. It remains in the repository temporarily
  pending a separately approved backup and migration; this task does not read,
  rewrite, or delete it.

## Redaction

`security_redaction.py` is the shared pure primitive for user-facing errors and
structured data. It redacts secret-like key names, bearer/query credentials,
private-key blocks, and explicitly supplied secret values. Callers must pass
untrusted nested data through `redact_value` before serialization.

`scripts/check_sensitive_artifacts.py` is the source guard. Historical
`licenses.db` is an explicit temporary baseline allowlist only; its backup and
migration are a separate change and must remove that allowlist entry.
