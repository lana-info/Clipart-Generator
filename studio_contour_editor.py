"""Self-contained, non-destructive alpha contour editor dialog for Vibix.

The module deliberately has no controller dependency.  It reads one PNG into
memory, edits only its alpha plane and can write a separately chosen PNG; the
source path is never overwritten by this dialog.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
from typing import Literal

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from v3_components import DEFAULT_TOKENS, V3_WINDOW_DEFAULT_SIZE
from studio_contour import BezierNode, BezierPath, extract_contours, sample_path
from studio_contour_session import ContourEditSession

MAX_IMAGE_PIXELS = 32_000_000
MAX_HISTORY = 30
MAX_AUTO_CONTOUR_PIXELS = 4 * 1024 * 1024
SNAP_RADIUS_PX = 12
ROI = tuple[int, int, int, int]
Point = tuple[float, float]


@dataclass
class _Node:
    point: Point
    in_handle: Point
    out_handle: Point
    kind: Literal["corner", "smooth"] = "corner"


@dataclass
class _Snapshot:
    alpha: np.ndarray
    roi: ROI | None
    nodes: list[_Node]


def _clone_nodes(nodes: list[_Node]) -> list[_Node]:
    return [_Node(n.point, n.in_handle, n.out_handle, n.kind) for n in nodes]


def _load_rgba(path: Path) -> np.ndarray:
    """Decode an allowed-size image without ever touching the source file."""
    with Image.open(path) as source:
        source.load()
        if source.width < 1 or source.height < 1 or source.width * source.height > MAX_IMAGE_PIXELS:
            raise ValueError("Изображение больше допустимого предела редактора (32 Мп).")
        return np.asarray(source.convert("RGBA"), dtype=np.uint8).copy()


class ContourCanvas(QWidget):
    """Paints the preview and direct-manipulation overlays in image coordinates."""

    changed = pyqtSignal()
    status_changed = pyqtSignal(str)

    def __init__(self, rgba: np.ndarray, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Opening must stay responsive for a valid 32 MP PNG.  The editor asks
        # for contour extraction only after the user explicitly chooses the
        # bounded auto-contour operation.
        self.session = ContourEditSession(rgba, history_limit=MAX_HISTORY, extract_paths=False)
        self.rgba = self.session.original_rgba
        self.roi: ROI | None = None
        self.nodes: list[_Node] = []
        self._active_path_index: int | None = None
        self._selected_node_index: int | None = None
        self.feather = 0
        self.snap_to_edge = True
        self.background: Literal["checker", "black", "white"] = "checker"
        self.tool: Literal["select", "restore", "remove", "pan"] = "select"
        self.brush_radius = 8
        self.brush_style = "hard"
        self._space_pan = False
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self._drag_mode: str | None = None
        self._drag_index = -1
        self._last_image_pos: Point | None = None
        self._before_drag: _Snapshot | None = None
        self._roi_anchor: Point | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(560, 430)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("Перетащите узел. Alt: исходящая ручка; Alt+Shift: входящая ручка.")

    @property
    def image_size(self) -> tuple[int, int]:
        return self.rgba.shape[1], self.rgba.shape[0]

    @property
    def alpha(self) -> np.ndarray:
        """The session-owned alpha plane; RGB remains immutable in the session."""
        return self.session.document.alpha

    def _snapshot(self) -> _Snapshot:
        return _Snapshot(self.alpha.copy(), self.roi, _clone_nodes(self.nodes))

    def _commit(self, before: _Snapshot) -> None:
        # Session owns the bounded alpha history.  ``before`` is only a short
        # lived gesture comparison so a click that changes nothing is not saved.
        self.session.checkpoint()
        self.changed.emit()

    def undo(self) -> None:
        if self.session.undo():
            self.nodes.clear(); self._active_path_index = None; self._selected_node_index = None
            self.update(); self.changed.emit()

    def redo(self) -> None:
        if self.session.redo():
            self.nodes.clear(); self._active_path_index = None; self._selected_node_index = None
            self.update(); self.changed.emit()

    def reset(self) -> None:
        if self.session.reset():
            self.nodes.clear(); self._active_path_index = None; self._selected_node_index = None; self.roi = None
            self.changed.emit(); self.update()

    def can_auto_contour(self) -> tuple[bool, str]:
        if self.alpha.size > MAX_AUTO_CONTOUR_PIXELS:
            return False, "Для этого размера пока доступна кисть. Автоконтур поддерживает PNG до 2048×2048 пикселей по площади."
        if not np.any(self.alpha == 0) or not np.any(self.alpha > 0):
            return False, "Автоконтур доступен только для уже прозрачного PNG."
        return True, ""

    def auto_contour(self) -> None:
        """Offer editable points from existing alpha only; never infer opaque RGB."""
        allowed, message = self.can_auto_contour()
        if not allowed:
            self.status_changed.emit(message); return
        # Bound full-image extraction, not ROI area: the core needs neighbouring
        # paths to protect holes and small details. This is a synchronous operation.
        self.status_changed.emit("Строим контур по существующей альфа-маске…")
        self._extract_contour()

    def _extract_contour(self) -> None:
        paths = self.session.document.paths
        if not paths:
            try:
                paths = extract_contours(self.alpha, tolerance=1.0)
            except (cv2.error, TypeError, ValueError) as exc:
                self.status_changed.emit(f"Автоконтур недоступен: {exc}")
                return
            self.session.document.paths = paths
        if not paths:
            self.status_changed.emit("Контур не найден. Выберите область с видимой прозрачностью.")
            return
        candidates = list(enumerate(paths))
        if self.roi:
            left, top, right, bottom = self.roi
            candidates = [(index, path) for index, path in candidates
                          if self._path_intersects(path, (left, top, right, bottom))]
        if not candidates:
            self.status_changed.emit("В области нет существующего альфа-контура.")
            return
        # Prefer an exterior path; hole paths remain represented and protected by
        # ContourDocument.apply_path when the exterior is moved.
        candidates.sort(key=lambda item: (item[1].fill_value != 255, -self._path_area(item[1])))
        self._active_path_index, path = candidates[0]
        self._selected_node_index = None
        self.nodes = [_Node(node.point, node.in_handle or node.point, node.out_handle or node.point, node.kind)
                      for node in path.nodes]
        if self.roi is None:
            points = sample_path(path)
            xs, ys = points[:, 0], points[:, 1]
            pad = max(8, int(max(self.image_size) * .03))
            self.roi = self._bounded_roi(int(xs.min()) - pad, int(ys.min()) - pad,
                                         int(xs.max()) + pad + 1, int(ys.max()) + pad + 1)
        # Selecting a proposal is UI state, not an alpha edit, and must not add
        # a misleading undo step.
        self.status_changed.emit(f"Автоконтур готов: {len(self.nodes)} точек.")
        self.update()

    def _activate_closest_path(self, fill_value: int, target: Point) -> bool:
        candidates = [(index, path) for index, path in enumerate(self.session.document.paths)
                      if path.fill_value == fill_value]
        if not candidates:
            self.nodes.clear(); self._active_path_index = None; self._selected_node_index = None
            return False
        def distance(item: tuple[int, BezierPath]) -> float:
            points = sample_path(item[1])
            centre = points.mean(axis=0)
            return float((centre[0] - target[0]) ** 2 + (centre[1] - target[1]) ** 2)
        self._active_path_index, path = min(candidates, key=distance)
        self._selected_node_index = None
        self.nodes = [_Node(node.point, node.in_handle or node.point, node.out_handle or node.point, node.kind)
                      for node in path.nodes]
        return True

    def _select_nearest_node(self, target: Point, *, kind: Literal["corner", "smooth"] | None = None) -> None:
        if not self.nodes:
            self._selected_node_index = None
            return
        index = min(range(len(self.nodes)), key=lambda candidate: (
            (self.nodes[candidate].point[0] - target[0]) ** 2
            + (self.nodes[candidate].point[1] - target[1]) ** 2
        ))
        self._selected_node_index = index
        if kind is None:
            return
        node = self.nodes[index]
        node.kind = kind
        if kind == "corner":
            node.in_handle = node.point
            node.out_handle = node.point
            return
        previous = np.asarray(self.nodes[index - 1].point, dtype=float)
        following = np.asarray(self.nodes[(index + 1) % len(self.nodes)].point, dtype=float)
        point = np.asarray(node.point, dtype=float)
        tangent = (following - previous) / 6.0
        node.in_handle = self._clamp_to_roi(tuple(point - tangent))
        node.out_handle = self._clamp_to_roi(tuple(point + tangent))

    @staticmethod
    def _path_area(path: BezierPath) -> float:
        points = sample_path(path)
        return abs(float(cv2.contourArea(np.rint(points).astype(np.float32))))

    @staticmethod
    def _path_intersects(path: BezierPath, roi: ROI) -> bool:
        points = sample_path(path)
        left, top, right, bottom = roi
        return not (points[:, 0].max() < left or points[:, 0].min() >= right
                    or points[:, 1].max() < top or points[:, 1].min() >= bottom)

    def _bounded_roi(self, left: int, top: int, right: int, bottom: int) -> ROI:
        width, height = self.image_size
        left, right = max(0, left), min(width, right)
        top, bottom = max(0, top), min(height, bottom)
        return (left, top, max(left + 1, right), max(top + 1, bottom))

    def _image_rect(self) -> QRectF:
        iw, ih = self.image_size
        scale = min(self.width() / iw, self.height() / ih) * self.zoom
        return QRectF((self.width() - iw * scale) / 2 + self.pan.x(),
                      (self.height() - ih * scale) / 2 + self.pan.y(), iw * scale, ih * scale)

    def _to_image(self, pos: QPointF) -> Point | None:
        rect = self._image_rect()
        if not rect.contains(pos): return None
        return ((pos.x() - rect.left()) * self.image_size[0] / rect.width(),
                (pos.y() - rect.top()) * self.image_size[1] / rect.height())

    def _to_screen(self, point: Point) -> QPointF:
        rect = self._image_rect()
        return QPointF(rect.left() + point[0] * rect.width() / self.image_size[0],
                       rect.top() + point[1] * rect.height() / self.image_size[1])

    def _point_in_roi(self, point: Point) -> bool:
        return self.roi is not None and self.roi[0] <= point[0] < self.roi[2] and self.roi[1] <= point[1] < self.roi[3]

    def _clamp_to_roi(self, point: Point) -> Point:
        if not self.roi: return point
        left, top, right, bottom = self.roi
        return (min(max(point[0], left), right - 1), min(max(point[1], top), bottom - 1))

    def _hit_node(self, point: Point) -> tuple[str, int] | None:
        rect = self._image_rect(); radius = 9 * self.image_size[0] / max(1.0, rect.width())
        for index, node in enumerate(self.nodes):
            for kind, candidate in (("node", node.point), ("in", node.in_handle), ("out", node.out_handle)):
                if (candidate[0] - point[0]) ** 2 + (candidate[1] - point[1]) ** 2 <= radius ** 2:
                    return kind, index
        return None

    @staticmethod
    def _lerp(left: Point, right: Point, amount: float) -> Point:
        return (
            left[0] + (right[0] - left[0]) * amount,
            left[1] + (right[1] - left[1]) * amount,
        )

    def _nearest_segment(self, point: Point, *, maximum_distance: float | None = None) -> tuple[int, float] | None:
        """Return the nearest cubic segment, optionally requiring a nearby hit."""
        if len(self.nodes) < 3:
            return None
        if maximum_distance is None:
            rect = self._image_rect()
            maximum_distance = 10 * self.image_size[0] / max(1.0, rect.width())
        best: tuple[float, int, float] | None = None
        for index, node in enumerate(self.nodes):
            following = self.nodes[(index + 1) % len(self.nodes)]
            for step in range(1, 33):
                amount = step / 32
                inverse = 1 - amount
                curve = (
                    inverse ** 3 * np.asarray(node.point)
                    + 3 * inverse ** 2 * amount * np.asarray(node.out_handle)
                    + 3 * inverse * amount ** 2 * np.asarray(following.in_handle)
                    + amount ** 3 * np.asarray(following.point)
                )
                distance = (curve[0] - point[0]) ** 2 + (curve[1] - point[1]) ** 2
                candidate = (float(distance), index, amount)
                if best is None or candidate < best:
                    best = candidate
        if best is None or best[0] > maximum_distance ** 2:
            return None
        return best[1], best[2]

    def _expand_roi_for_point(self, point: Point) -> None:
        """Keep the local alpha update bounded while allowing a new outer node."""
        if self.roi is None:
            self.roi = self._bounded_roi(round(point[0]), round(point[1]),
                                         round(point[0]) + 1, round(point[1]) + 1)
            return
        left, top, right, bottom = self.roi
        padding = 3
        self.roi = self._bounded_roi(
            min(left, round(point[0]) - padding),
            min(top, round(point[1]) - padding),
            max(right, round(point[0]) + padding + 1),
            max(bottom, round(point[1]) + padding + 1),
        )

    def _insert_node(self, point: Point, *, free_position: bool) -> bool:
        nearest = self._nearest_segment(point, maximum_distance=float("inf") if free_position else None)
        if nearest is None:
            self.status_changed.emit("Сначала постройте или выберите контур.")
            return False
        before = self._snapshot()
        if free_position:
            point = self._snap_to_source_edge(point)
            self._expand_roi_for_point(point)
            point = self._clamp_to_roi(point)
        else:
            point = self._clamp_to_roi(self._snap_to_source_edge(point))
        index, amount = nearest
        node = self.nodes[index]
        following = self.nodes[(index + 1) % len(self.nodes)]
        if free_position:
            inserted = _Node(point, point, point, "corner")
        else:
            first = self._lerp(node.point, node.out_handle, amount)
            second = self._lerp(node.out_handle, following.in_handle, amount)
            third = self._lerp(following.in_handle, following.point, amount)
            incoming = self._lerp(first, second, amount)
            outgoing = self._lerp(second, third, amount)
            position = self._lerp(incoming, outgoing, amount)
            node.out_handle = first
            following.in_handle = third
            inserted = _Node(position, incoming, outgoing, "smooth")
        inserted_index = index + 1
        self.nodes.insert(inserted_index, inserted)
        self._selected_node_index = inserted_index
        if free_position:
            try:
                self._apply_nodes_locally()
            except (IndexError, TypeError, ValueError) as exc:
                self.nodes = before.nodes
                self.roi = before.roi
                self._selected_node_index = None
                self.status_changed.emit(f"Контур не применён: {exc}")
                return False
            self._select_nearest_node(point, kind="corner")
            if not np.array_equal(before.alpha, self.alpha):
                self._commit(before)
        self.status_changed.emit("Точка добавлена. Перетащите её, чтобы изменить контур.")
        self.update()
        return True

    def _toggle_selected_node_kind(self) -> bool:
        index = self._selected_node_index
        if index is None or not 0 <= index < len(self.nodes):
            self.status_changed.emit("Выберите точку контура для изменения типа.")
            return False
        before = self._snapshot()
        node = self.nodes[index]
        target = node.point
        is_corner = node.kind == "corner"
        if is_corner:
            previous = np.asarray(self.nodes[index - 1].point, dtype=float)
            following = np.asarray(self.nodes[(index + 1) % len(self.nodes)].point, dtype=float)
            point = np.asarray(node.point, dtype=float)
            tangent = (following - previous) / 6.0
            node.in_handle = self._clamp_to_roi(tuple(point - tangent))
            node.out_handle = self._clamp_to_roi(tuple(point + tangent))
            node.kind = "smooth"
            label = "плавной"
        else:
            node.in_handle = node.point
            node.out_handle = node.point
            node.kind = "corner"
            label = "угловой"
        try:
            self._apply_nodes_locally()
        except (IndexError, TypeError, ValueError) as exc:
            self.nodes = before.nodes
            self._selected_node_index = index
            self.status_changed.emit(f"Контур не применён: {exc}")
            return False
        self._select_nearest_node(target, kind="smooth" if is_corner else "corner")
        if not np.array_equal(before.alpha, self.alpha):
            self._commit(before)
        self.status_changed.emit(f"Точка стала {label}.")
        self.update()
        return True

    def _delete_selected_node(self) -> bool:
        index = self._selected_node_index
        if index is None or not 0 <= index < len(self.nodes):
            self.status_changed.emit("Выберите точку контура для удаления.")
            return False
        if len(self.nodes) <= 3:
            self.status_changed.emit("В контуре должно остаться не менее трёх точек.")
            return False
        before = self._snapshot()
        self.nodes.pop(index)
        self._selected_node_index = min(index, len(self.nodes) - 1)
        try:
            self._apply_nodes_locally()
        except (IndexError, TypeError, ValueError) as exc:
            self.status_changed.emit(f"Контур не применён: {exc}")
            self.nodes = before.nodes
            self._selected_node_index = None
            return False
        if not np.array_equal(before.alpha, self.alpha):
            self._commit(before)
        self.status_changed.emit("Точка удалена.")
        self.update()
        return True

    def _snap_to_source_edge(self, point: Point) -> Point:
        """Snap only near the source alpha edge, never to arbitrary RGB texture."""
        if not self.snap_to_edge:
            return point
        radius = SNAP_RADIUS_PX
        width, height = self.image_size
        left = max(0, int(round(point[0])) - radius)
        top = max(0, int(round(point[1])) - radius)
        right = min(width, int(round(point[0])) + radius + 1)
        bottom = min(height, int(round(point[1])) + radius + 1)
        source = (self.rgba[top:bottom, left:right, 3] > 0).astype(np.uint8)
        edge = cv2.morphologyEx(source, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        ys, xs = np.nonzero(edge)
        if not len(xs):
            return point
        candidates = np.column_stack((xs + left, ys + top)).astype(float)
        distances = (candidates[:, 0] - point[0]) ** 2 + (candidates[:, 1] - point[1]) ** 2
        closest = int(np.argmin(distances))
        if distances[closest] > radius ** 2:
            return point
        return (float(candidates[closest, 0]), float(candidates[closest, 1]))

    def _stroke(self, start: Point, end: Point, value: int) -> None:
        if not self.roi: return
        before = self.alpha.copy()
        left, top, right, bottom = self.roi
        mask = np.zeros((bottom - top, right - left), dtype=np.uint8)
        p0 = (round(start[0] - left), round(start[1] - top))
        p1 = (round(end[0] - left), round(end[1] - top))
        cv2.line(mask, p0, p1, 255, max(1, self.brush_radius * 2), cv2.LINE_AA)
        cv2.circle(mask, p0, self.brush_radius, 255, -1, cv2.LINE_AA)
        cv2.circle(mask, p1, self.brush_radius, 255, -1, cv2.LINE_AA)
        if self.brush_style == "soft":
            sigma = max(0.45, self.brush_radius * 0.12)
            mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=sigma, sigmaY=sigma)
        region = self.alpha[top:bottom, left:right]
        coverage = mask.astype(np.float32) / 255.0
        region[:] = np.rint(region.astype(np.float32) * (1.0 - coverage) + value * coverage).astype(np.uint8)
        if not np.array_equal(before, self.alpha): self.update()

    def _apply_nodes_locally(self) -> bool:
        """Apply exactly one selected Bezier path through the alpha document.

        The document composites its old/new footprint in the selected ROI.  It
        deliberately preserves holes, disconnected detail and thin raster
        residuals, unlike assigning a filled polygon to the complete ROI.
        """
        if not self.roi or len(self.nodes) < 3 or self._active_path_index is None:
            return False
        if self._active_path_index >= len(self.session.document.paths):
            return False
        previous = self.session.document.paths[self._active_path_index]
        replacement = BezierPath(
            tuple(BezierNode(node.point, node.kind, in_handle=node.in_handle, out_handle=node.out_handle)
                  for node in self.nodes),
            previous.fill_value, self.alpha.shape, previous.contour_id,
        )
        self.session.document.apply_path(self._active_path_index, replacement, self.roi,
                                         feather=float(self.feather))
        centre = np.asarray([node.point for node in self.nodes], dtype=float).mean(axis=0)
        self._activate_closest_path(previous.fill_value, (float(centre[0]), float(centre[1])))
        return True

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        image_pos = self._to_image(event.position())
        if event.button() == Qt.MouseButton.MiddleButton or self.tool == "pan" or self._space_pan:
            self._drag_mode = "pan"; self._last_image_pos = (event.position().x(), event.position().y()); return
        if image_pos is None:
            return
        if event.button() == Qt.MouseButton.RightButton and self.tool == "select":
            hit = self._hit_node(image_pos)
            if hit:
                self._selected_node_index = hit[1]
                self._toggle_selected_node_kind()
                event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._before_drag = self._snapshot()
        if self.tool in ("remove", "restore") and self._point_in_roi(image_pos):
            # A raster brush edit makes cached vector proposals stale.  The next
            # Auto contour extracts fresh paths from the current alpha.
            self.nodes.clear(); self._active_path_index = None
            self.session.document.paths.clear()
            self._drag_mode = "brush"; self._last_image_pos = image_pos
            self._stroke(image_pos, image_pos, 0 if self.tool == "remove" else 255); return
        if self.tool == "select":
            hit = self._hit_node(image_pos)
            if hit:
                self._selected_node_index = hit[1]
                if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                    self._drag_mode = "in" if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else "out"
                else:
                    self._drag_mode = hit[0]
                self._drag_index = hit[1]; return
            if self.nodes and self._active_path_index is not None:
                # A click adds a point; a drag that crosses the movement threshold
                # instead becomes the familiar ROI selection gesture.
                self._drag_mode = "pending_add"
                self._roi_anchor = image_pos
                return
            self._drag_mode = "roi"; self._roi_anchor = image_pos
            self.roi = self._bounded_roi(round(image_pos[0]), round(image_pos[1]), round(image_pos[0]) + 1, round(image_pos[1]) + 1)

    def mouseMoveEvent(self, event) -> None:
        image_pos = self._to_image(event.position())
        if self._drag_mode == "pan" and self._last_image_pos:
            old = self._last_image_pos; self.pan += QPointF(event.position().x()-old[0], event.position().y()-old[1]); self._last_image_pos=(event.position().x(),event.position().y()); self.update(); return
        if image_pos is None: return
        if self._drag_mode == "pending_add" and self._roi_anchor:
            anchor = self._roi_anchor
            rect = self._image_rect()
            threshold = 4 * self.image_size[0] / max(1.0, rect.width())
            if (image_pos[0] - anchor[0]) ** 2 + (image_pos[1] - anchor[1]) ** 2 >= threshold ** 2:
                self._drag_mode = "roi"
                self.roi = self._bounded_roi(
                    round(min(anchor[0], image_pos[0])), round(min(anchor[1], image_pos[1])),
                    round(max(anchor[0] + 1, image_pos[0])), round(max(anchor[1] + 1, image_pos[1])),
                )
                self.update()
        elif self._drag_mode == "roi" and self.roi:
            anchor = self._roi_anchor or image_pos
            self.roi = self._bounded_roi(round(min(anchor[0], image_pos[0])), round(min(anchor[1], image_pos[1])), round(max(anchor[0] + 1, image_pos[0])), round(max(anchor[1] + 1, image_pos[1]))); self.update()
        elif self._drag_mode == "brush" and self._last_image_pos:
            self._stroke(self._last_image_pos, image_pos, 0 if self.tool == "remove" else 255); self._last_image_pos = image_pos
        elif self._drag_mode in ("node", "in", "out") and 0 <= self._drag_index < len(self.nodes):
            node = self.nodes[self._drag_index]; p = self._clamp_to_roi(image_pos)
            if self._drag_mode == "node":
                p = self._clamp_to_roi(self._snap_to_source_edge(p))
                dx, dy = p[0]-node.point[0], p[1]-node.point[1]
                node.point = p; node.in_handle = self._clamp_to_roi((node.in_handle[0]+dx,node.in_handle[1]+dy)); node.out_handle = self._clamp_to_roi((node.out_handle[0]+dx,node.out_handle[1]+dy))
            elif self._drag_mode == "in": node.in_handle = p
            else: node.out_handle = p
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_mode == "pending_add" and self._roi_anchor is not None:
            self._insert_node(self._roi_anchor, free_position=True)
            self._drag_mode = None; self._drag_index = -1; self._last_image_pos = None; self._before_drag = None; self._roi_anchor = None
            return
        if self._drag_mode and self._before_drag:
            if self._drag_mode in ("node", "in", "out") and self._before_drag.nodes != self.nodes:
                try:
                    self._apply_nodes_locally()
                except (IndexError, TypeError, ValueError) as exc:
                    self.status_changed.emit(f"Контур не применён: {exc}")
            if not np.array_equal(self._before_drag.alpha, self.alpha) or self._before_drag.roi != self.roi or self._before_drag.nodes != self.nodes:
                self._commit(self._before_drag)
            self.update()
        self._drag_mode = None; self._drag_index = -1; self._last_image_pos = None; self._before_drag = None; self._roi_anchor = None

    def wheelEvent(self, event) -> None:
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self.zoom = min(8.0, max(.25, self.zoom * factor)); self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._space_pan = True
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo(); event.accept(); return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redo(); event.accept(); return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._delete_selected_node(); event.accept(); return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._space_pan = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        self._space_pan = False
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self); p.fillRect(self.rect(), QColor("#101827"))
        rect = self._image_rect()
        # Draw the requested compositing backdrop at preview scale.
        if self.background == "checker":
            cell = 12
            visible = rect.intersected(QRectF(self.rect()))
            for y in range(int(visible.top()), int(visible.bottom()), cell):
                for x in range(int(visible.left()), int(visible.right()), cell):
                    p.fillRect(x, y, cell, cell, QColor("#273549") if ((x+y)//cell)%2 else QColor("#1b2737"))
        else: p.fillRect(rect, QColor("#070b11" if self.background == "black" else "#f8fafc"))
        result = self.rgba.copy(); result[..., 3] = self.alpha
        h,w,_ = result.shape
        image = QImage(result.data, w, h, w*4, QImage.Format.Format_RGBA8888).copy()
        p.drawImage(rect, image)
        p.setPen(QPen(QColor("#334155"), 1)); p.drawRect(rect)
        if self.roi:
            left,top,right,bottom=self.roi
            roi_rect = QRectF(self._to_screen((left,top)), self._to_screen((right,bottom))).normalized()
            p.setPen(QPen(QColor("#8ccfd0"), 1)); p.drawRoundedRect(roi_rect, 7, 7)
        if len(self.nodes) >= 3:
            path = QPainterPath(); path.moveTo(self._to_screen(self.nodes[0].point))
            for i,node in enumerate(self.nodes):
                nxt=self.nodes[(i+1)%len(self.nodes)]
                path.cubicTo(self._to_screen(node.out_handle), self._to_screen(nxt.in_handle), self._to_screen(nxt.point))
            p.setPen(QPen(QColor("#67e8f9"), 2)); p.drawPath(path)
            p.setPen(QPen(QColor("#8ccfd0"), 1))
            for index, node in enumerate(self.nodes):
                for handle in (node.in_handle,node.out_handle):
                    p.drawLine(self._to_screen(node.point),self._to_screen(handle))
                    p.setBrush(QColor("#101827")); p.drawEllipse(self._to_screen(handle),3,3)
                p.setBrush(QColor("#fde68a") if index == self._selected_node_index else QColor("#f8fafc")); p.drawEllipse(self._to_screen(node.point),5,5)
        p.end()


class ContourEditorDialog(QDialog):
    """Modal alpha-only editor. ``saved_path`` stays ``None`` until an explicit save."""

    def __init__(self, path: str | Path, parent: QWidget | None = None, *, rgba: np.ndarray | None = None) -> None:
        super().__init__(parent)
        self.source_path = Path(path)
        self.saved_path: Path | None = None
        self._rgba: np.ndarray | None = None
        self.setWindowTitle("Редактор контура · Vibix")
        self.resize(*V3_WINDOW_DEFAULT_SIZE); self.setMinimumSize(980,700)
        self.setStyleSheet(self._stylesheet())
        self._build_shell()
        self._shortcuts = []
        for key, action in (
            ("[", lambda: self._cycle_brush(-1)),
            ("]", lambda: self._cycle_brush(1)),
            ("V", lambda: self._set_tool("select")),
            ("B", lambda: self._set_tool("restore")),
            ("E", lambda: self._set_tool("remove")),
            ("H", lambda: self._set_tool("pan")),
            ("M", self._toggle_snap),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)
            self._shortcuts.append(shortcut)
        if rgba is not None:
            if not isinstance(rgba, np.ndarray) or rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4:
                raise TypeError("rgba must be a uint8 array with shape (height, width, 4)")
            if not rgba.shape[0] or not rgba.shape[1] or rgba.shape[0] * rgba.shape[1] > MAX_IMAGE_PIXELS:
                raise ValueError("rgba has unsupported dimensions")
            self._set_rgba(rgba.copy())
        else:
            self._open_path(self.source_path)

    def _stylesheet(self) -> str:
        t=DEFAULT_TOKENS
        return f"""QDialog {{background:{t.canvas};color:{t.text};font-family:'Segoe UI';}}
        QFrame#panel {{background:{t.surface};border:1px solid {t.border};border-radius:8px;}}
        QPushButton,QToolButton {{background:{t.surface_muted};color:{t.text};border:1px solid {t.border};border-radius:8px;padding:7px 10px;min-height:22px;}}
        QPushButton:hover,QToolButton:hover {{border-color:{t.focus};}} QPushButton[primary='true'] {{background:{t.accent};color:#062c2a;border-color:{t.accent};font-weight:600;}}
        QPushButton:disabled {{color:{t.disabled};background:{t.disabled_soft};border-color:{t.border};}}
        QLabel {{color:{t.text};}} QToolButton:checked {{border-color:{t.accent};background:{t.surface};}}
        QLabel#muted {{color:{t.text_muted};}} QLabel#title {{font-size:18px;font-weight:700;}}"""

    def _build_shell(self) -> None:
        outer=QVBoxLayout(self); outer.setContentsMargins(18,14,18,12); outer.setSpacing(10)
        head=QHBoxLayout(); title=QLabel("VIBIX   Редактор контура"); title.setObjectName("title"); head.addWidget(title); head.addStretch()
        local=QLabel("● Локальная правка"); local.setObjectName("muted"); head.addWidget(local); outer.addLayout(head)
        self.status=QLabel("Правка изменяет только альфа-маску в выбранной области."); self.status.setObjectName("muted"); outer.addWidget(self.status)
        body=QHBoxLayout(); body.setSpacing(12)
        self.tools=QFrame(); self.tools.setObjectName("panel"); tools_layout=QVBoxLayout(self.tools); tools_layout.setContentsMargins(7,7,7,7); tools_layout.setSpacing(5)
        self.tool_buttons={}
        for key,label in (("select","⌁\nВыбрать"),("restore","＋\nВернуть"),("remove","−\nУбрать"),("pan","✥\nРука")):
            b=QToolButton(); b.setText(label); b.setCheckable(True); b.clicked.connect(lambda checked=False,k=key:self._set_tool(k)); tools_layout.addWidget(b); self.tool_buttons[key]=b
        tools_layout.addStretch(); self.tool_buttons["select"].setChecked(True); body.addWidget(self.tools)
        self.canvas_holder=QFrame(); self.canvas_holder.setObjectName("panel"); self.canvas_layout=QVBoxLayout(self.canvas_holder); self.canvas_layout.setContentsMargins(8,8,8,8); body.addWidget(self.canvas_holder,1)
        panel=QFrame(); panel.setObjectName("panel"); panel.setFixedWidth(254); right=QVBoxLayout(panel); right.setContentsMargins(16,14,16,14); right.setSpacing(9)
        label=QLabel("Контур и альфа"); label.setObjectName("title"); right.addWidget(label)
        self.auto_button=QPushButton("Автоконтур"); self.auto_button.setProperty("primary",True); self.auto_button.clicked.connect(self._auto); right.addWidget(self.auto_button)
        self.snap_button = QToolButton()
        self.snap_button.setText("Притягивание к краю")
        self.snap_button.setToolTip("Притягивание точек к краю объекта. Клавиша M")
        self.snap_button.setAccessibleName("Притягивание точек к краю объекта")
        self.snap_button.setCheckable(True)
        self.snap_button.setChecked(True)
        self.snap_button.toggled.connect(self._set_snap)
        right.addWidget(self.snap_button)
        reset=QPushButton("Сбросить изменения"); reset.clicked.connect(self._reset); right.addWidget(reset)
        right.addWidget(QLabel("Край")); self.feather_buttons=[]; row=QHBoxLayout()
        group=QButtonGroup(self)
        for value in (0,1,2):
            b=QToolButton(); b.setText(f"{value} px"); b.setCheckable(True); b.setChecked(value==0); b.clicked.connect(lambda checked=False,v=value:self._set_feather(v)); group.addButton(b); row.addWidget(b); self.feather_buttons.append(b)
        right.addLayout(row)
        right.addWidget(QLabel("Тип кисти"))
        brush_styles = QHBoxLayout()
        self.brush_style_buttons = {}
        self.brush_style_group = QButtonGroup(self)
        for style, label in (("hard", "Жёсткая"), ("soft", "Мягкая")):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(style == "hard")
            button.clicked.connect(lambda checked=False, selected=style: self._set_brush_style(selected))
            self.brush_style_group.addButton(button)
            self.brush_style_buttons[style] = button
            brush_styles.addWidget(button)
        right.addLayout(brush_styles)
        right.addWidget(QLabel("Кисть, пиксели"))
        self.brush_sizes = (2, 8, 16, 32, 64)
        self.brush_buttons = {}
        sizes = QHBoxLayout()
        sizes.setSpacing(3)
        self.brush_group = QButtonGroup(self)
        for size in self.brush_sizes:
            button = QToolButton()
            button.setText(str(size))
            button.setStyleSheet("padding: 4px 3px;")
            button.setCheckable(True)
            button.setChecked(size == 16)
            button.setToolTip(f"Толщина {size} пикселей. Клавиши [ и ]")
            button.setAccessibleName(f"Кисть {size} пикселей")
            button.clicked.connect(lambda checked=False, value=size: self._set_brush(value))
            self.brush_group.addButton(button)
            self.brush_buttons[size] = button
            sizes.addWidget(button)
        right.addLayout(sizes)
        right.addWidget(QLabel("Просмотр")); views=QHBoxLayout(); view_group=QButtonGroup(self); self.view_buttons={}
        for key,label in (("checker","Сетка"),("black","Чёрн."),("white","Белый")):
            b=QToolButton(); b.setText(label); b.setCheckable(True); b.setChecked(key=="checker"); b.clicked.connect(lambda checked=False,k=key:self._set_background(k)); view_group.addButton(b); views.addWidget(b); self.view_buttons[key]=b
        right.addLayout(views); right.addStretch()
        rgb=QLabel("● Цвета не изменены"); rgb.setObjectName("muted"); right.addWidget(rgb)
        history=QHBoxLayout(); self.undo_button=QPushButton("↶ Отменить"); self.undo_button.clicked.connect(lambda:self.canvas.undo()); self.redo_button=QPushButton("↷ Повторить"); self.redo_button.clicked.connect(lambda:self.canvas.redo()); history.addWidget(self.undo_button); history.addWidget(self.redo_button); right.addLayout(history); body.addWidget(panel); outer.addLayout(body,1)
        bottom=QHBoxLayout(); self.open_button=QPushButton("Открыть другой PNG"); self.open_button.clicked.connect(self._open_picker); bottom.addWidget(self.open_button); bottom.addStretch(); cancel=QPushButton("Отмена"); cancel.clicked.connect(self.reject); self.save_button=QPushButton("Сохранить как PNG"); self.save_button.setProperty("primary",True); self.save_button.clicked.connect(self._save_as); bottom.addWidget(cancel); bottom.addWidget(self.save_button); outer.addLayout(bottom)

    def _open_path(self, path: Path) -> None:
        try: rgba=_load_rgba(path)
        except (OSError, ValueError):
            if hasattr(self, "canvas"):
                self.status.setText("Не удалось открыть другой PNG. Текущие правки остались в редакторе.")
            else:
                self._rgba = None
                self.status.setText("Изображение недоступно. Откройте другой PNG.")
                self.auto_button.setEnabled(False)
                self.save_button.setEnabled(False)
                self.undo_button.setEnabled(False)
                self.redo_button.setEnabled(False)
            return
        self.source_path=path; self._set_rgba(rgba)

    def _set_rgba(self, rgba: np.ndarray) -> None:
        self._rgba=rgba
        if hasattr(self,"canvas"):
            self.canvas.setParent(None); self.canvas.deleteLater()
        self.canvas=ContourCanvas(rgba); self.canvas.status_changed.connect(self.status.setText); self.canvas.changed.connect(self._update_history)
        self._set_tool("select")
        self._set_feather(0)
        self.feather_buttons[0].setChecked(True)
        self._set_brush_style("hard")
        self._set_brush(16)
        self._set_background("checker")
        self._set_snap(self.snap_button.isChecked())
        self.view_buttons["checker"].setChecked(True)
        self.canvas_layout.addWidget(self.canvas); self.auto_button.setEnabled(True); self.save_button.setEnabled(True); self.status.setText("Выберите область или построьте контур по существующей альфа-маске."); self._update_history()

    def _set_tool(self,key:str)->None:
        if not hasattr(self,"canvas"): return
        self.canvas.tool=key
        for name,b in self.tool_buttons.items(): b.setChecked(name==key)

    def _set_feather(self,value:int)->None:
        if hasattr(self,"canvas"): self.canvas.feather=value

    def _set_snap(self, enabled: bool) -> None:
        if hasattr(self, "canvas"):
            self.canvas.snap_to_edge = bool(enabled)

    def _toggle_snap(self) -> None:
        self.snap_button.setChecked(not self.snap_button.isChecked())

    def _set_brush_style(self, style: str) -> None:
        self.brush_style_buttons[style].setChecked(True)
        if hasattr(self, "canvas"):
            self.canvas.brush_style = style

    def _set_brush(self,value:int)->None:
        self.brush_buttons[value].setChecked(True)
        if hasattr(self,"canvas"): self.canvas.brush_radius=max(1,value//2)

    def _cycle_brush(self, step: int) -> None:
        current = next(size for size, button in self.brush_buttons.items() if button.isChecked())
        index = max(0, min(len(self.brush_sizes) - 1, self.brush_sizes.index(current) + step))
        self._set_brush(self.brush_sizes[index])

    def _set_background(self,key:str)->None:
        if hasattr(self,"canvas"): self.canvas.background=key; self.canvas.update()

    def _auto(self)->None:
        if hasattr(self,"canvas"): self.canvas.auto_contour()

    def _reset(self)->None:
        if hasattr(self,"canvas"): self.canvas.reset(); self.status.setText("Изменения маски сброшены.")

    def _update_history(self)->None:
        if hasattr(self,"canvas"):
            self.undo_button.setEnabled(self.canvas.session.can_undo); self.redo_button.setEnabled(self.canvas.session.can_redo)

    def _open_picker(self)->None:
        filename,_=QFileDialog.getOpenFileName(self,"Открыть PNG",str(self.source_path.parent),"PNG изображения (*.png)")
        if filename: self._open_path(Path(filename))

    def _save_as(self)->None:
        if self._rgba is None: return
        filename,_=QFileDialog.getSaveFileName(self,"Сохранить отдельный PNG",str(self.source_path.with_stem(self.source_path.stem+"_contour")),"PNG изображения (*.png)")
        if not filename: return
        destination=Path(filename).with_suffix(".png")
        try:
            if destination.resolve() == self.source_path.resolve():
                raise ValueError("Выберите отдельное имя: исходный PNG не перезаписывается.")
            from chroma_generation_record import (
                capture_generation_record, publish_generation_copy,
            )
            generation_record = capture_generation_record(self.source_path)
            if generation_record is None:
                self.canvas.session.save_copy(destination)
            else:
                staged = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=destination.parent, prefix=".contour-", suffix=".png", delete=False
                    ) as temporary:
                        staged = Path(temporary.name)
                        Image.fromarray(self.canvas.session.current_rgba(), "RGBA").save(
                            temporary, format="PNG"
                        )
                        temporary.flush(); os.fsync(temporary.fileno())
                    publish_generation_copy(staged, destination, generation_record, stage="final")
                finally:
                    if staged is not None:
                        staged.unlink(missing_ok=True)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.status.setText(str(exc)); return
        self.saved_path=destination; self.accept()

    def keyPressEvent(self,event)->None:
        if hasattr(self,"canvas") and event.matches(QKeySequence.StandardKey.Undo): self.canvas.undo(); return
        if hasattr(self,"canvas") and event.matches(QKeySequence.StandardKey.Redo): self.canvas.redo(); return
        super().keyPressEvent(event)
