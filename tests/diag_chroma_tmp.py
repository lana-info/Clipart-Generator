import hashlib, json, sys
import cv2, numpy as np
from tests.test_chroma_material_causality import _automatic, _petal_source

def _h(x):
    if isinstance(x, np.ndarray):
        return hashlib.sha1(np.ascontiguousarray(x).tobytes()).hexdigest()[:10]
    if isinstance(x, (tuple, list)):
        return [_h(i) for i in x]
    return str(x)[:30]

def test_dump(monkeypatch):
    log = []
    for name in ("distanceTransformWithLabels", "distanceTransform", "floodFill", "connectedComponents",
                 "connectedComponentsWithStats", "erode", "dilate"):
        orig = getattr(cv2, name)
        def wrap(*a, _o=orig, _n=name, **k):
            r = _o(*a, **k)
            f = sys._getframe(1)
            log.append([_n, f.f_code.co_name + ':' + str(f.f_lineno), _h(list(a[:1])), _h(r)])
            return r
        monkeypatch.setattr(cv2, name, wrap)
    _automatic(_petal_source((0, 1, 2)), 'blue', 'legacy')
    print("DIAG json", json.dumps(log))
