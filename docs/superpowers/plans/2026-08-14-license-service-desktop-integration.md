# License Service Desktop Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use workflow-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Clipart Generator 3.0 to the deployed signed license service, require online authorization before every V3 run, and produce a verified Windows installer.

**Architecture:** A focused `LicenseClient` owns Ed25519 device identity, HTTPS requests, canonical envelope verification, and local activation state. `V3ApplicationView` owns a shared online authorization gate and injects it into the three existing flow controllers immediately before worker creation. The remote administrator service remains separate and is never bundled into the installer.

**Tech Stack:** Python 3.12, PyQt6, `cryptography` Ed25519, RFC 8785 canonical JSON, `urllib`, `unittest`, PyInstaller, Inno Setup, GitHub Actions.

## Global Constraints

- Production base URL is exactly `https://services.etsyneuroclub.com/licenses`.
- Product ID is exactly `clipart-generator`.
- Server signing key ID is `license-v1`; pinned public key is `2J5W6NVq8-zE5g0MocublzW5aER1hzRqwFLGuzKuwMw`.
- No offline authorization fallback is allowed.
- A protected run must not create or start a worker until online validation succeeds.
- License keys, device private keys, passwords, TOTP values, cookies, and raw sensitive server responses must never be logged.
- The license service, PostgreSQL, and administrator routes are not bundled into the desktop installer.
- No customer license, public release, update manifest, commit, or push is changed without separate approval.

---

## File map

- `license_client.py`: signed protocol, device identity, persistent activation state, bounded HTTPS transport.
- `v3_license.py`: shared online gate and V3 activation dialog/controller.
- `v3_wizard.py`: license action/status signal in the shared shell.
- `v3_mode_selection.py`: construct one gate, open activation UI, and inject authorization into all flows.
- `v3_clipart_flow.py`, `v3_pinterest_flow.py`, `v3_processing_flow.py`: enforce the shared gate before worker creation.
- `main.py`: fixed production client construction and V3 application wiring; remove legacy editable server selection from the release path.
- `requirements.txt`: add exact runtime libraries needed for Ed25519 and RFC 8785 verification.
- `tests/test_license_client_security.py`: protocol, signature, nonce, expiry, URL, size, and no-offline regression coverage.
- `tests/test_v3_license_gate.py`: activation state and friendly error mapping.
- `tests/test_v3_license_flow_gate.py`: all three worker boundaries stay blocked on failed authorization.
- `.github/workflows/release-multi-platform.yml`: run focused license tests before packaging and verify packaged imports.
- `ERROR_LOG.md`: record the previously missed client/server contract mismatch and its regression guard.

### Task 1: Signed protocol client and persistent device identity

**Files:**
- Replace: `license_client.py`
- Modify: `requirements.txt`
- Modify: `tests/test_license_client_security.py`

**Interfaces:**
- Produces: `LicenseClient(base_url: str, state_path: str, public_keys: Mapping[str, str], product_id: str, timeout: int = 10)`.
- Produces: `LicenseClient.activate(license_key: str) -> LicenseAuthorization`.
- Produces: `LicenseClient.validate() -> LicenseAuthorization`.
- Produces: `LicenseClient.has_activation() -> bool`.
- Produces: `LicenseAuthorization(license_id, product_id, device_key, issued_at, expires_at)`.
- Produces: `LicenseError` with a safe user-facing message and no embedded secret.

- [ ] **Step 1: Add failing protocol tests**

Add tests that use a generated Ed25519 server key and a fake bounded JSON response:

```python
client = LicenseClient(
    "https://license.example",
    state_path,
    {"license-v1": encode(server_private.public_key().public_bytes_raw())},
    "clipart-generator",
)
authorization = client.activate("CG-TEST-KEY")
self.assertEqual(authorization.product_id, "clipart-generator")
self.assertNotIn("CG-TEST-KEY", Path(state_path).read_text("utf-8"))
```

Cover invalid signature, unknown `kid`, wrong product, wrong device key, wrong nonce, expired envelope, oversized response, remote HTTP URL, redirect, timeout, and network failure after activation. The last case must raise `LicenseError`, not return cached authorization.

- [ ] **Step 2: Confirm the old client fails the new contract tests**

Run:

```bash
python3 -m unittest tests.test_license_client_security -v
```

Expected: failures because the old client posts `/activate`, uses a fingerprint, and accepts an offline cache.

- [ ] **Step 3: Add runtime dependencies**

Add:

```text
cryptography>=43.0.0,<46.0.0
rfc8785>=0.1.4,<0.2.0
```

- [ ] **Step 4: Implement device identity and state**

Use a versioned JSON file under the app-data directory. Generate a 32-byte Ed25519 private key once, persist it atomically, and apply user-only file permissions where supported. Store only:

