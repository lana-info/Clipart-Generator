import base64, hashlib, json, zlib
from tests.test_chroma_material_causality import _automatic, _petal_source

def test_dump():
    r, stages = _automatic(_petal_source((0, 1, 2)), 'blue', 'legacy')
    out = {k: base64.b64encode(zlib.compress(v.tobytes(), 9)).decode() for k, v in stages.items()}
    out["final"] = base64.b64encode(zlib.compress(r.tobytes(), 9)).decode()
    print("DIAG json", json.dumps(out))
