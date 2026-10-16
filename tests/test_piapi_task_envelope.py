import tempfile
import unittest
from gpt25_provider import task_result, failure_reason, Gpt25ProviderError
from tests.test_gpt25_async_worker import OfflineWorker
URL = "https://images.example.org/recovered.png"
def wrapped(status="completed"):
    return {"code": 200, "data": {"task_id": "fixture_task", "status": status,
            "output": {"data": [{"url": URL}]}}, "message": "success"}
class PiapiTaskEnvelopeTests(unittest.TestCase):
    def test_wrapped_completed_uses_nested_record(self):
        self.assertEqual(task_result("piapi", wrapped()), ("completed", URL))
    def test_wrapped_failed_is_not_pending(self):
        self.assertEqual(task_result("piapi", wrapped("failed")), ("failed", None))
    def test_wrapped_processing_remains_pending(self):
        self.assertEqual(task_result("piapi", wrapped("processing")), ("pending", None))
    def test_legacy_flat_response_is_preserved(self):
        self.assertEqual(task_result("piapi", wrapped()["data"]), ("completed", URL))
    def test_invalid_wrapper_and_unsafe_url_fail(self):
        with self.assertRaises(Gpt25ProviderError): task_result("piapi", {"data": None})
        value=wrapped(); value["data"]["output"]["data"][0]["url"]="http://unsafe.example/image.png"
        with self.assertRaises(Gpt25ProviderError): task_result("piapi", value)
    def test_nested_failure_reason_is_visible(self):
        value=wrapped("failed");value["data"]["error"]={"message":"Provider refused."}
        self.assertEqual(failure_reason("piapi",value),"Provider refused")
    def test_restarted_worker_recovers_without_new_post(self):
        with tempfile.TemporaryDirectory() as temp:
            first=OfflineWorker(temp,"piapi");first._get_generation_profile=lambda _: ("auto","auto")
            first.responses=[{"task_id":"fixture_task"},TimeoutError("controlled interruption")]
            with self.assertRaisesRegex(RuntimeError,"без новой оплаты"):
                first._gpt25_generate_image("A cup","piapi/gpt-image-2.5")
            restarted=OfflineWorker(temp,"piapi");restarted._get_generation_profile=lambda _: ("auto","auto");restarted.responses=[wrapped()]
            self.assertEqual(restarted._gpt25_generate_image("A cup","piapi/gpt-image-2.5"),URL)
            self.assertEqual([c[0] for c in restarted.calls],["GET"])
if __name__ == "__main__": unittest.main()
