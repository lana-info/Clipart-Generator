# License and Update Service PRD

Status: Draft for approval

Updated: 2026-08-12

Implementation: Not started

## 1. Purpose

Create one self-hosted service on the existing VDS and an existing domain for
licensing and future update delivery for Clipart Generator and, later, other
desktop products.

The first version must use only the infrastructure already available to the
owner. It must not require paid APIs, paid storage, a new server, deployment, or
release publication during the design and implementation stages.

## 2. Confirmed business rules

- One license permits exactly one active device.
- A customer cannot reset or release a device from the application or a public
  web page.
- A customer may ask the owner to transfer the license to another device.
- Only an authenticated administrator can reset a device binding.
- After an administrative reset, the old device is no longer licensed; the
  customer may activate the new device.
- The application requires a successful online license check. There is no
  offline grace period and no offline license cache that grants access.
- The owner generates license keys in the administrative panel.
- License duration is not decided yet and must remain configurable.
- Update entitlement duration is not decided yet and must remain configurable
  independently from license duration.
- The private GitHub updates repository is not an active delivery channel.
- Existing public releases and the existing `version.json` must not be changed
  by this project without a separate release decision.

## 3. Product scope

### 3.1 First product

- Product code: `clipart-generator`.
- Default device limit: fixed to `1`.
- Initial client integration: Windows x64.
- The data model reserves `macos-arm64` as a future platform value; this does
  not claim that a packaged macOS client is currently supported.

### 3.2 Multiple products

The service must separate products, licenses, releases, and artifacts by a
stable `product_id`. A license for one product must never authorize another
product unless an explicit future entitlement model is approved.

## 4. Free first-stage infrastructure

- Existing VDS.
- Existing domain; recommended subdomain: `licenses.<your-domain>`.
  It is broad enough for licensing, administration, release manifests, and
  downloads for multiple products. The final hostname remains an owner
  decision and must be configured during staging setup.
- Free TLS certificate with automatic renewal.
- Reverse proxy terminating HTTPS.
- One isolated application service.
- One isolated PostgreSQL database and database user. Existing databases from
  other projects must not be reused.
- Installer files stored outside Git on the VDS with a retention limit.
- Encrypted backups stored outside the application container. A copy on the
  same VDS alone is not considered a complete disaster-recovery backup.
- Before production, select a no-new-cost off-VDS backup target already
  controlled by the owner, such as an owner computer or existing storage, and
  prove a restore from that copy.

The VDS currently has limited free disk space, so only current and explicitly
retained installer versions may be stored locally. Object storage is a future
option, not a first-stage dependency.

## 5. Service boundaries

Suggested public routes under one HTTPS subdomain:

```text
/api/v1/licenses/activate
/api/v1/licenses/validate
/api/v1/releases/{product}/{platform}
/downloads/{short_lived_token}
/health
```

Administrative routes are not public client routes. They must be protected by
administrator authentication. Production access must also be limited to an
owner-controlled network path where the existing VDS setup permits it:

```text
/admin/products
/admin/licenses
/admin/devices
/admin/releases
/admin/audit
```

There is no public or desktop-client `/reset` endpoint.

## 6. Administrative panel

The owner must be able to:

- sign in securely;
- generate one license key or a batch of keys;
- select the product;
- set a license start and expiry date, or mark it perpetual if that policy is
  approved later;
- set a separate updates-entitlement date, or mark it perpetual if approved;
- attach an internal order/customer reference and an administrative note;
- search and filter licenses;
- view license status and the active device;
- suspend, reactivate, or permanently revoke a license;
- reset the active device binding manually;
- extend license or update entitlement dates;
- view an audit history of all administrative actions;
- create release records and attach installer metadata when update delivery is
  approved.

For Clipart Generator, the normal form must keep the device limit at one rather
than exposing an easy-to-change field.

The full key is shown only at creation/export time. Routine lists display a
safe key identifier and suffix, never the reusable key value.

There is no public administrator registration. The first administrator is
created through a local VDS command or a one-time bootstrap procedure. Free
TOTP two-factor authentication and recovery codes are required before
production. Key export, device reset, suspension, revocation, release
publication, and signing-key operations require recent re-authentication.

## 7. License lifecycle

### 7.1 Generation

1. Administrator selects a product and license terms.
2. Server creates a cryptographically random key.
3. Server stores a lookup-safe protected representation, not a plaintext key.
4. The panel displays the full key once for delivery to the customer.
5. Creation is written to the audit log without recording the full key.

### 7.2 Activation

1. On first use, the installation creates an Ed25519 device key pair. In v1,
   the serialized private key is encrypted for the current Windows user with
   DPAPI; it is not described as a hardware-backed or non-exportable CNG key.
   Only the public key and privacy-bounded device metadata are sent to the
   server.
