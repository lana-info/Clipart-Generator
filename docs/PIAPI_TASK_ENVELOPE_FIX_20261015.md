# PiAPI task envelope correction, 2026-10-15

Confirmed defect in published Studio 3.2.26: real GET /api/v1/task responses place status and output inside data. The adapter inspected top-level status and returned pending even when data.status was completed.

Correction: unwrap the PiAPI data record for status, output and failure details. Preserve the legacy flat response and AtlasCloud behavior; leave the submit adapter unchanged. New regressions fail before the fix and pass afterward, including restart recovery via GET without a second POST. Existing provider, recovery and Qt diagnostic regression modules pass in isolated processes.

The live check queried four existing task IDs and submitted zero new generations. Accepted completed result URLs: 0 of 4 at verification time. Metadata-only evidence and test logs: ../artifacts/piapi-task-envelope-fix-20261015/. No credentials, image URLs or account values are included. No images were downloaded.

The installer has not been rebuilt or published. Owner-device acceptance remains pending. Blanket HTTP 400/404/410 expiry classification is a separate unresolved issue, not established as the cause of the four completed-task failures.

## Published Studio3.2.27

## Studio 3.2.27 stable published, 2026-10-15

Windows x64 and Mac Apple Silicon published from source3ef706543d8aef5ed216d0a7ac2f5d1fbbb2a8f0. Native build38831433270 and repeated fullCI38831432277 SUCCESS. Version/SHA/provenance and native/frozen/installed checks passed. New regression covers nested PiAPI task status/output and GET-only recovery. Server storedSHA2/2 and stable/latest discovery PASS; health200 and invalid-token403. Verified0600 database backup retained. Previous releases/modules preserved. Evidence: ../artifacts/studio-3.2.27-stable-20261015/.

Initial fullCI failed on unchanged legacy-blue chroma byte baseline (3440PASS/1FAIL); the same-source failed job was repeated without changing tests or golden bytes. Its instability is not established as fixed. Release status bookkeeping error was corrected without rebuilding installers.

No new paid generation was submitted. Prior tasks returned HTTP400; their images were not restored. Owner-device generation and saving remain unverified; blanket HTTP400/404/410 expiry classification remains a separate unresolved issue. Mac: Apple Silicon, ad-hoc signed, no notarization.
