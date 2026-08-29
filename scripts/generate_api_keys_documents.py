"""Generate polished PDF and DOCX exports of the API key guide.

The script uses only the Python standard library. PDF rendering is delegated to
an installed Chromium-compatible browser so Cyrillic text and hyperlinks stay
selectable. DOCX is written as a small standards-compliant OOXML package.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "API_KEYS_GUIDE.ru.md"
SCREENSHOT = ROOT / "website" / "vibix-download" / "assets" / "vibix-app-preview.png"
PDF_OUTPUT = ROOT / "output" / "pdf" / "Vibix_Images_API_Keys_Guide.ru.pdf"
DOCX_OUTPUT = ROOT / "output" / "doc" / "Vibix_Images_API_Keys_Guide.ru.docx"
TEMP_HTML = ROOT / "tmp" / "pdfs" / "Vibix_Images_API_Keys_Guide.ru.html"


@dataclass(frozen=True)
class Block:
    kind: str
    value: object


def parse_markdown(source: str) -> list[Block]:
    lines = source.splitlines()
    blocks: list[Block] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("# "):
            blocks.append(Block("title", stripped[2:].strip()))
            index += 1
            continue
        if stripped.startswith("## "):
            blocks.append(Block("heading", stripped[3:].strip()))
            index += 1
            continue
        if (
            stripped.startswith("|")
            and index + 1 < len(lines)
            and re.match(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$", lines[index + 1])
        ):
            rows: list[list[str]] = []
            rows.append([cell.strip() for cell in stripped.strip("|").split("|")])
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(
                    [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                )
                index += 1
            blocks.append(Block("table", rows))
            continue
        match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if match:
            start_number = int(match.group(1))
            items: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                item_match = re.match(r"^\d+\.\s+(.*)$", current)
                if not item_match:
                    break
                parts = [item_match.group(1)]
                index += 1
                while index < len(lines):
                    continuation = lines[index]
                    if not continuation.strip():
                        index += 1
                        break
                    if re.match(r"^\s*\d+\.\s+", continuation):
                        break
                    if continuation.strip().startswith("|"):
                        break
                    parts.append(continuation.strip())
                    index += 1
                items.append(" ".join(parts))
            blocks.append(Block("ordered", (start_number, items)))
            continue
        if stripped.startswith("- "):
            items = []
            while index < len(lines) and lines[index].strip().startswith("- "):
                parts = [lines[index].strip()[2:].strip()]
                index += 1
                while index < len(lines):
                    continuation = lines[index]
                    if not continuation.strip():
                        index += 1
                        break
                    if continuation.strip().startswith("- "):
                        break
                    parts.append(continuation.strip())
                    index += 1
                items.append(" ".join(parts))
            blocks.append(Block("unordered", items))
            continue

        paragraph = [stripped]
        index += 1
        while index < len(lines):
            following = lines[index].strip()
            if not following:
                index += 1
                break
            if following.startswith("#") or following.startswith("|"):
                break
            if re.match(r"^(?:\d+\.|-)\s+", following):
                break
            paragraph.append(following)
            index += 1
        blocks.append(Block("paragraph", " ".join(paragraph)))
    return blocks


INLINE_PATTERN = re.compile(
    r"\[([^\]]+)\]\((https?://[^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`"
)


def inline_html(text: str) -> str:
    result: list[str] = []
    offset = 0
    for match in INLINE_PATTERN.finditer(text):
        result.append(html.escape(text[offset : match.start()]))
        if match.group(1) is not None:
            label, url = match.group(1), match.group(2)
            result.append(
                f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
            )
        elif match.group(3) is not None:
            result.append(f"<strong>{html.escape(match.group(3))}</strong>")
        else:
            result.append(f"<code>{html.escape(match.group(4))}</code>")
        offset = match.end()
    result.append(html.escape(text[offset:]))
    return "".join(result)


def html_document(blocks: list[Block]) -> str:
    content: list[str] = []
    for block in blocks:
        if block.kind == "title":
            content.append(
                '<section class="cover"><div class="eyebrow">VIBIX IMAGES</div>'
                f"<h1>{inline_html(str(block.value))}</h1>"
                '<p class="lead">Регистрация, создание, ввод и безопасное использование '
                "ключей KIE.AI, fal.ai и PhotoRoom.</p>"
                '<div class="cover-meta">Руководство пользователя · 29 августа 2026 года</div>'
                "</section>"
            )
        elif block.kind == "heading":
            content.append(f"<h2>{inline_html(str(block.value))}</h2>")
            if block.value == "Куда ввести ключи в Vibix Images":
                content.append(
                    '<figure><img src="'
                    + SCREENSHOT.resolve().as_uri()
                    + '" alt="Экран выбора режима Vibix Images">'
                    '<figcaption>Экран выбора режима: кнопка «Настройки API» находится '
                    "в верхней панели.</figcaption></figure>"
                )
        elif block.kind == "paragraph":
            content.append(f"<p>{inline_html(str(block.value))}</p>")
        elif block.kind in {"ordered", "unordered"}:
            tag = "ol" if block.kind == "ordered" else "ul"
            if block.kind == "ordered":
                start_number, values = block.value
                start_attribute = f' start="{start_number}"' if start_number != 1 else ""
            else:
                values = block.value
                start_attribute = ""
            items = "".join(f"<li>{inline_html(item)}</li>" for item in values)
            content.append(f"<{tag}{start_attribute}>{items}</{tag}>")
        elif block.kind == "table":
            rows: list[list[str]] = block.value
            head = "".join(f"<th>{inline_html(cell)}</th>" for cell in rows[0])
            body = "".join(
                "<tr>" + "".join(f"<td>{inline_html(cell)}</td>" for cell in row) + "</tr>"
                for row in rows[1:]
            )
            content.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")

    return """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>API-ключи для Vibix Images</title>