```json
{
  "schema_version": 1,
  "device_private_key": "base64url",
  "license_id": "uuid-after-activation"
}
```

The device public key is derived on demand. The reusable license key is never written to disk.

- [ ] **Step 5: Implement signed activation and validation**

For each request generate `nonce = token_urlsafe(32)` and `proof = base64url(private.sign(nonce.encode("utf-8")))`. Post to `/api/v1/licenses/activate` or `/api/v1/licenses/validate`, verify RFC 8785 canonical payload bytes, and compare every returned claim using exact values.

- [ ] **Step 6: Run focused tests**

```bash
python3 -m unittest tests.test_license_client_security -v
```

Expected: all tests pass with zero failures.

- [ ] **Step 7: Inspect diff checkpoint**

Run `git diff -- license_client.py requirements.txt tests/test_license_client_security.py`. Do not commit.

### Task 2: Shared online license gate and activation UI

**Files:**
- Create: `v3_license.py`
- Create: `tests/test_v3_license_gate.py`
- Modify: `v3_wizard.py`
- Modify: `v3_mode_selection.py`
- Modify: `main.py`

**Interfaces:**
- Consumes: `LicenseClient.activate`, `LicenseClient.validate`, and `LicenseClient.has_activation`.
- Produces: `OnlineLicenseGate.activate(key: str) -> LicenseAuthorization`.
- Produces: `OnlineLicenseGate.authorize_run() -> LicenseAuthorization`.
- Produces: `LicenseDialog` that accepts a key transiently and clears its field after submission.
- Produces: `V3ApplicationView(..., license_gate: OnlineLicenseGate | None = None)`.

- [ ] **Step 1: Add failing gate tests**

```python
gate = OnlineLicenseGate(fake_client)
with self.assertRaisesRegex(LicenseError, "Активируйте лицензию"):
    gate.authorize_run()
gate.activate("CG-TEST")
self.assertEqual(gate.authorize_run().license_id, "license-id")
```

Also assert that network and rejection errors map to concise Russian messages without the submitted key or raw response.

- [ ] **Step 2: Implement `OnlineLicenseGate` and dialog**

The gate performs no offline fallback. The dialog shows these states: not activated, activation successful, server unavailable, rejected/revoked, and invalid signed response.

- [ ] **Step 3: Add shared shell license action**

Add `license_requested = pyqtSignal()` to `AppShell`, a top-bar button labeled `Лицензия`, and an accessible status label. Wire the signal in `V3ApplicationView._replace_shell` to the single gate-owned dialog.

- [ ] **Step 4: Construct production client in `main.py`**

Use:

```python
LicenseClient(
    base_url="https://services.etsyneuroclub.com/licenses",
    state_path=os.path.join(app_data, "license_state.json"),
    public_keys={"license-v1": "2J5W6NVq8-zE5g0MocublzW5aER1hzRqwFLGuzKuwMw"},
    product_id="clipart-generator",
    timeout=10,
)
```

Pass one `OnlineLicenseGate` into `V3ApplicationView`.

- [ ] **Step 5: Run gate and release-entrypoint tests**

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_v3_license_gate tests.test_release_entrypoint -v
```

Expected: all tests pass and the V3 application still opens with three mode cards.

- [ ] **Step 6: Inspect diff checkpoint**

Run `git diff -- v3_license.py v3_wizard.py v3_mode_selection.py main.py tests/test_v3_license_gate.py`. Do not commit.

### Task 3: Enforce authorization at every worker boundary

**Files:**
- Modify: `v3_clipart_flow.py`
- Modify: `v3_pinterest_flow.py`
- Modify: `v3_processing_flow.py`
- Create: `tests/test_v3_license_flow_gate.py`

**Interfaces:**
- Consumes: `authorization_provider: Callable[[], LicenseAuthorization]`.
- Produces: each `install_*_flow(..., authorization_provider=...)` and controller constructor accepts the callback.
- Invariant: `worker_factory` and `worker.start()` are unreachable when authorization raises.

- [ ] **Step 1: Add one failing test per V3 mode**

For Clipart, Pinterest, and Processing inject:

```python
authorization = Mock(side_effect=LicenseError("Требуется интернет"))
worker_factory = Mock()
controller.start()
authorization.assert_called_once_with()
worker_factory.assert_not_called()
```

- [ ] **Step 2: Add the authorization callback to controllers**

Invoke the callback in each `start()` after local request validation and immediately before `worker_factory(**request.worker_kwargs())`. Convert `LicenseError` to the existing safe run-status path.

- [ ] **Step 3: Inject one shared callback from `V3ApplicationView`**

Pass `self._license_gate.authorize_run` to all three `install_*_flow` calls. A missing gate in tests defaults to a callback that raises rather than silently authorizing production runs; explicit test doubles may authorize.

- [ ] **Step 4: Run all three flow tests**

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_v3_license_flow_gate tests.test_v3_clipart_flow tests.test_v3_pinterest_flow tests.test_v3_processing_flow -v
```

