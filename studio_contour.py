"""Bounded, UI-independent editable contours for an alpha mask.

This module deliberately edits alpha only.  The caller owns preview, undo and
image persistence; ``ContourDocument.apply_path`` is the small atomic operation
needed by those layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import CancelledError
from math import isfinite
from typing import Any, Literal, Sequence

import cv2
import numpy as np


MAX_IMAGE_PIXELS = 32_000_000
MAX_AUTO_CONTOUR_SIDE = 4100
MAX_PATHS = 256
MAX_NODES_PER_PATH = 4_096
MAX_FEATHER_PX = 2.0
MAX_COORDINATE = 100_000.0

Point = tuple[float, float]
ROI = tuple[int, int, int, int]


def _point(value: Sequence[float], *, name: str = "point") -> Point:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ValueError(f"{name} must have two coordinates")
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} coordinates must be numbers") from exc
    if not (isfinite(x) and isfinite(y)):
        raise ValueError(f"{name} coordinates must be finite")
    if abs(x) > MAX_COORDINATE or abs(y) > MAX_COORDINATE:
        raise ValueError(f"{name} coordinates exceed the supported range")
    return (x, y)


@dataclass(frozen=True)
class BezierNode:
    """A closed-path node.  ``in_handle``/``out_handle`` are absolute points."""

    point: Point
    kind: Literal["corner", "smooth"] = "corner"
    in_handle: Point | None = None
    out_handle: Point | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "point", _point(self.point, name="node"))
        if self.kind not in ("corner", "smooth"):
            raise ValueError("node kind must be 'corner' or 'smooth'")
        if self.in_handle is not None:
            object.__setattr__(self, "in_handle", _point(self.in_handle, name="in_handle"))
        if self.out_handle is not None:
            object.__setattr__(self, "out_handle", _point(self.out_handle, name="out_handle"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "point": list(self.point), "kind": self.kind,
            "in_handle": list(self.in_handle) if self.in_handle else None,
            "out_handle": list(self.out_handle) if self.out_handle else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BezierNode":
        if not isinstance(value, dict):
            raise ValueError("node must be an object")
        return cls(value.get("point"), value.get("kind", "corner"),
                   value.get("in_handle"), value.get("out_handle"))


@dataclass(frozen=True)
class BezierPath:
    """A single closed exterior or hole contour in final-image pixel space."""

    nodes: tuple[BezierNode, ...]
    fill_value: Literal[0, 255]
    source_shape: tuple[int, int]
    contour_id: int | None = None

    def __post_init__(self) -> None:
        if not 3 <= len(self.nodes) <= MAX_NODES_PER_PATH:
            raise ValueError(f"a path needs 3..{MAX_NODES_PER_PATH} nodes")
        if self.fill_value not in (0, 255):
            raise ValueError("fill_value must be 0 (hole) or 255 (exterior)")
        if (not isinstance(self.source_shape, tuple) or len(self.source_shape) != 2
                or any(not isinstance(n, int) or n <= 0 for n in self.source_shape)):
            raise ValueError("source_shape must be (height, width) of positive integers")
        if self.source_shape[0] * self.source_shape[1] > MAX_IMAGE_PIXELS:
            raise ValueError("source image exceeds pixel limit")
        for node in self.nodes:
            if not isinstance(node, BezierNode):
                raise TypeError("nodes must be BezierNode values")
            for handle in (node.point, node.in_handle, node.out_handle):
                if handle is not None and not (0.0 <= handle[0] < self.source_shape[1]
                                                and 0.0 <= handle[1] < self.source_shape[0]):
                    raise ValueError("node and handle coordinates must lie within source_shape")

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [node.to_dict() for node in self.nodes],
                "fill_value": self.fill_value, "source_shape": list(self.source_shape),
                "contour_id": self.contour_id}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BezierPath":
        if not isinstance(value, dict):
            raise ValueError("path must be an object")
        nodes = value.get("nodes")
        if not isinstance(nodes, list):
            raise ValueError("path nodes must be a list")
        source_shape = value.get("source_shape")
        if not isinstance(source_shape, list) or len(source_shape) != 2:
            raise ValueError("source_shape must be a two-item list")
        return cls(tuple(BezierNode.from_dict(item) for item in nodes),
                   value.get("fill_value"), tuple(source_shape), value.get("contour_id"))


def _validate_alpha(alpha: np.ndarray) -> np.ndarray:
    if not isinstance(alpha, np.ndarray) or alpha.ndim != 2 or alpha.dtype != np.uint8:
        raise TypeError("alpha must be a two-dimensional uint8 array")
    if not alpha.shape[0] or not alpha.shape[1] or alpha.size > MAX_IMAGE_PIXELS:
        raise ValueError("alpha has unsupported dimensions")
    return alpha


def _validate_roi(roi: Sequence[int], shape: tuple[int, int]) -> ROI:
    if len(roi) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) for v in roi):
        raise ValueError("ROI must contain four integer bounds")
    left, top, right, bottom = map(int, roi)
    height, width = shape
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("ROI must be non-empty and lie within alpha bounds")
    return left, top, right, bottom


def _check_cancelled(cancelled):
    if cancelled is not None and cancelled():
        raise CancelledError()


def changed_path_roi(previous: BezierPath, replacement: BezierPath) -> ROI:
    """Conservative bounds of changed cubic segments, in original pixels.

    A cubic stays within its control-point hull. Unchanged segments cancel in
    the old/new coverage difference. Topology changes fall back to both whole
    paths. Padding covers integer rounding and the maximum supported
    extraction-error cleanup band (tolerance <= 8 pixels).
    """
    def segments(path):
        return [(node.point, _auto_handles(path.nodes, i)[1],
                 _auto_handles(path.nodes, (i+1) % len(path.nodes))[0],
                 path.nodes[(i+1) % len(path.nodes)].point)
                for i, node in enumerate(path.nodes)]
    old, new = segments(previous), segments(replacement)
    changed = [segment for a,b in zip(old,new) if a != b for segment in (a,b)] if len(old) == len(new) else old+new
    if not changed:
        return (0,0,1,1)
    points = np.asarray(changed, dtype=float).reshape(-1,2)
    height, width = previous.source_shape
    padding = 13  # max tolerance 8 + neighbour 1 + feather 2 + rounding 2
    return (max(0,int(np.floor(points[:,0].min()))-padding),
            max(0,int(np.floor(points[:,1].min()))-padding),
            min(width,int(np.ceil(points[:,0].max()))+padding+1),
            min(height,int(np.ceil(points[:,1].max()))+padding+1))


def extract_contours(alpha: np.ndarray, *, tolerance: float = 1.0, cancelled=None) -> list[BezierPath]:
    """Extract exteriors and holes without simplifying more than tolerance pixels.

    ``CHAIN_APPROX_NONE`` retains the original alpha boundary first.  OpenCV's
    Douglas-Peucker approximation is then bounded by ``tolerance`` in the final
    pixel coordinate system, so it is never a global image smoothing operation.
    """
    alpha = _validate_alpha(alpha)
    if not isfinite(float(tolerance)) or not 0.0 <= float(tolerance) <= 8.0:
        raise ValueError("tolerance must be finite and between 0 and 8 pixels")
    _check_cancelled(cancelled)
    binary = cv2.compare(alpha, 0, cv2.CMP_GT)
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if len(contours) > MAX_PATHS:
        raise ValueError("mask has too many contours to edit safely")
    paths: list[BezierPath] = []
    hierarchy_rows = hierarchy[0] if hierarchy is not None else []
    for index, contour in enumerate(contours):
        _check_cancelled(cancelled)
        simplified = cv2.approxPolyDP(contour, float(tolerance), True) if tolerance else contour
        points = simplified.reshape(-1, 2)
        if len(points) < 3:
            # A one-pixel component or one-pixel-wide branch has no closed Bezier
            # area to edit.  It intentionally has no path proposal; its raster
            # alpha remains in ContourDocument.alpha and is never rebuilt from
            # paths, so edits elsewhere cannot silently discard it.
            continue
        if len(points) > MAX_NODES_PER_PATH:
            raise ValueError("contour has too many nodes to edit safely")
        # CCOMP depth one contours are holes.  This also handles masks touching
        # the image boundary without relying on clockwise/counter-clockwise sign.
        parent = int(hierarchy_rows[index][3]) if len(hierarchy_rows) else -1
        fill_value: Literal[0, 255] = 0 if parent >= 0 else 255
        paths.append(BezierPath(tuple(BezierNode((float(x), float(y))) for x, y in points),
                                fill_value, alpha.shape, index))
    return paths


def _auto_handles(nodes: tuple[BezierNode, ...], index: int) -> tuple[Point, Point]:
    node = nodes[index]
    previous = np.asarray(nodes[index - 1].point, dtype=float)
    current = np.asarray(node.point, dtype=float)
    following = np.asarray(nodes[(index + 1) % len(nodes)].point, dtype=float)
    if node.kind == "corner":
        return node.in_handle or tuple(current), node.out_handle or tuple(current)
    tangent = (following - previous) / 6.0
    return (node.in_handle or tuple(current - tangent), node.out_handle or tuple(current + tangent))


def sample_path(path: BezierPath, *, samples_per_segment: int = 12) -> np.ndarray:
    """Return a closed polyline sampling each cubic segment of ``path``."""
    if not isinstance(samples_per_segment, int) or not 2 <= samples_per_segment <= 128:
        raise ValueError("samples_per_segment must be an integer from 2 to 128")
    nodes = path.nodes
    sampled: list[np.ndarray] = []
    for index, node in enumerate(nodes):
        nxt = nodes[(index + 1) % len(nodes)]
        _, out_handle = _auto_handles(nodes, index)
        in_handle, _ = _auto_handles(nodes, (index + 1) % len(nodes))
        t = np.linspace(0.0, 1.0, samples_per_segment, endpoint=False)[:, None]
        p0, p1, p2, p3 = map(lambda p: np.asarray(p, dtype=float),
                             (node.point, out_handle, in_handle, nxt.point))
        sampled.append((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)
    return np.vstack(sampled)


def rasterize_path(path: BezierPath, roi: Sequence[int], *, feather: float = 0.0) -> np.ndarray:
    """Rasterize a path into an 8-bit coverage mask for the explicit ROI only."""
    left, top, right, bottom = _validate_roi(roi, path.source_shape)
    if not isfinite(float(feather)) or not 0.0 <= float(feather) <= MAX_FEATHER_PX:
        raise ValueError(f"feather must be finite and between 0 and {MAX_FEATHER_PX} pixels")
    # Round in image coordinates: bankers rounding after an odd ROI offset
    # would otherwise flip half-pixel ties and change edge pixels.
    points = np.rint(sample_path(path)).astype(np.int32)
    points[:, 0] -= left
    points[:, 1] -= top
    coverage = np.zeros((bottom - top, right - left), dtype=np.uint8)
    # The normal path is deliberately binary.  LINE_AA makes a hidden one-pixel
    # feather even when the caller asked for a hard alpha boundary.
    cv2.fillPoly(coverage, [np.rint(points).astype(np.int32)], 255, lineType=cv2.LINE_8)
    if not feather or not np.any(coverage) or np.all(coverage):
        return coverage

    # A Gaussian has infinite tails, so its nominal sigma cannot honour a
    # two-pixel final-image limit.  A signed Euclidean distance gives a compact
    # linear band instead.  Pixel centres immediately inside/outside the edge
    # are at -/+0.5 respectively: consequently a feather of 2 has at most two
    # partially covered samples per edge, and no sample farther away changes.
    inside = coverage > 0
    inside_distance = cv2.distanceTransform(inside.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    outside_distance = cv2.distanceTransform((~inside).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    signed_distance = np.where(inside, -(inside_distance - 0.5), outside_distance - 0.5)
    bounded = np.clip(0.5 - signed_distance / float(feather), 0.0, 1.0)
    if feather <= 1.0:
        # At one final pixel, centre sampling would otherwise round straight from
        # opaque to transparent.  Keep the transition on the single inner edge
        # sample (never outside the requested one-pixel band).
        bounded[inside & (inside_distance <= 1.0)] = 1.0 - float(feather) / 2.0
    return np.rint(bounded * 255.0).astype(np.uint8)


@dataclass
class ContourDocument:
    """Editable alpha plus serializable extracted paths; RGB is never mutated."""

    alpha: np.ndarray
    paths: list[BezierPath] = field(default_factory=list)
    extraction_tolerance: float = 1.0
    _source_alpha: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.alpha = _validate_alpha(self.alpha).copy()
        if not isfinite(float(self.extraction_tolerance)) or not 0 <= float(self.extraction_tolerance) <= 8:
            raise ValueError("extraction_tolerance must be finite and between 0 and 8 pixels")
        self.extraction_tolerance = float(self.extraction_tolerance)
        if len(self.paths) > MAX_PATHS:
            raise ValueError("too many paths")
        if any(path.source_shape != self.alpha.shape for path in self.paths):
            raise ValueError("path source_shape must match alpha")
        self._source_alpha = self.alpha.copy()

    @classmethod
    def from_alpha(cls, alpha: np.ndarray, *, tolerance: float = 1.0) -> "ContourDocument":
        alpha = _validate_alpha(alpha)
        return cls(alpha, extract_contours(alpha, tolerance=tolerance), tolerance)

    @property
    def source_alpha(self) -> np.ndarray:
        """Immutable-by-convention snapshot taken when this editing session opened."""
        return self._source_alpha.copy()

    def to_dict(self) -> dict[str, Any]:
        return {"source_shape": list(self.alpha.shape), "paths": [path.to_dict() for path in self.paths],
                "extraction_tolerance": self.extraction_tolerance}

    def apply_path(self, path_index: int, replacement: BezierPath, roi: Sequence[int], *, feather: float = 0.0, cancelled=None) -> np.ndarray:
        """Replace one contour locally and return a copy of the new alpha.

        The old and new coverage are composited only in ``roi``; the path does
        not need to fit there.  An exterior clears/fills only its changed local
        footprint, and a hole does the inverse.  This makes node movement visible
        while leaving every alpha pixel outside ROI byte-identical.  A successful
        partial edit refreshes the contour proposal from its resulting raster.
        """
        if not isinstance(path_index, int) or not 0 <= path_index < len(self.paths):
            raise IndexError("path_index is out of range")
        _check_cancelled(cancelled)
        previous = self.paths[path_index]
        if replacement.source_shape != self.alpha.shape or replacement.fill_value != previous.fill_value:
            raise ValueError("replacement must match image shape and contour role")
        bounds = _validate_roi(roi, self.alpha.shape)
        # In particular, do not binarize anti-aliased source alpha merely because
        # a caller opens and reapplies an extracted thin contour unchanged.
        if replacement == previous:
            return self.alpha.copy()
        # OpenCV clips polygon edges at the raster bounds. Keep a context band
        # for feathering/edge cleanup, then crop: only supplied ROI is mutated.
        left, top, right, bottom = bounds
        height, width = self.alpha.shape
        padding = 13
        work_roi = (max(0, left-padding), max(0, top-padding),
                    min(width, right+padding), min(height, bottom+padding))
        crop = (slice(top-work_roi[1], bottom-work_roi[1]),
                slice(left-work_roi[0], right-work_roi[0]))
        old_raster = rasterize_path(previous, work_roi, feather=feather)
        new_raster = rasterize_path(replacement, work_roi, feather=feather)
        old_coverage = old_raster[crop].astype(np.float32) / 255.0
        new_coverage = new_raster[crop].astype(np.float32) / 255.0
        # A UI normally supplies a small edge ROI.  If neither old nor new path
        # reaches it, keep the existing editable proposal exactly as-is.
        if np.array_equal(old_coverage, new_coverage):
            return self.alpha.copy()
        left, top, right, bottom = bounds
        candidate = self.alpha.copy()
        region = candidate[top:bottom, left:right].astype(np.float32)
        protected_opaque, protected_holes = self._other_path_protection(path_index, bounds, region, cancelled=cancelled)
        # A nonzero pixel not covered by the selected old path is an unrepresented
        # raster residual (for example, a one-pixel hair).  Preserve it when a
        # contour expands; ordinary transparent background remains fillable.
        protected_residual = (region > 0) & (old_coverage == 0)
        if previous.fill_value == 255:
            # Only the symmetric difference changes.  In particular, alpha in an
            # unchanged inner hole is not overwritten when its outer contour moves.
            # Apply relative coverage loss: when a feathered old edge moves
            # away completely, its original alpha must reach zero too.
            old_only = np.divide(np.clip(old_coverage - new_coverage, 0.0, 1.0),
                old_coverage, out=np.zeros_like(old_coverage), where=old_coverage > 0)
            new_only = np.clip(new_coverage - old_coverage, 0.0, 1.0)
            if np.any(old_only):
                # The simplified old polygon can miss real edge pixels. Remove
                # those only beside a changed segment and only when they belong
                # to this extracted exterior; unrelated raster details survive.
                radius = int(np.ceil(self.extraction_tolerance)) + 1
                changed_edge = cv2.dilate((old_raster > new_raster).astype(np.uint8),
                    np.ones((2 * radius + 1, 2 * radius + 1), np.uint8))[crop] > 0
                missed_edge = protected_residual & (new_coverage == 0) & changed_edge
                if np.any(missed_edge):
                    owned = self._extracted_footprint(previous, bounds, cancelled=cancelled)
                    if owned is not None:
                        old_only[missed_edge & owned] = 1.0
            old_only[protected_opaque] = 0.0
            new_only[protected_holes | protected_residual] = 0.0
            region = region * (1.0 - old_only)
            region = np.maximum(region, new_only * 255.0)
        else:
            old_only = np.clip(old_coverage - new_coverage, 0.0, 1.0)
            new_only = np.clip(new_coverage - old_coverage, 0.0, 1.0)
            old_only[protected_opaque | protected_holes | protected_residual] = 0.0
            # Opaque material outside the old hole is what expansion removes;
            # it is not an unrepresented residual of an exterior contour.
            # Separate islands retain explicit other-path protection.
            new_only[protected_opaque] = 0.0
            region = np.maximum(region, old_only * 255.0)
            region = region * (1.0 - new_only)
        candidate[top:bottom, left:right] = np.rint(np.clip(region, 0, 255)).astype(np.uint8)
        # Other paths can become topologically stale after any edit.  Rebuild the
        # proposal from the candidate before publishing it, rather than silently
        # retaining paths whose fill role no longer matches the alpha.
        _check_cancelled(cancelled)
        candidate_paths = extract_contours(candidate, tolerance=self.extraction_tolerance, cancelled=cancelled)
        _check_cancelled(cancelled)
        self.alpha = candidate
        self.paths = candidate_paths
        return self.alpha.copy()

    def _extracted_footprint(self, path: BezierPath, roi: ROI, *, cancelled=None) -> np.ndarray | None:
        """Exact source outline, verified against geometry rather than an ID alone.

        Draft batch edits can reuse original paths after a different component
        has changed. Try the current mask and then the session snapshot. Manual
        paths and modified curves have no authoritative raster footprint.
        """
        if path.contour_id is None or any(node.kind != "corner" or
                node.in_handle is not None or node.out_handle is not None for node in path.nodes):
            return None
        expected = np.asarray([node.point for node in path.nodes])
        for alpha in (self.alpha, self._source_alpha):
            _check_cancelled(cancelled)
            binary = cv2.compare(alpha, 0, cv2.CMP_GT)
            contours, hierarchy = cv2.findContours(binary,
                cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
            if hierarchy is None:
                continue
            candidates = list(range(len(contours)))
            if isinstance(path.contour_id, int) and 0 <= path.contour_id < len(contours):
                candidates.remove(path.contour_id)
                candidates.insert(0, path.contour_id)
            for index in candidates:
                _check_cancelled(cancelled)
                if hierarchy[0][index][3] >= 0:
                    continue
                contour = contours[index]
                approximation = (cv2.approxPolyDP(contour, self.extraction_tolerance, True)
                                 if self.extraction_tolerance else contour)
                if not np.array_equal(approximation.reshape(-1, 2), expected):
                    continue
                left, top, right, bottom = roi
                # A filled outer polygon also covers holes and tiny islands
                # inside them. Membership must follow the actual 8-connected
                # foreground, using the same connectivity as findContours.
                seed = tuple(int(value) for value in contour[0, 0])
                cv2.floodFill(binary, None, seed, 128, flags=8)
                _check_cancelled(cancelled)
                return binary[top:bottom, left:right] == 128
        return None

    def _other_path_protection(self, selected_index: int, roi: ROI,
                               region: np.ndarray, *, cancelled=None) -> tuple[np.ndarray, np.ndarray]:
        """Return only neighbouring editable geometry that must not be overwritten."""
        opaque = np.zeros(region.shape, dtype=bool)
        holes = np.zeros(region.shape, dtype=bool)
        selected_outline = sample_path(self.paths[selected_index])
        material_parents = []
        for index, path in enumerate(self.paths):
            _check_cancelled(cancelled)
            if index == selected_index:
                continue
            controls = np.asarray([point for i, node in enumerate(path.nodes)
                                   for point in (node.point, *_auto_handles(path.nodes, i))])
            left, top, right, bottom = roi
            if (controls[:,0].max() < left-1 or controls[:,0].min() >= right+1
                    or controls[:,1].max() < top-1 or controls[:,1].min() >= bottom+1):
                continue
            # Enclosing ancestors are the material around this editable edge,
            # not separate details. Protecting their whole filled polygon would
            # prevent a hole from expanding, or a nested island from expanding.
            # Descendants and neighbouring paths still retain their protection.
            outline = sample_path(path).astype(np.float32)
            distances = [cv2.pointPolygonTest(outline, tuple(map(float, point)), False)
                         for point in selected_outline]
            if distances and min(distances) >= 0 and max(distances) > 0:
                if self.paths[selected_index].fill_value == 0 and path.fill_value == 255:
                    material_parents.append((abs(cv2.contourArea(outline)), outline))
                continue
            covered = rasterize_path(path, roi) > 0
            if path.fill_value == 255:
                opaque |= covered & (region > 0)
            else:
                holes |= covered & (region == 0)
        if material_parents:
            # A stale proposal can miss single-pixel islands created by a brush.
            # Only components touching the nearest enclosing exterior belong
            # to the material around this hole; detached raw details survive.
            outline = min(material_parents, key=lambda item: item[0])[1]
            binary = cv2.compare(self.alpha, 0, cv2.CMP_GT)
            height, width = binary.shape
            for x, y in np.rint(outline).astype(np.int32):
                _check_cancelled(cancelled)
                if 0 <= x < width and 0 <= y < height and binary[y, x] == 255:
                    cv2.floodFill(binary, None, (int(x), int(y)), 128, flags=8)
            left, top, right, bottom = roi
            opaque |= (region > 0) & (binary[top:bottom, left:right] != 128)
        return opaque, holes

    def apply_to_rgba(self, rgba: np.ndarray) -> np.ndarray:
        """Return RGBA with unchanged RGB and this document's alpha channel."""
        if not isinstance(rgba, np.ndarray) or rgba.dtype != np.uint8 or rgba.shape != (*self.alpha.shape, 4):
            raise ValueError("rgba must be uint8 with shape (height, width, 4)")
        result = rgba.copy()
        result[..., 3] = self.alpha
        return result
