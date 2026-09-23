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
  --version 1.1.0 --studio-min 3.2.1 --studio-max-exclusive 3.3.0 \
  --platform windows-x64 --platform macos-x64
```

This prepares four workflows (including `auto-clipart`) and the shared
`image-processing` component from explicit inventories, signs each
package, and verifies it with the desktop installer for every declared platform.
It outputs ZIPs and `release-set.json` with SHA-256/size/compatibility. It never
imports payload code, runs providers, sweeps user directories or overwrites an
existing release directory. A filesystem failure may leave an incomplete new
directory; do not publish it without successful verification.

The 2026-09-19 candidate artifacts are in
`/root/projects/Clipart Generator/artifacts/official-modules-1.0.0-20260919`.
These are independently signed workflow packages, not desktop installers.
Those historical artifacts contain only the three legacy workflows. The legacy
generation module is `clipart`; automatic collections use `auto-clipart` and must
be packaged from the new source checkpoint. Its payload includes the automatic
controller and a package-local copy of the reused generation controller, so an
ordinary generator update cannot silently replace that base. The eight-step Core
shell, state adapter and export services remain dependencies of the shell.
New packages also own planning/prompt dependencies listed below.
Do not offer this package to the historical 3.2.0 test installer: it lacks that
Core composition. The current test packages use minimum Studio 3.2.1, keeping
older installers on their compatible legacy module releases. A new installed
acceptance build is required before production publication of automatic Clipart.

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
- Verify an installed shell trusts the publisher and opens all four workflows;
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

## Shared processing bridge and independent news (2026-09-23)

This implementation has not been deployed or built into an installed release.
Deploy the compatible service and additive migration013 before distributing the
new Studio bridge. The older service does not derive shared-component download
rights from workflow entitlements. Historical Studio3.2.1 packages do not imply
that the installed shell supports this new API: choose a new approved bridge
release version and set all new packages' studio-min accordingly. Do not publish
using the older example version bounds above without that compatibility check.

The component contains `studio_processing_engine.py`, `chroma_key.py`,
`chroma_rim.py` and `chroma_profile.py`. Shell-owned `studio_processing_api.py`
defines API1 and result validation; worker dispatch, credentials and receipts stay
in Studio. The selected engine reports its actual profile to receipts. Built-in
v9 remains available before first component installation. Once selected, an
invalid component produces an error instead of silently using another algorithm.

Automatic Clipart includes its builder/planning UI, text client, planner, object
compiler, commercial/style/holiday guidance and prompt generator/schema. Ordinary
Generation owns its generator/schema. Packaging rewrites inventory-local imports
and eagerly loads helpers within the runtime callback to avoid later bytecode
writes in immutable verified package directories.

The Updates dialog still has four workflow rows. A consumer check discovers both
its workflow release and the shared processing release. The existing Update button
stages both and atomically activates them, or updates only the engine if that is
the sole available change. Active engine jobs or live updated workflow pages block
activation. Failure restores previous pointers and loaded code. A live entitlement
for any consumer allows component download; it never unlocks another workflow.

To prepare only an algorithm update, use the existing single-package tool after
explicit artifact/release authorization (placeholders require approved values):

```bash
python studio_module_packaging.py --module image-processing \
  --version <component-version> --studio-min <bridge-version> \
  --studio-max-exclusive <incompatible-version> \
  --platform windows-x64 --platform macos-x64 \
  --key-id vibix-publisher-v1 --signing-key-file <protected-key-path> \
  --output <new-absolute-zip-path>
```

Upload the verified ZIP using `studio_module_release.py upload-draft`, then review
and publish that component revision only. Workflow package versions need not
change for a compatible algorithm update. Compatibility-breaking API changes
still require a coordinated Studio release. Never store the private key in Git.

News needs no ZIP or application version bump after this bridge is installed.
In admin choose «Новости Studio», enter a title and body, save a draft or publish.
To edit published text, withdraw it first. The latest published announcement is
shown; withdrawing it may reveal an older still-published announcement. Withdraw
all to clear the home feed. Text is plain (100/600 characters), without executable
HTML. Publication date is server-generated. Studio refreshes at startup/every10min
and keeps its last received announcement offline. Changes reach offline users
when they next connect. A valid license/device is required; an expired update
entitlement does not prevent reading news.

Source verification: full PostgreSQL service suite, signed local HTTPS delivery,
component-only updates, grouped rollback, rights/revocation, worker leases,
package-local prompt execution, and Chrome/offscreen news scenarios. See STATE.md
for counts and `docs/ui/3.1/independent-components-news/` for approved/actual views.
Installed Windows, final signed production artifacts and deployment are separate
acceptance steps and were not executed by these source checks.
