from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from studio_asset_api import AssetHandle, AssetHandleError
from studio_assets import AssetStore, AssetStoreError


def test_asset_handle_is_immutable_portable_and_contains_no_path_or_source_module():
    digest = hashlib.sha256(b"portable").hexdigest()
    handle = AssetHandle(digest, digest, 8, "motif.png", "image/png")
    encoded = handle.to_dict()
    assert encoded == {
        "schema_version": 1,
        "asset_id": digest,
        "sha256": digest,
        "size": 8,
        "filename": "motif.png",
        "media_type": "image/png",
    }
    assert AssetHandle.from_dict(encoded) == handle
    assert not hasattr(handle, "path")
    assert not hasattr(handle, "source_module")
    with pytest.raises(AttributeError):
        handle.filename = "changed.png"


def test_asset_handle_rejects_unsafe_or_mismatched_metadata():
    digest = hashlib.sha256(b"portable").hexdigest()
    base = {
        "schema_version": 1, "asset_id": digest, "sha256": digest, "size": 8,
        "filename": "motif.png", "media_type": "image/png",
    }
    for bad in (
        {**base, "schema_version": 2},
        {**base, "asset_id": "0" * 64},
        {**base, "size": True},
        {**base, "filename": "/private/motif.png"},
        {**base, "media_type": ""},
        {**base, "path": "/private/motif.png"},
    ):
        with pytest.raises(AssetHandleError):
            AssetHandle.from_dict(bad)


def test_existing_asset_store_handoff_survives_source_deletion_and_restart():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source = root / "source.png"
        payload = b"portable image bytes"
        source.write_bytes(payload)
        store = AssetStore(root / "assets")
        record = store.import_file(source)
        handle = store.to_handle(record)
        source.unlink()

        assert not hasattr(handle, "path")
        assert store.resolve_handle(handle).read_bytes() == payload
        restarted = AssetStore(root / "assets")
        assert restarted.resolve_handle(AssetHandle.from_dict(handle.to_dict())).read_bytes() == payload


def test_store_rechecks_handle_integrity_instead_of_trusting_public_metadata():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source = root / "source.png"
        source.write_bytes(b"asset")
        store = AssetStore(root / "assets")
        handle = store.to_handle(store.import_file(source))
        forged = AssetHandle(
            handle.asset_id, handle.sha256, handle.size + 1,
            handle.filename, handle.media_type,
        )
        with pytest.raises(AssetStoreError, match="integrity"):
            store.resolve_handle(forged)
