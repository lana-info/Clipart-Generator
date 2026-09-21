"""Create a persistent, self-contained visual report from verified local goldens."""
import argparse
from dataclasses import replace
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chroma_benchmark import load_manifest, load_golden_fixture, score_result, _build_contact_sheet
from chroma_key import remove_chroma_key_automatic
from chroma_provenance import PROFILE_VERSION


def build_report(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    manifest = load_manifest(ROOT / 'benchmarks/chroma/manifest.json')
    sections, metrics = [], []
    for case in manifest['cases']:
        fixture = load_golden_fixture(manifest, case)
        stages = {}
        after = remove_chroma_key_automatic(
            fixture.input_image, fixture.key_color, subject_profile='opaque_clipart',
            stage_observer=lambda name, image: stages.update({name: image}),
        )
        before = stages['opaque_boundary']
        rows = [(replace(fixture, case_id=fixture.case_id + ' v4'), before),
                (replace(fixture, case_id=fixture.case_id + ' v5'), after)]
        sheet_name = fixture.case_id + '-comparison.png'
        _build_contact_sheet(rows).save(destination / sheet_name)
        before.save(destination / (fixture.case_id + '-v4.png'))
        after.save(destination / (fixture.case_id + '-v5.png'))
        fixture.input_image.save(destination / (fixture.case_id + '-source.png'))
        truth = fixture.expected_foreground.convert('RGBA')
        truth.putalpha(fixture.expected_mask)
        truth.save(destination / (fixture.case_id + '-truth.png'))
        scores = {name: score_result(image, fixture.expected_mask, fixture.expected_foreground)
                  for name, image in [('v4', before), ('v5', after)]}
        metrics.append({'case': fixture.case_id, **scores})
        sections.append(
            f'<section><h2>{html.escape(fixture.case_id)}</h2>'
            '<p>Верхний ряд: v4. Нижний ряд: v5. Столбцы: исходник, эталон, '
            'шахматная, чёрная, белая и розовая подложки.</p>'
            f'<a href="{sheet_name}"><img src="{sheet_name}" alt="Сравнение краёв"></a>'
            f'<p>Ошибка alpha: {scores["v4"]["alpha_mae"]:.6f} → '
            f'{scores["v5"]["alpha_mae"]:.6f} (меньше лучше).</p>'
            f'<p><a href="{fixture.case_id}-source.png">Исходник</a> · '
            f'<a href="{fixture.case_id}-truth.png">Эталон</a> · '
            f'<a href="{fixture.case_id}-v4.png">PNG v4</a> · '
            f'<a href="{fixture.case_id}-v5.png">PNG v5</a></p></section>'
        )
    (destination / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vibix: проверка края</title><style>
body{font:16px/1.5 system-ui;margin:24px auto;padding:0 20px;max-width:1500px;color:#202124;background:#fff}
img{display:block;width:100%;height:auto}section{border-top:1px solid #ccc;padding:20px 0}
a{color:#006e70}h1{font-size:28px}h2{font-size:20px}
</style><h1>Vibix: сравнение качества края</h1>
<p>Воспроизводимые синтетические PNG с известным эталоном. Это не реальные платные генерации
и не новое сравнение с Clipbrook. Частично прозрачный материал показан для диагностики,
но не входит в требования к клипартам.</p>
<p>Картинки открываются в исходном размере по нажатию. <a href="metrics.json">Все измерения</a>.</p>
'''
    page += f'<p>Текущий профиль: {PROFILE_VERSION}.</p>' + ''.join(sections) + '</html>'
    (destination / 'index.html').write_text(page, encoding='utf-8')
    return destination / 'index.html'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    print(build_report(parser.parse_args().output_dir))
