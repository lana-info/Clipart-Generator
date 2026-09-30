"""Review-only catalog mockups. No API calls or application writes."""
from pathlib import Path
import os, sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from PyQt6.QtWidgets import QApplication, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QProgressBar
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from v3_mode_selection import ModeSelectionScreen
OUT = Path(__file__).parent
app = QApplication.instance() or QApplication([])
if not (OUT/'current.png').exists():
    current = ModeSelectionScreen(); current.resize(1120,780); current.show(); app.processEvents()
    current.grab().save(str(OUT/'current.png')); current.close()
modules = [
 ('Генерация изображений','Изображения и серии по вашим промптам','studio-generation-cover.png'),
 ('Автоматический клипарт','Идеи, наборы клипартов и экспорт коллекций','mode-clipart.png'),
 ('Обработка изображений','Фон, прозрачность и качество изображений','mode-processing.png'),
 ('Pinterest','Пины по промптам, без публикации','mode-pinterest.png'),
 ('Конструктор промптов','7 вариантов для изображений и коротких Reels','studio-prompt-composer-cover.png'),
]
styles='''QWidget{background:#101a28;color:#eff5fa;font-family:Arial;font-size:14px} QFrame#card,QFrame#account{background:#1c2b3b;border:1px solid #3c5365;border-radius:8px} QLabel{background:transparent;border:0} QPushButton{background:#273f50;border:1px solid #506a7b;border-radius:5px;padding:9px 15px;color:#eff5fa} QPushButton:disabled{background:#25313d;color:#9aaaba;border-color:#3a4a57} QPushButton#primary{background:#087e80;border:0} QProgressBar{background:#152331;border:1px solid #506a7b;border-radius:4px;text-align:center} QProgressBar::chunk{background:#18a4a5}'''
for state in ['empty','mixed','downloading','offline','error','not-published']:
    w=QWidget();w.setStyleSheet(styles);w.resize(1120,780)
    layout=QVBoxLayout(w);layout.setContentsMargins(22,18,22,18);layout.setSpacing(12)
    top=QHBoxLayout();brand=QLabel('VIBIX Studio');brand.setStyleSheet('font-size:24px;font-weight:600;color:#2ad1cf');top.addWidget(brand);top.addStretch()
    for text in ['Лицензия','Обновления модулей','Настройки API','Диагностика']:top.addWidget(QPushButton(text))
    layout.addLayout(top)
    heading=QHBoxLayout();title=QLabel('Модули');title.setStyleSheet('font-size:24px;font-weight:600');heading.addWidget(title);heading.addStretch();layout.addLayout(heading)
    layout.addWidget(QLabel('Устанавливайте нужные инструменты. Ваши проекты и настройки сохраняются в Studio.'))
    if state=='offline':
        layout.addWidget(QLabel('Нет связи с сервером. Показан сохранённый доступ; скачивание временно недоступно.'))
    grid=QGridLayout();grid.setSpacing(12)
    for i,(name,description,picture) in enumerate(modules):
        card=QFrame();card.setObjectName('card');cl=QVBoxLayout(card);cl.setContentsMargins(12,10,12,12);cl.setSpacing(7)
        art=QLabel();art.setFixedHeight(112);art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if picture:art.setPixmap(QPixmap(str(ROOT/'assets'/picture)).scaled(320,112,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        else:art.setText('EN  ·  RU  /  7 вариантов');art.setStyleSheet('color:#2ad1cf;font-size:21px')
        cl.addWidget(art)
        title=QLabel(name);title.setWordWrap(True);title.setStyleSheet('font-size:17px;font-weight:600');cl.addWidget(title)
        desc=QLabel(description);desc.setWordWrap(True);desc.setStyleSheet('color:#bdcbd7;font-size:13px');cl.addWidget(desc)
        action='Скачать';message='Доступен по вашей лицензии';enabled=True
        if i==4:action='Нет доступа';message='Модуль не входит в вашу лицензию';enabled=False
        if state!='empty' and i in (0,2):action='Открыть';message='Установлен'
        if state=='mixed' and i==2:action='Открыть';message='Установлен · доступно обновление'
        if state=='offline' and i not in (0,2):action='Повторить проверку';message='Для скачивания нужен интернет'
        if state=='not-published' and i==4:action='Ожидается выпуск';message='Доступ есть · пакет ещё не опубликован';enabled=False
        if state=='downloading' and i==1:
            message='Скачивание · 46%';action='Отменить';bar=QProgressBar();bar.setValue(46);bar.setFixedHeight(20);cl.addWidget(bar)
        if state=='error' and i==1:message='Загрузка прервана. Попробуйте ещё раз.';action='Повторить скачивание'
        status=QLabel(message);status.setWordWrap(True);status.setStyleSheet('color:#8ed4cd;font-size:12px');cl.addWidget(status);cl.addStretch()
        button=QPushButton(action);button.setEnabled(enabled);button.setObjectName('primary' if enabled else '');cl.addWidget(button)
        grid.addWidget(card,i//3,i%3)
    layout.addLayout(grid,1)
    bottom=QHBoxLayout();bottom.addWidget(QLabel('Продолжить работу · ваши сохранённые проекты'),1);bottom.addWidget(QPushButton('Все проекты'));layout.addLayout(bottom)
    news=QLabel('Новости Studio  ·  Здесь будут появляться новости и обновления инструментов.');news.setStyleSheet('color:#a9bac8;font-size:12px');layout.addWidget(news)
    w.show();app.processEvents();assert w.size().width()==1120 and w.size().height()==780
    assert w.grab().save(str(OUT/(state+'.png')));w.close()
print('Current catalog and 6 proposal states captured at 1120x780')
