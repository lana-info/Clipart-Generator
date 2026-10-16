# PiAPI task envelope correction, 2026-10-15

Confirmed defect in published Studio 3.2.26: real GET /api/v1/task responses place status and output inside data. The adapter inspected top-level status and returned pending even when data.status was completed.

Correction: unwrap the PiAPI data record for status, output and failure details. Preserve the legacy flat response and AtlasCloud behavior; leave the submit adapter unchanged. New regressions fail before the fix and pass afterward, including restart recovery via GET without a second POST. Existing provider, recovery and Qt diagnostic regression modules pass in isolated processes.

The live check queried four existing task IDs and submitted zero new generations. Accepted completed result URLs: 0 of 4 at verification time. Metadata-only evidence and test logs: ../artifacts/piapi-task-envelope-fix-20261015/. No credentials, image URLs or account values are included. No images were downloaded.

The installer has not been rebuilt or published. Owner-device acceptance remains pending. Blanket HTTP 400/404/410 expiry classification is a separate unresolved issue, not established as the cause of the four completed-task failures.
