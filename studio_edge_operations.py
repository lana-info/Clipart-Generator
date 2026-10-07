"""Alpha-only edge actions, independent of Qt and safe to run in a worker.

Smoothing reconstructs a subpixel boundary from the existing >=128 silhouette.
It only attenuates opaque-side corner pixels: no hidden RGB is exposed, faint
strokes are retained and straight edges/interiors are left alone. It cannot
recover detail previously removed by sharpening. Selected contour nodes bound
an explicit narrow guide region; invalid selection never becomes global.
"""
from __future__ import annotations

from concurrent.futures import CancelledError
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from studio_contour import BezierPath, MAX_PATHS, _auto_handles

EDGE_SHARPEN_LUT = tuple(round(max(0, min(255, 2 * value - 127.5))) for value in range(256))
MAX_EDGE_PIXELS = 40_000_000
_TILE = 128
_SUBPIXELS = 8
_SCOPE_RADIUS = 2
_MAX_SCOPE_SAMPLES = 200_000


def _check_cancelled(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise CancelledError()


def selection_scope(size, paths, selection, cancelled=None):
    """Return a binary 2px-radius band on selected runs, or None for global.

A segment is included only if both its endpoint nodes are selected. Single
selected nodes include their own neighbourhood; separate runs never bridge an
unselected arc. Curves are sampled at <=0.5px control-polygon increments.
"""
    _check_cancelled(cancelled)
    selected = frozenset(selection)
    if not selected:
        return None
    if len(paths) > MAX_PATHS:
        raise ValueError('Слишком много контуров')
    width, height = size
    by_path = {}
    for pair in selected:
        if (not isinstance(pair, tuple) or len(pair) != 2
                or any(isinstance(i, bool) or not isinstance(i, int) for i in pair)):
            raise ValueError('Выделение не соответствует контуру')
        pi, ni = pair
        if not 0 <= pi < len(paths) or not isinstance(paths[pi], BezierPath):
            raise ValueError('Выделение не соответствует контуру')
        path = paths[pi]
        if path.source_shape != (height, width) or not 0 <= ni < len(path.nodes):
            raise ValueError('Выделение не соответствует изображению')
        by_path.setdefault(pi, set()).add(ni)
    scope = Image.new('L', size, 0)
    draw = ImageDraw.Draw(scope)
    samples = 0
    for pi, indices in by_path.items():
        path = paths[pi]
        nodes = path.nodes
        for ni in sorted(indices):
            _check_cancelled(cancelled)
            x, y = nodes[ni].point
            draw.ellipse((x-_SCOPE_RADIUS, y-_SCOPE_RADIUS,
                          x+_SCOPE_RADIUS, y+_SCOPE_RADIUS), fill=255)
            next_index = (ni+1) % len(nodes)
            if next_index not in indices:
                continue
            _, h1 = _auto_handles(nodes, ni)
            h2, _ = _auto_handles(nodes, next_index)
            controls = [nodes[ni].point, h1, h2, nodes[next_index].point]
            length = sum(math.dist(a, b) for a, b in zip(controls, controls[1:]))
            count = max(2, math.ceil(length * 2)+1)
            samples += count
            if samples > _MAX_SCOPE_SAMPLES:
                raise ValueError('Слишком сложное выделение. Выберите меньший участок.')
            t = np.linspace(0, 1, count)[:, None]
            p0, p1, p2, p3 = np.asarray(controls, dtype=np.float64)
            curve = ((1-t)**3*p0 + 3*(1-t)**2*t*p1
                     + 3*(1-t)*t*t*p2 + t**3*p3)
            draw.line([tuple(p) for p in curve], fill=255, width=2*_SCOPE_RADIUS+1)
    _check_cancelled(cancelled)
    return scope


def _smooth_corners(alpha, cancelled):
    # Work in bounded tiles plus a one-pixel halo. Uniform tiles need no work.
    # Threshold is stable because target coverage is clamped to >=128 on the
    # originally solid side. Repeated clicks therefore cannot erode the object.
    height, width = alpha.shape
    result = alpha.copy()
    for top in range(0, height, _TILE):
        for left in range(0, width, _TILE):
            _check_cancelled(cancelled)
            bottom, right = min(top+_TILE, height), min(left+_TILE, width)
            y0, x0 = max(0, top-1), max(0, left-1)
            y1, x1 = min(height, bottom+1), min(width, right+1)
            tile = alpha[y0:y1, x0:x1]
            solid = (tile >= 128).astype(np.uint8)*255
            if not solid.any() or solid.all():
                continue
            # Existing AA is evidence of intentional coverage, not jagged paint.
            # Protect it and its neighbours. Also retain sparse 1px strokes.
            fractional = ((tile > 0) & (tile < 255)).astype(np.uint8)
            near_fractional = cv2.dilate(fractional, np.ones((3,3), np.uint8))
            support = cv2.boxFilter((solid > 0).astype(np.uint8), cv2.CV_16U,
                                    (3,3), normalize=False,
                                    borderType=cv2.BORDER_REPLICATE)
            eligible = (tile == 255) & (near_fractional == 0) & (support >= 4)
            if not eligible.any():
                continue
            enlarged = cv2.resize(solid, None, fx=_SUBPIXELS, fy=_SUBPIXELS,
                                  interpolation=cv2.INTER_LINEAR)
            coverage = cv2.resize((enlarged >= 128).astype(np.float32)*255,
                                  (tile.shape[1], tile.shape[0]),
                                  interpolation=cv2.INTER_AREA)
            coverage = np.maximum(128, np.rint(coverage)).astype(np.uint8)
            inner = np.s_[top-y0:bottom-y0, left-x0:right-x0]
            current = alpha[top:bottom, left:right]
            result[top:bottom, left:right] = np.where(
                eligible[inner], np.minimum(current, coverage[inner]), current)
    _check_cancelled(cancelled)
    return result


def edge_proposal(mask, operation, paths=(), selection=frozenset(), cancelled=None):
    """Return a new L mask; never mutate inputs or commit partial work."""
    _check_cancelled(cancelled)
    if not isinstance(mask, Image.Image) or mask.mode != 'L':
        raise ValueError('Маска должна быть в режиме L')
    if mask.width*mask.height > MAX_EDGE_PIXELS:
        raise ValueError('Обработка края поддерживает до 40 мегапикселей')
    if operation not in ('sharpen', 'smooth'):
        raise ValueError('Неизвестное действие края')
    scope = selection_scope(mask.size, paths, selection, cancelled)
    _check_cancelled(cancelled)
    if operation == 'sharpen':
        proposal = mask.point(EDGE_SHARPEN_LUT)
    else:
        proposal = Image.fromarray(_smooth_corners(np.asarray(mask), cancelled))
    _check_cancelled(cancelled)
    if scope is not None:
        proposal = Image.composite(proposal, mask, scope)
    _check_cancelled(cancelled)
    return proposal
