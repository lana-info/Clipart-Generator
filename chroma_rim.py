"""Reference-backed reclassification of a provisional opaque boundary.

Independent two-colour projection using the source's interior, not a port of
Clipbrook source. No island removal or global recolouring is performed.
"""
import cv2
import numpy as np
from PIL import Image


def ambiguous_pale_material(observed, background, key):
    """Preserve near-white paint when the borrowed colour prior is ambiguous.

    An impossible coverage fit does not prove additive spill. A nearly neutral
    pale sample with no key dominance can equally be a different painted
    material. Preserve that source colour rather than borrowing a neighbour's
    hue. The 230/24 bounds describe this conservative policy, not segmentation
    confidence. Identical near-white additive light may remain unchanged.
    """
    key = np.asarray(key, dtype=np.float32)
    key_channel = int(np.argmax(key))
    non_key = [channel for channel in range(3) if channel != key_channel]
    recovered = (observed - background[:, None] * key) / np.maximum(
        1.0 - background[:, None], 0.01,
    )
    impossible = np.any((recovered < -2.0) | (recovered > 257.0), axis=1)
    pale = ((np.min(observed[:, non_key], axis=1) >= 230.0)
            & (np.ptp(observed, axis=1) <= 24.0)
            & (observed[:, key_channel] <= np.max(observed[:, non_key], axis=1)))
    return impossible & pale


def mixture_coverage(observed, foreground_scale, background, key):
    """Separate additive key spill from coverage when a pure mix is impossible.

    Normally C=s*F+b*K implies coverage 1-b, allowing F to be darker or
    brighter than its local reference. If that would require a channel above
    255 (allowing two intensity levels of source-space fitting error), the fit cannot be
    a pure background mixture. Retain its foreground signal but raise coverage
    toward s; excess key contribution is then additive spill. This avoids
    clipping RGB into a white/yellow highlight. In-gamut highlights and darker
    feathers keep the ordinary solution, without a neighbour-brightness cap.
    """
    coverage = np.clip(1.0 - background, 0.0, 1.0)
    signal = observed - background[:, None] * key
    overflow = np.max(signal, axis=1) > 255.0 * coverage + 2.0
    return np.where(overflow, np.maximum(coverage, np.clip(foreground_scale, 0.0, 1.0)), coverage)


