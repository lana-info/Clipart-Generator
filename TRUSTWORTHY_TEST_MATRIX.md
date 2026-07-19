# Trustworthy Test Matrix

This matrix describes the application's real user-facing features and the
test evidence required for each one. The target is observable behavior and
failure safety, not a coverage percentage.

| Feature | Business risk | Primary evidence | Negative/boundary evidence |
| --- | --- | --- | --- |
| KIE image generation | A prompt can produce the wrong model, payload, task state, or output file. | `tests/test_trustworthy_feature_contracts.py` checks prompt/reference payloads, task routing, polling, result URL extraction, and a network-free generation-to-PNG publication flow. | `tests/test_kie_routing.py` checks missing keys, provider errors, malformed output, cancellation, and secret-safe errors. |
| Local processing and upscale | Processing can corrupt alpha, dimensions, or the selected order. | `tests/test_local_processing_acceptance.py` and `tests/test_upscale_positions.py` check Real-ESRGAN 2x/4x, alpha, Unsharp, edge shrink, trim, and order. | `tests/test_security_boundaries.py` checks animated and oversized local inputs; local failure and missing tool cases are covered by acceptance tests. |
| Image/data validation | Invalid or hostile data can reach a provider/model or replace a valid output. | `tests/test_metadata_inspector.py`, `tests/test_c2pa_inspector.py`, and provider tests validate supported images and metadata. | Corrupt, animated, oversized, decompression-bomb, malformed metadata, and bounded-response cases are rejected without publication. |
| Prompt, CSV, and references preparation | Imported prompts or references can be silently changed or misrouted. | `tests/test_trustworthy_feature_contracts.py` checks BOM, delimiter detection, quoted commas, blank rows, JSON prompt entries, and reference limits. | Empty CSV, missing usable prompt, too many references, and missing local reference behavior are asserted. |
| Settings and compatibility | A saved setting can silently change the next run or break legacy configs. | `tests/test_main_ui_acceptance.py`, `tests/test_cleanup_ui.py`, and `tests/test_upscale_positions.py` cover persistence and legacy defaults. | Invalid/absent fields, disabled-step behavior, and before/after/both upscale settings are covered. |
| Final output and cleanup | A partial/corrupt result can overwrite a previous valid file. | `tests/test_final_save_cleanup.py` and `tests/test_metadata_cleanup_acceptance.py` cover atomic final save, pixels/alpha, ICC/DPI, raw/output, and combined cleanup. | Cancellation, cleanup failure, invalid provider output, C2PA restrictions, and existing-output preservation are asserted. |
| License lifecycle | A valid user can be locked out or an invalid license can be accepted offline. | `tests/test_license_client_security.py` checks cache creation, restart/offline validation, and expiration. | Remote HTTP, ambiguous POST failure, oversized response, malformed response, and route fallback rules are asserted. |
| Update/publication boundary | An unsafe or partial installer download can be executed. | `tests/test_security_boundaries.py` checks verified installer bytes and SHA-256. | HTTP/credential URLs, oversized manifest/installer, checksum mismatch cleanup, and HTTPS redirect constraints are asserted. No release or GitHub publication is part of this suite. |

## Trust Controls

- External API calls are stubbed or intercepted; tests do not spend credits.
- Provider and license secrets are test-only markers and must not appear in
  logs or failure bodies.
- Tests assert files, decoded pixels, alpha, dimensions, payloads, task states,
  and request counts where those are part of the user-visible contract.
- Negative controls must fail when the relevant guard is deliberately bypassed;
  a green test alone is not considered proof.

## Current Verification

- Python compilation of changed modules and tests passes in the available
  bundled runtime.
- The full project test command is recorded in `TASKS.md` and passes `198/198`
  in the project's local `.venv`. The bundled Codex runtime itself lacks
  project dependencies `PyQt6` and `cv2`.
- The pure-Python license suite passes 7/7.
- No network, paid request, release, commit, or push is performed by this
  testing task.
