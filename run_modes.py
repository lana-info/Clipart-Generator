"""Pure mapping between UI launch scenarios and worker modes."""

RUN_MODE_LABELS = {
    "generate_only": "Только генерация изображений",
    "process_only": "Только обработка файлов",
    "both": "Всё вместе",
}
RUN_MODE_WORKER_MODES = {
    "generate_only": "mode1_generate_only",
    "process_only": "mode2_process",
    "both": "mode_both",
}


def worker_mode_for(run_mode: str) -> str:
    return RUN_MODE_WORKER_MODES.get(run_mode, "mode1_generate_only")


def label_for(run_mode: str) -> str:
    return RUN_MODE_LABELS.get(run_mode, run_mode)
