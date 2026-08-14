# Clipart Generator license-service desktop integration

## Goal

Ship `ClipartGenerator-Setup-3.0.exe` only after the desktop application uses
the deployed Clipart License Service for online activation and validation.
The application has no offline operating mode: when the service cannot be
reached or authorization cannot be proven, protected work does not start.

## Selected approach

Replace the legacy fingerprint-based `/activate`, `/validate`, and `/status`
client with the current signed API contract. Do not add a compatibility mode
or a fallback to the old protocol because either would create a weaker bypass
path.

The license service remains a separately deployed service. It is not bundled
inside the desktop installer. The installer contains only the desktop client,
the pinned server verification key, and normal application runtime resources.

## Client identity and secrets

- Base URL: `https://services.etsyneuroclub.com/licenses`.
- Product ID: `clipart-generator`.
- On first activation the client creates an Ed25519 device key pair.
- The private device key is stored in a dedicated versioned state file under
  the per-user application-data directory. Writes are atomic and user-only
  file permissions are applied where the platform supports them. The key is
  never logged, returned to the server, or placed in application config.
- The server license-signing public key and expected key ID are pinned in the
  application. No private server key is added to the repository or installer.
- The entered license key is sent only during activation. After successful
  activation the client persists the returned license ID and no longer needs
  the reusable license key for routine validation.

## Activation and validation flow

### Activation

1. The user enters a license key.
2. The client loads or creates its device key pair.
3. The client creates a fresh cryptographically random nonce and signs it with
   the device private key.
4. The client posts `product_id`, `license_key`, device public key, nonce, and
   proof to `/api/v1/licenses/activate` over HTTPS.
5. The client verifies the signed response envelope using the pinned server
   public key.
6. The client rejects an unknown key ID, invalid signature, wrong product,
   wrong device key, wrong nonce, expired authorization, or malformed data.
7. On success it stores only the license ID and required local device state.

### Before protected work

1. The client creates and signs a fresh nonce.
2. The client posts the license ID, product ID, device public key, nonce, and
   proof to `/api/v1/licenses/validate`.
3. The client validates the returned signed envelope and its claims.
4. Only then may Clipart, Pinterest, or Processing work start.

There is no offline cache fallback. A network failure, timeout, rejected
license, or unverifiable response blocks the operation with a concise Russian
message and does not expose keys or raw server responses.

## Application integration

- Replace the legacy `LicenseClient` implementation while keeping a small,
  explicit interface for activation and validation.
- Remove editable license-server URL fields from the normal flow; production
  uses the fixed HTTPS service URL.
- Preserve the existing license entry action, but make its success state come
  only from a verified signed envelope.
- Add one shared authorization gate immediately before the execution boundary
  used by each V3 mode. UI-only checks are insufficient; the operation must
  remain blocked if validation is bypassed or fails.
- Existing user projects, outputs, prompts, API credentials, and settings are
  not migrated or deleted.

## Server boundary

The deployed service continues to own:

- administrator authentication and TOTP;
- product and license creation;
- activation binding to one device;
- license update, suspension, revocation, key rotation, and device release;
- signed authorization responses and audit records.

Desktop code never connects to PostgreSQL or administrator endpoints.

## Verification

Required automated checks:

- device key creation and persistence;
- activation request shape and fresh proof;
- validation request shape and fresh proof;
- valid signed envelope acceptance;
- rejection of tampering, replayed nonce, unknown key ID, wrong product,
  wrong device, expiry, HTTP errors, oversized responses, and non-HTTPS URLs;
- no offline acceptance after network failure;
- all three V3 work modes are blocked before execution without authorization;
- local end-to-end service test: issue license, activate, validate, revoke,
  and confirm subsequent validation fails;
- application regression suite and license-service suite pass;
- Windows workflow builds the V3 executable before Inno Setup and produces a
  setup file plus SHA-256.

The live service health check and a non-destructive test-license flow may be
used for final verification. No customer license is changed and no release is
published as part of the build.

## Delivery

The final local deliverables are:

- `release/ClipartGenerator-Setup-3.0.exe`;
- `release/ClipartGenerator-Setup-3.0.sha256`;
- a concise verification report with tests, build run, artifact hash, and any
  remaining manual clean-install risk.

Commit, push, release publication, and public update-manifest changes require
separate explicit approval.
