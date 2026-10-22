"""Narrow Core façade for the downloaded Patterns module, with cancellable Qt jobs.

Core owns projects, imported files, background work and writing to the user's
folder.  The signed module supplies only the pure engine (``kernel``).  Nothing
here imports the engine: a missing or disabled module cannot break stored data.
"""
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from studio_patterns_storage import PatternsLibrary

MODULE_ID = "patterns"
MAX_SHEETS = 50
_FORBIDDEN = '/\\<>:"|?*'
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_FORMATS = {"png": ".png", "jpg": ".jpg"}


class PatternsJob(QObject):
    finished = pyqtSignal(object, object)
    progress = pyqtSignal(int, int)

    def __init__(self, work, on_done, on_error, on_progress, cleanup, lease=None):
        super().__init__()
        self._cancelled = threading.Event()
        self._work, self._on_done, self._on_error = work, on_done, on_error
        self._on_progress, self._cleanup, self._lease = on_progress, cleanup, lease
        self.finished.connect(self._deliver)
        self.progress.connect(self._tick)

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="patterns-job").start()
        return self

    def cancel(self):
        self._cancelled.set()

    def _run(self):
        result, error = None, None
        try:
            if not self._cancelled.is_set():
                result = self._work(self._cancelled.is_set, self.progress.emit)
        except ValueError as exc:
            error = str(exc)
        except Exception:
            # Exceptions may embed personal paths; the user message stays generic.
            error = "Не удалось завершить операцию. Проверьте файлы и свободное место и повторите."
        finally:
            self.finished.emit(result, error)

    @pyqtSlot(int, int)
    def _tick(self, done, total):
        if self._on_progress is not None and not self._cancelled.is_set():
            self._on_progress(done, total)

    @pyqtSlot(object, object)
    def _deliver(self, result, error):
        try:
            if not self._cancelled.is_set():
                if error:
                    self._on_error(error)
                else:
                    self._on_done(result)
        finally:
            if self._lease is not None:
                self._lease.close()
            self._cleanup(self)
            self._work = self._on_done = self._on_error = self._on_progress = None


def safe_name(value):
    """A user-chosen set name becomes the stem of file names: no paths, no tricks."""
    name = value.strip() if isinstance(value, str) else ""
    if (not name or len(name) > 100 or any(ord(c) < 32 or c in _FORBIDDEN for c in name)
            or name.endswith((".", " ")) or name.split(".")[0].rstrip(" ").casefold() in _RESERVED):
        raise ValueError("Введите имя набора до 100 символов без символов \\ / : * ? \" < > |")
    return name


