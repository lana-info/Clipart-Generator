"""Mockup: add/delete pen points and move/delete a lasso group (for owner approval)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
SRC = HERE.parent / "06-pen-curve-points" / "6-pen-mixed-closed-dark.png"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TEAL, ORANGE, RED, TEXT, PANEL = (45, 212, 191), (245, 180, 90), (240, 110, 110), (228, 237, 246), (27, 38, 54)
font = lambda size, bold=False: ImageFont.truetype(BOLD if bold else FONT, size)

base = Image.open(SRC).convert("RGB")
w, h = base.size
right = base.crop((w // 2 + 3, 0, w, h))
# points of the closed contour in the crop (measured on the real screenshot)
pts = [(270, 183), (567, 183), (715, 440), (567, 694), (270, 694), (122, 440)]

def card(title, caption, hint, panel_text):
    img = right.copy()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, img.width, 38), fill=(14, 22, 36))
    d.text((12, 8), title, font=font(20, True), fill=TEAL)
    # replace the "Точки не выделены" line in the side panel with the new status/hint
    d.rectangle((838, 705, img.width - 22, 730), fill=PANEL)
    d.text((842, 709), panel_text, font=font(12), fill=TEXT)
    d.rectangle((0, h - 74, 812, h), fill=(14, 22, 36))
    d.text((12, h - 68), caption, font=font(16, True), fill=TEXT)
    d.text((12, h - 40), hint, font=font(14), fill=(166, 181, 200))
    return img, d

def cursor(d, x, y, sign, colour):
    d.line((x, y, x + 14, y + 14), fill=TEXT, width=2)
    d.ellipse((x + 14, y + 6, x + 34, y + 26), fill=colour)
    d.text((x + 19, y + 3), sign, font=font(18, True), fill=(10, 16, 28))

cards = []
img, d = card("1. Добавить точку на линию", "Ctrl + щелчок ЛЕВОЙ по линии — угловая точка; Ctrl + щелчок ПРАВОЙ — точка кривой.",
              "При наведении с Ctrl на линию курсор «+» и подсвечена точка вставки. Форма линии не меняется.",
              "Ctrl+щелчок по линии — добавить точку")
x, y = 418, 166
d.ellipse((x - 7, y - 7, x + 7, y + 7), outline=ORANGE, width=3)
cursor(d, x + 4, y + 4, "+", TEAL); cards.append(img)

img, d = card("2. Удалить точку", "Ctrl + щелчок по точке или Delete — удалить точку (контур остаётся замкнутым, минимум 3 точки).",
              "При наведении с Ctrl на точку курсор «−», точка обведена красным. Ctrl+Z возвращает.",
              "Ctrl+щелчок по точке — удалить")
x, y = pts[1]
d.ellipse((x - 9, y - 9, x + 9, y + 9), outline=RED, width=3)
cursor(d, x + 6, y + 6, "−", RED); cards.append(img)

img, d = card("3. Группа точек: лассо → перетащить или Delete", "Лассо (или Shift+щелчок) выделяет несколько точек; тянете любую — двигаются все вместе.",
              "Стрелки двигают группу на 1 px (Shift — на 10 px). Delete удаляет все выделенные. Esc — снять выделение.",
              "Выделено точек: 3 · Delete — удалить")
group = pts[1:4]
for gx, gy in group:
    d.ellipse((gx - 7, gy - 7, gx + 7, gy + 7), fill=TEAL)
# ghost of the moved group (+40 px right)
ghost = [(gx + 40, gy) for gx, gy in group]
d.line([pts[0]] + ghost + [pts[4]], fill=ORANGE, width=2)
for gx, gy in ghost:
    d.ellipse((gx - 6, gy - 6, gx + 6, gy + 6), outline=ORANGE, width=2)
d.line((pts[2][0] + 8, 440, pts[2][0] + 34, 440), fill=ORANGE, width=3)
cards.append(img)

out = Image.new("RGB", (right.width, right.height * 3 + 20), (8, 12, 20))
for i, c in enumerate(cards):
    out.paste(c, (0, i * (right.height + 10)))
    c.save(HERE / f"0{i + 1}-proposed.png")
out.save(HERE / "all-proposed.png")
