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

from chroma_key import (
    KEY_COLORS,
    SHADED_KEY_MAX_LEVEL,
    chroma_gap,
    measure_chroma_background,
    shaded_key_pocket,
)

KEY_CHANNEL = {"red": 0, "green": 1, "blue": 2}
KEY_DISTANCE = 45.0             # RGB distance to the measured key that is sure background
KEY_HUE_GAP = 60.0              # degrees of chroma difference that still matches the requested key: a
#                                 dark but saturated key is the same key, only less bright
DARK_KEY_RATIO = 1.6            # shaded key: key channel this many times the strongest other channel ...
DARK_KEY_LEAD = 40              # ... and this far ahead of it
SHADED_KEY_MAX_HALF_WIDTH = 2.5  # shaded key slivers are thin; a wider key-like patch is subject
SHADED_KEY_REACH = 2            # a sliver this close to the engine's transparent area is an edge, not a gap
SOLID_TINT = 15                 # sure subject leads the key channel by less than this over every other channel
SOLID_EROSION = 7               # engine-opaque pixels this deep inside are sure subject regardless of tint
TINT_CHROMA_GAP = 45.0          # degrees between a pixel's chroma and the key's: a subject colour at least
#                                 this far off the key hue may have its key-channel lead read against
#                                 the subject field; a tinted rim pixel moves toward the key hue, and
#                                 by this gap key mixtures beyond ~t=0.2 stop qualifying
FIELD_CHROMA_SIGMA = 12.0       # reach of the blurred subject field the extra chroma is measured against;
#                                 the unknown band of an opaque fur field measured 3-16 px wide
#                                 (p99 15.6, max 18.6 on the R3 fixture); at 1.5x the widest unbacked
#                                 band a half-plane of core still passes FIELD_WEIGHT_MIN (weight 0.06)
FIELD_WEIGHT_MIN = 0.05         # blurred core share below which there is no trusted field
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


def _enclosed_shaded_key(rgb: np.ndarray, engine_alpha: np.ndarray, channel: int, key: np.ndarray) -> np.ndarray:
    """Slivers of shaded key enclosed by the subject (dark gaps between leaves): key-dominant hue, at most ~5 px wide.

    Whatever the engine made of them (solid or a partial mixture), they are background: the subject is on every
    side. A sliver that touches the engine's transparent area is an edge and is left to the matting, as are wider
    key-like patches (a blue flower). "Shaded" means the same as in ``shaded_key_pocket``: the key channel at most
    SHADED_KEY_MAX_LEVEL of the measured key's. A brighter key-dominant speck is a detail the engine deliberately
    kept opaque (the owner's 1-px key-coloured detail contract), and deleting it here would punch a hole.
    """
    others = np.delete(rgb, channel, axis=2)
    key_lead = rgb[..., channel][..., None] - others
    candidate = ((engine_alpha > 0) & (rgb[..., channel] > DARK_KEY_RATIO * others.max(axis=2))
                 & (key_lead.min(axis=2) > DARK_KEY_LEAD / 255.0)
                 & (rgb[..., channel] <= SHADED_KEY_MAX_LEVEL * key[channel]))
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


def _field_key_excess(rgb: np.ndarray, core: np.ndarray, key: np.ndarray):
    """The pixel's extra chroma along the key's chroma axis over its subject field, the field's spread there, and whether a field exists.

    A chromatic subject leads the key channel by its own pigment: yellow fur (240, 210, 45)
    under a red key leads red over green by 30, over blue by 195, without any key tint
    (docs/ERRORS.md {#chroma-review-20261029}, R3) — and an untinted test tuned to a neutral
    subject throws exactly such fur into the unknown band, where the matting strips its
    alpha. What a key tint adds is chroma along the field-to-key gradient, i.e. the key's
    own chroma direction, so the pixel's chroma projection is judged against the blurred
    sure-core field's projection. The field's own pigment spread along that axis (warm
    strands inside the fur; under a green key the fur-to-strand difference is nearly
    parallel to it) is measured the same way and widens the tolerance exactly where the
    two cannot be told apart. Returns (excess, spread, known_field).
    """
    chroma = np.stack([rgb[..., 0] - rgb[..., 1], rgb[..., 1] - rgb[..., 2]], axis=2).astype(np.float32)
    key_chroma = np.array([key[0] - key[1], key[1] - key[2]], np.float64)
    key_hat = key_chroma / max(float(np.linalg.norm(key_chroma)), 1e-6)
    projection = (chroma * key_hat).sum(axis=2)
    size = (int(FIELD_CHROMA_SIGMA * 6) | 1,) * 2
    core_f = core.astype(np.float32)
    weight = cv2.GaussianBlur(core_f, size, FIELD_CHROMA_SIGMA)
    known_field = weight > FIELD_WEIGHT_MIN
    safe = np.maximum(weight, 1e-6)
    mean = cv2.GaussianBlur(projection * core_f, size, FIELD_CHROMA_SIGMA) / safe
    mean_square = cv2.GaussianBlur(projection * projection * core_f, size, FIELD_CHROMA_SIGMA) / safe
    spread = np.sqrt(np.maximum(mean_square - mean * mean, 0.0))
    return projection - mean, spread, known_field


