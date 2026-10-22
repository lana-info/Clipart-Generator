from __future__ import annotations
import ast, base64, contextlib, copy, os, pathlib, struct, tempfile, threading, types, unittest, zlib
from types import SimpleNamespace
from unittest.mock import Mock, patch
import gpt25_provider as adapter
from tests.test_gpt25_async_worker import OfflineWorker, namespace
ROOT = pathlib.Path(__file__).resolve().parents[1]
def extract(file, cls, name, values):
    c = next(n for n in ast.parse((ROOT/file).read_text(encoding="utf-8")).body if isinstance(n,ast.ClassDef) and n.name==cls)
    f = copy.deepcopy(next(n for n in c.body if isinstance(n,ast.FunctionDef) and n.name==name)); env=dict(values)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[f],type_ignores=[])),file,"exec",flags=__import__("__future__").annotations.compiler_flag),env)
    return env[name]
def png():
    def chunk(k,d): return struct.pack(">I",len(d))+k+d+struct.pack(">I",zlib.crc32(k+d)&0xffffffff)
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",2,2,8,6,0,0,0))+chunk(b"IDAT",zlib.compress((b"\x00"+b"\x11\x22\x33\xff"*2)*2))+chunk(b"IEND",b"")
class SafeBatchTests(unittest.TestCase):
    def test_controller_admission_precedes_queue_and_worker(self):
        for mode in ("clipart","processing","pinterest"):
            for reject in (False,True):
                with self.subTest(mode=mode,reject=reject):
                    events=[]; req=object(); w=Mock(); w.isRunning.return_value=False; w.start.side_effect=lambda:events.append("worker")
                    shell=Mock(); shell.another_run_is_active.return_value=False; shell.show_results.side_effect=RuntimeError("denied") if reject else lambda:events.append("admission")
                    queue=Mock(); queue.start_new.side_effect=lambda _:events.append("queue")
                    c=SimpleNamespace(shell=shell,worker=None,run_queue=queue,review_page=Mock(),error=Mock(),started=Mock(),locale="ru",_request=lambda:req,create_worker_for_request=lambda _:w)
                    env={"build_clipart_run_request":lambda _:req,"ClipartFlowError":ValueError,"PinterestFlowError":ValueError,"_safe_runtime_error":str,"_pinterest_text":lambda *a,**k:"blocked"}
                    result=extract("v3_"+mode+"_flow.py",mode.title()+"FlowController","start",env)(c)
                    if reject:
                        self.assertIsNone(result); w.start.assert_not_called(); queue.start_new.assert_not_called(); self.assertIsNone(c.worker)
                    else: self.assertIs(result,req); self.assertEqual(events,["admission","queue","worker"])
    def test_inline_output_and_safe_repr(self):
        encoded=base64.b64encode(png()).decode()
        for wrapped in (False,True):
            record={"status":"completed","output":{"data":[{"b64_json":encoded}]}}
            state,image=adapter.task_result("piapi",{"data":record} if wrapped else record)
            self.assertEqual(state,"completed"); self.assertEqual(image.data,png()); self.assertNotIn(encoded,repr(image)); self.assertNotIn(repr(png()),repr(image))
    def test_inline_rejects_bad_and_oversized(self):
        for value in ("%%%","秘密",42,base64.b64encode(b"not an image").decode()):
            with self.subTest(kind=type(value).__name__),self.assertRaises(adapter.Gpt25ProviderError): adapter.task_result("piapi",{"status":"completed","output":{"data":[{"b64_json":value}]}})
        with patch.object(adapter,"MAX_INLINE_IMAGE_BYTES",8),self.assertRaises(adapter.Gpt25ProviderError): adapter.task_result("piapi",{"status":"completed","output":{"data":[{"b64_json":base64.b64encode(png()).decode()}]}})
    def test_wrapped_submission_id(self): self.assertEqual(adapter.submitted_task_id("piapi",{"data":{"task_id":"accepted_123"}}),"accepted_123")
    def test_failure_closes_admission_before_releasing_provider_slot(self):
        with tempfile.TemporaryDirectory() as folder:
            w=OfflineWorker(folder,"piapi"); w._publish_lock=threading.RLock(); w.is_running=True; w._paid_submission_open=True; w.stop_after_current_requested=False
            for name in ("request_stop_after_current","_ensure_provider_submission_allowed","_admit_paid_submission"): setattr(w,name,types.MethodType(extract("main.py","WorkerThread",name,{"ProcessingCancelled":namespace["ProcessingCancelled"]}),w))
            @contextlib.contextmanager
            def lease(_):
                try: yield
                finally: self.assertFalse(w._paid_submission_open)
            w._provider_lease=lease; w._item_context=threading.local(); w._shared_state_lock=threading.Lock(); w._consecutive_provider_failures=0; w.progress=Mock()
            w._diagnostic_context=SimpleNamespace(provider="piapi",last_http_status=None)
            w._note_provider_failure=types.MethodType(extract("main.py","WorkerThread","_note_provider_failure",{"PROVIDER_FAILURE_STOP_THRESHOLD":1,"PROVIDER_FAILURE_STOP_PROVIDERS":frozenset({"piapi"})}),w)
            w.responses=[{"task_id":"accepted_123"},{"status":"failed","error":{"message":"Our servers are currently overloaded"}}]
            with self.assertRaisesRegex(RuntimeError,"overloaded"): w._gpt25_generate_image("cup","piapi/gpt-image-2.5-flare")
            self.assertTrue(w.stop_after_current_requested); self.assertTrue(w.is_running)
            with self.assertRaises(namespace["ProcessingCancelled"]): w._gpt25_generate_image("next cup","piapi/gpt-image-2.5-flare")
            self.assertEqual([c[0] for c in w.calls],["POST","GET"])
    def test_inline_recovery_is_get_only(self):
        with tempfile.TemporaryDirectory() as folder:
            w=OfflineWorker(folder,"piapi"); w.responses=[{"task_id":"accepted_123"},TimeoutError("temporary")]
            with self.assertRaises(RuntimeError): w._gpt25_generate_image("cup","piapi/gpt-image-2.5-flare")
            restarted=OfflineWorker(folder,"piapi"); restarted.responses=[{"data":{"status":"completed","output":{"data":[{"b64_json":base64.b64encode(png()).decode()}]}}}]
            self.assertEqual(restarted._gpt25_generate_image("cup","piapi/gpt-image-2.5-flare").data,png()); self.assertEqual([c[0] for c in restarted.calls],["GET"])
    def test_real_png_save_is_atomic_and_preserves_existing_file_on_bad_image(self):
        try: from PIL import Image
        except ImportError: self.skipTest("Pillow unavailable: image-save validation not verified")
        from io import BytesIO
        env={"os":os,"tempfile":tempfile,"Gpt25InlineImage":adapter.InlineImageResult,"Image":Image,"BytesIO":BytesIO,"MAX_API_RESPONSE_BYTES":128*1024*1024,"MAX_PROVIDER_IMAGE_DIMENSION":32768,"MAX_PROVIDER_IMAGE_PIXELS":70000000,"ProcessingCancelled":namespace["ProcessingCancelled"],"inspect_diagnostic_image":lambda _:{}}
        w=SimpleNamespace(_ensure_running=lambda:None,export_300_dpi=False,progress=Mock(),_emit_diagnostic=Mock()); w._save_png_from_any_image_bytes=types.MethodType(extract("main.py","WorkerThread","_save_png_from_any_image_bytes",env),w); download=extract("main.py","WorkerThread","_download_file",env)
        with tempfile.TemporaryDirectory() as folder:
            p=pathlib.Path(folder)/"result.png"; download(w,adapter.InlineImageResult(png()),str(p)); self.assertEqual(p.read_bytes(),png())
            with Image.open(p) as image: self.assertEqual(image.size,(2,2))
            with self.assertRaises(RuntimeError): download(w,adapter.InlineImageResult(b"bad image"),str(p))
            self.assertEqual(p.read_bytes(),png()); self.assertEqual(list(p.parent.glob("*.stage.png")),[])
