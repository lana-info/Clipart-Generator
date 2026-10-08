"""Build the same Core shell inventory as Windows on a native macOS runner."""
from __future__ import annotations

import argparse
import platform
import plistlib
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURES = {"arm64", "x86_64"}
FORWARDED_OPTIONS = {"add-data", "exclude-module", "hidden-import", "collect-submodules", "copy-metadata"}
MACOS_RUNTIME = "realesrgan-ncnn-vulkan-20220424-macos"


def pyinstaller_arguments(root: Path, target_arch: str) -> list[str]:
    if target_arch not in ARCHITECTURES:
        raise ValueError("Unsupported macOS architecture")
    source = (root / "build.ps1").read_text(encoding="utf-8-sig")
    options = re.findall(r'--([\w-]+)\s+"([^"\r\n]+)"', source)
    arguments = ["--noconfirm", "--clean", "--windowed", "--name", "Vibix Images",
                 "--osx-bundle-identifier", "com.vibix.images", "--target-arch", target_arch,
                 "--icon", "assets/vibix-images.ico"]
    for option, value in options:
        if option not in FORWARDED_OPTIONS:
            continue
        if option == "add-data":
            origin, destination = value.split(";", 1)
            if origin.startswith("realesrgan-ncnn-vulkan-"):
                origin = destination = MACOS_RUNTIME
            value = origin + ":" + destination
        arguments.extend(("--" + option, value))
    arguments.append("main.py")
    return arguments


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-arch", choices=sorted(ARCHITECTURES), required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if sys.platform != "darwin" or platform.machine() != args.target_arch:
        parser.error("Build must run on the selected native macOS architecture")
    version = (ROOT / "release/VERSION.txt").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", args.version) or args.version != version:
        parser.error("Build version must match committed release/VERSION.txt")
    subprocess.run([sys.executable, "-m", "PyInstaller", *pyinstaller_arguments(ROOT, args.target_arch)],
                   cwd=ROOT, check=True)
    plist = ROOT / "dist/Vibix Images.app/Contents/Info.plist"
    metadata = plistlib.loads(plist.read_bytes())
    metadata.update(CFBundleShortVersionString=version, CFBundleVersion=version)
    plist.write_bytes(plistlib.dumps(metadata))
    # Updating Info.plist invalidates PyInstaller's ad-hoc bundle signature.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", "dist/Vibix Images.app"],
                   cwd=ROOT, check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", "dist/Vibix Images.app"],
                   cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