2. Client sends product, license key, application version, device public key,
   and a signature over a fresh server challenge.
3. Server validates the challenge, product, key status, time limits, and device
   binding in one database transaction.
4. If there is no active device, the server creates the binding.
5. If that device public key is already active, activation succeeds.
6. If another device is active, activation fails.
7. Server returns a short-lived, digitally signed activation response bound to
   product, activation, device public key, application version/policy, audience,
   nonce, issue/expiry times, and signing-key identifier (`kid`).
8. Client verifies the response with an embedded public key.

The reusable license key is used only for initial activation or an explicitly
approved reactivation. Later validation uses the activation identity, a fresh
nonce/challenge, and proof of possession of the device private key.

### 7.3 Continuous online validation

- A fresh successful server round-trip is mandatory at application startup.
- Every protected generation or processing operation requires another fresh
  server round-trip immediately before it starts. A previous signed response,
  even if unexpired, never authorizes a later operation while offline.
- Periodic revalidation while the application is open is an additional health
  check, not a substitute for the per-operation check.
- If the server cannot be reached, no new protected operation starts.
- If connectivity or authorization is lost during an active operation, the
  operation stops at the next safe non-destructive boundary. Completed outputs
  are preserved, corrupt or partial output is not published, and no next item
  starts.
- A local cache may store UI information but must never authorize offline use.

### 7.4 Administrative device transfer

1. Customer contacts the owner outside the desktop application.
2. Administrator finds the license and reviews its history.
3. Administrator confirms the reset and records a reason.
4. Server marks the old activation as released and revokes its sessions.
5. Customer activates the new device normally.

## 8. Security requirements

- HTTPS is mandatory; plain remote HTTP is rejected.
- Server signing private keys and administrative credentials never enter the
  desktop application or Git.
- The desktop application contains only public server verification keys and
  its OS-protected per-install device private key.
- License responses and update manifests are digitally signed.
- V1 license responses and update manifests use Ed25519 detached signatures
  over RFC 8785 canonical JSON encoded as UTF-8. They use separate signing
  keys. Every signed envelope contains `schema_version`, `algorithm`, `kid`,
  `payload`, and `signature`; public-key rollover, private-key backup, rotation,
  and revocation are documented and tested before production.
- V1 device challenge proof also uses Ed25519 and a versioned API contract.
  Algorithm fields remain explicit so a later version can migrate without
  silently changing verification rules.
- License keys contain at least 128 bits of entropy from an operating-system
  cryptographically secure random generator. Predictable or sequential serial
  numbers are prohibited.
- License lookup uses a server-secret HMAC and a versioned secret; verification
  uses a separate protected hash. Secret rotation must not expose plaintext
  keys or make existing licenses unverifiable.
- Plaintext reusable license keys are not stored in logs or routine database
  fields.
- Administrative passwords use a modern password hash.
- Administrator sessions use secure, HTTP-only, same-site cookies, CSRF
  protection, expiry, and login rate limiting.
- Two-factor authentication must be supported before production use.
- Activation, validation, login, key generation, device reset, revocation, and
  release changes are rate-limited and audited.
- Concurrent activation requests cannot create more than one active device.
- Responses are bounded and errors do not disclose keys, credentials, internal
  paths, SQL, or provider bodies.
- Database, signing keys, backups, artifacts, and logs are excluded from Git.
- The legacy local `licenses.db` is removed from future source tracking; its
  contents must not be printed or copied into documentation.
- Desktop controls make bypass harder but cannot make a Python desktop client
  impossible to patch. Server-side state, per-operation validation, device-key
  proof, rate limits, and audit evidence are the authoritative controls.
- The service-level installer signature is a free Ed25519 signature over the
  published artifact metadata and SHA-256 digest. It is separate from Windows
  Authenticode code signing. Authenticode may reduce Windows reputation
  warnings but can require a paid certificate and is not a dependency of the
  free first stage.

## 9. Proposed database model

### `products`

- `id` UUID primary key
- `code` unique stable product code
- `name`
- `status`
- `created_at`, `updated_at`

### `licenses`

- `id` UUID primary key
- `product_id` foreign key
- `key_lookup_hmac` unique HMAC lookup value
- `key_secret_version` for controlled server-secret rotation
- `key_verifier_hash` protected verification value
- `key_suffix` safe display suffix
- `status`: `active`, `suspended`, `revoked`
- `starts_at`, nullable `expires_at`
- nullable `updates_until`
- `max_devices` constrained to `1` for Clipart Generator
- nullable `customer_reference`, `order_reference`, `admin_note`
- `created_at`, `updated_at`, nullable `revoked_at`

Expiry is an effective state computed from `expires_at`, not a stored status
that can drift from time. Administrative lists and API responses expose the
effective state consistently.

