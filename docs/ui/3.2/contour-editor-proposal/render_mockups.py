"""Render non-production Vibix contour-editor approval mockups.

Run from the repository root:
  /tmp/vibix32-venv/bin/python docs/ui/3.2/contour-editor-proposal/render_mockups.py

Uses the tracked Chroma fixture only; it never reads user workspaces or calls
network services.  The outputs are fixed 1120x780 approval artifacts.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
FIXTURE = ROOT / "assets/mode-clipart.png"
W, H = 1120, 780

BG, PANEL, PANEL_2 = "#101827", "#1f2937", "#263345"
LINE, INK, MUTED = "#334155", "#f8fafc", "#b8c4d3"
ACCENT, CYAN, DANGER = "#2dd4bf", "#67e8f9", "#ff7588"
SUCCESS, WARNING = "#69d4a4", "#e7b55a"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def f(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)

def rr(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)

def text(d, xy, value, size=13, color=INK, bold=False, anchor=None):
    d.text(xy, value, font=f(size, bold), fill=color, anchor=anchor)

def checker(canvas, box, cell=12):
    d = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    for y in range(y0, y1, cell):
        for x in range(x0, x1, cell):
            odd = ((x - x0) // cell + (y - y0) // cell) % 2
            d.rectangle((x, y, min(x + cell, x1), min(y + cell, y1)), fill="#253143" if odd else "#1c2736")

def pill(d, box, label, fill, color=INK, dot=None):
    rr(d, box, 11, fill)
    x = box[0] + 10
    if dot:
        d.ellipse((x, box[1] + 8, x + 7, box[1] + 15), fill=dot)
        x += 12
    text(d, (x, box[1] + 5), label, 11, color, bold=True)

def button(d, box, label, primary=False, enabled=True):
    fill = ACCENT if primary and enabled else ("#263247" if enabled else "#1b2431")
    color = "#ffffff" if primary and enabled else (INK if enabled else "#708096")
    rr(d, box, 8, fill, None if primary else LINE)
    text(d, ((box[0]+box[2])//2, (box[1]+box[3])//2-1), label, 12, color, bold=primary, anchor="mm")

def icon(d, x, y, kind, active=False):
    col = "#ffffff" if active else MUTED
    if kind == "pointer":
        d.polygon([(x, y), (x+3, y+17), (x+7, y+12), (x+12, y+20), (x+15, y+18), (x+10, y+10), (x+17, y+9)], fill=col)
    elif kind == "brush":
        d.line((x+2,y+17,x+13,y+4), fill=col, width=4)
        d.ellipse((x,y+15,x+6,y+21), fill=col)
    elif kind == "minus":
        d.ellipse((x,y+2,x+19,y+21), outline=col, width=2); d.line((x+5,y+11,x+14,y+11),fill=col,width=2)
    elif kind == "hand":
        d.rounded_rectangle((x+4,y+5,x+14,y+18),3,outline=col,width=2); d.line((x+5,y+6,x+3,y+1),fill=col,width=2)
    else:
        d.ellipse((x+3,y+3,x+17,y+17),outline=col,width=2)

def header(d, title, subtitle):
    d.rectangle((0,0,W,H), fill=BG)
    d.rectangle((0,0,W,62), fill="#111b2a")
    text(d, (28,21), "VIBIX", 16, "#ffffff", True)
    text(d, (91,23), "Images", 16, MUTED)
    d.line((180,17,180,44), fill=LINE, width=1)
    text(d, (202,18), title, 17, INK, True)
    text(d, (202,39), subtitle, 11, MUTED)
    pill(d, (918,19,1012,42), "Локально", "#28344a", dot=SUCCESS)
    button(d, (1025,14,1092,47), "Закрыть")

def draw_image(canvas, area, mode="checker", selected=False, faded=False):
    x0,y0,x1,y1=area
    if mode == "checker": checker(canvas, area)
    elif mode == "black": ImageDraw.Draw(canvas).rectangle(area, fill="#090d13")
    else: ImageDraw.Draw(canvas).rectangle(area, fill="#eff3f7")
    # Tracked project illustration. It remains visibly labelled as a mockup
    # asset: the editor proposal makes no claim about a final mask's quality.
    im=Image.open(FIXTURE).convert("RGBA")
    im.thumbnail((650, 325), Image.Resampling.LANCZOS)
    if faded: im.putalpha(im.getchannel("A").point(lambda a:int(a*.36)))
    px=(x0+x1-im.width)//2; py=(y0+y1-im.height)//2
    canvas.alpha_composite(im,(px,py))
    d=ImageDraw.Draw(canvas)
    # The default view keeps the generated outline visible but quiet; selecting
    # the ROI reveals the editable anchors and handles.
    # A simple local ROI around the cup (left object), illustrative only.
    roi=(px+14, py+53, px+206, py+270)
    d.rounded_rectangle(roi, radius=8, outline="#8ccfd0", width=1)
    points=[(px+39,py+91),(px+91,py+70),(px+154,py+82),(px+190,py+137),(px+170,py+236),(px+76,py+253),(px+23,py+201)]
    smooth=[]
    for p,q in zip(points,points[1:]+points[:1]):
        smooth += [p,((p[0]+q[0])//2,(p[1]+q[1])//2)]
    d.line(smooth+[points[0]], fill=CYAN if selected else "#55b7c5", width=2, joint="curve")
    if selected:
        # The seven visible anchors and three handles make direct adjustment clear.
        # Handles prove local, direct adjustment, without suggesting freeform raster edits.
        for i,p in enumerate(points):
            if i in (0,2,4):
                h=(p[0]+(22 if i!=2 else -20),p[1]-18)
                d.line((p,h),fill="#88a7c8",width=1)
                d.ellipse((h[0]-3,h[1]-3,h[0]+3,h[1]+3),fill="#122033",outline="#88a7c8")
            d.ellipse((p[0]-5,p[1]-5,p[0]+5,p[1]+5), fill="#ffffff", outline=CYAN, width=2)
        pill(d,(x0+16,y0+16,x0+226,y0+40),"ROI · 7 точек · 3 рукоятки","#172c3a",dot=CYAN)
    else:
        pill(d,(x0+16,y0+16,x0+296,y0+40),"Иллюстрация для макета · не проверка качества","#283543",dot=WARNING)

def toolbar(d, active="pointer"):
    d.rectangle((24,91,78,510), fill=PANEL, outline=LINE)
    tools=[("pointer","Выбрать"),("brush","Восстановить"),("minus","Убрать"),("hand","Рука")]
    for i,(k,label) in enumerate(tools):
        y=106+i*54
        a=k==active
        if a: rr(d,(31,y,71,y+40),8,ACCENT)
        icon(d,48,y+9,k,a)
    d.line((33,345,69,345),fill=LINE)
    text(d,(51,365),"Ctrl+Z",10,MUTED,anchor="ma")
    text(d,(51,397),"Ctrl+Shift+Z",8,MUTED,anchor="ma")

def right_panel(d, selected=True, missing=False, error=False):
    x=842
    d.rectangle((x,82,1100,710), fill=PANEL)
    text(d,(866,106),"Контур и альфа",17,INK,True)
    text(d,(866,132),"Правка только в выделенной области",11,MUTED)
    d.line((866,153,1076,153),fill=LINE)
    text(d,(866,174),"Инструмент",12,MUTED,True)
    button(d,(866,191,970,225),"Автоконтур",True)
    button(d,(978,191,1076,225),"Сбросить",False,enabled=selected)
    text(d,(866,249),"Края",12,MUTED,True)
    rr(d,(866,266,1076,306),8,"#141c28",LINE)
    text(d,(874,279),"Сглаж.",12,INK)
    for i,v in enumerate(("0 px","1 px","2 px")):
        xx=940+i*45
        rr(d,(xx,272,xx+37,300),6,ACCENT if i==0 else "#202c3b",None if i==0 else LINE)
        text(d,(xx+18,286),v,10,"#fff" if i==0 else MUTED,True,anchor="mm")
    text(d,(866,327),"Кисть",12,MUTED,True)
    rr(d,(866,344,1076,384),8,"#141c28",LINE)
    text(d,(879,357),"Размер",12,INK)
    d.line((944,364,1033,364),fill="#657990",width=3); d.ellipse((983,357,997,371),fill="#fff")
    text(d,(1044,357),"24 px",11,MUTED)
    text(d,(866,408),"Просмотр",12,MUTED,True)
    views=(("▦", "Сетка", 866, 934), ("●", "Чёрный", 938, 1003), ("■", "Белый", 1007, 1076))
    for i,(mark,lab,x0,x1) in enumerate(views):
        rr(d,(x0,427,x1,454),6,"#28415a" if i==0 else "#1b2533", None if i==0 else LINE)
        text(d,(x0+8,433),mark,11,CYAN if i==0 else MUTED)
        text(d,(x0+23,434),lab,9,INK if i==0 else MUTED, bold=i==0)
    d.line((866,480,1076,480),fill=LINE)
    pill(d,(866,498,1076,523),"Цвета не изменены","#20334a",dot=SUCCESS)
    text(d,(866,544),"История",12,MUTED,True)
    button(d,(866,561,966,595),"↶  Отменить",False,enabled=True)
    button(d,(976,561,1076,595),"↷  Повторить",False,enabled=False)

def footer(d, enabled=True):
    d.rectangle((0,722,W,780),fill="#141c28")
    text(d,(26,741),"Рабочая область: 512 × 512 px",11,MUTED)
    text(d,(26,759),"Маска изменяется локально. Исходное изображение остаётся нетронутым.",11,"#74849a")
    button(d,(828,735,930,768),"Отмена")
    button(d,(942,735,1092,768),"Применить локально",True,enabled)

def base(name, mode="checker", selected=True, active="pointer", info="Готово к точной правке"):
    c=Image.new("RGBA",(W,H),BG); d=ImageDraw.Draw(c)
    header(d,"Редактор контура",info)
    toolbar(d,active)
    rr(d,(96,82,822,710),10,"#101722",LINE)
    draw_image(c,(112,98,806,694),mode,selected)
    # ruler / coordinate help
    pill(d,(130,653,300,678),"100%   ·   колесо: масштаб", "#1b2839")
    right_panel(d,selected)
    footer(d,True)
    c.convert("RGB").save(OUT/name, quality=95)

def error_state():
    c=Image.new("RGBA",(W,H),BG);d=ImageDraw.Draw(c)
    header(d,"Редактор контура","Контур нуждается в уточнении")
    toolbar(d)
    rr(d,(96,82,822,710),10,"#101722",LINE); checker(c,(112,98,806,694))
    rr(d,(243,303,675,454),12,"#1d2938",LINE,1)
    text(d,(459,337),"Автоконтур не уверен в этой области",18,INK,True,anchor="mm")
    text(d,(459,370),"Выберите область с объектом, чтобы уточнить контур.",12,MUTED,anchor="mm")
    text(d,(459,392),"Изображение и текущая маска не изменены.",12,MUTED,anchor="mm")
    button(d,(300,414,502,448),"Выбрать другую область",True)
    button(d,(514,414,618,448),"Вернуться")
    right_panel(d,False,error=True); footer(d,False)
    c.convert("RGB").save(OUT/"error-no-contour-1120x780.png",quality=95)

def missing_state():
    c=Image.new("RGBA",(W,H),BG);d=ImageDraw.Draw(c)
    header(d,"Редактор контура","Файл результата больше недоступен")
    toolbar(d)
    rr(d,(96,82,822,710),10,"#101722",LINE)
    # empty canvas, deliberately no fiction asset
    text(d,(459,333),"Изображение не найдено",20,INK,True,anchor="mm")
    text(d,(459,366),"Результат был перемещён или удалён вне Vibix.",12,MUTED,anchor="mm")
    button(d,(354,410,564,444),"Открыть другой PNG",True)
    pill(d,(312,470,680,496),"Работа с копией. Исходник не меняется","#20334a",dot=WARNING)
    right_panel(d,False,missing=True); footer(d,False)
    c.convert("RGB").save(OUT/"missing-image-1120x780.png",quality=95)

if __name__ == "__main__":
    base("default-populated-1120x780.png", selected=False, info="Автоматический контур готов к проверке")
    base("selected-roi-nodes-1120x780.png", selected=True, active="pointer", info="Выделена локальная область · 7 точек")
    error_state()
    missing_state()
    print("Rendered 4 non-production approval mockups in", OUT)
