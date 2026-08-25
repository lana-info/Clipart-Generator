# Azure: Windows installer build

`azure-pipelines.yml` is a manual, build-only pipeline. It creates the Windows
installer and publishes only these two files as the `windows-installer` artifact:

- `VibixImages-Setup-<version>.exe`
- `VibixImages-Setup-<version>.sha256`

The pipeline does not publish a GitHub release, deploy the license service, call
paid providers, change accounts, or use project secrets.

## How to run it

1. In Azure DevOps, connect the repository and choose **Pipelines → New pipeline**.
2. Select the repository's existing YAML file: `/azure-pipelines.yml`.
3. Run the pipeline manually from the branch containing this file.
4. Use the requested release version. The current build target is `3.0.5`.
5. When the run succeeds, download the `windows-installer` pipeline artifact.

Azure verifies the Windows build, packaged startup smoke test, installer creation,
and checksum. Installation, DPI/visual behavior, UAC/SmartScreen, and testing
with a real license account still require a real Windows machine.

## Latest successful run

Run `136` completed successfully on 2026-08-25 from branch
`codex/tech-debt-11`. The `windows-installer` artifact contains:

- `VibixImages-Setup-3.0.5.exe`
- `VibixImages-Setup-3.0.5.sha256`

The checksum was verified after downloading the artifact. Manual Windows
installation and visual smoke are still required before public delivery.
