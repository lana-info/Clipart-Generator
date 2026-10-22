"""Patterns: signed package, Core host, projects and export (no UI stage yet)."""
import ast
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from PIL import Image, ImageDraw, ImageFilter
from PyQt6.QtWidgets import QApplication

import studio_patterns
import studio_patterns_storage as storage
from studio_module_packaging import prepare_official_workflow_release
from studio_module_runtime import ModuleAuthorizationError, ModuleRuntimeError, ModuleRuntimeHost
from studio_modules import ModuleStore
from studio_patterns_host import MAX_SHEETS, PatternsHost, safe_name
from studio_patterns_package import PATTERNS_ENGINE, patterns_payload
from studio_patterns_storage import PatternsConflict, PatternsLibrary

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("patterns-runtime")
    key = Ed25519PrivateKey.generate()  # Ephemeral test signer; no publisher key material.
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    package = prepare_official_workflow_release(
        source_root=ROOT, module_id="patterns", version="1.0.0", studio_min="3.2.8",
        studio_max_exclusive="3.3.0", platforms=["linux-x64"], key_id="test", private_key=key)
    path = tmp / "patterns.zip"
    path.write_bytes(package)
    store = ModuleStore(tmp / "modules", studio_version="3.2.8", platform="linux-x64", trusted_keys={"test": public})
    store.install(path)
    store.activate("patterns", "1.0.0")
    allowed = {"load", "command:kernel"}
    host = ModuleRuntimeHost(store, lambda module, action: module == "patterns" and action in allowed)
    host.load_active("patterns")
    yield host, allowed
    host.unload("patterns")


@pytest.fixture(scope="module")
def kernel(runtime):
    return runtime[0].invoke_command("patterns", "kernel")