class PatternsHost:
    can_handoff = False

    def __init__(self, root, *, authorize, runtime=None, kernel=None):
        if kernel is None:
            raise ValueError("Модуль Patterns не загружен")
        self._kernel = kernel
        self._library = PatternsLibrary(root)
        self._authorize, self._runtime = authorize, runtime
        self._jobs = set()
        self._closed = False

    @property
    def algorithm_version(self):
        return self._kernel.ALGORITHM_VERSION

    def _check(self):
        if self._closed:
            raise ValueError("Модуль закрыт")
        if self._authorize() is not True:
            raise ValueError("Нет доступа к модулю")

    # -- library ------------------------------------------------------------

    def import_png(self, path):
        self._check()
        return self._library.import_png(path)

    def asset_available(self, handle):
        self._check()
        return self._library.asset_available(handle)

    def list_projects(self):
        self._check()
        return self._library.list_projects()

    def load_project(self, project_id):
        self._check()
        return self._library.load(project_id)

    def save_project(self, payload, name, project_id=None, expected_revision=None):
        self._check()
        return self._library.save(payload, name, project_id, expected_revision)

    def delete_project(self, project_id, expected_revision):
        self._check()
        return self._library.delete(project_id, expected_revision)

    # -- engine bridge ------------------------------------------------------

    def _scene(self, payload):
        """Build an engine scene from a project; paths never leave Core and the job."""
        k = self._kernel
        if payload.get("algorithm_version") != k.ALGORITHM_VERSION:
            raise ValueError("Проект создан другой версией алгоритма и не может быть пересобран")
        scene = payload.get("scene")
        if not isinstance(scene, dict):
            raise ValueError("В проекте нет сцены")
        owned = {item["asset_id"]: item for item in payload.get("assets", [])}
        data = {"schema_version": 1, "width": scene.get("width"), "height": scene.get("height"),
                "repeat_mode": scene.get("repeat_mode", "straight"), "seed": scene.get("seed", 0),
                "background": scene.get("background", [255, 255, 255, 255]),
                "assets": [{"id": asset_id, "path": str(self._library.asset_path(handle))}
                           for asset_id, handle in owned.items()],
                "elements": scene.get("elements", [])}
        try:
            return k.PatternScene.from_dict(data)
        except k.PatternValidationError as error:
            raise ValueError(str(error)) from error

    def _seam(self, image):
        report = self._kernel.seam_report(image)
        return {"horizontal": report.horizontal, "vertical": report.vertical,
                "score": report.score, "status": report.status.value}

    def _render(self, payload):
        k = self._kernel
        try:
            if payload.get("mode") == "tile":
                tile = payload.get("tile") or {}
                from PIL import Image
                with Image.open(self._library.asset_path(tile.get("asset"))) as source:
                    source.load()
                    image = source.copy()
                if tile.get("layout") == "mirror":
                    image = k.mirror_tile(image)
                else:
                    image = k.make_seamless(image, tile.get("band", 0.2))
            else:
                image = k.render_supertile(self._scene(payload))
        except k.PatternValidationError as error:
            raise ValueError(str(error)) from error
        return {"image": image, "seam": self._seam(image)}

    def asset_info(self, handle):
        """Size and alpha of an owned image, e.g. to restore a saved project."""
        self._check()
        from PIL import Image
        with Image.open(self._library.asset_path(handle)) as image:
            return {"width": image.width, "height": image.height,
                    "has_alpha": "A" in image.getbands() or "transparency" in image.info}

    def thumbnail(self, handle, size=96):
        """A small RGBA copy of an owned image for lists; the stored file is never altered."""
        self._check()
        from PIL import Image
        if type(size) is not int or not 16 <= size <= 512:
            raise ValueError("Недопустимый размер миниатюры")
        with Image.open(self._library.asset_path(handle)) as source:
            source.draft("RGB", (size * 2, size * 2))
            image = source.convert("RGBA")
        image.thumbnail((size, size))
        return image

    def layout_elements(self, payload, *, count, min_gap, scale_range, angle_range, seed):
        """Place new elements (locked ones stay) and return them with any warnings."""
        self._check()
        k = self._kernel
        self._library._check_payload(payload)
        scene = self._scene(payload)
        scene = k.PatternScene(scene.width, scene.height, scene.assets, scene.elements,
                               scene.repeat_mode, seed, scene.background, scene.schema_version)
        try:
            laid_out, warnings = k.layout_scene(scene, count=count, min_gap=min_gap,
                                                scale_range=tuple(scale_range), angle_range=tuple(angle_range))
        except k.PatternValidationError as error:
            raise ValueError(str(error)) from error
        return [element.to_dict() for element in laid_out.elements], list(warnings)

    def preview_image(self, image, copies=3, max_pixels=4_000_000):
        """3x3 or 5x5 repeat of a rendered sheet, bounded in size, seam in the centre."""
        self._check()
        k = self._kernel
        try:
            return k.tile_preview(image, copies, max_pixels)
        except k.PatternValidationError as error:
            raise ValueError(str(error)) from error

    def _job(self, work, on_done, on_error, on_progress=None):
        self._check()
        lease = self._runtime.acquire_job_lease(MODULE_ID) if self._runtime else None

        def deliver(result):
            try:
                self._check()
            except ValueError:
                on_error("Доступ к модулю изменился. Результат не применён.")
                return
            on_done(result)

        job = PatternsJob(work, deliver, on_error, on_progress, self._jobs.discard, lease)
        self._jobs.add(job)
        return job.start()

    def render_sheet(self, payload, on_done, on_error):
        """Render one sheet from a project payload off the UI thread."""
        self._check()
        self._library._check_payload(payload)
        return self._job(lambda cancelled, progress: None if cancelled() else self._render(payload),
                         on_done, on_error)

    # -- export -------------------------------------------------------------

    def plan_export(self, folder, name, count, fmt="png"):
        """Resolve target files before writing; existing files are reported, never overwritten."""
        self._check()
        if fmt not in _FORMATS:
            raise ValueError("Формат должен быть PNG или JPG")
        if type(count) is not int or not 1 <= count <= MAX_SHEETS:
            raise ValueError(f"Листов должно быть от 1 до {MAX_SHEETS}")
        target = Path(folder)
        if target.is_symlink() or not target.is_dir():
            raise ValueError("Выберите существующую папку")
        stem = safe_name(name)
        files = [target / f"{stem} {index:02d}{_FORMATS[fmt]}" for index in range(1, count + 1)]
        return {"folder": str(target), "files": [f.name for f in files],
                "conflicts": [f.name for f in files if f.exists()]}

    def export_sheets(self, images, folder, name, fmt, inches, dpi, background, on_done, on_error, on_progress=None):
        """Write sheets to ``folder`` in a Core job; stops before writing on any name conflict."""
        k = self._kernel
        plan = self.plan_export(folder, name, len(images), fmt)
        if plan["conflicts"]:
            raise ValueError("Файлы уже существуют: " + ", ".join(plan["conflicts"][:3]))
        side = k.inches_to_px(inches, dpi)
        targets = [Path(folder) / file for file in plan["files"]]
        background = tuple(background)

        def work(cancelled, progress):
            written = []
            for index, (image, target) in enumerate(zip(images, targets), start=1):
                if cancelled():
                    break
                if target.exists():
                    raise ValueError(f"Файл уже существует: {target.name}")
                result = k.export_tile(image, target, size=(side, side), dpi=dpi, background=background)
                written.append(str(result.path))
                progress(index, len(targets))
            return {"written": written, "cancelled": len(written) < len(targets)}

        return self._job(work, on_done, on_error, on_progress)

    def close(self):
        self._closed = True
        for job in tuple(self._jobs):
            job.cancel()
