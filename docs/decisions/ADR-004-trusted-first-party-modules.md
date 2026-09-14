# ADR-004: Trusted first-party module boundary

Status: Accepted — 2026-09-14

## Context

Vibix Studio is distributed as one paid desktop application with independently entitled modules. A customer may own any subset of official modules; missing modules must not be required for the modules they did buy.

The first release uses one Python/PyQt process. Official module packages are produced and signed by Vibix. Arbitrary third-party executable plugins are outside the first-release scope.

## Decision

The module boundary is a modularity, entitlement, lifecycle and stable-API boundary. It is not a hostile-code sandbox against deliberate same-process Python introspection.

Official module code is trusted first-party code and runs with the desktop application's process privileges after package signature/integrity, compatibility and entitlement checks pass.

Core must still prevent architectural coupling: no Core imports of module implementations, no module-to-module implementation imports, exact capability contracts, independent install/update/disable/uninstall, and preservation of projects/assets when a module is absent.
## Consequences

- Same-process `__globals__`, name-mangling or similar hostile introspection is not an acceptance criterion for official modules.
- Bugs are still contained through narrow APIs, scoped state, Core-owned paid-provider/job admission, error boundaries and regression tests.
- A module may own local UI/worker implementation where appropriate, but paid provider submissions and authoritative project persistence remain Core-governed.
- Entitlement is checked independently per `module_id`; buying one module never implicitly grants another.
- Package signature proves trusted publisher/integrity; entitlement separately decides whether that user may install/activate/run the module.
- If Vibix later accepts third-party untrusted executable plugins, this ADR no longer provides sufficient isolation. That future model requires process/sandbox isolation and a separate security design.

## Review guidance

Code review should treat cross-module imports, entitlement bypass, unsafe lifecycle/update behavior, data loss, Core bypass for paid work, and crashes/regressions as defects. It should not report deliberate same-process Python introspection by trusted official module code as a security-boundary escape.