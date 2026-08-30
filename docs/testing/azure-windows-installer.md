# Azure: Windows installer build

`azure-pipelines.yml` is a manual, Windows-only fallback pipeline. The preferred
3.1.0 candidate path is the manual GitHub Actions workflow
`release-multi-platform.yml`; use Azure only when that workflow is unavailable.
Azure creates the installer and publishes the build evidence as the
`windows-installer` artifact, including at least:

- `VibixImages-Setup-<version>.exe`
- `VibixImages-Setup-<version>.sha256`

The pipeline does not publish a GitHub release, deploy the license service, call
paid providers, change accounts, or use project secrets.

## How to run it

1. In Azure DevOps, connect the repository and choose **Pipelines → New pipeline**.
2. Select the repository's existing YAML file: `/azure-pipelines.yml`.
3. Run the pipeline manually from the branch containing this file.
4. Keep the version as `3.1.0` for the current release candidate unless another
   version is intentionally requested.
5. When the run succeeds, download the `windows-installer` pipeline artifact.

Azure verifies the Windows build, packaged startup smoke test, installer creation,
checksum and available staged UI evidence. Installation, visual behavior,
UAC/SmartScreen, credentials, outage grace and testing with a real license
account still require the checklist on a real Windows machine. Neither this
pipeline nor the GitHub workflow publishes an update or authorizes a paid
provider request.
