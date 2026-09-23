"""Design proposal only; does not modify the application editor."""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor,QImage,QPainter,QPainterPath,QPen
from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QPushButton
from v3_components import build_v3_stylesheet,apply_v3_theme
from v3_transparency_preview import ClipartTransparencyEditorPage
OUT=Path(__file__).parent
app=QApplication([])

def row(layout, labels, selected=None, disabled=False):
    box=QHBoxLayout();box.setSpacing(4)
    for label in labels:
        button=QPushButton(label);button.setCheckable(selected is not None)
        button.setChecked(label==selected);button.setEnabled(not disabled)
        button.setMinimumHeight(30)
        if len(labels) == 6:button.setStyleSheet('font-size:11px;padding:4px 1px;')
        if label in ('Сохранить PNG','Применить контур') and not disabled:button.setStyleSheet('background:#26cbb9;color:#062c2a;font-weight:600;')
        box.addWidget(button)
    layout.addLayout(box)

def label(layout,text,muted=False):
    w=QLabel(text);w.setWordWrap(True)
    if muted:w.setStyleSheet('color:#93a9bf;font-size:12px;')
    layout.addWidget(w)

def fixture(path):
    image=QImage(512,512,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
    p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#2a9d95'))
    ring=QPainterPath();ring.addEllipse(QRectF(280,178,152,154));ring.addEllipse(QRectF(305,201,100,106));p.drawPath(ring)
    p.setBrush(QColor('#3eafa4'));p.drawRoundedRect(QRectF(112,167,222,205),38,38)
    p.setBrush(QColor('#98ded0'));p.drawEllipse(QRectF(112,135,222,66))
    p.setBrush(QColor('#694338'));p.drawEllipse(QRectF(127,148,192,38))
    p.setBrush(QColor('#ffe0a3'));p.drawEllipse(QRectF(187,231,70,70));p.end();image.save(str(path))

with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'cup-01.png';fixture(path)
    for state in ('before','brush','bezier','bezier-empty','missing'):
        win=QWidget();win.setWindowTitle('Макет · Vibix Studio');win.resize(1120,780)
        apply_v3_theme(win)
        win.setStyleSheet(build_v3_stylesheet()+'''QPushButton{padding:4px 6px;background:#263548;color:#e4edf6;border:1px solid #3b4b60;border-radius:6px;} QPushButton:disabled{color:#74869a;background:#202b39;} QPushButton:checked{border:1px solid #28cbbb;background:#164741;color:#ecfffc;} QPushButton:checked:disabled{color:#74869a;background:#202b39;border-color:#3b4b60;}''')
        outer=QVBoxLayout(win);outer.setContentsMargins(20,16,20,16)
        head=QHBoxLayout();head.addWidget(QLabel('VIBIX  Studio'));head.addStretch();head.addWidget(QLabel('Обработка  /  Прозрачность'));outer.addLayout(head)
        page=ClipartTransparencyEditorPage();outer.addWidget(page,1)
        page.set_files([] if state=='missing' else [path])
        if state!='before':
            previous=page.right_panel.layout().takeAt(1).widget();previous.setParent(None)
            panel=QFrame();panel.setProperty('v3Card',True);tools=QVBoxLayout(panel);tools.setContentsMargins(10,10,10,10);tools.setSpacing(8)
            empty=state=='missing';mode='Кисть' if state in ('brush','missing') else 'Безье'
            label(tools,'Масштаб');row(tools,['Fit','50%','100%','150%','200%','300%'],'Fit',empty)
            label(tools,'Инструмент');row(tools,['Кисть','Безье'],mode,empty)
            if mode=='Кисть':
                row(tools,['Добавить','Стереть'],'Стереть',empty)
                label(tools,'Диаметр кисти, px');row(tools,['8','16','32','64','128','256'],'64',empty)
                label(tools,'Жёсткость     ━━━━━━━●━━    70%',True)
                label(tools,'Размер кисти виден на холсте.',True)
            else:
                row(tools,['Вернуть область','Убрать область'],'Убрать область')
                row(tools,['Автоконтур'])
                label(tools,'Клик: точка. Потяните при добавлении, чтобы задать изгиб.',True)
                if state=='bezier':row(tools,['Применить контур','Убрать контур'])
                else:row(tools,['Применить контур'],disabled=True)
                label(tools,'Контур меняет маску после применения.',True)
            label(tools,'Фон проверки');row(tools,['Сетка','Белый','Чёрный'],'Сетка',empty)
            swatches=QHBoxLayout()
            for color in ('#ff1493','#00a651','#55c7f7'):
                b=QPushButton();b.setFixedSize(26,24);b.setStyleSheet(f'background:{color};');b.setEnabled(not empty);swatches.addWidget(b)
            swatches.addStretch();tools.addLayout(swatches)
            row(tools,['↶','↷','Сброс'],disabled=empty)
            tools.addStretch();row(tools,['Сохранить PNG','К результатам'],disabled=empty)
            page.right_panel.layout().addWidget(panel,3)
            if state=='missing':
                page.title_label.setText('Проверка и корректировка прозрачности · нет изображения')
            if state=='brush':
                page.canvas.brush_radius=32;page.canvas._brush_scene_point=QPointF(121,257)
            if state=='bezier':
                scene=page.canvas.scene();pen=QPen(QColor('#24d8c5'),2);pen.setCosmetic(True)
                curve=QPainterPath(QPointF(112,180));curve.cubicTo(90,230,102,335,140,362);curve.cubicTo(180,382,260,382,302,361)
                scene.addPath(curve,pen)
                for x,y in ((112,180),(140,362),(302,361)):
                    scene.addEllipse(x-4,y-4,8,8,pen,QColor('#10202e'))
                scene.addLine(140,362,102,335,pen);scene.addLine(140,362,180,382,pen)
                for x,y in ((102,335),(180,382)):scene.addEllipse(x-3,y-3,6,6,pen,QColor('#24d8c5'))
        win.show();app.processEvents();page.canvas.set_zoom(None);app.processEvents()
        assert win.width()==1120 and win.height()==780
        win.grab().save(str(OUT/f'{state}-1120x780.png'));win.close();win.deleteLater();app.processEvents()
print(OUT)