def _chroma_gap_pixels(rgb: np.ndarray, key: np.ndarray) -> np.ndarray:
    """Per-pixel chroma angle to the key, the same (r-g, g-b) convention as ``chroma_gap``."""
    pixel_chroma = np.stack([rgb[..., 0] - rgb[..., 1], rgb[..., 1] - rgb[..., 2]], axis=2)
    key_chroma = np.array([key[0] - key[1], key[1] - key[2]], np.float64)
    norms = np.linalg.norm(pixel_chroma, axis=2) * np.linalg.norm(key_chroma)
    cosine = np.divide((pixel_chroma * key_chroma).sum(axis=2), norms, out=np.full(rgb.shape[:2], 0.0),
                       where=norms > 1e-6)
    # A neutral (chroma-free) pixel has no hue to compare: 90 degrees off anything, the
    # same convention chroma_gap uses. It passes the gap test, but a neutral subject leads
    # no channel, so the field allowance stays zero in effect.
    return np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))


def _trimap(rgb: np.ndarray, engine_alpha: np.ndarray, channel: int, key: np.ndarray):
    """Return (sure_background, sure_subject) boolean masks; everything else is unknown."""
    key_lead = rgb[..., channel][..., None] - np.delete(rgb, channel, axis=2)
    near_key = np.linalg.norm(rgb - key, axis=2) < KEY_DISTANCE / 255.0
    opaque = engine_alpha >= 255
    shaded_key = _enclosed_shaded_key(rgb, engine_alpha, channel, key)
    # A shade of the key in a thin gap is background even when the engine solved
    # coverage there; without this the closed-form solve would read the shade as
    # subject coverage and paint a film across the gap.
    shaded_pocket = shaded_key_pocket(rgb, key)
    background = near_key | (engine_alpha == 0) | shaded_key | shaded_pocket
    # CR-3 (docs/ERRORS.md {#chroma-review-20261029}, R3): a chromatic subject leads the
    # key channel by its own pigment. Only a pixel whose hue is far off the key's hue may
    # measure its key-ward chroma against the subject field instead of zero: a tinted rim
    # pixel moves toward the key hue (past TINT_CHROMA_GAP key mixtures beyond ~t=0.2 stop
    # qualifying), hue-close subjects (a leaf under the green key) keep the neutral rule,
    # and without a sure core in reach there is no field to measure against.
    core = _erode(opaque, SOLID_EROSION) & ~background
    excess, spread, known_field = _field_key_excess(rgb, core, key)
    far_from_key = _chroma_gap_pixels(rgb, key) > TINT_CHROMA_GAP
    untinted = (key_lead < SOLID_TINT / 255.0).all(axis=2)
    # Over the field, key tint can only add chroma along the key's own axis; within the
    # field's measured spread along that axis plus SOLID_TINT an opaque far-hue pixel is
    # still sure subject. Hue-close subjects (a leaf under the green key) and pixels with
    # no sure core in reach keep the neutral rule.
    untinted |= far_from_key & known_field & (excess < SOLID_TINT / 255.0 + spread)
    subject = opaque & (_erode(opaque, SOLID_EROSION) | untinted) & ~background
    # Key-like pixels deep inside the engine's opaque area are not trusted as background (only slivers are).
    background &= ~_erode(opaque, BACKGROUND_EROSION) | shaded_key | shaded_pocket
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


