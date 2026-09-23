"""Render actual approved news UI using synthetic text and isolated desktop data."""
from pathlib import Path
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='studio-news-preview-') as temp:
        os.environ['LOCALAPPDATA'] = temp
        from PyQt6.QtWidgets import QApplication
        from v3_mode_selection import V3ApplicationView
        app = QApplication.instance() or QApplication([])
        view = V3ApplicationView(draft_path=Path(temp) / 'draft.json')
        view.resize(1120, 780)
        view.show()
        item = dict(id='a'*32, title='Более чистые края клипарта',
            body='Подготовили улучшение удаления цветного фона. Подробности и доступные версии смотрите в обновлениях модулей.',
            published_at='2026-09-23T12:00:00+00:00')
        for state, rows, offline in [('populated', [item], False), ('empty', [], False), ('offline', [item], True)]:
            view.mode_selection.news_panel.set_news(rows, offline=offline)
            app.processEvents()
            assert view.grab().save(str(output / f'home-{state}-actual-1120x780.png'))
            assert len(view.mode_selection.mode_cards) == 3
        view.close()
        app.processEvents()


if __name__ == '__main__':
    main()
