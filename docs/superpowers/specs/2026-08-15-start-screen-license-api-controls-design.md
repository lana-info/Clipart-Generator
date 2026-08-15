# Start-screen license and API controls design

## Goal

Before a work mode is selected, the first screen must show the current license state and provide direct access to license replacement and API settings.

## UI

A compact card is placed at the top of `ModeSelectionScreen`, above the mode prompt. It contains:

- `Лицензия: <status>`;
- `Проверено онлайн: <server time>` after a successful signed authorization, otherwise `Онлайн-проверка не выполнена`;
- `Сменить лицензию` button;
- `Настройки API` button.

The full license key and license identifier are never displayed. The authorization expiry is not presented as the purchased license term: the current server contract only exposes a five-minute signed authorization envelope, not the commercial license expiration.

## State and interactions

`OnlineLicenseGate` retains only the latest in-memory `LicenseAuthorization`. Successful activation or validation updates it; failures clear it. The mode-selection card reads the safe status and verification timestamp from the gate.

`V3ApplicationView` connects both start-screen buttons to the existing license and API dialogs. It refreshes both the start-screen card and the wizard top bar after startup validation and after a license dialog closes. The packaged startup factory explicitly refreshes the card after successful online authorization because the view is constructed before that check.

## Security and failure behavior

- No reusable license key is stored or rendered.
- No offline fallback is introduced.
- A failed online check cannot be shown as successful.
- Existing worker-level online checks remain unchanged.
- API secrets continue to use the existing settings dialog and credential-store behavior.

## Verification

Add regression tests for the visible controls, emitted actions, safe status text, in-memory authorization tracking, and startup refresh. Run targeted UI/licensing tests, the packaged-entrypoint smoke check, then the full suite.
