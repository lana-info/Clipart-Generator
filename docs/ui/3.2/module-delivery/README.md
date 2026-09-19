# Module Update Proposal

Status: awaiting owner approval. These are synthetic 1120x780 Qt mockups, not
working product screens. Regenerate with `render_proposal.py` and the existing
test venv under `QT_QPA_PLATFORM=offscreen`; no license or provider is contacted.

The proposed home action `Обновления модулей` opens one compact window for the
three existing workflows. It shows installed/available versions and exact access.
`Обновить` or `Скачать` starts one selected transfer; package verification precedes
installation. Live projects block activation, while the existing version remains
usable. Errors preserve that version and require an explicit retry. No access
disables delivery. Future automatic Clipart/Patterns/Mockups stay unreleased.

- `before.png`: current screen with synthetic license status.
- `proposal-available.png`: installed/current/update/download states.
- `proposal-downloading.png`: transfer progress; repeated actions disabled.
- `proposal-busy.png`: activation blocked by a live project.
- `proposal-error.png`: verification failure, previous version preserved.
- `proposal-no-access.png`: delivery disabled by license rights.

Closing the window must not silently start/retry work. Cancellation, rollback
controls and the final activation confirmation need their own complete state
design before implementation if included; they are not approved by these images.
The admin module-release editor is also outside this proposal.