def pump(app, predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


def make_png(path, size=(20, 16), color=(220, 40, 90, 255)):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((1, 1, size[0] - 2, size[1] - 2), fill=color)
    image.save(path)
    return path


def make_texture(path, size=(96, 72)):
    import numpy as np
    data = np.random.default_rng(3).integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(data, "RGB").filter(ImageFilter.GaussianBlur(5)).save(path)
    return path


def scene_payload(handles, elements=None, mode="straight"):
    ids = [h["asset_id"] for h in handles]
    elements = elements if elements is not None else [
        {"id": "a", "asset_id": ids[0], "x": 10, "y": 12, "scale": 1.0, "angle": 15},
        {"id": "b", "asset_id": ids[0], "x": 60, "y": 50, "scale": 1.2, "angle": 0},
    ]
    return {"schema_version": 1, "algorithm_version": 1, "mode": "pngs", "assets": list(handles),
            "scene": {"width": 100, "height": 80, "repeat_mode": mode, "seed": 7,
                      "background": [250, 244, 232, 255], "elements": elements}}


# --- package and runtime ---------------------------------------------------

def test_payload_inventory_and_relative_imports():
    files = patterns_payload(ROOT)
    assert set(files) == {"entry.py", *PATTERNS_ENGINE}
    tools = files["studio_patterns_tools.py"].decode()
    assert "from .studio_patterns import" in tools and "from studio_patterns import" not in tools
    assert b"from studio_module_api import" in files["entry.py"]
    # Source files at the repository root are untouched by packaging.
    assert "from studio_patterns import" in (ROOT / "studio_patterns_tools.py").read_text()


def test_verified_package_loads_and_serves_the_kernel(runtime, kernel):
    host, allowed = runtime
    assert kernel.PatternScene.__module__.startswith("_studio_module_patterns_")
    registration = host.registration("patterns")
    assert registration is not None
    assert {d.mime_type for d in registration.document_types} == {"application/vnd.vibix.patterns-project+json"}
    assert [page.name for page in registration.pages] == ["main"]
    assert kernel.MAX_DIMENSION == studio_patterns.MAX_DIMENSION
    assert kernel.ALGORITHM_VERSION == 1


def test_command_needs_entitlement_and_module_stays_pinned_by_jobs(runtime, kernel):
    host, allowed = runtime
    allowed.discard("command:kernel")
    with pytest.raises(ModuleAuthorizationError):
        host.invoke_command("patterns", "kernel")
    allowed.add("command:kernel")
    lease = host.acquire_job_lease("patterns")
    with pytest.raises(ModuleRuntimeError):
        host.unload("patterns")
    lease.close()


def test_core_never_imports_the_engine_and_limits_match():
    for name in ("studio_patterns_host.py", "studio_patterns_storage.py"):
        tree = ast.parse((ROOT / name).read_text())
        for node in ast.walk(tree):
            names = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                     else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            assert not any(n.startswith(("studio_patterns_tools", "studio_patterns_entry", "studio_patterns."))
                           or n == "studio_patterns" for n in names), name
    assert storage.MAX_ASSET_SIDE == studio_patterns.MAX_DIMENSION
    assert storage.MAX_ASSET_PIXELS == studio_patterns.MAX_ASSET_PIXELS
    assert storage.MAX_PROJECT_BYTES == studio_patterns.MAX_JSON_BYTES
    assert storage.MAX_PROJECT_ASSETS == studio_patterns.MAX_ASSETS


def test_host_requires_a_loaded_kernel(tmp_path):
    with pytest.raises(ValueError):
        PatternsHost(tmp_path, authorize=lambda: True)


# --- library -----------------------------------------------------------------

def test_import_validates_and_deduplicates(tmp_path):
    library = PatternsLibrary(tmp_path / "lib")
    source = make_png(tmp_path / "motif.png")
    first = library.import_png(source)
    assert first["width"] == 20 and first["has_alpha"] is True
    assert library.import_png(source)["handle"] == first["handle"]
    assert library.asset_path(first["handle"]).read_bytes() == source.read_bytes()
    jpg = tmp_path / "x.jpg"
    Image.new("RGB", (4, 4)).save(jpg)
    fake_png = tmp_path / "fake.png"
    fake_png.write_bytes(b"not an image")
    huge = tmp_path / "huge.png"
    Image.new("L", (storage.MAX_ASSET_SIDE + 1, 1)).save(huge)
    for bad in (jpg, fake_png, huge):
        with pytest.raises(Exception):
            library.import_png(bad)
    assert not library.asset_available({**first["handle"], "asset_id": "0" * 64, "sha256": "0" * 64})


def test_project_revisions_conflicts_and_foreign_assets(tmp_path):
    library = PatternsLibrary(tmp_path / "lib")
    info = library.import_png(make_png(tmp_path / "m.png"))
    payload = scene_payload([info["handle"]])
    saved = library.save(payload, " Весенний сад ")
    assert saved["revision"] == 1 and saved["name"] == "Весенний сад"
    again = library.save(payload, "Весенний сад", saved["id"], 1)
    assert again["revision"] == 2 and again["created_at"] == saved["created_at"]
    with pytest.raises(PatternsConflict):
        library.save(payload, "x", saved["id"], 1)
    with pytest.raises(PatternsConflict):
        library.save(payload, "x", saved["id"])
    with pytest.raises(ValueError):
        library.save(payload, "   ")
    foreign = dict(info["handle"], asset_id="1" * 64, sha256="1" * 64)
    with pytest.raises(ValueError, match="не принадлежит"):
        library.save(scene_payload([foreign]), "x")
    for broken in ({**payload, "schema_version": 2}, {**payload, "mode": "other"}, "text"):
        with pytest.raises(ValueError):
            library.save(broken, "x")
    assert [p["name"] for p in library.list_projects()] == ["Весенний сад"]
    assert library.load(saved["id"])["payload"]["scene"]["seed"] == 7
    with pytest.raises(PatternsConflict):
        library.delete(saved["id"], 1)
    library.delete(saved["id"], 2)
    with pytest.raises(ValueError):
        library.load(saved["id"])


def test_projects_survive_without_the_module(tmp_path):
    library = PatternsLibrary(tmp_path / "lib")
    info = library.import_png(make_png(tmp_path / "m.png"))
    saved = library.save(scene_payload([info["handle"]]), "keep me")
    reopened = PatternsLibrary(tmp_path / "lib")  # no module, no engine involved
    assert reopened.load(saved["id"])["payload"] == saved["payload"]


# --- host jobs ---------------------------------------------------------------

class FakeRuntime:
    def __init__(self):
        self.leases = []

    def acquire_job_lease(self, module_id):
        lease = type("Lease", (), {"closed": 0, "close": lambda self: setattr(self, "closed", self.closed + 1)})()
        self.leases.append(lease)
        return lease


def make_host(tmp_path, kernel, **kw):
    return PatternsHost(tmp_path / "root", authorize=kw.pop("authorize", lambda: True), kernel=kernel, **kw)


def test_render_pngs_sheet_matches_the_engine_and_is_seamless(tmp_path, app, kernel):
    runtime = FakeRuntime()
    host = make_host(tmp_path, kernel, runtime=runtime)
    info = host.import_png(make_png(tmp_path / "m.png"))
    payload = scene_payload([info["handle"]])
    done, errors = [], []
    host.render_sheet(payload, done.append, errors.append)
    pump(app, lambda: done or errors)
    assert not errors
    image, seam = done[0]["image"], done[0]["seam"]
    assert image.size == (100, 80) and seam["status"] == "ready"
    direct = studio_patterns.render_supertile(studio_patterns.PatternScene.from_dict({
        "schema_version": 1, "width": 100, "height": 80, "seed": 7, "background": [250, 244, 232, 255],
        "assets": [{"id": info["handle"]["asset_id"], "path": str(host._library.asset_path(info["handle"]))}],
        "elements": payload["scene"]["elements"]}))
    assert image.tobytes() == direct.tobytes()
    pump(app, lambda: runtime.leases[0].closed == 1)
    host.close()


@pytest.mark.parametrize("mode,size", [("half_row", (100, 160)), ("half_column", (200, 80)), ("mirror", (200, 160))])
def test_render_supports_every_repeat_mode(tmp_path, app, kernel, mode, size):
    host = make_host(tmp_path, kernel)
    info = host.import_png(make_png(tmp_path / "m.png"))
    done, errors = [], []
    host.render_sheet(scene_payload([info["handle"]], mode=mode), done.append, errors.append)
    pump(app, lambda: done or errors)
    assert not errors and done[0]["image"].size == size and done[0]["seam"]["status"] == "ready"


def test_render_tile_mode_improves_the_seam_and_supports_mirror(tmp_path, app, kernel):
    host = make_host(tmp_path, kernel)
    info = host.import_png(make_texture(tmp_path / "tile.png"))
    before = kernel.seam_report(Image.open(tmp_path / "tile.png").convert("RGB")).score
    base = {"schema_version": 1, "algorithm_version": 1, "mode": "tile", "assets": [info["handle"]]}
    results = {}
    for layout in ("straight", "mirror"):
        done, errors = [], []
        host.render_sheet({**base, "tile": {"asset": info["handle"], "band": 0.25, "layout": layout}},
                          done.append, errors.append)
        pump(app, lambda: done or errors)
        assert not errors
        results[layout] = done[0]
    assert results["straight"]["image"].size == (96, 72) and results["straight"]["seam"]["score"] < before / 2
    assert results["mirror"]["image"].size == (192, 144) and results["mirror"]["seam"]["status"] == "ready"


def test_render_errors_are_user_readable_and_path_free(tmp_path, app, kernel):
    host = make_host(tmp_path, kernel)
    info = host.import_png(make_png(tmp_path / "m.png"))
    errors = []
    bad = scene_payload([info["handle"]], elements=[{"id": "a", "asset_id": "f" * 64, "x": 1, "y": 1}])
    host.render_sheet(bad, lambda _: None, errors.append)
    pump(app, lambda: errors)
    assert str(tmp_path) not in errors[0]
    stale = scene_payload([info["handle"]])
    stale["algorithm_version"] = 99
    errors.clear()
    host.render_sheet(stale, lambda _: None, errors.append)
    pump(app, lambda: errors)
    assert "алгоритма" in errors[0]


def test_access_is_rechecked_before_applying_results_and_on_close(tmp_path, app, kernel):
    allowed = [True]
    host = make_host(tmp_path, kernel, authorize=lambda: allowed[0])
    info = host.import_png(make_png(tmp_path / "m.png"))
    done, errors = [], []
    host.render_sheet(scene_payload([info["handle"]]), done.append, errors.append)
    allowed[0] = False
    pump(app, lambda: done or errors)
    assert not done and "Доступ к модулю изменился" in errors[0]
    with pytest.raises(ValueError, match="Нет доступа"):
        host.list_projects()
    allowed[0] = True
    cancelled = []
    runtime = FakeRuntime()
    second = make_host(tmp_path / "other", kernel, runtime=runtime)
    info = second.import_png(make_png(tmp_path / "m.png"))
    second.render_sheet(scene_payload([info["handle"]]), cancelled.append, cancelled.append)
    second.close()
    pump(app, lambda: runtime.leases[0].closed == 1)
    assert cancelled == []
    with pytest.raises(ValueError, match="закрыт"):
        second.list_projects()


# --- export -------------------------------------------------------------------

@pytest.mark.parametrize("name", ["", "   ", "a/b", "a\\b", "x:y", "CON", "nul.txt", "bad.", "q" * 101, "tab\tname", 5])
def test_unsafe_set_names_are_rejected(name):
    with pytest.raises(ValueError):
        safe_name(name)
    assert safe_name("Весенний сад ") == "Весенний сад"


def test_plan_reports_conflicts_without_writing(tmp_path, kernel):
    host = make_host(tmp_path, kernel)
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "Сад 02.png").write_bytes(b"mine")
    plan = host.plan_export(folder, "Сад", 3, "png")
    assert plan["files"] == ["Сад 01.png", "Сад 02.png", "Сад 03.png"] and plan["conflicts"] == ["Сад 02.png"]
    for args in ((tmp_path / "missing", "Сад", 1), (folder, "Сад", 0), (folder, "Сад", MAX_SHEETS + 1),
                 (folder, "Сад", 1, "gif"), (folder / "Сад 02.png", "Сад", 1)):
        with pytest.raises(ValueError):
            host.plan_export(*args)
    link = tmp_path / "link"
    link.symlink_to(folder)
    with pytest.raises(ValueError):
        host.plan_export(link, "Сад", 1)
    assert (folder / "Сад 02.png").read_bytes() == b"mine"


