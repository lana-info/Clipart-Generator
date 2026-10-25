"""Publisher-side preparation of immutable, signed Studio module artifacts.

Only explicitly supplied payload bytes are included. This never walks a source
tree, imports module code, or reads the publisher's private key from disk.
"""
from __future__ import annotations

import base64
import ast
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from studio_modules import (
    MAX_FILES, MAX_PACKAGE_BYTES, MAX_MANIFEST_BYTES,
    ModulePackageError, ModuleStore, canonical_manifest, _member, _version,
)


OFFICIAL_WORKFLOW_FILES = {
    "prompt-composer": (),
    "patterns": (),
    "auto-clipart": (
        "studio_auto_clipart_flow.py", "v3_clipart_flow.py",
        "studio_clipart_recipe.py", "studio_clipart_references.py", "studio_reference_editor.py",
        "studio_clipart_builder_ui.py", "studio_planning_ui.py", "studio_text_client.py",
        "studio_clipart_planner.py", "studio_clipart_objects.py",
        "studio_commercial_prompt_guidance.py", "studio_holiday_profiles.py",
        "studio_style_profiles.py", "studio_palette_library.py",
        "clipart_prompt_generator.py", "clipart_prompt_schema.py",
        "studio_clipart_versions.py", "studio_clipart_review_ui.py", "studio_clipart_recovery.py",
    ),
    "clipart": ("v3_clipart_flow.py", "clipart_prompt_generator.py", "clipart_prompt_schema.py"),
    "processing": ("v3_processing_flow.py",),
    "pinterest": ("v3_pinterest_flow.py", "pinterest_pin_composer.py",
                  "pinterest_pin_templates.py", "pinterest_prompt_schema.py"),
}

AUTO_CLIPART_STYLE_PREVIEWS = (
    "watercolor", "gouache", "hand-drawn", "doodle", "pencil", "minimal-line-art",
    "flat-vector", "sticker", "pixel-art", "kawaii", "chibi", "storybook",
    "pastel-nursery", "whimsical", "scandinavian-folk", "vintage-illustration",
    "cottagecore", "retro", "gothic-dark",
)

OFFICIAL_COMPONENT_FILES = {
    "image-processing": (
        "studio_processing_engine.py", "chroma_key.py", "chroma_rim.py", "chroma_profile.py",
    ),
}


def prepare_official_workflow_release(*, source_root: Path, module_id: str, **metadata) -> bytes:
    """Package an explicit first-party workflow inventory, without manual ZIP assembly.

    Workflow-owned helpers are imported relatively inside the verified package;
    shared Core APIs retain their existing imports and compatibility range.
    """
    if module_id == "prompt-composer":
        from studio_prompt_composer_package import composer_payload
        return prepare_module_release(module_id=module_id, entrypoint="entry.py",
                                      files=composer_payload(source_root), **metadata)
    if module_id == "patterns":
        from studio_patterns_package import patterns_payload
        return prepare_module_release(module_id=module_id, entrypoint="entry.py",
                                      files=patterns_payload(source_root), **metadata)
    try:
        inventory = {**OFFICIAL_WORKFLOW_FILES, **OFFICIAL_COMPONENT_FILES}[module_id]
    except KeyError as exc:
        raise ModulePackageError("Unknown official workflow") from exc
    owned = {Path(name).stem for name in inventory}
    files = {}
    for name in inventory:
        source = Path(source_root) / name
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_PACKAGE_BYTES:
            raise ModulePackageError("Invalid official workflow source")
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in owned:
                node.level = 1
            elif isinstance(node, ast.Import) and any(alias.name in owned for alias in node.names):
                raise ModulePackageError("Workflow-owned imports must use from syntax")
        files[name] = ast.unparse(tree).encode("utf-8")
    if module_id == "auto-clipart":
        for key in AUTO_CLIPART_STYLE_PREVIEWS:
            name = f"assets/style_previews/{key}.jpg"
            source = Path(source_root) / name
            if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_PACKAGE_BYTES:
                raise ModulePackageError("Invalid style preview source")
            files[name] = source.read_bytes()
    if module_id in OFFICIAL_COMPONENT_FILES:
        files["entry.py"] = (
            "from studio_module_api import ModuleRegistration, CommandDeclaration\n"
            "from studio_processing_api import PROCESSING_CAPABILITY\n"
            "from studio_processing_api import ProcessingEngine\n"
            "_engine = None\n"
            "def bind(context):\n"
            "    global _engine\n"
            "    context.capabilities.require(PROCESSING_CAPABILITY)\n"
            "    from .studio_processing_engine import create_engine\n"
            "    _engine = create_engine()\n"
            "    if not isinstance(_engine, ProcessingEngine):\n"
            "        raise ValueError('Unsupported processing engine')\n"
            "def engine():\n"
            "    return _engine\n"
            "def register(context):\n"
            "    return ModuleRegistration(context.module_id, context.version,\n"
            "        commands=(CommandDeclaration('engine', engine),),\n"
            "        capabilities=(PROCESSING_CAPABILITY,))\n"
        ).encode("utf-8")
        return prepare_module_release(module_id=module_id, entrypoint="entry.py", files=files, **metadata)
    flow = Path(inventory[0]).stem
    installer = {"clipart": "install_clipart_flow", "processing": "install_processing_flow",
                 "pinterest": "install_pinterest_flow", "auto-clipart": "install_auto_clipart_flow"}[module_id]
    arguments = "host, locale=locale" if module_id == "pinterest" else "host"
    files["entry.py"] = (
        "from studio_module_api import ModuleRegistration, CommandDeclaration\n"
        "def install(host, *, locale):\n"
        "    from importlib import import_module\n"
        # Controllers outlive this callback. Preload owned helpers while the
        # runtime suppresses bytecode, so later UI/worker lazy imports cannot
        # add __pycache__ files to an immutable, signed package inventory.
        f"    for name in {tuple(Path(name).stem for name in inventory)!r}:\n"
        "        import_module('.' + name, __package__)\n"
        f"    from .{flow} import {installer}\n"
        f"    return {installer}({arguments})\n"
        "def register(context):\n"
        "    return ModuleRegistration(context.module_id, context.version,\n"
        "        commands=(CommandDeclaration('install_workflow', install),))\n"
    ).encode("utf-8")
    return prepare_module_release(module_id=module_id, entrypoint="entry.py", files=files, **metadata)


