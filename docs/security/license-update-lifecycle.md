# License and update lifecycle contract

The desktop client uses versioned `/api/v1` endpoints. License validation is
fail-closed: revoked, expired, tampered, malformed, or unavailable validation
does not create an authorized run. An outage is reported as an outage, never as
valid cached authorization.

Signed manifests are accepted only for the matching product/license and after
signature, size, URL, hash, and installer checks. Trust-root rotation uses
overlapping key IDs (`license-v1`, then `license-v2`); a new client may accept
both during the rotation window, and the old key is removed only after the
service stops issuing signatures with it. No public key is changed in source
without a corresponding migration and contract test.

The client allows five minutes of clock skew for signed timestamps. Endpoint
timeouts are bounded at 30 seconds for lifecycle requests. Old `/api/v1`
clients remain supported during a controlled endpoint migration; unsupported
versions fail closed with a typed compatibility error.

On Windows, the current accepted policy is the user-profile ACL boundary for
`.env` and `license_state.json`; DPAPI/Credential Manager migration is a
separate product/security decision. Diagnostics and ordinary config must never
include license keys, device private keys, provider keys, nonces, or response
bodies.
