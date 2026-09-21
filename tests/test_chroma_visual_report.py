from html.parser import HTMLParser
import json
from scripts.chroma_visual_report import build_report


def test_visual_report_contains_real_local_assets_and_metrics(tmp_path):
    page = build_report(tmp_path / 'report')
    links = []
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            links.extend(value for key, value in attrs if key in {'href', 'src'})
    Links().feed(page.read_text(encoding='utf-8'))
    assert links
    assert all((page.parent / link).is_file() for link in links)
    metrics = json.loads((page.parent / 'metrics.json').read_text())
    assert len(metrics) == 6
    opening = next(item for item in metrics if item['case'] == 'openings-blue')
    assert opening['v5']['alpha_mae'] < opening['v4']['alpha_mae']
