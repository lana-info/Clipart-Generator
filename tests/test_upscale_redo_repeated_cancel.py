"""«Апскейл заново» после остановки можно повторять сколько угодно раз (приёмка владельца 2026-10-30).

Существующие тесты проверяют один цикл «повтор → стоп → снова доступно». Владелец нажимает стоп
несколько раз подряд на 30 картинках; второй и третий цикл не должны терять вход апскейла, счётчик
попыток обязан расти, а запрос — каждый раз брать сохранённые картинки, а не результат прошлого повтора.
"""
from pathlib import Path

import pytest
from PIL import Image

from v3_clipart_flow import ClipartRunRequest
from v3_project_state import ProjectMode
from v3_run_queue import RunItemStatus, RunQueueSession

COUNT = 30


def _png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), (200, 40, 40, 255)).save(path)
    return path


@pytest.fixture
def session(tmp_path):
    request = ClipartRunRequest(
        mode="mode1_generate_only", work_dir=str(tmp_path), settings={"output_dir": str(tmp_path / "output")},
        generated_prompts=[{"prompt": f"object {index}", "references": [], "object_id": f"o{index}"}
                           for index in range(COUNT)])
    queue = RunQueueSession(request, ProjectMode.CLIPART)
    for index, item in enumerate(queue.items):
        item.status = RunItemStatus.SUCCEEDED
        item.output_path = str(_png(tmp_path / "output" / f"object{index}_ready.png"))
        item.cutout_path = str(_png(Path(queue.transient_dir) / f"gen_upscale_input_{index:03d}.png"))
    queue.running = False
    return queue


def _stop_after_start(queue, indices):
    request = queue.prepare_upscale_redo(indices)
    assert request is not None
    queue.handle_cancelled_terminal()
    return request


def test_three_stopped_redo_cycles_keep_every_picture_redoable(session):
    everything = list(range(COUNT))
    inputs = [item.cutout_path for item in session.items]
    first_attempts = [item.attempts for item in session.items]
    for cycle in range(3):
        assert session.upscale_redoable_indices(everything) == everything, f"cycle {cycle}"
        request = _stop_after_start(session, everything)
        assert request.selected_files == [str(Path(path).resolve()) for path in inputs], f"cycle {cycle}"
        assert {item.status for item in session.items} == {RunItemStatus.CANCELLED}
        assert session.running is False
    assert [item.cutout_path for item in session.items] == inputs
    assert [item.attempts for item in session.items] == [count + 3 for count in first_attempts]


def test_a_stopped_redo_of_a_few_rows_leaves_the_others_untouched(session):
    chosen = [3, 4, 20]
    untouched = [index for index in range(COUNT) if index not in chosen]
    outputs = {index: session.items[index].output_path for index in untouched}
    _stop_after_start(session, chosen)
    _stop_after_start(session, chosen)
    for index in untouched:
        assert session.items[index].status is RunItemStatus.SUCCEEDED
        assert session.items[index].output_path == outputs[index]
    assert {session.items[index].status for index in chosen} == {RunItemStatus.CANCELLED}
    assert session.upscale_redoable_indices(range(COUNT)) == sorted(set(chosen) | set(untouched))


def test_a_vanished_input_is_refused_instead_of_crashing_the_next_cycle(session):
    """Антивирус или чистка унесли сохранённый вход между двумя повторами: честный отказ для этой строки."""
    _stop_after_start(session, [0, 1])
    Path(session.items[1].cutout_path).unlink()
    assert session.upscale_redoable_indices([0, 1]) == [0]
    request = session.prepare_upscale_redo([0, 1])
    assert request is not None and len(request.selected_files) == 1
    assert session.items[1].status is RunItemStatus.CANCELLED
