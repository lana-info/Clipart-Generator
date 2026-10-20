from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from tests.test_auto_clipart_workflow import app, workspace  # noqa: F401  (fixtures)


def _prepare(controller, count=50):
    brief = controller.brief
    brief.total.setValue(count)
    from studio_clipart_objects import new_object
    editor = brief.object_editor
    editor.items = [dict(new_object("hero", index), name=f"Гусёнок-именинник номер {index}") for index in range(1, count + 1)]
    editor.selected = 0
    editor.refresh()
    return brief


def test_ideas_step_fits_one_page_without_scrolling(workspace):
    _view, controller, _gate, _worker = workspace
    brief = _prepare(controller)
    brief.pages.setCurrentIndex(4)
    brief.planning.status.setText(brief.planning.automatic_ready_text(50))
    brief.setParent(None)
    brief.resize(940, 430)          # what is left under the Studio header and the step bar at 980x700
    brief.show()
    QApplication.processEvents()
    page = brief.pages.currentWidget()
    shot = os.environ.get("IDEAS_STEP_SHOT")
    if shot:
        brief.grab().save(shot)
    assert page.verticalScrollBar().maximum() == 0, "the ideas step must not need scrolling"
    shot = os.environ.get("IDEAS_STEP_SHOT")
    if shot:
        brief.grab().save(shot)
    brief.close()


def test_ideas_step_has_few_clear_buttons(workspace):
    _view, controller, _gate, _worker = workspace
    brief = _prepare(controller, 3)
    brief.pages.setCurrentIndex(4)
    brief.setParent(None)
    brief.resize(940, 430)
    brief.show()
    QApplication.processEvents()
    planning, editor = brief.planning, brief.object_editor
    assert editor.isVisible()                                    # no "show ideas" toggle any more
    assert planning.all_button.isVisible() and planning.one_button.isVisible()
    assert planning.one_button.accessibleName() == "Заменить эту идею" and planning.one_button.text() == ""
    assert planning.all_button.text() in ("Подготовить набор", "Подобрать заново")
    assert [b.accessibleName() for b in editor.buttons] == ["Добавить", "Дублировать", "Удалить"]
    assert all(b.text() == "" and not b.icon().isNull() and b.toolTip() for b in editor.buttons)
    # add / duplicate / delete / replace sit together in ONE row under the list
    row = [editor.tool_row.itemAt(i).widget() for i in range(editor.tool_row.count()) if editor.tool_row.itemAt(i).widget()]
    assert row == [*editor.buttons, planning.one_button]
    assert len({w.mapTo(brief, w.rect().topLeft()).y() for w in row}) == 1
    assert not any(b.text() in ("Посмотреть и изменить идеи", "Скрыть идеи")
                   for b in brief.findChildren(type(planning.all_button)))
    brief.close()


def test_model_tab_still_reachable_and_ideas_return(workspace):
    _view, controller, _gate, _worker = workspace
    brief = _prepare(controller, 3)
    brief.pages.setCurrentIndex(4)
    brief.setParent(None)
    brief.resize(940, 430)
    brief.show()
    QApplication.processEvents()
    planning = brief.planning
    planning.tabs.setCurrentIndex(1)
    QApplication.processEvents()
    assert planning.model_page.isVisible() and planning.model.isVisible()
    assert not brief.object_editor.isVisible()
    planning.tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert brief.object_editor.isVisible() and planning.all_button.isVisible()
    brief.close()
