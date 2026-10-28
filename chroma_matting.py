"""Edge matting for a chroma-keyed generation: soft alpha and key-free colour on fur, hair and leaf edges.

The keyed frame is composite = alpha * subject + (1 - alpha) * key. A hard key decision on the edge pixels
leaves hair tips blue-tinted and opaque. This module keeps the engine cut-out where it is sure and solves the
thin uncertain band properly:

1. trimap: sure background (key colour, engine-transparent, dark shaded key), sure subject (engine-opaque and
   not key-tinted), the rest is unknown;
2. closed-form matting (Levin, Lischinski, Weiss) gives alpha in the unknown band;
3. subject colour is estimated without key mixed in, alpha is re-derived from it by the compositing equation,
   and the colour is estimated again;
4. remaining key tint on the edge is capped at what the nearest sure subject pixel has.

Pure numpy/scipy. Returns an RGBA image whose colour under alpha zero is the extended subject colour.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
from scipy import sparse
from scipy.sparse.linalg import spsolve

from chroma_key import KEY_COLORS, measure_chroma_background

KEY_CHANNEL = {"red": 0, "green": 1, "blue": 2}
KEY_DISTANCE = 45.0             # RGB distance to the measured key that is sure background
DARK_KEY_RATIO = 1.6            # shaded key: key channel this many times the strongest other channel ...
DARK_KEY_LEAD = 40              # ... and this far ahead of it
SHADED_KEY_MAX_HALF_WIDTH = 2.5  # shaded key slivers are thin; a wider key-like patch is subject
SHADED_KEY_REACH = 2            # a sliver this close to the engine's transparent area is an edge, not a gap
SOLID_TINT = 15                 # sure subject leads the key channel by less than this over every other channel
SOLID_EROSION = 7               # engine-opaque pixels this deep inside are sure subject regardless of tint
BACKGROUND_EROSION = 3
SOLVER_EPS = 1e-7
WINDOW_CHUNK = 40000
FOREGROUND_SMOOTHNESS = 2.0
FOREGROUND_REACH = 9            # px around the subject where colour is solved; farther is copied from the nearest
MAX_UNKNOWN_PIXELS = 400000


def _dilate(mask: np.ndarray, size: int) -> np.ndarray:
    return cv2.dilate(mask.astype(np.uint8), np.ones((size, size), np.uint8)) > 0


def _erode(mask: np.ndarray, size: int) -> np.ndarray:
    return cv2.erode(mask.astype(np.uint8), np.ones((size, size), np.uint8)) > 0


def _enclosed_shaded_key(rgb: np.ndarray, engine_alpha: np.ndarray, channel: int) -> np.ndarray:
    """Slivers of shaded key enclosed by the subject (dark gaps between leaves): key-dominant hue, at most ~5 px wide.

    Whatever the engine made of them (solid or a partial mixture), they are background: the subject is on every
    side. A sliver that touches the engine's transparent area is an edge and is left to the matting, as are wider
    key-like patches (a blue flower).
    """
    others = np.delete(rgb, channel, axis=2)
    key_lead = rgb[..., channel][..., None] - others
    candidate = ((engine_alpha > 0) & (rgb[..., channel] > DARK_KEY_RATIO * others.max(axis=2))
                 & (key_lead.min(axis=2) > DARK_KEY_LEAD / 255.0))
    if not candidate.any():
        return candidate
    mask = candidate.astype(np.uint8)
    thickness = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    count, labels = cv2.connectedComponents(mask, connectivity=8)
    widest = np.zeros(count, np.float32)
    np.maximum.at(widest, labels.ravel(), thickness.ravel())
    open_to_outside = np.zeros(count, bool)
    open_to_outside[np.unique(labels[candidate & _dilate(engine_alpha == 0, 2 * SHADED_KEY_REACH + 1)])] = True
    enclosed_thin = (widest <= SHADED_KEY_MAX_HALF_WIDTH) & ~open_to_outside
    enclosed_thin[0] = False
    return candidate & enclosed_thin[labels]


def _trimap(rgb: np.ndarray, engine_alpha: np.ndarray, channel: int, key: np.ndarray):
    """Return (sure_background, sure_subject) boolean masks; everything else is unknown."""
    key_lead = rgb[..., channel][..., None] - np.delete(rgb, channel, axis=2)
    near_key = np.linalg.norm(rgb - key, axis=2) < KEY_DISTANCE / 255.0
    opaque = engine_alpha >= 255
    shaded_key = _enclosed_shaded_key(rgb, engine_alpha, channel)
    background = near_key | (engine_alpha == 0) | shaded_key
    untinted = (key_lead < SOLID_TINT / 255.0).all(axis=2)
    subject = opaque & (_erode(opaque, SOLID_EROSION) | untinted) & ~background
    # Key-like pixels deep inside the engine's opaque area are not trusted as background (only slivers are).
    background &= ~_erode(opaque, BACKGROUND_EROSION) | shaded_key
    return background, subject


def _closed_form_alpha(rgb: np.ndarray, known: np.ndarray, known_alpha: np.ndarray) -> np.ndarray:
    """Matting Laplacian solve restricted to the unknown pixels; known pixels are fixed values."""
    height, width = known.shape
    unknown = ~known
    flat_unknown = unknown.ravel()
    pixel_index = np.arange(height * width).reshape(height, width)
    centres = _dilate(unknown, 3)
    centres[[0, -1], :] = False
    centres[:, [0, -1]] = False
    cy, cx = np.nonzero(centres)
    offsets = np.array([(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
    colours = rgb.reshape(-1, 3)
    rows, cols, values = [], [], []
    identity = np.eye(3)
    for start in range(0, cy.size, WINDOW_CHUNK):
        sy, sx = cy[start:start + WINDOW_CHUNK], cx[start:start + WINDOW_CHUNK]
        window = pixel_index[sy[:, None] + offsets[:, 0], sx[:, None] + offsets[:, 1]]
        patch = colours[window]
        centred = patch - patch.mean(axis=1, keepdims=True)
        covariance = np.einsum("nki,nkj->nij", centred, centred) / 9.0 + SOLVER_EPS / 9.0 * identity
        inverse = np.linalg.inv(covariance)
        affinity = np.einsum("nki,nij,nlj->nkl", centred, inverse, centred)
        laplacian = np.eye(9) - (1.0 + affinity) / 9.0
        row = np.broadcast_to(window[:, :, None], laplacian.shape)
        col = np.broadcast_to(window[:, None, :], laplacian.shape)
        keep = flat_unknown[row]
        rows.append(row[keep])
        cols.append(col[keep])
        values.append(laplacian[keep])
    unknown_index = np.flatnonzero(flat_unknown)
    position = np.full(height * width, -1, np.int64)
    position[unknown_index] = np.arange(unknown_index.size)
    row = np.concatenate(rows)
    col = np.concatenate(cols)
    value = np.concatenate(values)
    system = sparse.coo_matrix((value, (position[row], col)), shape=(unknown_index.size, height * width)).tocsr()
    unknown_columns = system[:, unknown_index].tocsc()
    fixed = np.zeros(height * width)
    fixed[~flat_unknown] = known_alpha.ravel()[~flat_unknown]
    right = -(system @ fixed)
    solution = spsolve(unknown_columns, right)
    alpha = known_alpha.astype(np.float64).copy().ravel()
    alpha[unknown_index] = np.clip(solution, 0.0, 1.0)
    return alpha.reshape(height, width)


def _estimate_subject_colour(rgb: np.ndarray, alpha: np.ndarray, key: np.ndarray) -> np.ndarray:
    """Subject colour F with rgb = alpha*F + (1-alpha)*key, smooth along the edge; sure pixels keep rgb."""
    height, width = alpha.shape
    solid = alpha >= 1.0
    reach = _dilate(alpha > 0, 2 * (FOREGROUND_REACH // 2) + 1)
    unknown = reach & ~solid
    colour = rgb.copy()
    unknown_index = np.flatnonzero(unknown.ravel())
    if unknown_index.size:
        position = np.full(height * width, -1, np.int64)
        position[unknown_index] = np.arange(unknown_index.size)
        flat_alpha = alpha.ravel()
        diagonal = flat_alpha[unknown_index] ** 2 + 1e-6
        rows, cols = [], []
        degree = np.zeros(unknown_index.size)
        right = (flat_alpha[unknown_index, None] * (rgb.reshape(-1, 3)[unknown_index]
                                                    - (1.0 - flat_alpha[unknown_index, None]) * key))
        fixed_part = np.zeros_like(right)
        flat_colour = rgb.reshape(-1, 3)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            ys, xs = np.divmod(unknown_index, width)
            ny, nx = ys + dy, xs + dx
            inside = (ny >= 0) & (ny < height) & (nx >= 0) & (nx < width)
            neighbour = np.where(inside, ny * width + nx, 0)
            degree += inside
            is_unknown = inside & unknown.ravel()[neighbour]
            rows.append(np.flatnonzero(is_unknown))
            cols.append(position[neighbour[is_unknown]])
            is_fixed = inside & ~unknown.ravel()[neighbour]
            fixed_part[is_fixed] += flat_colour[neighbour[is_fixed]]
        r = np.concatenate(rows)
        c = np.concatenate(cols)
        smooth = FOREGROUND_SMOOTHNESS
        laplacian = sparse.coo_matrix((np.full(r.size, -smooth), (r, c)),
                                      shape=(unknown_index.size,) * 2)
        system = (sparse.diags(diagonal + smooth * degree) + laplacian).tocsc()
        solved = np.column_stack([
            spsolve(system, right[:, channel] + smooth * fixed_part[:, channel]) for channel in range(3)
        ])
        flat_colour = colour.reshape(-1, 3)
        flat_colour[unknown_index] = np.clip(solved, 0.0, 1.0)
    subject = alpha > 0
    if subject.any() and not subject.all():
        _, labels = cv2.distanceTransformWithLabels((~subject).astype(np.uint8), cv2.DIST_L2, 5,
                                                    labelType=cv2.DIST_LABEL_PIXEL)
        palette = np.zeros((int(labels.max()) + 1, 3))
        palette[labels[subject]] = colour[subject]
        colour = np.where(subject[..., None], colour, palette[labels])
    return colour


def _cap_key_tint(colour: np.ndarray, alpha: np.ndarray, channel: int) -> np.ndarray:
    """Edge colour may lead the key channel no more than the nearest sure subject pixel does."""
    visible = alpha > 0
    trusted = (alpha >= 1.0) & (cv2.distanceTransform(visible.astype(np.uint8), cv2.DIST_L2, 5) > 3)
    edge = visible & ~trusted
    if not trusted.any() or not edge.any():
        return colour
    _, labels = cv2.distanceTransformWithLabels((~trusted).astype(np.uint8), cv2.DIST_L2, 5,
                                                labelType=cv2.DIST_LABEL_PIXEL)
    palette = np.zeros((int(labels.max()) + 1, 3))
    palette[labels[trusted]] = colour[trusted]
    reference = palette[labels]
    capped = colour.copy()
    excess = np.zeros(alpha.shape)
    for other in (c for c in range(3) if c != channel):
        allowed = np.maximum(reference[..., channel] - reference[..., other], 0.0)
        excess = np.maximum(excess, (colour[..., channel] - colour[..., other]) - allowed)
    capped[..., channel] = np.where(edge, colour[..., channel] - np.maximum(excess, 0.0), colour[..., channel])
    return capped


def matte_edges(source: Image.Image, cutout: Image.Image, key_color: str,
                *, max_unknown: int = MAX_UNKNOWN_PIXELS) -> Image.Image:
    """Return ``cutout`` re-matted along its edges, or ``cutout`` itself when there is nothing to do.

    ``source`` is the generated frame with the key background; ``cutout`` is the engine result for it
    (same size). A key colour that is not red/green/blue, or a size mismatch, returns ``cutout`` untouched.
    Raises ``ValueError`` when the uncertain band exceeds ``max_unknown`` pixels, so the caller can fall back.
    """
    channel = KEY_CHANNEL.get(str(key_color or "").strip().lower())
    if channel is None or source.size != cutout.size:
        return cutout
    rgb = np.asarray(source.convert("RGB"), np.float64) / 255.0
    engine = np.asarray(cutout.convert("RGBA"))
    key = np.array(measure_chroma_background(source), np.float64) / 255.0
    if np.linalg.norm(key - np.array(KEY_COLORS[key_color.strip().lower()]) / 255.0) > 0.35:
        return cutout
    background, subject = _trimap(rgb, engine[..., 3], channel, key)
    unknown = ~background & ~subject
    count = int(unknown.sum())
    dropped = background & (engine[..., 3] > 0)
    if count == 0:
        if not dropped.any():
            return cutout
        pixels = engine.copy()
        pixels[dropped, 3] = 0
        result = Image.fromarray(pixels, "RGBA")
        result.info.update(cutout.info)
        return result
    if count > max_unknown:
        raise ValueError("Слишком широкая область края для матирования")

    ys, xs = np.nonzero(unknown)
    y0, y1 = max(ys.min() - 4, 0), min(ys.max() + 5, rgb.shape[0])
    x0, x1 = max(xs.min() - 4, 0), min(xs.max() + 5, rgb.shape[1])
    window = (slice(y0, y1), slice(x0, x1))
    known = ~unknown[window]
    alpha = np.zeros(rgb.shape[:2])
    alpha[window] = _closed_form_alpha(rgb[window], known, subject[window].astype(np.float64))

    colour = np.zeros_like(rgb)
    for _ in range(2):
        band = (alpha > 0) & (alpha < 1)
        colour[window] = _estimate_subject_colour(rgb[window], alpha[window], key)
        direction = colour - key
        mixture = ((rgb - key) * direction).sum(axis=2) / np.maximum((direction * direction).sum(axis=2), 1e-3)
        alpha = np.where(band, np.clip(mixture, 0.0, 1.0), alpha)
    alpha[alpha < 0.01] = 0.0
    colour[window] = _estimate_subject_colour(rgb[window], alpha[window], key)
    colour[window] = _cap_key_tint(colour[window], alpha[window], channel)

    outside = np.ones(alpha.shape, bool)
    outside[window] = False
    alpha[outside] = 0.0
    output = np.dstack([colour, alpha])
    result = Image.fromarray(np.clip(np.rint(output * 255.0), 0, 255).astype(np.uint8), "RGBA")
    untouched = engine[..., 3] == 255
    untouched &= _erode(untouched, SOLID_EROSION) & ~unknown & ~background
    pixels = np.asarray(result).copy()
    pixels[untouched] = engine[untouched]
    result = Image.fromarray(pixels, "RGBA")
    result.info.update(cutout.info)
    return result
