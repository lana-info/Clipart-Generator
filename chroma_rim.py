"""Reference-backed reclassification of a provisional opaque boundary.

Independent two-colour projection using the source's interior, not a port of
Clipbrook source. No island removal or global recolouring is performed.
"""
import cv2
import numpy as np
from PIL import Image


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
