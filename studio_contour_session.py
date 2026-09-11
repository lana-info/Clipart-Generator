"""Undoable, non-UI editing session around :mod:`studio_contour`."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image

from studio_contour import MAX_IMAGE_PIXELS, ContourDocument


DEFAULT_HISTORY_LIMIT = 50
DEFAULT_HISTORY_BYTES = 64 * 1024 * 1024


class ContourEditSession:
    """Own an immutable RGBA source and bounded alpha-only edit history.

    Call :meth:`checkpoint` after a completed ``session.document.apply_path``.
    ``undo`` also safely handles a pending, uncheckpointed document mutation.
    """

    def __init__(
        self,
        rgba: np.ndarray,
        *,
        tolerance: float = 1.0,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        history_bytes: int = DEFAULT_HISTORY_BYTES,
        extract_paths: bool = True,
    ) -> None:
        if (not isinstance(rgba, np.ndarray) or rgba.dtype != np.uint8 or rgba.ndim != 3
                or rgba.shape[2] != 4):
            raise TypeError("rgba must be a uint8 array with shape (height, width, 4)")
        if not rgba.shape[0] or not rgba.shape[1] or rgba.shape[0] * rgba.shape[1] > MAX_IMAGE_PIXELS:
            raise ValueError("rgba has unsupported dimensions")
        if isinstance(history_limit, bool) or not isinstance(history_limit, int) or history_limit < 1:
            raise ValueError("history_limit must be a positive integer")
        if isinstance(history_bytes, bool) or not isinstance(history_bytes, int) or history_bytes < rgba.shape[0] * rgba.shape[1]:
            raise ValueError("history_bytes must hold at least one alpha snapshot")
        self._original_rgba = rgba.copy()
        self._original_rgba.flags.writeable = False
        self._tolerance = tolerance
        if not isinstance(extract_paths, bool):
            raise TypeError("extract_paths must be boolean")
        self._extract_paths = extract_paths
        self._history_limit = history_limit
        self._history_bytes_limit = history_bytes
        self.document = self._make_document(self._original_rgba[..., 3])
        # Reset always uses the immutable source; Undo stops at the oldest
        # retained predecessor, which advances when checkpoints are evicted.
        self._base_alpha = self._original_rgba[..., 3]
        self._undo: list[np.ndarray] = []
        self._redo: list[np.ndarray] = []

    @property
    def original_rgba(self) -> np.ndarray:
        """A writable copy of the source pixels, never the session's backing array."""
        return self._original_rgba.copy()

    @property
    def can_undo(self) -> bool:
        if not np.array_equal(self.document.alpha, self._checkpoint_alpha()):
            return True
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def history_bytes(self) -> int:
        base_bytes = 0 if np.shares_memory(self._base_alpha, self._original_rgba) else self._base_alpha.nbytes
        return base_bytes + sum(snapshot.nbytes for snapshot in (*self._undo, *self._redo))

    def checkpoint(self) -> bool:
        """Record the current alpha if it differs from the last checkpoint."""
        current = self.document.alpha
        if np.array_equal(current, self._checkpoint_alpha()):
            return False
        self._undo.append(current.copy())
        self._redo.clear()
        self._trim_history()
        return True

    def undo(self) -> bool:
        """Restore the preceding checkpoint, including pending uncheckpointed edits."""
        current = self.document.alpha
        if not np.array_equal(current, self._checkpoint_alpha()):
            # The direct document mutation is a new branch; no old redo state is
            # valid.  The pending state itself becomes the only redo candidate.
            self._redo.clear()
            self._redo.append(current.copy())
            self._restore(self._checkpoint_alpha())
            self._trim_history()
            return True
        if not self._undo:
            return False
        self._redo.append(self._undo.pop())
        self._restore(self._checkpoint_alpha())
        self._trim_history()
        return True

    def redo(self) -> bool:
        """Restore the next recorded alpha state, if one is available."""
        # A caller can alter session.document directly.  Such an uncheckpointed
        # mutation invalidates a previously undone future rather than reviving it.
        if not np.array_equal(self.document.alpha, self._checkpoint_alpha()):
            self._redo.clear()
            return False
        if not self._redo:
            return False
        snapshot = self._redo.pop()
        self._undo.append(snapshot)
        self._restore(snapshot)
        self._trim_history()
        return True

    def reset(self) -> bool:
        """Restore original alpha as an undoable checkpoint; RGB was never edited."""
        original_alpha = self._original_rgba[..., 3]
        changed = not np.array_equal(self.document.alpha, original_alpha)
        if not changed:
            return False
        # Preserve a pending direct edit, so one Undo returns exactly to what the
        # user saw just before Reset.  Then record reset as a normal new branch.
        if not np.array_equal(self.document.alpha, self._checkpoint_alpha()):
            self._undo.append(self.document.alpha.copy())
        self._redo.clear()
        self._restore(original_alpha)
        self._undo.append(original_alpha.copy())
        self._trim_history()
        return changed

    def current_rgba(self) -> np.ndarray:
        """Compose the edited alpha with source RGB without mutating the source."""
        return self.document.apply_to_rgba(self._original_rgba)

    def save_copy(self, path: str | Path) -> Path:
        """Write a new PNG only; an existing destination is always refused."""
        destination = Path(path)
        if destination.suffix.casefold() != ".png":
            raise ValueError("contour session output must be a PNG")
        if not destination.parent.is_dir():
            raise FileNotFoundError("destination directory does not exist")
        # Write the complete PNG to a same-directory file first.  ``link`` publishes
        # it only if destination is still absent, without exposing a partial PNG.
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w+b", dir=destination.parent,
                                             prefix=".contour-", suffix=".png", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                Image.fromarray(self.current_rgba(), "RGBA").save(temporary, format="PNG")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.link(temporary_path, destination)
        except FileExistsError:
            raise FileExistsError(f"refusing to overwrite existing output: {destination}") from None
        except Exception:
            raise
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return destination

    def _restore(self, alpha: np.ndarray) -> None:
        self.document = self._make_document(alpha)

    def _make_document(self, alpha: np.ndarray) -> ContourDocument:
        if self._extract_paths:
            return ContourDocument.from_alpha(alpha, tolerance=self._tolerance)
        # Opening, brush editing and history do not require vector extraction.
        # The UI explicitly requests paths only when the user selects Auto contour.
        return ContourDocument(alpha, extraction_tolerance=self._tolerance)

    def _checkpoint_alpha(self) -> np.ndarray:
        return self._undo[-1] if self._undo else self._base_alpha

    def _trim_history(self) -> None:
        # Eviction advances the undo boundary, never silently reconnects it to
        # the original. The additional predecessor counts towards the byte cap.
        while len(self._undo) > self._history_limit:
            self._base_alpha = self._undo.pop(0)
        while self.history_bytes > self._history_bytes_limit and len(self._undo) > 1:
            self._base_alpha = self._undo.pop(0)
        while self.history_bytes > self._history_bytes_limit and self._redo:
            self._redo.pop(0)
        while self.history_bytes > self._history_bytes_limit and self._undo:
            self._base_alpha = self._undo.pop(0)