def repair_edge_chroma(source: Image.Image, provisional: Image.Image, key: np.ndarray) -> Image.Image:
    """Repair supported key-coloured specks and opponent-colour fringe.

    The rim is measured from opaque coverage, so a partially keyed enclosed
    gap is eligible too. Two interior depths must agree on chromaticity in the
    same connected subject. Preserve existing partial coverage. An opaque speck
    may regain partial coverage only if a source/key mixture fits and yields
    in-gamut RGB. Flat paint, enclosed marks, supplied alpha, consistent partial
    mixtures and non-key hue reversals are protected.
    """
    original = np.asarray(source.convert("RGBA"))
    pixels = np.array(provisional.convert("RGBA"))
    key = np.asarray(key, dtype=np.float32)
    key_channel = int(np.argmax(key))
    non_key = [channel for channel in range(3) if channel != key_channel]
    opaque = pixels[..., 3] == 255
    visible = pixels[..., 3] > 0
    kernel = np.ones((3, 3), np.uint8)
    depth = cv2.distanceTransform(opaque.astype(np.uint8), cv2.DIST_L2, 5)
    candidate = visible & (depth <= 2.0) & (original[..., 3] == 255)
    del depth
    flat = opaque.copy()
    for channel in range(3):
        plane = original[..., channel]
        flat &= cv2.dilate(plane, kernel) - cv2.erode(plane, kernel) <= 1
    candidate &= ~cv2.dilate(flat.astype(np.uint8), kernel).astype(bool)
    del flat
    if not np.any(candidate):
        return provisional
    _, components = cv2.connectedComponents(visible.astype(np.uint8), connectivity=8)
    reliable = np.ones(int(np.count_nonzero(candidate)), bool)
    references = []
    for size in (5, 9):
        core = cv2.erode(opaque.astype(np.uint8), np.ones((size, size), np.uint8)).astype(bool)
        if not np.any(core):
            return provisional
        distance, labels = cv2.distanceTransformWithLabels(
            (~core).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL,
        )
        reliable &= distance[candidate] <= 12.0
        del distance
        lookup = np.zeros(int(labels.max()) + 1, np.float32)
        lookup[labels[core]] = components[core]
        reliable &= lookup[labels[candidate]] == components[candidate]
        reference = np.empty((len(reliable), 3), np.float32)
        for channel in range(3):
            lookup[labels[core]] = original[..., channel][core]
            reference[:, channel] = lookup[labels[candidate]]
        reference /= np.maximum(reference[:, non_key].max(axis=1, keepdims=True), 1.0)
        references.append(reference)
        del lookup, labels, core
    del components
    shallow, deep = references
    reference_difference = np.max(np.abs(shallow - deep), axis=1)
    chroma = (shallow + deep) * 0.5
    observed = pixels[candidate, :3].astype(np.float32)
    level = observed[:, non_key].max(axis=1)
    predicted = chroma * level[:, None]
    key_excess = observed[:, key_channel] - predicted[:, key_channel]
    difference = observed[:, non_key[0]] - observed[:, non_key[1]]
    predicted_difference = predicted[:, non_key[0]] - predicted[:, non_key[1]]
    # On blue, a depleted green channel leaves magenta even after blue despill.
    # Opaque samples still need positive key excess; otherwise genuine saturated
    # texture (e.g. golden fur on a green key) would be mistaken for this fringe.
    opponent_fringe = (
        (key_excess > np.where(opaque[candidate], 2.0, -8.0))
        & (np.abs(difference) - np.abs(predicted_difference) > 18.0)
        & (observed[:, key_channel] - observed[:, non_key].min(axis=1) > 8.0)
    )
    key_speck = observed[:, key_channel] - level > 20.0
    # A green stem must not acquire the hue of an adjacent yellow flower.
    colour_consensus = ((reference_difference < 0.12) & (chroma[:, key_channel] < 0.9)
                        & (difference * predicted_difference >= 0.0))
    # A weak key mixture can have uncertain reference chromaticity but still
    # agree in source RGB. Such samples may only be unmixed, never repainted:
    # preserve their observed non-key hue and demand a bounded source fit below.
    mixture_consensus = (key_speck & (chroma[:, key_channel] < 1.05)
                         & ((reference_difference < 0.12) | (reference_difference * level <= 16.0)))
    reliable &= (opponent_fringe | key_speck) & (level > 12.0) & (colour_consensus | mixture_consensus)
    alpha = pixels[candidate, 3:4].astype(np.float32) / 255.0
    error = np.max(np.abs(
        observed * alpha + key * (1.0 - alpha) - original[candidate, :3],
    ), axis=1)
    reliable &= opaque[candidate] | (error > 3.0)
    if not np.any(reliable):
        return provisional
    # Merely recolouring an opaque key mixture leaves a dark solid speck. Use
    # the source fit to recover its coverage too, with brightness independent
    # of alpha. Reject fits that would recreate the clipped-highlight defect.
    source_rgb = original[candidate, :3].astype(np.float32)
    ff = np.sum(chroma * chroma, axis=1)
    fk = chroma @ key
    kk = float(key @ key)
    cf = np.sum(source_rgb * chroma, axis=1)
    ck = source_rgb @ key
    determinant = ff * kk - fk * fk
    stable = determinant > 0.01 * ff * kk
    background = np.divide(ck * ff - cf * fk, determinant,
                           out=np.zeros_like(ck), where=stable)
    scale = np.divide(cf * kk - ck * fk, determinant,
                      out=np.zeros_like(ck), where=stable)
    residual = np.max(np.abs(source_rgb - scale[:, None] * chroma - background[:, None] * key), axis=1)
    coverage = 1.0 - background
    recover_alpha = (reliable & opaque[candidate] & stable & (background > 0.10)
                     & (coverage > 0.05) & (residual < 24.0) & (scale > 0.0))
    recovered = (source_rgb - background[:, None] * key) / np.maximum(coverage[:, None], 0.05)
    recover_alpha &= (recovered.max(axis=1) <= 255.0) & (recovered.min(axis=1) >= 0.0)
    # At a material junction, both depths may agree on key excess while their
    # non-key hue differs from the sample. If unmixing would clip RGB, treat this
    # as additive spill only. Never borrow the neighbour's non-key channels or
    # reduce coverage in this ambiguous case.
    spill_only = (reliable & opaque[candidate] & key_speck & ~colour_consensus
                  & stable & (background > 0.10) & (coverage > 0.05) & (scale > 0.0)
                  & (recovered.max(axis=1) > 255.0) & (chroma[:, key_channel] < 0.9)
                  & (np.abs(shallow[:, key_channel] - deep[:, key_channel]) * level <= 12.0))
    reliable &= colour_consensus | recover_alpha | spill_only
    supported = np.zeros(opaque.shape, bool)
    supported[candidate] = reliable
    count, regions = cv2.connectedComponents(supported.astype(np.uint8), connectivity=8)
    near_partial = cv2.dilate((visible & ~opaque).astype(np.uint8), kernel).astype(bool)
    edge_regions = np.zeros(count, bool)
    edge_regions[np.unique(regions[supported & near_partial])] = True
    edge_regions[0] = False
    reliable &= edge_regions[regions[candidate]]
    recover_alpha &= reliable
    spill_only &= reliable
    corrected = pixels[candidate].copy()
    colour_repair = reliable & colour_consensus
    corrected[colour_repair, :3] = np.rint(np.clip(predicted[colour_repair], 0.0, 255.0)).astype(np.uint8)
    corrected[spill_only, key_channel] = np.rint(predicted[spill_only, key_channel]).astype(np.uint8)
    # Keep the chroma repair when a speck also has an opponent-channel defect;
    # otherwise unmixing its raw RGB would turn the blue spot into a pink one.
    opponent_mix = recover_alpha & opponent_fringe & colour_consensus
    recovered[opponent_mix] = chroma[opponent_mix] * recovered[opponent_mix][:, non_key].max(axis=1, keepdims=True)
    corrected[recover_alpha, :3] = np.rint(recovered[recover_alpha]).astype(np.uint8)
    corrected[recover_alpha, 3] = np.rint(coverage[recover_alpha] * 255.0).astype(np.uint8)
    pixels[candidate] = corrected
    return Image.fromarray(pixels)


