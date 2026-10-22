import base64, json, zlib
import numpy as np
import chroma_key
from tests.test_chroma_material_causality import _automatic, _petal_source

def test_dump():
    _automatic(_petal_source((0, 1, 2)), 'blue', 'legacy')
    a = chroma_key._DIAG['alpha'].astype(np.float32)
    print("DIAG json", json.dumps({"shape": a.shape, "alpha": base64.b64encode(zlib.compress(a.tobytes(), 9)).decode()}))
