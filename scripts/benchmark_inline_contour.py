"""Reproducible Linux GUI timing/RSS probe; run each case in a fresh process."""
import argparse
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import resource
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from studio_contour import changed_path_roi
from v3_transparency_preview import ClipartTransparencyEditorPage

parser = argparse.ArgumentParser()
parser.add_argument('--size', type=int, default=4100)
parser.add_argument('--detail', action='store_true')
args = parser.parse_args()
app = QApplication([])
with tempfile.TemporaryDirectory() as temporary:
    source = Path(temporary)/'fixture.png'
    size = args.size
    image = Image.new('RGBA',(size,size),(30,60,90,0))
    draw = ImageDraw.Draw(image)
    if args.detail:
        points=[]
        for i in range(1600):
            angle=i*math.tau/1600
            radius=size*(.37+.025*math.sin(angle*100))
            points.append((size/2+radius*math.cos(angle),size/2+radius*math.sin(angle)))
        draw.polygon(points,fill=(30,60,90,255))
    else:
        draw.ellipse((size*.1,size*.1,size*.9,size*.9),fill=(30,60,90,255))
    draw.ellipse((size*.4,size*.4,size*.6,size*.6),fill=(30,60,90,0))
    image.save(source); del image,draw
    page=ClipartTransparencyEditorPage(); page.resize(1120,780)
    page.set_files([source]); page.show(); app.processEvents(); page._set_tool('pen')
    canvas=page.canvas
    gaps=[]; last=[time.monotonic()]
    def tick():
        now=time.monotonic(); gaps.append(now-last[0]); last[0]=now
    timer=QTimer(); timer.timeout.connect(tick); timer.start(5)
    def measure(operation):
        gaps.clear(); last[0]=time.monotonic(); start=last[0]
        operation()
        while canvas.contour_busy and time.monotonic()-start<60:
            QTest.qWait(5)
        if canvas.contour_busy:
            raise RuntimeError('Timeout')
        tick()
        return {'seconds':round(time.monotonic()-start,3),'max_ui_tick_gap_ms':round(max(gaps)*1000,1)}
    extraction=measure(canvas.auto_contour)
    if not canvas.contour.paths:
        raise RuntimeError(page.contour_status.text())
    path=canvas.contour.paths[0]; nodes=list(path.nodes); node=nodes[0]
    nodes[0]=replace(node,point=(node.point[0]+10,node.point[1]+10))
    replacement=replace(path,nodes=tuple(nodes))
    canvas.contour.paths[0]=replacement
    roi=changed_path_roi(path,replacement)
    apply=measure(canvas.apply_contour)
    if canvas.contour.dirty:
        raise RuntimeError(page.contour_status.text())
    report={'size':size,'detail':args.detail,'nodes':sum(len(p.nodes) for p in canvas.contour.paths),
            'extract':extraction,'apply':apply,'roi_pixels':(roi[2]-roi[0])*(roi[3]-roi[1]),
            'peak_process_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
            'logical_cpus':os.cpu_count()}
    print(json.dumps(report))
    page.close()