def suppress_edge_key_spill(source: Image.Image, provisional: Image.Image, key: np.ndarray) -> Image.Image:
    """Remove confirmed key-channel excess without changing edge coverage.

    Two independently eroded interior references must agree on the expected
    key-channel value after fitting brightness to the other two channels.
    Different materials, flat painted marks and enclosed dots are protected.
    """
    pixels = np.array(provisional.convert("RGBA"))
    original = np.asarray(source.convert("RGBA"))
    opaque = pixels[..., 3] == 255
    visible = pixels[..., 3] > 0
    depth = cv2.distanceTransform(visible.astype(np.uint8), cv2.DIST_L2, 5)
    candidate = visible & (depth <= 4.0) & (original[..., 3] == 255)
    del depth
    kernel = np.ones((3, 3), np.uint8)
    flat = opaque.copy()
    for channel in range(3):
        plane = original[..., channel]
        flat &= cv2.dilate(plane, kernel) - cv2.erode(plane, kernel) <= 1
    candidate &= ~(opaque & cv2.dilate(flat.astype(np.uint8), kernel).astype(bool))
    del flat
    if not np.any(candidate):
        return provisional
    _, components = cv2.connectedComponents(visible.astype(np.uint8), connectivity=8)
    key_channel = int(np.argmax(key))
    other_channels = [channel for channel in range(3) if channel != key_channel]
    observed = pixels[candidate, :3].astype(np.float32)
    other = observed[:, other_channels]
    reliable = np.ones(len(observed), bool)
    estimates = []
    for size in (11, 21):
        core = cv2.erode(opaque.astype(np.uint8), np.ones((size, size), np.uint8)).astype(bool)
        if not np.any(core):
            return provisional
        distance, labels = cv2.distanceTransformWithLabels(
            (~core).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL,
        )
        reliable &= distance[candidate] <= 32.0
        del distance
        lookup = np.zeros(int(labels.max()) + 1, np.int32)
        lookup[labels[core]] = components[core]
        reliable &= lookup[labels[candidate]] == components[candidate]
        reference = np.empty((len(observed), 3), np.float32)
        for channel in range(3):
            lookup[labels[core]] = original[..., channel][core]
            reference[:, channel] = lookup[labels[candidate]]
        del lookup, labels, core
        reference_other = reference[:, other_channels]
        denominator = np.sum(reference_other * reference_other, axis=1)
        scale = np.divide(np.sum(reference_other * other, axis=1), denominator,
                          out=np.zeros_like(denominator), where=denominator > 1.0)
        estimate = scale * reference[:, key_channel]
        residual = np.max(np.abs(other - scale[:, None] * reference_other), axis=1)
        reliable &= ((scale >= 0.3) & (scale <= 1.6)
                     & (residual <= np.where(opaque[candidate], 5.0, 32.0))
                     & (estimate >= 0.0) & (estimate <= 255.0))
        estimates.append(estimate)
    del components
    shallow, deep = estimates
    estimate = (shallow + deep) * 0.5
    reliable &= ((np.abs(shallow - deep) <= 12.0)
                 & (observed[:, key_channel] - estimate > np.where(opaque[candidate], 32.0, 20.0)))
    alpha = pixels[..., 3][candidate, None].astype(np.float32) / 255.0
    reconstruction_error = np.max(np.abs(
        observed * alpha + np.asarray(key) * (1.0 - alpha)
        - original[..., :3][candidate],
    ), axis=1)
    # A correctly unmixed green/red detail can exceed another material's
    # reference. Do not reinterpret a source-consistent partial-alpha colour.
    reliable &= opaque[candidate] | (reconstruction_error > 3.0)
    supported = np.zeros(opaque.shape, bool)
    supported[candidate] = reliable
    background_neighbour = cv2.dilate((~visible).astype(np.uint8), kernel).astype(bool)
    count, regions = cv2.connectedComponents(supported.astype(np.uint8), connectivity=8)
    edge_regions = np.zeros(count, bool)
    edge_regions[np.unique(regions[supported & (~opaque | background_neighbour)])] = True
    edge_regions[0] = False
    reliable &= ~opaque[candidate] | edge_regions[regions[candidate]]
    if not np.any(reliable):
        return provisional
    corrected = pixels[candidate].copy()
    corrected[reliable, key_channel] = np.rint(estimate[reliable]).astype(np.uint8)
    pixels[candidate] = corrected
    return Image.fromarray(pixels)


