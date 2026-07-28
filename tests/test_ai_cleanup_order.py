import inspect

import main


def test_worker_cleanup_order_matches_run_plan():
    source = inspect.getsource(main.WorkerThread._run_processing_pipeline)
    assert source.index("_metadata_cleanup_requested") < source.index("_visible_mark_cleanup_pipeline_step")
    assert source.index("_visible_mark_cleanup_pipeline_step") < source.index("clean_invisible_watermark")