<style>
@page {
  size: A4;
  margin: 17mm 16mm 24mm;
  @bottom-left { content: "Vibix Images · API-ключи"; color: #718184; font: 8pt Arial, sans-serif; }
  @bottom-right { content: "Страница " counter(page) " из " counter(pages); color: #718184; font: 8pt Arial, sans-serif; }
}
* { box-sizing: border-box; }
body { margin: 0; color: #172033; font: 10.5pt/1.48 Arial, "DejaVu Sans", sans-serif; }
a { color: #087f78; text-decoration: none; overflow-wrap: anywhere; }
h1 { margin: 16mm 0 7mm; max-width: 155mm; color: #fff; font-size: 30pt; line-height: 1.08; }
h2 { margin: 8mm 0 3mm; color: #0d4f57; font-size: 18pt; line-height: 1.2; break-after: avoid; }
p { margin: 0 0 3.2mm; break-inside: avoid; orphans: 3; widows: 3; }
ol, ul { margin: 0 0 4mm 6mm; padding-left: 5mm; }
li { margin: 0 0 2mm; padding-left: 1.2mm; break-inside: avoid; }
strong { color: #0d4f57; }
code { background: #eef5f4; border: 1px solid #d7e7e5; border-radius: 3px; padding: 0.2mm 1mm; font-size: 9.5pt; }
table { width: 100%; margin: 3mm 0 5mm; border-collapse: collapse; break-inside: avoid; }
th { background: #0d4f57; color: white; text-align: left; font-weight: 700; }
th, td { border: 0.3mm solid #c9d8d7; padding: 2.2mm 2.5mm; vertical-align: top; }
tbody tr:nth-child(even) { background: #f3f8f7; }
.cover { min-height: 273mm; margin: -17mm -16mm 0; padding: 34mm 22mm; color: #d8eeee;
  background: linear-gradient(145deg, #071426 0%, #0c2538 55%, #0b5b61 100%); break-after: page; }
.eyebrow { display: inline-block; color: #44d7cb; font-weight: 800; letter-spacing: 0.12em; }
.lead { max-width: 145mm; color: #d8eeee; font-size: 15pt; line-height: 1.45; }
.cover-meta { margin-top: 28mm; color: #9bc7c6; font-size: 10pt; }
figure { margin: 3mm 0 6mm; padding: 3mm; background: #0e1c2d; border-radius: 3mm; break-inside: avoid; }
figure img { display: block; width: 100%; height: auto; border-radius: 2mm; }
figcaption { margin-top: 2mm; color: #d8eeee; font-size: 9pt; }
</style></head><body>
""" + "\n".join(content) + "\n</body></html>"


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"

for prefix, namespace in (("w", W_NS), ("r", R_NS), ("wp", WP_NS), ("a", A_NS), ("pic", PIC_NS)):
    ET.register_namespace(prefix, namespace)


def q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


class WordBuilder:
    def __init__(self) -> None:
        self.document = ET.Element(q(W_NS, "document"))
        self.body = ET.SubElement(self.document, q(W_NS, "body"))
        self.relationships: list[tuple[str, str, str]] = []
        self.next_rel = 2

    def add_relationship(self, kind: str, target: str) -> str:
        rel_id = f"rId{self.next_rel}"
        self.next_rel += 1
        self.relationships.append((rel_id, kind, target))
        return rel_id

    @staticmethod
    def add_text_run(parent: ET.Element, text: str, *, bold: bool = False, code: bool = False) -> None:
        run = ET.SubElement(parent, q(W_NS, "r"))
        if bold or code:
            properties = ET.SubElement(run, q(W_NS, "rPr"))
            if bold:
                ET.SubElement(properties, q(W_NS, "b"))
            if code:
                fonts = ET.SubElement(properties, q(W_NS, "rFonts"))
                fonts.set(q(W_NS, "ascii"), "Consolas")
                fonts.set(q(W_NS, "hAnsi"), "Consolas")
                shade = ET.SubElement(properties, q(W_NS, "shd"))
                shade.set(q(W_NS, "fill"), "EEF5F4")
        node = ET.SubElement(run, q(W_NS, "t"))
        if text.startswith(" ") or text.endswith(" "):
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = text

    def add_inline(self, parent: ET.Element, text: str) -> None:
        offset = 0
        for match in INLINE_PATTERN.finditer(text):
            if match.start() > offset:
                self.add_text_run(parent, text[offset : match.start()])
            if match.group(1) is not None:
                rel_id = self.add_relationship(
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                    match.group(2),
                )
                hyperlink = ET.SubElement(parent, q(W_NS, "hyperlink"))
                hyperlink.set(q(R_NS, "id"), rel_id)
                run = ET.SubElement(hyperlink, q(W_NS, "r"))
                properties = ET.SubElement(run, q(W_NS, "rPr"))
                color = ET.SubElement(properties, q(W_NS, "color"))
                color.set(q(W_NS, "val"), "087F78")
                underline = ET.SubElement(properties, q(W_NS, "u"))
                underline.set(q(W_NS, "val"), "single")
                node = ET.SubElement(run, q(W_NS, "t"))
                node.text = match.group(1)
            elif match.group(3) is not None:
                self.add_text_run(parent, match.group(3), bold=True)
            else:
                self.add_text_run(parent, match.group(4), code=True)
            offset = match.end()
        if offset < len(text):
            self.add_text_run(parent, text[offset:])

    def paragraph(self, text: str, style: str | None = None) -> ET.Element:
        paragraph = ET.SubElement(self.body, q(W_NS, "p"))
        if style:
            properties = ET.SubElement(paragraph, q(W_NS, "pPr"))
            paragraph_style = ET.SubElement(properties, q(W_NS, "pStyle"))
            paragraph_style.set(q(W_NS, "val"), style)
        self.add_inline(paragraph, text)
        return paragraph

    def list_item(self, text: str, *, ordered: bool, number: int = 1) -> None:
        paragraph = ET.SubElement(self.body, q(W_NS, "p"))
        properties = ET.SubElement(paragraph, q(W_NS, "pPr"))
        indent = ET.SubElement(properties, q(W_NS, "ind"))
        indent.set(q(W_NS, "left"), "520")
        indent.set(q(W_NS, "hanging"), "360")
        self.add_text_run(paragraph, f"{number}. " if ordered else "• ", bold=True)
        self.add_inline(paragraph, text)

    def table(self, rows: list[list[str]]) -> None:
        table = ET.SubElement(self.body, q(W_NS, "tbl"))
        properties = ET.SubElement(table, q(W_NS, "tblPr"))
        style = ET.SubElement(properties, q(W_NS, "tblStyle"))
        style.set(q(W_NS, "val"), "TableGrid")
        width = ET.SubElement(properties, q(W_NS, "tblW"))
        width.set(q(W_NS, "w"), "0")
        width.set(q(W_NS, "type"), "auto")
        for row_index, row in enumerate(rows):
            row_node = ET.SubElement(table, q(W_NS, "tr"))
            for cell in row:
                cell_node = ET.SubElement(row_node, q(W_NS, "tc"))
                paragraph = ET.SubElement(cell_node, q(W_NS, "p"))
                self.add_inline(paragraph, cell)
                if row_index == 0:
                    for run in paragraph.findall(q(W_NS, "r")):
                        properties_node = run.find(q(W_NS, "rPr"))
                        if properties_node is None:
                            properties_node = ET.SubElement(run, q(W_NS, "rPr"))
                        ET.SubElement(properties_node, q(W_NS, "b"))

    def image(self, path: Path) -> None:
        rel_id = self.add_relationship(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
            "media/image1.png",
        )
        paragraph = ET.SubElement(self.body, q(W_NS, "p"))
        properties = ET.SubElement(paragraph, q(W_NS, "pPr"))
        center = ET.SubElement(properties, q(W_NS, "jc"))
        center.set(q(W_NS, "val"), "center")
        run = ET.SubElement(paragraph, q(W_NS, "r"))
        drawing = ET.SubElement(run, q(W_NS, "drawing"))
        inline = ET.SubElement(drawing, q(WP_NS, "inline"))
        extent = ET.SubElement(inline, q(WP_NS, "extent"))
        extent.set("cx", "5760720")
        extent.set("cy", "4014574")
        doc_props = ET.SubElement(inline, q(WP_NS, "docPr"))
        doc_props.set("id", "1")
        doc_props.set("name", "Экран Vibix Images")
        graphic = ET.SubElement(inline, q(A_NS, "graphic"))
        graphic_data = ET.SubElement(graphic, q(A_NS, "graphicData"))
        graphic_data.set("uri", "http://schemas.openxmlformats.org/drawingml/2006/picture")
        picture = ET.SubElement(graphic_data, q(PIC_NS, "pic"))
        non_visual = ET.SubElement(picture, q(PIC_NS, "nvPicPr"))
        non_visual_props = ET.SubElement(non_visual, q(PIC_NS, "cNvPr"))
        non_visual_props.set("id", "0")
        non_visual_props.set("name", path.name)
        ET.SubElement(non_visual, q(PIC_NS, "cNvPicPr"))
        fill = ET.SubElement(picture, q(PIC_NS, "blipFill"))
        blip = ET.SubElement(fill, q(A_NS, "blip"))
        blip.set(q(R_NS, "embed"), rel_id)
        stretch = ET.SubElement(fill, q(A_NS, "stretch"))
        ET.SubElement(stretch, q(A_NS, "fillRect"))
        shape = ET.SubElement(picture, q(PIC_NS, "spPr"))
        transform = ET.SubElement(shape, q(A_NS, "xfrm"))
        offset = ET.SubElement(transform, q(A_NS, "off"))
        offset.set("x", "0")
        offset.set("y", "0")
        ext = ET.SubElement(transform, q(A_NS, "ext"))
        ext.set("cx", "5760720")
        ext.set("cy", "4014574")
        geometry = ET.SubElement(shape, q(A_NS, "prstGeom"))
        geometry.set("prst", "rect")
        ET.SubElement(geometry, q(A_NS, "avLst"))

    def finish(self) -> bytes:
        section = ET.SubElement(self.body, q(W_NS, "sectPr"))
        page_size = ET.SubElement(section, q(W_NS, "pgSz"))
        page_size.set(q(W_NS, "w"), "11906")
        page_size.set(q(W_NS, "h"), "16838")
        margins = ET.SubElement(section, q(W_NS, "pgMar"))
        for name, value in (("top", "1134"), ("right", "1134"), ("bottom", "1134"), ("left", "1134")):
            margins.set(q(W_NS, name), value)
        return ET.tostring(self.document, encoding="utf-8", xml_declaration=True)


def xml_bytes(text: str) -> bytes:
    return text.strip().encode("utf-8")


def build_docx(blocks: list[Block], destination: Path) -> None:
    builder = WordBuilder()
    for block in blocks:
        if block.kind == "title":
            builder.paragraph(str(block.value), "Title")
            builder.paragraph(
                "Регистрация, создание, ввод и безопасное использование ключей "
                "KIE.AI, fal.ai и PhotoRoom.",
                "Subtitle",
            )
            builder.paragraph("Руководство пользователя · 29 августа 2026 года")
        elif block.kind == "heading":
            builder.paragraph(str(block.value), "Heading1")
            if block.value == "Куда ввести ключи в Vibix Images":
                builder.image(SCREENSHOT)
                builder.paragraph(
                    "Экран выбора режима: кнопка «Настройки API» находится в верхней панели.",
                    "Caption",
                )
        elif block.kind == "paragraph":
            builder.paragraph(str(block.value))
        elif block.kind in {"ordered", "unordered"}:
            if block.kind == "ordered":
                start_number, values = block.value
            else:
                start_number, values = 1, block.value
            for offset, item in enumerate(values):
                builder.list_item(
                    item,
                    ordered=block.kind == "ordered",
                    number=start_number + offset,
                )
        elif block.kind == "table":
            builder.table(block.value)

    destination.parent.mkdir(parents=True, exist_ok=True)
    relationships = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    ]
    for rel_id, kind, target in builder.relationships:
        mode = ' TargetMode="External"' if kind.endswith("/hyperlink") else ""
        relationships.append(
            f'<Relationship Id="{rel_id}" Type="{kind}" Target="{html.escape(target, quote=True)}"{mode}/>'
        )

    package = {
        "[Content_Types].xml": xml_bytes("""
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
              <Default Extension="xml" ContentType="application/xml"/>
              <Default Extension="png" ContentType="image/png"/>
              <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
              <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
              <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
              <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
            </Types>
        """),
        "_rels/.rels": xml_bytes("""
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
              <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
              <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
            </Relationships>
        """),
        "word/document.xml": builder.finish(),
        "word/_rels/document.xml.rels": xml_bytes(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(relationships)
            + "</Relationships>"
        ),
        "word/styles.xml": xml_bytes("""
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Arial"/><w:sz w:val="21"/><w:color w:val="172033"/></w:rPr></w:rPrDefault></w:docDefaults>
              <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:style>
              <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="200" w:after="240"/></w:pPr><w:rPr><w:b/><w:color w:val="0D4F57"/><w:sz w:val="52"/></w:rPr></w:style>
              <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:rPr><w:color w:val="527274"/><w:sz w:val="28"/></w:rPr></w:style>
              <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="320" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="0D4F57"/><w:sz w:val="34"/></w:rPr></w:style>
              <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:i/><w:color w:val="527274"/><w:sz w:val="18"/></w:rPr></w:style>
              <w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="C9D8D7"/><w:left w:val="single" w:sz="4" w:color="C9D8D7"/><w:bottom w:val="single" w:sz="4" w:color="C9D8D7"/><w:right w:val="single" w:sz="4" w:color="C9D8D7"/><w:insideH w:val="single" w:sz="4" w:color="C9D8D7"/><w:insideV w:val="single" w:sz="4" w:color="C9D8D7"/></w:tblBorders></w:tblPr></w:style>
            </w:styles>
        """),
        "docProps/core.xml": xml_bytes(f"""
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
              <dc:title>Как получить API-ключи для Vibix Images</dc:title><dc:creator>Vibix Images</dc:creator><dc:language>ru-RU</dc:language>
              <dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now(UTC).isoformat()}</dcterms:created>
            </cp:coreProperties>
        """),
        "docProps/app.xml": xml_bytes("""
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Vibix Images documentation generator</Application></Properties>
        """),
        "word/media/image1.png": SCREENSHOT.read_bytes(),
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in package.items():
            archive.writestr(name, payload)


def find_browser() -> str:
    for name in ("google-chrome", "chromium", "chromium-browser"):
        executable = shutil.which(name)
        if executable:
            return executable
    raise RuntimeError("Chromium-compatible browser is required to create PDF")


def build_pdf(html_text: str, destination: Path) -> None:
    TEMP_HTML.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    TEMP_HTML.write_text(html_text, encoding="utf-8")
    environment = dict(os.environ)
    environment.setdefault("LANG", "C.UTF-8")
    subprocess.run(
        [
            find_browser(),
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--no-pdf-header-footer",
            f"--print-to-pdf={destination}",
            TEMP_HTML.resolve().as_uri(),
        ],
        check=True,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-html", action="store_true", help="Keep intermediate HTML")
    args = parser.parse_args()
    if not SOURCE.is_file() or not SCREENSHOT.is_file():
        raise FileNotFoundError("Guide source or UI screenshot is missing")
    blocks = parse_markdown(SOURCE.read_text(encoding="utf-8"))
    build_docx(blocks, DOCX_OUTPUT)
    build_pdf(html_document(blocks), PDF_OUTPUT)
    if not args.keep_html:
        TEMP_HTML.unlink(missing_ok=True)
    print(PDF_OUTPUT)
    print(DOCX_OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