Expected: all tests pass and failed authorization creates no worker.

- [ ] **Step 5: Inspect diff checkpoint**

Run `git diff -- v3_clipart_flow.py v3_pinterest_flow.py v3_processing_flow.py v3_mode_selection.py tests/test_v3_license_flow_gate.py`. Do not commit.

### Task 4: Cross-project contract and revocation regression

**Files:**
- Create: `tests/test_license_service_contract.py`
- Modify: `/root/projects/Clipart Generator/license-service/tests/test_api.py`
- Modify: `/root/projects/Clipart Generator/license-service/ERROR_LOG.md`
- Modify: `ERROR_LOG.md`

**Interfaces:**
- Consumes: exact production routes and signed envelope schema.
- Produces: a regression that fails if desktop request fields/routes or server response claims drift.

- [ ] **Step 1: Add contract fixture test**

Run a loopback `ThreadingHTTPServer` using a generated server key. Issue a test license, activate with the real desktop client, validate, revoke in the in-memory service, then assert desktop validation raises a safe rejection.

- [ ] **Step 2: Add server-side client contract assertions**

Assert activation accepts `product_id`, `license_key`, `device_key`, `nonce`, and `proof`; validation accepts `license_id`, `product_id`, `device_key`, `nonce`, and `proof`; both return an envelope containing matching product, device, nonce, and expiry.

- [ ] **Step 3: Run both project suites**

```bash
python3 -m unittest tests.test_license_service_contract -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Expected: desktop contract passes; license-service suite passes except only explicitly environment-gated PostgreSQL integration skips.

- [ ] **Step 4: Record root cause and guard**

Document that release packaging previously proceeded while the desktop used the legacy fingerprint contract, and name `tests/test_license_service_contract.py` plus workflow tests as the regression guard. Do not include credentials, live license keys, or raw envelopes.

### Task 5: Security and full regression gate

**Files:**
- Modify if needed: `.github/workflows/release-multi-platform.yml`
- Modify if needed: `build.ps1`

- [ ] **Step 1: Add CI license checks before PyInstaller**

Run the protocol, gate, flow-boundary, and contract tests on Windows before packaging. Add a packaged import check for `cryptography`, `rfc8785`, `license_client`, and `v3_license`.

- [ ] **Step 2: Scan changed code for secret exposure and bypasses**

Inspect all logging, exceptions, state files, redirects, response bounds, and every `worker.start()` call. Confirm there is no old `/activate`, `/validate`, `/status`, fingerprint, or offline-cache authorization path reachable from the release entrypoint.

- [ ] **Step 3: Run focused and broad tests**

```bash
python3 -m unittest tests.test_license_client_security tests.test_v3_license_gate tests.test_v3_license_flow_gate tests.test_license_service_contract -v
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
python3 -m py_compile main.py license_client.py v3_license.py
```

Expected: zero failures. Any environment-only skip must be listed explicitly.

- [ ] **Step 4: Review final diff and status**

Run `git status --short --branch`, `git diff --stat`, and `git diff`. Do not stage or commit.

### Task 6: Build and retrieve Windows installer

**Files:**
- Generated locally after download: `release/ClipartGenerator-Setup-3.0.exe`
- Generated locally after download: `release/ClipartGenerator-Setup-3.0.sha256`

- [ ] **Step 1: Pushless build prerequisite check**

GitHub Actions can build only a remote commit. Because commit and push require separate approval, first present the changed files, diff summary, test results, and secret scan to the user and request explicit commit/push approval.

- [ ] **Step 2: After approval, commit and push the reviewed scope**

Create one intentional feature commit on `codex/license-server` and push only that branch. Do not merge, tag, or publish a Release.

- [ ] **Step 3: Dispatch build-only workflow**

```bash
gh workflow run release-multi-platform.yml --ref codex/license-server --field app_version=3.0
```

- [ ] **Step 4: Wait for Windows job and inspect logs**

Require success for dependency install, license tests, syntax, PyInstaller, V3 entrypoint, Inno Setup, hash calculation, and artifact upload.

- [ ] **Step 5: Download and verify artifact**

Download `windows-3.0`, verify the SHA-256 sidecar matches a fresh local calculation, and place the `.exe` and `.sha256` in `release/` without modifying `version.json`.

- [ ] **Step 6: Final report**

Report artifact paths, byte size, SHA-256, workflow run URL, tests, and remaining clean-Windows manual smoke risk. Do not publish the installer or update the public channel.