def _estimate_subject_colour(rgb: np.ndarray, alpha: np.ndarray, background: np.ndarray) -> np.ndarray:
    """Subject colour F with rgb = alpha*F + (1-alpha)*background, smooth along the edge; sure pixels keep rgb.

    ``background`` is the local background colour per pixel (the measured key on a
    plain background, the shade inside a shaded gap), so the unmixing stays valid
    where the generator darkened the key.
    """
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
                                                    - (1.0 - flat_alpha[unknown_index, None])
                                                    * background.reshape(-1, 3)[unknown_index]))
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
    """Pull a key-tinted edge colour towards the nearest sure subject colour.

    The edge may lead the key channel no more than the nearest sure subject pixel does.
    Cutting only the key channel, however, leaves the rim green: for the owner's frames
    (rough_02/04, 2026-10-29) the blue was removed while red and green stayed, and the
    edge turned olive. The excess is therefore removed by moving the whole colour towards
    the trusted neighbour in proportion to it, so the rim keeps the subject's hue.
    """
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
    excess = np.zeros(alpha.shape)
    lead = np.zeros(alpha.shape)
    for other in (c for c in range(3) if c != channel):
        allowed = np.maximum(reference[..., channel] - reference[..., other], 0.0)
        excess = np.maximum(excess, (colour[..., channel] - colour[..., other]) - allowed)
        lead = np.maximum(lead, colour[..., channel] - colour[..., other])
    weight = np.clip(excess / np.maximum(lead, 1e-3), 0.0, 1.0)[..., None]
    blended = colour + (reference - colour) * weight
    return np.where(edge[..., None], blended, colour)


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
    requested_key = np.array(KEY_COLORS[key_color.strip().lower()], np.float64) / 255.0
    # One sample of the key hue is the key: a dark rendered key is not another colour.
    if chroma_gap(requested_key, key) > KEY_HUE_GAP:
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

    # An edge composites against the background it actually touches. On the plain
    # frame that is the measured key; on the rim of a shaded gap it is the shade,
    # and unmixing such a rim against the bright key would invent paint.
    if np.any(background):
        _, background_labels = cv2.distanceTransformWithLabels(
            (~background).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL,
        )
        background_palette = np.zeros((int(background_labels.max()) + 1, 3))
        background_palette[background_labels[background]] = rgb[background]
        local_background = background_palette[background_labels]
    else:
        local_background = np.broadcast_to(key, rgb.shape).copy()

    ys, xs = np.nonzero(unknown)
    y0, y1 = max(ys.min() - 4, 0), min(ys.max() + 5, rgb.shape[0])
    x0, x1 = max(xs.min() - 4, 0), min(xs.max() + 5, rgb.shape[1])
    window = (slice(y0, y1), slice(x0, x1))
    known = ~unknown[window]
    alpha = np.zeros(rgb.shape[:2])
    alpha[window] = _closed_form_alpha(rgb[window], known, subject[window].astype(np.float64))

    colour = np.zeros_like(rgb)
    local_window = local_background[window]
    for _ in range(2):
        band = (alpha > 0) & (alpha < 1)
        colour[window] = _estimate_subject_colour(rgb[window], alpha[window], local_window)
        direction = colour - local_background
        mixture = ((rgb - local_background) * direction).sum(axis=2) / np.maximum(
            (direction * direction).sum(axis=2), 1e-3
        )
        alpha = np.where(band, np.clip(mixture, 0.0, 1.0), alpha)
    alpha[alpha < 0.01] = 0.0
    colour[window] = _estimate_subject_colour(rgb[window], alpha[window], local_window)
    colour[window] = _cap_key_tint(colour[window], alpha[window], channel)

    outside = np.ones(alpha.shape, bool)
    outside[window] = False
    alpha[outside] = 0.0
    output = np.dstack([colour, alpha])
    result = Image.fromarray(np.clip(np.rint(output * 255.0), 0, 255).astype(np.uint8), "RGBA")
    pixels = np.asarray(result).copy()
    # The unknown band's window does not cover the whole frame: whatever it never
    # examined keeps the engine's own decision, and only the background the engine
    # left visible is dropped.
    pixels[outside] = engine[outside]
    pixels[dropped, 3] = 0
    untouched = engine[..., 3] == 255
    untouched &= _erode(untouched, SOLID_EROSION) & ~unknown & ~background
    pixels[untouched] = engine[untouched]
    result = Image.fromarray(pixels, "RGBA")
    result.info.update(cutout.info)
    return result
