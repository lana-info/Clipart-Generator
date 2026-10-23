"""Alpha-only edge actions, independent of Qt and safe to run in a worker.

Smoothing reconstructs a subpixel boundary from the existing >=128 silhouette.
It only attenuates opaque-side corner pixels: no hidden RGB is exposed, faint
strokes are retained and straight edges/interiors are left alone. It cannot
recover detail previously removed by sharpening. Selected contour nodes bound
an explicit narrow guide region; invalid selection never becomes global.

Harder/softer change only the width of the alpha transition (a fixed 3 px step,
never narrower than 3 px, so the edge stays antialiased); shrink/grow move the
edge by exactly one pixel. Width steps re-render a ramp from a subpixel signed
distance; shifts are grey erosion/dilation by a unit circle that keeps the edge
profile. Neither makes a staircase. A lasso area, when given, bounds every action.
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
EDGE_MIN_WIDTH = 3.0
EDGE_MAX_WIDTH = 24.0
EDGE_WIDTH_STEP = 3.0
EDGE_OPERATIONS = ('sharpen', 'smooth', 'harder', 'softer', 'shrink', 'grow')
_MAX_AREA_POLYGONS = 64
_MAX_AREA_POINTS = 100_000
_AREA_FADE = 4
_SHIFT_DIRECTIONS = 32


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


def area_scope(size, area, cancelled=None):
    """Binary mask of the lasso polygons (image coordinates), or None when there is no area."""
    _check_cancelled(cancelled)
    if not area:
        return None
    if len(area) > _MAX_AREA_POLYGONS or sum(len(polygon) for polygon in area) > _MAX_AREA_POINTS:
        raise ValueError('Слишком сложная область лассо')
    scope = Image.new('L', size, 0)
    draw = ImageDraw.Draw(scope)
    for polygon in area:
        points = [(float(x), float(y)) for x, y in polygon]
        if len(points) < 3:
            raise ValueError('Область лассо должна иметь хотя бы три точки')
        draw.polygon(points, fill=255)
    _check_cancelled(cancelled)
    return scope


def edge_width(alpha, scope=None):
    """Typical width in pixels of the alpha transition, or None when no edge is in scope.

    A linear ramp of width W has slope 1/W; the median slope of mid-transition pixels is robust to corners.
    """
    a = np.asarray(alpha).astype(np.float32) / 255
    inside = a >= 0.5
    padded = np.pad(inside, 1, mode='edge')
    border = inside & ~(padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:])
    middle = (a > 0.1) & (a < 0.9)
    if scope is not None:
        border &= scope
        middle &= scope
    if not border.any():
        return None
    if not middle.any():
        return 1.0
    gy, gx = np.gradient(a)
    slope = float(np.median(np.hypot(gx, gy)[middle]))
    return float(min(EDGE_MAX_WIDTH * 2, max(1.0, 1 / max(slope, 1e-6))))


def _signed_distance(alpha, width):
    """Subpixel distance to the 50 % line, positive inside.

    Inside the ramp it comes from alpha itself; a fully opaque or empty pixel adds its distance to the nearest
    pixel of the other kind to that pixel's own distance, so the ramp continues smoothly beyond the old edge.
    """
    a = np.asarray(alpha).astype(np.float32) / 255
    partial = (a > 0) & (a < 1)
    own = np.where(partial, (a - 0.5) * width, np.where(a >= 1, 0.5, -0.5)).astype(np.float32)
    result = own.copy()
    for solid, sign in ((a >= 1, 1.0), (a <= 0, -1.0)):
        if not solid.any() or solid.all():
            continue
        # Zero pixels of ``source`` are the pixels we measure from: everything that is not ``solid``.
        source = solid.astype(np.uint8)
        distance, labels = cv2.distanceTransformWithLabels(source, cv2.DIST_L2, 5,
                                                           labelType=cv2.DIST_LABEL_PIXEL)
        rows, columns = np.nonzero(source == 0)
        nearest = own[rows, columns]
        start = nearest[labels[solid] - 1]
        result[solid] = start + sign * distance[solid]
    return result


def _ramp(distance, width):
    return np.clip(np.rint((0.5 + distance / width) * 255), 0, 255).astype(np.uint8)


def _width_step(alpha, harder, scope):
    width = edge_width(alpha, scope)
    if width is None or (harder and width <= EDGE_MIN_WIDTH * 1.35) or (not harder and width >= EDGE_MAX_WIDTH):
        return alpha
    target = (max(EDGE_MIN_WIDTH, width - EDGE_WIDTH_STEP) if harder
              else min(EDGE_MAX_WIDTH, width + EDGE_WIDTH_STEP))
    distance = _signed_distance(alpha, width)
    if not harder:
        # The wider ramp keeps its outer end where the old one ended: empty background is never revealed.
        distance = distance + (width - target) / 2
    result = _ramp(distance, target)
    if not harder:
        result[alpha == 0] = 0
    return result


def _shift(alpha, pixels):
    """Move the edge by one pixel keeping its profile: grey erosion/dilation by an exact unit circle.

    Each pixel takes the min (shrink) or max (grow) of alpha sampled one pixel away in every direction, so a
    soft edge of any shape slides by one pixel and keeps its softness; flat interior and background stay put.
    """
    source = alpha.astype(np.float32)
    pick = np.minimum if pixels < 0 else np.maximum
    result = source.copy()
    for k in range(_SHIFT_DIRECTIONS):
        angle = 2 * math.pi * k / _SHIFT_DIRECTIONS
        moved = cv2.warpAffine(source, np.float32([[1, 0, math.cos(angle)], [0, 1, math.sin(angle)]]),
                               (source.shape[1], source.shape[0]), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)
        result = pick(result, moved)
    return np.clip(np.rint(result), 0, 255).astype(np.uint8)


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


def edge_proposal(mask, operation, paths=(), selection=frozenset(), cancelled=None, area=()):
    """Return a new L mask; never mutate inputs or commit partial work.

    Scope: the lasso ``area`` if given, else the band of selected contour nodes, else the whole image.
    """
    _check_cancelled(cancelled)
    if not isinstance(mask, Image.Image) or mask.mode != 'L':
        raise ValueError('Маска должна быть в режиме L')
    if mask.width*mask.height > MAX_EDGE_PIXELS:
        raise ValueError('Обработка края поддерживает до 40 мегапикселей')
    if operation not in EDGE_OPERATIONS:
        raise ValueError('Неизвестное действие края')
    scope = area_scope(mask.size, area, cancelled)
    if scope is None:
        scope = selection_scope(mask.size, paths, selection, cancelled)
    _check_cancelled(cancelled)
    if operation == 'sharpen':
        proposal = mask.point(EDGE_SHARPEN_LUT)
    elif operation == 'smooth':
        proposal = Image.fromarray(_smooth_corners(np.asarray(mask), cancelled))
    else:
        alpha = np.asarray(mask)
        inside = None if scope is None else np.asarray(scope) > 0
        if operation in ('harder', 'softer'):
            result = _width_step(alpha, operation == 'harder', inside)
        else:
            result = _shift(alpha, -1 if operation == 'shrink' else 1)
        if scope is not None and area:
            # Fade the change in over a few pixels inside the lasso line, so no step shows where it crosses the edge;
            # outside the area nothing changes.
            core = cv2.erode(np.asarray(scope), np.ones((2 * _AREA_FADE + 1,) * 2, np.uint8))
            weight = cv2.GaussianBlur(core.astype(np.float32) / 255, (0, 0), _AREA_FADE / 2)
            weight = np.where(np.asarray(scope) > 0, np.maximum(weight, core / 255), 0)
            result = np.rint(alpha + (result.astype(np.float32) - alpha) * weight).astype(np.uint8)
        proposal = Image.fromarray(np.ascontiguousarray(result))
    _check_cancelled(cancelled)
    if scope is not None:
        proposal = Image.composite(proposal, mask, scope)
    _check_cancelled(cancelled)
    return proposal
