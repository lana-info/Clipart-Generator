# PiAPI balance diagnostics, 2026-10-15

Owner requirement: failures must identify the operation, stage and available cause, not only a generic error. Record actual HTTP status when observed, expected balance field, bounded response field/type schema and correlation ID. Never include credentials, scalar account values, raw response, prompts or images. Unknown causes must remain explicitly unknown.

Implemented on branch codex/fix-piapi-balance-diagnostics-20261015 from Studio 3.2.25 source 8ffed97. API-settings worker now records balance start/success/failure directly into the existing journal; ZIP export retains these records. Unknown JSON field names are masked; only approved field names/types are retained. Numeric balances and existing supported balance schemas are unchanged.

Checks: the targeted backend, transport, Qt, journal, ZIP and API-settings regression suite passed before this document was written. Exact output: ../artifacts/piapi-balance-diagnostics-20261015/regression-tests.log (outside Git).

Not verified: the actual account response and balance on the owner's device. This change enables diagnosis; it is not evidence that the reported balance parsing issue has been fixed. No paid API requests, installer build, deployment or publication were performed. Studio 3.2.25 remains the published release.

## Studio 3.2.26 publication, 2026-10-15

Windows x64 and Mac Apple Silicon Core stable 3.2.26 were built, verified and published from source 33a717d. Native build 38792120951 and full Desktop CI 38792121825 SUCCESS. Native transport/Qt/journal/ZIP regressions are included in the release workflow. Both stored SHA and update selection checks passed; service health 200 and invalid token 403. Verified 0600 database backup retained; previous releases and modules preserved. No paid requests. Owner-device acceptance remains pending. Evidence is retained outside Git in ../artifacts/studio-3.2.26-stable-20261015/.