def prepare_module_release(
    *, module_id: str, version: str, studio_min: str, studio_max_exclusive: str,
    platforms: list[str], entrypoint: str, files: dict[str, bytes],
    key_id: str, private_key: Ed25519PrivateKey,
) -> bytes:
    """Return a signed artifact after verifying it with the client installer.

    The caller owns signing-key custody and selects the exact release payload.
    Output is deterministic for identical inputs. No source files or user data
    are modified and no payload code is executed.
    """
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ModulePackageError("An Ed25519 publisher key is required")
    if not isinstance(key_id, str) or not key_id.strip() or len(key_id) > 128:
        raise ModulePackageError("Invalid publisher key identifier")
    if (not isinstance(platforms, list) or not platforms
            or any(p not in {"windows-x64", "macos-x64", "macos-arm64", "linux-x64"} for p in platforms)
            or len(set(platforms)) != len(platforms)):
        raise ModulePackageError("Invalid release platforms")
    if _version(studio_min) >= _version(studio_max_exclusive):
        raise ModulePackageError("Empty Studio compatibility range")
    if not isinstance(files, dict) or not files or len(files) + 2 > MAX_FILES:
        raise ModulePackageError("Invalid package inventory")
    payload = {}
    total = 0
    for name, content in files.items():
        _member(name)
        if name.casefold() in {"manifest.json", "signature.json"} or not isinstance(content, bytes):
            raise ModulePackageError("Invalid package payload")
        total += len(content)
        if total > MAX_PACKAGE_BYTES:
            raise ModulePackageError("Expanded package exceeds limit")
        payload[name] = content
    if len({name.casefold() for name in payload}) != len(payload):
        raise ModulePackageError("Case-colliding payload paths")
    if entrypoint not in payload:
        raise ModulePackageError("Missing entrypoint")
    manifest = {
        "schema_version": 1, "module_id": module_id, "version": version,
        "module_api": 1, "studio_min": studio_min,
        "studio_max_exclusive": studio_max_exclusive,
        "platforms": sorted(platforms), "entrypoint": entrypoint,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()},
    }
    signed = canonical_manifest(manifest)
    if len(signed) > MAX_MANIFEST_BYTES:
        raise ModulePackageError("Manifest too large")
    signature = json.dumps({
        "key_id": key_id, "signature": base64.b64encode(private_key.sign(signed)).decode("ascii")
    }, sort_keys=True).encode("utf-8")
    payload.update({"manifest.json": signed, "signature.json": signature})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(payload):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload[name])
    artifact = output.getvalue()
    if len(artifact) > MAX_PACKAGE_BYTES:
        raise ModulePackageError("Package exceeds limit")
    public = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    with tempfile.TemporaryDirectory(prefix="vibix-module-check-") as temp:
        root = Path(temp)
        package = root / "release.zip"
        package.write_bytes(artifact)
        for platform in platforms:
            store = ModuleStore(root / "inspection", studio_version=studio_min,
                                platform=platform, trusted_keys={key_id: public})
            store.inspect_package(package)
    return artifact


def main(argv=None) -> int:
    """Controlled release entrypoint; never publishes or generates signing keys."""
    import argparse
    import os
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    parser = argparse.ArgumentParser(description="Prepare a signed official Studio workflow package")
    parser.add_argument("--module", choices=sorted({**OFFICIAL_WORKFLOW_FILES, **OFFICIAL_COMPONENT_FILES}), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--studio-min", required=True)
    parser.add_argument("--studio-max-exclusive", required=True)
    parser.add_argument("--platform", action="append", required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--signing-key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.suffix.lower() != ".zip":
        parser.error("output must be a new ZIP file")
    if args.signing_key_file.stat().st_size > 16384:
        parser.error("invalid signing key file")
    key = load_pem_private_key(args.signing_key_file.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        parser.error("an Ed25519 signing key is required")
    content = prepare_official_workflow_release(
        source_root=args.source_root, module_id=args.module, version=args.version,
        studio_min=args.studio_min, studio_max_exclusive=args.studio_max_exclusive,
        platforms=args.platform, key_id=args.key_id, private_key=key,
    )
    # Exclusive creation preserves any previous release artifact.
    with args.output.open("xb") as handle:
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            args.output.unlink(missing_ok=True)
            raise
    print(json.dumps({"module_id": args.module, "version": args.version,
                      "filename": args.output.name, "size": len(content),
                      "sha256": hashlib.sha256(content).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
