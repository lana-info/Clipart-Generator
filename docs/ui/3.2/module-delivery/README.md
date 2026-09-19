# Module Update Proposal

Implementation checkpoint, 2026-09-19: the owner approved the corrected layout.
`studio_module_update_ui.py` implements the dialog; home wiring is in
`v3_mode_selection.py`. `render_actual.py` captures these real controls using
synthetic releases and controlled background workers, with no provider access.
`actual-available/downloading/verifying/installed/no-access/error.png` are the
implementation comparison at 1120x780. Transfer has real byte-driven progress;
verification uses the animated indeterminate bar (pixel change asserted).
Close is blocked while an operation runs. Open workflows require finishing work
and restarting Studio before their update. Empty publisher trust disables delivery
explicitly. The 9 local TLS integration tests separately exercise actual signed
delivery; screenshots alone are not proof of networking or production readiness.

Status: owner accepted the base layout with two corrections on 2026-09-19:
remove the future-module footer and show visible download progress. Both corrections
are reflected here. These are synthetic 1120x780 Qt mockups, not
working product screens. Regenerate with `render_proposal.py` and the existing
test venv under `QT_QPA_PLATFORM=offscreen`; no license or provider is contacted.

The proposed home action `Обновления модулей` opens one compact window for the
three existing workflows. It shows installed/available versions and exact access.
`Обновить` or `Скачать` starts one selected transfer; package verification precedes
installation. Live projects block activation, while the existing version remains
usable. Errors preserve that version and require an explicit retry. No access
disables delivery. Future modules are not advertised in this window.
The check button concerns modules only. Studio itself retains its separate startup
update notification and installer flow; the footer version is informational.

- `before.png`: current screen with synthetic license status.
- `proposal-available.png`: installed/current/update/download states.
- `proposal-checking.png`: indeterminate indicator while checking releases.
- `proposal-downloading.png`: progress bar, actual percent and received/total MB;
  repeated actions disabled. The snapshot uses synthetic 42%.
- `proposal-verifying.png`: indeterminate indicator during package verification;
  no artificial percentage after the transfer is complete.
- `proposal-busy.png`: activation blocked by a live project.
- `proposal-error.png`: verification failure, previous version preserved.
- `proposal-no-access.png`: delivery disabled by license rights.

Closing the window must not silently start/retry work. Cancellation, rollback
controls and the final activation confirmation need their own complete state
design before implementation if included; they are not approved by these images.
The admin module-release editor is also outside this proposal.
