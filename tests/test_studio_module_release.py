import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from studio_module_release import (
    AdminDraftUploader, NoRedirect, initialize_key, load_signing_key, main, prepare_release_set,
)
from studio_modules import ModulePackageError, ModuleStore


@pytest.fixture
def publisher(tmp_path):
    path = tmp_path / "private" / "publisher.pem"
    public = initialize_key(path)
    return path, {"fixture": public}


def test_key_initialization_is_exclusive_private_and_never_prints_secret(publisher):
    path, trust = publisher
    assert load_signing_key(path, "fixture", trust).public_key().public_bytes_raw() == trust["fixture"]
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        initialize_key(path)
    assert path.read_bytes() == original
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
        path.chmod(0o644)
        with pytest.raises(ValueError, match="0600"):
            load_signing_key(path, "fixture", trust)


def test_key_must_be_pinned_and_not_symlinked(publisher, tmp_path):
    path, trust = publisher
    with pytest.raises(ValueError, match="not pinned"):
        load_signing_key(path, "unknown", trust)
    link = tmp_path / "link.pem"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="location"):
        load_signing_key(link, "fixture", trust)


def test_prepare_all_real_workflows_are_verified_and_output_never_overwritten(publisher, tmp_path):
    path, trust = publisher
    output = tmp_path / "release"
    args = dict(output=output, key_path=path, key_id="fixture", trusted_keys=trust,
                version="1.0.0", studio_min="3.2.0", studio_max_exclusive="3.3.0",
                platforms=["windows-x64", "macos-x64"])
    rows = prepare_release_set(**args)
    assert {r["module_id"] for r in rows} == {"clipart", "processing", "pinterest", "auto-clipart", "image-processing", "prompt-composer"}
    for row in rows:
        store = ModuleStore(tmp_path / "inspect", studio_version="3.2.0",
                            platform="windows-x64", trusted_keys=trust)
        assert store.inspect_package(output / row["filename"])["module_id"] == row["module_id"]
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError):
        prepare_release_set(**args)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert json.loads((output / "release-set.json").read_text())["releases"] == rows


@pytest.mark.parametrize("url", ["http://example.com", "https://user:pass@example.com",
    "https://example.com/?secret=x", "https://example.com/#x", "https://example.com/../other",
    "https://example.com/%2fother"])
def test_admin_upload_requires_clean_https_origin(url):
    with pytest.raises(ValueError):
        AdminDraftUploader(url)


def test_redirect_is_rejected_instead_of_forwarding_session():
    with pytest.raises(ValueError, match="redirect"):
        NoRedirect().redirect_request(None, None, 307, "", {}, "https://elsewhere.test")


def test_untrusted_package_makes_no_draft_request(publisher, tmp_path):
    path, trust = publisher
    rows = prepare_release_set(output=tmp_path / "release", key_path=path, key_id="fixture",
        trusted_keys=trust, version="1.0.0", studio_min="3.2.0", studio_max_exclusive="3.3.0",
        platforms=["windows-x64"])
    uploader = AdminDraftUploader("https://example.com/licenses")
    uploader.csrf = "fixture-csrf"
    uploader._post = Mock()
    with pytest.raises(ModulePackageError):
        uploader.upload(tmp_path / "release" / rows[0]["filename"], product_id="clipart-generator",
                        platform="windows-x64", studio_version="3.2.0", trusted_keys={})
    uploader._post.assert_not_called()
    uploader.close()
    assert uploader.csrf is None


def test_cli_failure_does_not_print_raw_secret_exception():
    output, errors = io.StringIO(), io.StringIO()
    with patch("studio_module_release.initialize_key", side_effect=RuntimeError("secret-value")), \
            redirect_stdout(output), redirect_stderr(errors):
        assert main(["init-key", "--key-file", "/not-used.pem"]) == 1
    assert "secret-value" not in output.getvalue() + errors.getvalue()


def test_old_server_cannot_receive_module_bytes_as_shell_release(publisher, tmp_path):
    path, trust = publisher
    rows = prepare_release_set(output=tmp_path / "release", key_path=path, key_id="fixture",
        trusted_keys=trust, version="1.0.0", studio_min="3.2.0", studio_max_exclusive="3.3.0",
        platforms=["windows-x64"])
    uploader = AdminDraftUploader("https://example.com/licenses")
    uploader.csrf = "fixture-csrf"
    uploader._post = Mock(return_value={"id": "old-server-draft", "status": "draft"})
    with pytest.raises(ValueError, match="requested module draft"):
        uploader.upload(tmp_path / "release" / rows[0]["filename"], product_id="clipart-generator",
                        platform="windows-x64", studio_version="3.2.0", trusted_keys=trust)
    assert uploader._post.call_count == 1


def test_upload_cli_refuses_echoed_password_fallback_without_terminal():
    with patch("studio_module_release.sys.stdin.isatty", return_value=False), \
            patch("studio_module_release.getpass.getpass") as prompt, \
            patch("studio_module_release.AdminDraftUploader") as uploader, redirect_stderr(io.StringIO()):
        assert main(["upload-draft", "/not-read.zip", "--service-url", "https://example.test",
                     "--platform", "windows-x64", "--studio-version", "3.2.0"]) == 1
    prompt.assert_not_called()
    uploader.assert_not_called()
