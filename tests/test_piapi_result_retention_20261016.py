from __future__ import annotations
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from tests.test_gpt25_async_worker import OfflineWorker


class ResultRetentionTests(unittest.TestCase):
    def test_retention_requires_a_valid_old_timestamp(self):
        from gpt25_provider import result_retention_elapsed
        now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(result_retention_elapsed('', now=now))
        self.assertFalse(result_retention_elapsed('not a date', now=now))
        self.assertFalse(result_retention_elapsed((now - timedelta(minutes=59)).isoformat(), now=now))
        self.assertTrue(result_retention_elapsed((now - timedelta(minutes=60)).isoformat(), now=now))
        self.assertTrue(result_retention_elapsed('2026-10-16T10:00:00', now=now))

    def make_worker(self, temp):
        worker = OfflineWorker(temp, 'piapi')

        def gone(url, method='GET', payload=None, headers=None, timeout=None):
            worker.calls.append((method, url, payload, headers))
            if method == 'POST':
                worker._diagnostic_context.gpt25_post_started = True
                return {'task_id': 'piapi_task_ret'}
            worker._diagnostic_context.last_http_status = 400
            raise RuntimeError('HTTP status=400')

        worker._request_json = gone
        return worker

    def test_http400_inside_retention_window_stays_recoverable(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = self.make_worker(temp)
            with self.assertRaisesRegex(RuntimeError, 'без новой оплаты'):
                worker._gpt25_generate_image('A cup', 'piapi/gpt-image-2.5-flare')
            self.assertEqual(worker.gpt25_task_journals['piapi'].pending()[0].status, 'poll_deferred')

    def test_http400_after_retention_window_requires_new_paid_consent(self):
        with tempfile.TemporaryDirectory() as temp:
            first = self.make_worker(temp)
            with self.assertRaises(RuntimeError):
                first._gpt25_generate_image('A cup', 'piapi/gpt-image-2.5-flare')
            journal = first.gpt25_task_journals['piapi']
            old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec='seconds')
            journal._write({key: replace(value, created_at=old) for key, value in journal._read().items()})
            second = self.make_worker(temp)
            with self.assertRaisesRegex(RuntimeError, 'больше недоступен'):
                second._gpt25_generate_image('A cup', 'piapi/gpt-image-2.5-flare')
            self.assertEqual(second.gpt25_task_journals['piapi'].pending()[0].status, 'expired')
            with self.assertRaisesRegex(RuntimeError, 'требует подтверждения'):
                self.make_worker(temp)._gpt25_generate_image('A cup', 'piapi/gpt-image-2.5-flare')
            self.assertEqual([call[0] for call in first.calls], ['POST', 'GET'])
            self.assertEqual([call[0] for call in second.calls], ['GET'])
