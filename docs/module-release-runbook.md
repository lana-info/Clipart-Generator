# Official Module Releases

## Trust And Custody

Studio pins `vibix-publisher-v1` in `studio_module_delivery.py`. Only the public
Ed25519 key is committed. Packages cannot add trust keys. License and release
metadata signing remain separate from package signing.

The publisher key was provisioned on 2026-09-19 at
`/root/.local/share/vibix-studio-signing/publisher-v1.pem`, outside all checkouts,
with directory mode 0700 and file mode 0600. Never print, attach, commit or copy
the private key into a build artifact, `.env`, or desktop installation.
There is currently no verified off-host backup. Before production publication,
the operator must arrange secure recovery custody; loss requires a shell release
pinning a new public key. Key rotation/revocation likewise requires a controlled
shell update, not an unsigned server setting.

`studio_module_release.py init-key --key-file <protected-path>` is a one-time
operator command. It refuses to overwrite a key or create one in this checkout,
and prints only its public half. A new public key must be reviewed and pinned in
the shell before `prepare` accepts its private key.

## Preparation

Run from the reviewed Studio checkout with its existing Python environment:

```bash
python studio_module_release.py prepare \
  --key-file /root/.local/share/vibix-studio-signing/publisher-v1.pem \
  --key-id vibix-publisher-v1 \
  --output /absolute/path/to/new-release-directory \
  --version 1.0.0 --studio-min 3.2.0 --studio-max-exclusive 3.3.0 \
  --platform windows-x64 --platform macos-x64
```

This prepares all three existing workflows from explicit inventories, signs each
package, and verifies it with the desktop installer for every declared platform.
It outputs ZIPs and `release-set.json` with SHA-256/size/compatibility. It never
imports payload code, runs providers, sweeps user directories or overwrites an
existing release directory. A filesystem failure may leave an incomplete new
directory; do not publish it without successful verification.

The 2026-09-19 candidate artifacts are in
`/root/projects/Clipart Generator/artifacts/official-modules-1.0.0-20260919`.
These are independently signed workflow packages, not desktop installers.
The legacy generation module is `clipart`; the future automatic collection
workflow remains the separate `auto-clipart` identity.

## Draft Upload

After the module-aware service and migration 012 pass staging acceptance:

```bash
python studio_module_release.py upload-draft /absolute/path/processing-1.0.0.zip \
  --service-url https://services.etsyneuroclub.com/licenses \
  --platform windows-x64 --studio-version 3.2.0
```

The command requires an interactive terminal and prompts privately for admin
password and TOTP; it refuses the echoed-password fallback. Credentials are never
command arguments or saved sessions. HTTPS certificate validation remains enabled;
redirects are refused. Signature, platform, compatibility and package structure
are rechecked before any draft is created. Metadata is extracted from the signed
package, and the exact inspected bytes are uploaded and compared with the server's
hash and size. Repeat explicitly for each module/platform to be released.

No automatic retry or publication occurs. A failure can leave a draft; the command
prints its ID immediately after creation. Inspect that draft in the panel before
retrying. A successful upload remains invisible to desktop manifests until the
administrator publishes it. Use the panel to publish or withdraw releases.

## Acceptance And Recovery

- Test service migration 012 on a disposable database first; production rollout
  must preserve the active deployment override in the service runbook.
- Verify an installed shell trusts the publisher and opens all three workflows;
  check download progress, interruption, bad signature and denied/revoked rights.
- Check existing projects and the separate video product registration unchanged.
- Test Windows installer/update and native UI on Windows; offscreen Linux Qt
  tests do not establish installed Windows acceptance.
- Withdraw published module rows before rolling a server back to code without
  module-aware manifest filtering. Otherwise the old server can advertise ZIPs
  as application updates. Withdrawing a release does not uninstall active code.
- A known installed prior module can be restored via the verified runtime
  rollback API when no workflow owns an active lease. There is no user-facing
  rollback control in the current update dialog.

No production artifacts or customer releases were published during preparation.