def test_export_writes_sized_files_and_never_overwrites(tmp_path, app, kernel):
    runtime = FakeRuntime()
    host = make_host(tmp_path, kernel, runtime=runtime)
    folder = tmp_path / "out"
    folder.mkdir()
    sheets = [Image.new("RGBA", (30, 20), (200, 30, 60, 255)), Image.new("RGBA", (30, 20), (0, 0, 0, 0))]
    done, errors, ticks = [], [], []
    host.export_sheets(sheets, folder, "Сад", "png", 1, 72, (255, 255, 255), done.append, errors.append,
                       lambda i, n: ticks.append((i, n)))
    pump(app, lambda: done or errors)
    assert not errors and done[0]["cancelled"] is False and len(done[0]["written"]) == 2
    assert ticks[-1] == (2, 2)
    for file in ("Сад 01.png", "Сад 02.png"):
        with Image.open(folder / file) as saved:
            assert saved.size == (72, 72) and saved.info["dpi"][0] == pytest.approx(72, abs=0.01)
    pump(app, lambda: runtime.leases[0].closed == 1)
    before = (folder / "Сад 01.png").read_bytes()
    with pytest.raises(ValueError, match="уже существуют"):
        host.export_sheets(sheets, folder, "Сад", "png", 1, 72, (255, 255, 255), done.append, errors.append)
    assert (folder / "Сад 01.png").read_bytes() == before and len(list(folder.iterdir())) == 2
    host.export_sheets(sheets[:1], folder, "Сад", "jpg", 1, 72, (10, 200, 30), done.append, errors.append)
    pump(app, lambda: len(done) == 2)
    with Image.open(folder / "Сад 01.jpg") as saved:
        assert saved.format == "JPEG" and saved.mode == "RGB"


def test_export_failure_message_has_no_paths(tmp_path, app, kernel):
    from types import SimpleNamespace

    def failing_export(image, target, **kwargs):
        raise OSError(f"cannot write {target}")

    host = make_host(tmp_path, SimpleNamespace(**{**vars(kernel), "export_tile": failing_export}))
    folder = tmp_path / "out"
    folder.mkdir()
    errors = []
    host.export_sheets([Image.new("RGBA", (4, 4))], folder, "Сад", "png", 1, 72, (255, 255, 255),
                       lambda _: None, errors.append)
    pump(app, lambda: errors)
    assert str(tmp_path) not in errors[0] and "Сад" not in errors[0]
    assert list(folder.iterdir()) == []
