# Vibix Images Windows Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Replace the visible Windows product identity `Clipart Generator` with the approved `Vibix Images` name, icon, and branded Inno Setup installer while keeping the release channel Windows-only.

**Architecture:** Store the approved SVG as the source asset and generate a multi-resolution ICO used by both PyInstaller and Inno Setup. Centralize the visible application name in `main.py`, update the Windows build and installer configuration to use the same constants, and keep historical release documentation and update-service contracts unchanged unless they are active packaging paths.

**Tech Stack:** PyQt6, PyInstaller, Inno Setup, PowerShell, SVG/ICO assets, Python unittest.

**Spec:** `docs/superpowers/specs/2026-08-17-vibix-shared-mark-design.md`

## Global Constraints

- Product name: `Vibix Images`.
- Subtitle: `AI Image Generation & Processing`.
- Shared family mark: a solid white `V` plus one separate dark pixel at the lower right, aligned to the same lower baseline.
- The canonical SVG geometry is the approved geometry in `docs/brand/vibix-shared-mark.svg`.
- Windows is the only release target for this change.
- Do not commit generated installers, build directories, API keys, or user data.
- Do not run GitHub Actions or create a release as part of this implementation.

### Task 1: Add the Windows brand assets and runtime name constants

**Files:**
- Create: `app_identity.py`
- Create: `assets/vibix-images.svg`
- Create: `assets/vibix-images.ico`
- Modify: `main.py`
- Modify: `v3_mode_selection.py`
- Test: `tests/test_branding.py`

**Interfaces:**
- `app_identity.APP_NAME` is the single visible product name consumed by window titles and user-facing runtime strings; `main` re-exports it for existing callers.
- `v3_mode_selection.default_work_directory()` returns a `Path` ending in `Vibix Images`.

- [x] **Step 1: Write failing branding tests**

```python
def test_approved_product_identity_and_default_folder():
    import main
    from v3_mode_selection import default_work_directory

    assert main.APP_NAME == "Vibix Images"
    assert default_work_directory().name == "Vibix Images"


def test_icon_source_has_approved_geometry():
    from pathlib import Path

    svg = Path("assets/vibix-images.svg").read_text(encoding="utf-8")
    assert "M21 28H40L54 69L68 28H86L62 82H46Z" in svg
    assert 'x="83" y="69" width="13" height="13"' in svg
```

Run: `python3 -m unittest tests.test_branding -v`
Expected: FAIL because the constants and asset do not exist yet.

- [x] **Step 2: Add the approved SVG and generate the ICO**

Copy the approved geometry into `assets/vibix-images.svg`, using `#2DD4BF` for
the tile, `#FFFFFF` for the `V`, and `#0F766E` for the pixel. Generate
`assets/vibix-images.ico` at 16, 24, 32, 48, 64, 128, and 256 pixels from that
SVG with the available local image conversion tool; do not redraw the mark.

- [x] **Step 3: Centralize the runtime name and use the new default folder**

Add `APP_NAME = "Vibix Images"` next to `APP_VERSION`, replace the two main
window title strings and the startup diagnostic sentence with `APP_NAME`, and
change the V3 Pictures default suffix to `Vibix Images`. Keep the license
product id and update manifest URL unchanged because they are server contracts.

- [x] **Step 4: Run the branding tests**

Run: `python3 -m unittest tests.test_branding -v`
Expected: PASS.

- [x] **Step 5: Commit the assets and runtime identity**

```bash
git add assets/vibix-images.svg assets/vibix-images.ico main.py v3_mode_selection.py tests/test_branding.py
git commit -m "feat: add Vibix Images runtime branding"
```

### Task 2: Apply branding to PyInstaller and Inno Setup

**Files:**
- Modify: `build.ps1`
- Modify: `installer.iss`
- Test: `tests/test_branding.py`

**Interfaces:**
- PyInstaller output directory: `dist\Vibix Images`.
- Packaged executable: `Vibix Images.exe`.
- Installer output: `release\VibixImages-Setup-{AppVersion}.exe`.

- [x] **Step 1: Add build and installer assertions**

```python
def test_windows_packaging_uses_vibix_identity():
    from pathlib import Path

    build = Path("build.ps1").read_text(encoding="utf-8")
    installer = Path("installer.iss").read_text(encoding="utf-8")
    assert '--name "Vibix Images"' in build
    assert '--icon "assets/vibix-images.ico"' in build
    assert '#define AppName "Vibix Images"' in installer
    assert '#define AppExeName "Vibix Images.exe"' in installer
    assert 'SetupIconFile=assets\\vibix-images.ico' in installer
```

Run: `python3 -m unittest tests.test_branding -v`
Expected: FAIL until both packaging files are updated.

- [x] **Step 2: Update PyInstaller and Inno Setup**

Change the PyInstaller name and icon, the expected `dist` path, Inno Setup
metadata, installer icon, application directory, shortcut names, executable
name, and output base filename. Keep the fixed Inno `AppId` so future updates
are recognized as the same installed product.

- [x] **Step 3: Run the packaging assertions**

Run: `python3 -m unittest tests.test_branding -v`
Expected: PASS.

- [ ] **Step 4: Commit the Windows packaging identity**

```bash
git add build.ps1 installer.iss tests/test_branding.py
git commit -m "feat: brand Windows installer as Vibix Images"
```

### Task 3: Align active release helpers and tests

**Files:**
- Modify: `scripts/refresh_updates_repo.ps1`
- Modify: `tests/test_main_ui_acceptance.py`
- Modify: `tests/test_release_entrypoint.py`
- Modify: `tests/test_security_boundaries.py`
- Modify: `tests/test_update_client.py`
- Modify: `tests/test_v3_mode_selection.py`
- Modify: `tests/test_v3_updater.py`

**Interfaces:**
- Active Windows artifact naming uses `VibixImages-Setup-{version}.exe`.
- Update temporary installer naming uses `VibixImages-Update-{timestamp}.exe`.

- [x] **Step 1: Replace active expectations**

Update only executable names, window-title assertions, default-folder names,
and active release-helper patterns. Do not rewrite historical release notes or
the license product id.

- [x] **Step 2: Run targeted tests**

Run: `python3 -m unittest tests.test_branding tests.test_main_ui_acceptance tests.test_release_entrypoint tests.test_security_boundaries tests.test_update_client tests.test_v3_mode_selection tests.test_v3_updater -v`
Expected: PASS.

- [ ] **Step 3: Commit active helper and test alignment**

```bash
git add scripts/refresh_updates_repo.ps1 tests
git commit -m "test: align active release checks with Vibix Images"
```

### Task 4: Update current project documentation and verify without building

**Files:**
- Modify: `PROJECT.md`
- Modify: `STATE.md`
- Modify: `CLIENT_DELIVERY.md`
- Modify: `PROJECT_KNOWLEDGE_BASE.md`

- [x] **Step 1: Record the visible product identity**

Document `Vibix Images`, the subtitle, the approved icon source, the Windows
installer filename pattern, and the fact that the legacy license product id
and update URL remain server contracts.

- [x] **Step 2: Run the full source verification**

Run: `python3 -m py_compile main.py v3_mode_selection.py`

Run: `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v`

Expected: compilation succeeds and the full test suite reports zero failures.
No PyInstaller, Inno Setup, GitHub Actions, or release publication is run in
this task.

- [x] **Step 3: Commit the documentation and final source state**

```bash
git add PROJECT.md STATE.md CLIENT_DELIVERY.md PROJECT_KNOWLEDGE_BASE.md
git commit -m "docs: record Vibix Images Windows branding"
```