def refine_edge_mixture(source: Image.Image, provisional: Image.Image, key: np.ndarray) -> Image.Image:
    """Reconstruct edge coverage and colour from a local opaque colour prior.

    A two-vector least-squares fit C = s*F + b*K separates foreground brightness
    from background contribution. Coverage starts at 1-b, not s: a darker feather
    is not necessarily more transparent. Impossible out-of-gamut solutions also
    account for additive spill. F constrains the background contribution,
    with foreground brightness estimated independently of coverage. Recover colour from the
    observed source, preserving its non-key colour differences instead of
    repainting a stem with its leaf's RGB. The prior must belong to the same visible
    component; interiors, existing holes and supplied source alpha are protected.
    """
    pixels = np.array(provisional.convert("RGBA"))
    source_pixels = np.asarray(source.convert("RGBA"))
    opaque = pixels[..., 3] == 255
    core = cv2.erode(opaque.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    if not np.any(core):
        return provisional
    visible = pixels[..., 3] > 0
    depth = cv2.distanceTransform(visible.astype(np.uint8), cv2.DIST_L2, 5)
    candidate = visible & (~opaque | (depth <= 3.0)) & (source_pixels[..., 3] == 255)
    del depth
    # A spatially constant painted patch is not evidence of a background mix.
    # Protect its border too, even if it is next to the external contour.
    kernel = np.ones((3, 3), np.uint8)
    flat = opaque.copy()
    for channel in range(3):
        plane = source_pixels[..., channel]
        flat &= cv2.dilate(plane, kernel) - cv2.erode(plane, kernel) <= 1
    candidate &= ~(opaque & cv2.dilate(flat.astype(np.uint8), kernel).astype(bool))
    del flat
    if not np.any(candidate):
        return provisional
    distance, labels = cv2.distanceTransformWithLabels(
        (~core).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL,
    )
    candidate &= distance <= 24.0
    del distance
    if not np.any(candidate):
        return provisional
    _, components = cv2.connectedComponents(visible.astype(np.uint8), connectivity=8)
    lookup = np.zeros(int(labels.max()) + 1, np.int32)
    lookup[labels[core]] = components[core]
    candidate &= lookup[labels] == components
    del components, lookup, visible
    if not np.any(candidate):
        return provisional
    reference = np.empty((int(np.count_nonzero(candidate)), 3), np.float32)
    lookup = np.zeros(int(labels.max()) + 1, np.float32)
    for channel in range(3):
        lookup[labels[core]] = source_pixels[..., channel][core]
        reference[:, channel] = lookup[labels[candidate]]
    del lookup, labels, core
    observed = source_pixels[..., :3][candidate].astype(np.float32)
    key = np.asarray(key, dtype=np.float32)
    ff = np.sum(reference * reference, axis=1)
    fk = reference @ key
    kk = float(key @ key)
    cf = np.sum(observed * reference, axis=1)
    ck = observed @ key
    determinant = ff * kk - fk * fk
    stable = determinant > 0.01 * ff * kk
    foreground = np.divide(cf * kk - ck * fk, determinant,
                           out=np.zeros_like(cf), where=stable)
    background = np.divide(ck * ff - cf * fk, determinant,
                           out=np.zeros_like(ck), where=stable)
    residual = np.max(np.abs(
        observed - foreground[:, None] * reference - background[:, None] * key,
    ), axis=1)
    mixture_alpha = 1.0 - background
    coverage = mixture_coverage(observed, foreground, background, key)
    # Absolute error alone admits a yellow flower as the colour prior of a
    # dark green stem. Require agreement relative to the foreground signal too.
    signal = foreground * np.max(reference, axis=1)
    reliable = (stable & (residual <= np.minimum(24.0, 1.0 + 0.06 * signal)) & (foreground > 0.0)
                & (mixture_alpha > 0.04) & (mixture_alpha < 1.0))
    non_key = [channel for channel in range(3) if channel != int(np.argmax(key))]
    first, second = non_key
    observed_difference = (observed[:, first] - observed[:, second]
                           - background * (key[first] - key[second]))
    reference_difference = reference[:, first] - reference[:, second]
    # Do not reverse the two non-key channels (for example green into yellow)
    # at a material junction, even when an absolute fit looks plausible.
    hue_conflict = ((np.abs(observed_difference) > 0.5)
                    & (np.abs(reference_difference) > 2.0)
                    & (observed_difference * reference_difference < 0.0))
    reliable &= ~hue_conflict
    reliable &= ~(opaque[candidate] & ambiguous_pale_material(observed, background, key))
    reliable &= ~opaque[candidate] | (background > 0.10)
    prior = pixels[candidate].astype(np.float32)
    prior_alpha = prior[:, 3:4] / 255.0
    reconstruction_error = np.max(np.abs(
        prior[:, :3] * prior_alpha + key * (1.0 - prior_alpha) - observed,
    ), axis=1)
    # Preserve already consistent partial-alpha solutions, allowing for byte
    # rounding. A new colour prior should not undo a more precise earlier fit.
    reliable &= opaque[candidate] | (reconstruction_error > 3.0)
    # An enclosed key-tinted dot is a painted detail, not an external mixture.
    # Reclassify opaque samples only along a supported path to existing edge
    # coverage or transparent background; colour similarity alone is ambiguous.
    supported = np.zeros(opaque.shape, bool)
    supported[candidate] = reliable
    background_neighbour = cv2.dilate((pixels[..., 3] == 0).astype(np.uint8), kernel).astype(bool)
    count, regions = cv2.connectedComponents(supported.astype(np.uint8), connectivity=8)
    edge_regions = np.zeros(count, bool)
    edge_regions[np.unique(regions[supported & (~opaque | background_neighbour)])] = True
    edge_regions[0] = False
    reliable &= ~opaque[candidate] | edge_regions[regions[candidate]]
    del supported, background_neighbour, regions, edge_regions
    if not np.any(reliable):
        return provisional
    corrected = pixels[candidate].copy()
    recovered = (observed[reliable] - background[reliable, None] * key) / coverage[reliable, None]
    corrected[reliable, :3] = np.rint(np.clip(recovered, 0, 255)).astype(np.uint8)
    corrected[reliable, 3] = np.rint(coverage[reliable] * 255).astype(np.uint8)
    pixels[candidate] = corrected
    return Image.fromarray(pixels)


def reclassify_rim(source, provisional, key):
    pixels = np.array(provisional.convert('RGBA'))
    rgb = np.asarray(source.convert('RGB'))
    opaque = pixels[..., 3] == 255
    core = cv2.erode(opaque.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    if not np.any(core):
        return provisional
    depth = cv2.distanceTransform(opaque.astype(np.uint8), cv2.DIST_L2, 3)
    distance, labels = cv2.distanceTransformWithLabels(
        (~core).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL,
    )
    candidate = opaque & (depth <= 1.5) & (distance <= 4)
    if not np.any(candidate):
        return provisional
    reference = np.empty((np.count_nonzero(candidate), 3), np.float32)
    lookup = np.zeros(int(labels.max()) + 1, np.float32)
    for channel in range(3):
        lookup[labels[core]] = rgb[..., channel][core]
        reference[:, channel] = lookup[labels[candidate]]
    # Nearby but disconnected details must not borrow another object's colour.
    _, components = cv2.connectedComponents((pixels[..., 3] > 0).astype(np.uint8))
    component_lookup = np.zeros(int(labels.max()) + 1, np.int32)
    component_lookup[labels[core]] = components[core]
    same_component = component_lookup[labels[candidate]] == components[candidate]
    observed = rgb[candidate].astype(np.float32)
    direction = reference - key
    denominator = np.sum(direction * direction, axis=1)
    alpha = np.divide(np.sum((observed-key)*direction, axis=1), denominator,
                      out=np.zeros_like(denominator), where=denominator > 1)
    residual = np.linalg.norm(observed-(key+alpha[:, None]*direction), axis=1)
    reliable = same_component & (denominator > 96**2) & (residual <= 3) & (alpha >= .1) & (alpha <= .95)
    repaired = pixels[candidate].copy()
    recovered = (observed[reliable]-(1-alpha[reliable, None])*key)/alpha[reliable, None]
    repaired[reliable, :3] = np.rint(np.clip(recovered, 0, 255)).astype(np.uint8)
    repaired[reliable, 3] = np.rint(alpha[reliable]*255).astype(np.uint8)
    pixels[candidate] = repaired
    return Image.fromarray(pixels)


def recolour_rim_specks(image: Image.Image, key) -> Image.Image:
    """Replace the colour of key-tinted dark specks on the subject's rim.

    Key spill leaves opaque grey-violet pixels at the tips of fur and feathers.
    Alpha is not touched: a rim pixel (within 2.5 px of the solid interior) that
    is much darker than the nearby light interior and whose colour is pushed
    towards the measured key takes the local interior colour, if it forms a tiny blob (a long run is a painted
    stroke). A darker shade of
    the same hue (a painted outline) and dark paint that is not key-tinted stay.
    """
    arr = np.asarray(image.convert("RGBA")).astype(np.float32)
    alpha = arr[..., 3]
    rgb = arr[..., :3]
    solid = (alpha >= 250).astype(np.uint8)
    depth = cv2.distanceTransform(solid, cv2.DIST_L2, 3)
    rim = (alpha > 0) & (depth <= 2.5)
    core = (depth >= 4).astype(np.float32)
    weight = cv2.blur(core, (15, 15))[..., None]
    reference = cv2.blur(rgb * core[..., None], (15, 15)) / np.maximum(weight, 1e-3)
    luma = np.array([0.3, 0.59, 0.11], dtype=np.float32)
    reference_luma = reference @ luma
    pixel_luma = rgb @ luma
    drop = reference_luma - pixel_luma
    scale = np.clip(pixel_luma / np.maximum(reference_luma, 1.0), 0.0, 1.0)
    deviation = rgb - reference * scale[..., None]
    tint = np.asarray(key, dtype=np.float32) - 127.5
    tint /= max(float(np.linalg.norm(tint)), 1.0)
    size = np.linalg.norm(deviation, axis=2)
    key_tinted = (size > 12.0) & ((deviation @ tint) > 0.5 * size)
    speck = rim & (weight[..., 0] > 0.05) & (reference_luma >= 185.0) & (drop > 60.0) & key_tinted
    # A painted stroke along the edge is a long run; spill specks sit at single tips.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(speck.astype(np.uint8), connectivity=8)
    small = (stats[:, cv2.CC_STAT_AREA] <= 12) & (np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT]) <= 5)
    small[0] = False
    speck = small[labels]
    if not speck.any():
        return image
    out = arr.copy()
    out[..., :3][speck] = reference[speck]
    result = Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")
    result.info.update(image.info)
    return result
