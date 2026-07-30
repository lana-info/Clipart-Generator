from run_modes import label_for, worker_mode_for


def test_run_mode_mapping():
    assert worker_mode_for("process_only") == "mode2_process"
    assert worker_mode_for("both") == "mode_both"
    assert label_for("generate_only") == "Только генерация изображений"