### `device_activations`

- `id` UUID primary key
- `license_id` foreign key
- `device_public_key`, `device_key_algorithm`
- `device_key_format_version`
- nullable privacy-bounded `device_hash` for diagnostics only
- nullable safe `device_label`
- `status`: `active`, `released`, `blocked`
- `activated_at`, `last_seen_at`, nullable `released_at`
- nullable `released_by_admin_id`, `release_reason`

PostgreSQL must enforce at most one active activation per license with a partial
unique index equivalent to:

```sql
CREATE UNIQUE INDEX one_active_device_per_license
ON device_activations (license_id)
WHERE status = 'active';
```

Activation and administrative release also run in explicit transactions; the
application-layer check is not the only concurrency control.

### `license_sessions`

- `id` UUID primary key
- `license_id`, `activation_id`
- `token_id_hash`
- `issued_at`, `expires_at`, nullable `revoked_at`
- `last_seen_at`

### `administrators`

- `id` UUID primary key
- unique normalized `email`
- `password_hash`
- encrypted or protected two-factor secret
- `status`, `created_at`, `last_login_at`

### `audit_events`

- `id` UUID primary key
- event type and timestamp
- nullable product, license, activation, release, and administrator references
- safe subject identifier
- bounded metadata without secrets or full license keys
- request correlation identifier and privacy-bounded source information

### `releases`

- `id` UUID primary key
- `product_id`
- semantic `version`
- `channel`: initially `stable`; future `beta` supported
- `platform`, `minimum_supported_version`
- `status`: `draft`, `published`, `withdrawn`
- nullable `published_at`, release notes

The tuple `(product_id, version, channel, platform)` is unique.

### `release_artifacts`

- `id` UUID primary key
- `release_id`
- private storage path and safe filename
- `size_bytes`, `sha256`, digital signature
- `signature_schema_version`, `signature_algorithm`, `signing_key_id`
- `created_at`

### `download_tokens`

- `id` UUID primary key
- `license_id`, `artifact_id`
- unique token hash
- `created_at`, `expires_at`, nullable `used_at` or bounded usage counter

## 10. Update delivery boundary

Update delivery is designed now but implemented only after licensing is stable
and update terms are approved.

- Client requests the current release for its product and platform.
- Server verifies the license and `updates_until` policy.
- Server returns a signed manifest and short-lived download URL.
- Client verifies manifest signature, HTTPS, file size, SHA-256, and artifact
  signature before offering installation.
- Installer launch requires explicit user confirmation.
- The old GitHub updates URL, release scripts, and manifest are not modified
  until a separate migration and release plan is approved.

## 11. Out of scope for the first implementation

- Payments and automatic key delivery after purchase.
- Customer accounts or customer self-service device reset.
- Offline authorization.
- Paid object storage, CDN, email, SMS, or external authentication APIs.
- Multiple active devices per Clipart Generator license.
- Deployment to production before staging and security review.
- Automatic release/build publication.
- Changes to existing public GitHub releases.

## 12. Open business decisions

- Exact production subdomain; recommendation: `licenses.<your-domain>`.
- Perpetual purchase or time-limited subscription.
- Default license duration.
- Whether updates are perpetual or limited to a separate entitlement period.
- Whether an expired update entitlement allows use of the last eligible version.
- Customer/order reference fields required in the panel.

These decisions must be configuration and data-policy choices, not hard-coded
assumptions in the desktop application.

## 13. Acceptance criteria before production

- A key can be generated only by an authenticated administrator.
- A generated Clipart Generator key activates exactly one device.
- A second device is rejected under concurrent and sequential attempts.
- No public/client operation can reset a device.
- Administrative reset releases the old device and permits one new activation.
- Revoked, suspended, expired, wrong-product, and unknown keys fail closed.
- Disconnecting immediately after a successful validation blocks the next
  protected operation; no offline cache or unexpired prior response grants
  access.
- Every generation and processing entry point, including batch and mixed
  workflows, is covered by the same fresh per-operation gate.
- Signed authorization cannot be changed without detection.
- Full keys and secrets are absent from logs, API errors, reports, and Git.
- Admin bootstrap, TOTP, recovery, re-authentication, rate limits, and audit
  events are tested.
- An encrypted off-VDS backup and a successful restore test are production
  prerequisites.
- Installer metadata and downloads cannot be accessed without entitlement when
  update delivery is enabled.
- Existing generation and processing behavior is unchanged except for the
  approved license gate.
- Linux automated tests and Windows packaged-client checks pass before release.

## 14. Delivery rule

Server implementation should live in a separate private repository so server
secrets, deployment configuration, database migrations, and administration code
do not become part of the desktop distribution. This repository retains the
client integration contract and product-side acceptance documentation.
