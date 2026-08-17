import unittest

from run_lifecycle import RunLifecycle, RunLifecycleState


class RunLifecycleTests(unittest.TestCase):
    def test_cancel_then_finish_is_cancelled_and_not_success(self):
        lifecycle = RunLifecycle()
        lifecycle.start()
        lifecycle.request_cancel()
        event = lifecycle.finish()
        self.assertEqual(event.name, "cancelled")
        self.assertEqual(lifecycle.state, RunLifecycleState.CANCELLED)
        self.assertEqual(lifecycle.finish().name, "terminal_ignored")

    def test_failure_is_terminal_and_start_is_idempotent(self):
        lifecycle = RunLifecycle()
        self.assertEqual(lifecycle.start().name, "started")
        self.assertEqual(lifecycle.start().name, "start_ignored")
        self.assertEqual(lifecycle.finish(error_code="provider_error").name, "failed")
        self.assertEqual(lifecycle.finish(error_code="late").name, "terminal_ignored")


if __name__ == "__main__":
    unittest.main()
