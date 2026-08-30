"""Generate illustrated PDF and DOCX editions of the Vibix Images user guide.

Only the Python standard library is required. Chromium renders the PDF so
Cyrillic text, selectable links, and UI screenshots remain high quality. The
DOCX is emitted as a standards-compliant OOXML package.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "USER_GUIDE.ru.md"
PDF_OUTPUT = ROOT / "output" / "pdf" / "Vibix_Images_User_Guide.ru.pdf"
DOCX_OUTPUT = ROOT / "output" / "doc" / "Vibix_Images_User_Guide.ru.docx"
TEMP_HTML = ROOT / "tmp" / "pdfs" / "Vibix_Images_User_Guide.ru.html"
GUIDE_CREATED_AT = "2026-08-30T00:00:00Z"


@dataclass(frozen=True)
class Block:
    kind: str
    value: object
    extra: str = ""


def parse_markdown(source: str) -> list[Block]:
    lines = source.splitlines()
    blocks: list[Block] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            index += 1
            body: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            index += 1
            blocks.append(Block("code", "\n".join(body), language))
            continue
        image_match = re.fullmatch(r"!\[([^]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            blocks.append(Block("image", image_match.group(2), image_match.group(1)))
            index += 1
            continue
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            blocks.append(Block("title" if level == 1 else f"heading{level}", heading_match.group(2)))
            index += 1
            continue
        if (
            stripped.startswith("|")
            and index + 1 < len(lines)
            and re.match(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$", lines[index + 1])
        ):
            rows = [[cell.strip() for cell in stripped.strip("|").split("|")]]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            blocks.append(Block("table", rows))
            continue
        ordered = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if ordered:
            start = int(ordered.group(1))
            items: list[str] = []
            while index < len(lines):
                item_match = re.match(r"^\s*\d+\.\s+(.+)$", lines[index])
                if not item_match:
                    break
                text = [item_match.group(1).strip()]
                index += 1
                while index < len(lines):
                    continuation = lines[index]
                    if not continuation.strip():
                        index += 1
                        break
                    if re.match(r"^\s*(?:\d+\.|-)\s+", continuation):
                        break
                    if continuation.strip().startswith(("#", "|", "```", "![")):
                        break
                    text.append(continuation.strip())
                    index += 1
                items.append(" ".join(text))
            blocks.append(Block("ordered", (start, items)))
            continue
        if re.match(r"^\s*-\s+", lines[index]):
            items = []
            while index < len(lines):
                item_match = re.match(r"^\s*-\s+(.+)$", lines[index])
                if not item_match:
                    break
                text = [item_match.group(1).strip()]
                index += 1
                while index < len(lines):
                    continuation = lines[index]
                    if not continuation.strip():
                        index += 1
                        break
                    if re.match(r"^\s*-\s+", continuation):
                        break
                    if continuation.strip().startswith(("#", "|", "```", "![")):
                        break
                    text.append(continuation.strip())
                    index += 1
                items.append(" ".join(text))
            blocks.append(Block("unordered", items))
            continue
        paragraph = [stripped]
        index += 1
        while index < len(lines):
            following = lines[index].strip()
            if not following:
                index += 1
                break
            if following.startswith(("#", "|", "```", "![")):
                break
            if re.match(r"^(?:\d+\.|-)\s+", following):
                break
            paragraph.append(following)
            index += 1
        blocks.append(Block("paragraph", " ".join(paragraph)))
    return blocks


INLINE_PATTERN = re.compile(
    r"\[([^]]+)\]\((https?://[^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`"
)


def inline_html(text: str) -> str:
    output: list[str] = []
    offset = 0
    for match in INLINE_PATTERN.finditer(text):
        output.append(html.escape(text[offset : match.start()]))
        if match.group(1) is not None:
            output.append(
                f'<a href="{html.escape(match.group(2), quote=True)}">'
                f"{html.escape(match.group(1))}</a>"
            )
        elif match.group(3) is not None:
            output.append(f"<strong>{html.escape(match.group(3))}</strong>")
        else:
            output.append(f"<code>{html.escape(match.group(4))}</code>")
        offset = match.end()
    output.append(html.escape(text[offset:]))
    return "".join(output)


def resolve_asset(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def html_document(blocks: list[Block]) -> str:
    body: list[str] = []
    for block in blocks:
        if block.kind == "title":
            body.append(
                '<section class="cover"><div class="eyebrow">VIBIX IMAGES</div>'
                f"<h1>{inline_html(str(block.value))}</h1>"
                '<p class="lead">От API-ключей и промптов до прозрачных PNG, '
                "Pinterest и обработки готовых изображений.</p>"
                '<div class="cover-meta">Версия 3.0.7 · 30 августа 2026 года</div>'
                "</section>"
            )
        elif block.kind == "heading2":
            body.append(f'<h2 class="section">{inline_html(str(block.value))}</h2>')
        elif block.kind == "heading3":
            body.append(f"<h3>{inline_html(str(block.value))}</h3>")
        elif block.kind == "paragraph":
            body.append(f"<p>{inline_html(str(block.value))}</p>")
        elif block.kind in {"ordered", "unordered"}:
            tag = "ol" if block.kind == "ordered" else "ul"
            start, items = block.value if block.kind == "ordered" else (1, block.value)
            start_attr = f' start="{start}"' if tag == "ol" and start != 1 else ""
            body.append(
                f"<{tag}{start_attr}>"
                + "".join(f"<li>{inline_html(item)}</li>" for item in items)
                + f"</{tag}>"
            )
        elif block.kind == "table":
            rows: list[list[str]] = block.value
            head = "".join(f"<th>{inline_html(cell)}</th>" for cell in rows[0])
            content = "".join(
                "<tr>" + "".join(f"<td>{inline_html(cell)}</td>" for cell in row) + "</tr>"
                for row in rows[1:]
            )
            body.append(f"<table><thead><tr>{head}</tr></thead><tbody>{content}</tbody></table>")
        elif block.kind == "code":
            body.append(f"<pre><code>{html.escape(str(block.value))}</code></pre>")
        elif block.kind == "image":
            path = resolve_asset(str(block.value))
            body.append(
                f'<figure><img src="{path.resolve().as_uri()}" alt="{html.escape(block.extra, quote=True)}">'
                f"<figcaption>{inline_html(block.extra)}</figcaption></figure>"
            )
    return """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Vibix Images — руководство пользователя</title>
<style>
@page {
  size: A4; margin: 16mm 15mm 21mm;
  @bottom-left { content: "Vibix Images · Руководство пользователя"; color: #6b7f85; font: 8pt Arial, sans-serif; }
  @bottom-right { content: "Страница " counter(page) " из " counter(pages); color: #6b7f85; font: 8pt Arial, sans-serif; }
}
* { box-sizing: border-box; }
body { margin: 0; color: #172033; font: 10.25pt/1.45 Arial, "DejaVu Sans", sans-serif; }
a { color: #087f78; text-decoration: none; overflow-wrap: anywhere; }
h1 { margin: 15mm 0 8mm; max-width: 155mm; color: #fff; font-size: 31pt; line-height: 1.08; }
h2 { margin: 0 0 4mm; color: #0d4f57; font-size: 19pt; line-height: 1.2; break-after: avoid; }
h2.section { break-before: page; }
h3 { margin: 7mm 0 2.5mm; color: #14666b; font-size: 13.5pt; line-height: 1.25; break-after: avoid; }
p { margin: 0 0 3.2mm; orphans: 3; widows: 3; }
ol, ul { margin: 0 0 4mm 5mm; padding-left: 5mm; }
li { margin: 0 0 1.8mm; padding-left: 1mm; break-inside: avoid; }
strong { color: #0d4f57; }
code { font-family: "DejaVu Sans Mono", Consolas, monospace; }
p code, li code, td code { background: #eef5f4; border: 0.2mm solid #d7e7e5; border-radius: 2px; padding: 0.2mm 0.8mm; }
pre { margin: 3mm 0 5mm; padding: 3mm; color: #dff7f4; background: #102033; border-left: 1.4mm solid #24bcb4; border-radius: 2mm; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 8.7pt; line-height: 1.4; break-inside: avoid; }
table { width: 100%; margin: 3mm 0 5mm; border-collapse: collapse; font-size: 9.2pt; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { background: #0d4f57; color: white; text-align: left; font-weight: 700; }
th, td { border: 0.25mm solid #c9d8d7; padding: 2mm 2.2mm; vertical-align: top; }
tbody tr:nth-child(even) { background: #f3f8f7; }
.cover { min-height: 273mm; margin: -16mm -15mm 0; padding: 34mm 21mm; color: #d8eeee; background: linear-gradient(145deg, #071426 0%, #0c2538 55%, #0b5b61 100%); break-after: page; }
.eyebrow { color: #44d7cb; font-weight: 800; letter-spacing: 0.13em; }
.lead { max-width: 145mm; color: #d8eeee; font-size: 15pt; line-height: 1.45; }
.cover-meta { margin-top: 30mm; color: #9bc7c6; font-size: 10pt; }
figure { margin: 4mm 0 6mm; padding: 3mm; background: #0e1c2d; border-radius: 3mm; break-inside: avoid; }
figure img { display: block; width: 100%; max-height: 165mm; object-fit: contain; border-radius: 2mm; }
figcaption { margin-top: 2mm; color: #d8eeee; font-size: 8.8pt; }
</style></head><body>""" + "\n".join(body) + "\n</body></html>"


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
for prefix, namespace in (("w", W_NS), ("r", R_NS), ("wp", WP_NS), ("a", A_NS), ("pic", PIC_NS)):
    ET.register_namespace(prefix, namespace)


def q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Only PNG guide images are supported: {path}")
    return struct.unpack(">II", header[16:24])


class WordBuilder:
    def __init__(self) -> None:
        self.document = ET.Element(q(W_NS, "document"))
        self.body = ET.SubElement(self.document, q(W_NS, "body"))
        self.relationships: list[tuple[str, str, str, bool]] = []
        self.media: dict[str, bytes] = {}
        self.next_rel = 3
        self.next_image = 1

    def relationship(self, kind: str, target: str, *, external: bool = False) -> str:
        rel_id = f"rId{self.next_rel}"
        self.next_rel += 1
        self.relationships.append((rel_id, kind, target, external))
        return rel_id

    @staticmethod
    def run(parent: ET.Element, text: str, *, bold: bool = False, code: bool = False) -> None:
        run = ET.SubElement(parent, q(W_NS, "r"))
        if bold or code:
            properties = ET.SubElement(run, q(W_NS, "rPr"))
            if bold:
                ET.SubElement(properties, q(W_NS, "b"))
            if code:
                fonts = ET.SubElement(properties, q(W_NS, "rFonts"))
                fonts.set(q(W_NS, "ascii"), "Consolas")
                fonts.set(q(W_NS, "hAnsi"), "Consolas")
        node = ET.SubElement(run, q(W_NS, "t"))
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = text

    def inline(self, parent: ET.Element, text: str) -> None:
        offset = 0
        for match in INLINE_PATTERN.finditer(text):
            if match.start() > offset:
                self.run(parent, text[offset : match.start()])
            if match.group(1) is not None:
                rel_id = self.relationship(
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                    match.group(2),
                    external=True,
                )
                hyperlink = ET.SubElement(parent, q(W_NS, "hyperlink"))
                hyperlink.set(q(R_NS, "id"), rel_id)
                run = ET.SubElement(hyperlink, q(W_NS, "r"))
                props = ET.SubElement(run, q(W_NS, "rPr"))
                color = ET.SubElement(props, q(W_NS, "color"))
                color.set(q(W_NS, "val"), "087F78")
                underline = ET.SubElement(props, q(W_NS, "u"))
                underline.set(q(W_NS, "val"), "single")
                node = ET.SubElement(run, q(W_NS, "t"))
                node.text = match.group(1)
            elif match.group(3) is not None:
                self.run(parent, match.group(3), bold=True)
            else:
                self.run(parent, match.group(4), code=True)
            offset = match.end()
        if offset < len(text):
            self.run(parent, text[offset:])

    def paragraph(self, text: str = "", style: str | None = None) -> ET.Element:
        paragraph = ET.SubElement(self.body, q(W_NS, "p"))
        if style:
            props = ET.SubElement(paragraph, q(W_NS, "pPr"))
            node = ET.SubElement(props, q(W_NS, "pStyle"))
            node.set(q(W_NS, "val"), style)
        self.inline(paragraph, text)
        return paragraph

    def list_item(self, text: str, *, ordered: bool, number: int) -> None:
        paragraph = ET.SubElement(self.body, q(W_NS, "p"))
        props = ET.SubElement(paragraph, q(W_NS, "pPr"))
        indent = ET.SubElement(props, q(W_NS, "ind"))
        indent.set(q(W_NS, "left"), "560")
        indent.set(q(W_NS, "hanging"), "340")
        self.run(paragraph, f"{number}. " if ordered else "• ", bold=True)
        self.inline(paragraph, text)

    def code(self, text: str) -> None:
        paragraph = ET.SubElement(self.body, q(W_NS, "p"))
        props = ET.SubElement(paragraph, q(W_NS, "pPr"))
        style = ET.SubElement(props, q(W_NS, "pStyle"))
        style.set(q(W_NS, "val"), "CodeBlock")
        for index, line in enumerate(text.splitlines() or [""]):
            if index:
                run = ET.SubElement(paragraph, q(W_NS, "r"))
                ET.SubElement(run, q(W_NS, "br"))
            self.run(paragraph, line, code=True)

    def table(self, rows: list[list[str]]) -> None:
        table = ET.SubElement(self.body, q(W_NS, "tbl"))
        props = ET.SubElement(table, q(W_NS, "tblPr"))
        style = ET.SubElement(props, q(W_NS, "tblStyle"))
        style.set(q(W_NS, "val"), "TableGrid")
        width = ET.SubElement(props, q(W_NS, "tblW"))
        width.set(q(W_NS, "w"), "0")
        width.set(q(W_NS, "type"), "auto")
        for row_index, row in enumerate(rows):
            row_node = ET.SubElement(table, q(W_NS, "tr"))
            cant_split = ET.SubElement(ET.SubElement(row_node, q(W_NS, "trPr")), q(W_NS, "cantSplit"))
            del cant_split
            for cell in row:
                cell_node = ET.SubElement(row_node, q(W_NS, "tc"))
                paragraph = ET.SubElement(cell_node, q(W_NS, "p"))
                self.inline(paragraph, cell)
                if row_index == 0:
                    for run in paragraph.findall(q(W_NS, "r")):
                        run_props = run.find(q(W_NS, "rPr"))
                        if run_props is None:
                            run_props = ET.SubElement(run, q(W_NS, "rPr"))
                        ET.SubElement(run_props, q(W_NS, "b"))

    def image(self, path: Path, caption: str) -> None:
        width_px, height_px = png_size(path)
        max_width = int(6.45 * 914400)
        max_height = int(6.35 * 914400)
        width = max_width
        height = round(width * height_px / width_px)
        if height > max_height:
            height = max_height
            width = round(height * width_px / height_px)
        media_name = f"image{self.next_image}.png"
        self.media[f"word/media/{media_name}"] = path.read_bytes()
        image_id = self.next_image
        self.next_image += 1
        rel_id = self.relationship(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
            f"media/{media_name}",
        )
        paragraph = ET.SubElement(self.body, q(W_NS, "p"))
        props = ET.SubElement(paragraph, q(W_NS, "pPr"))
        center = ET.SubElement(props, q(W_NS, "jc"))
        center.set(q(W_NS, "val"), "center")
        run = ET.SubElement(paragraph, q(W_NS, "r"))
        drawing = ET.SubElement(run, q(W_NS, "drawing"))
        inline = ET.SubElement(drawing, q(WP_NS, "inline"))
        extent = ET.SubElement(inline, q(WP_NS, "extent"))
        extent.set("cx", str(width))
        extent.set("cy", str(height))
        doc_props = ET.SubElement(inline, q(WP_NS, "docPr"))
        doc_props.set("id", str(image_id))
        doc_props.set("name", caption or path.name)
        graphic = ET.SubElement(inline, q(A_NS, "graphic"))
        graphic_data = ET.SubElement(graphic, q(A_NS, "graphicData"))
        graphic_data.set("uri", "http://schemas.openxmlformats.org/drawingml/2006/picture")
        picture = ET.SubElement(graphic_data, q(PIC_NS, "pic"))
        non_visual = ET.SubElement(picture, q(PIC_NS, "nvPicPr"))
        c_nv_pr = ET.SubElement(non_visual, q(PIC_NS, "cNvPr"))
        c_nv_pr.set("id", str(image_id))
        c_nv_pr.set("name", path.name)
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
        ext.set("cx", str(width))
        ext.set("cy", str(height))
        geometry = ET.SubElement(shape, q(A_NS, "prstGeom"))
        geometry.set("prst", "rect")
        ET.SubElement(geometry, q(A_NS, "avLst"))
        self.paragraph(caption, "Caption")

    def page_break(self) -> None:
        paragraph = ET.SubElement(self.body, q(W_NS, "p"))
        run = ET.SubElement(paragraph, q(W_NS, "r"))
        br = ET.SubElement(run, q(W_NS, "br"))
        br.set(q(W_NS, "type"), "page")

    def finish(self) -> bytes:
        section = ET.SubElement(self.body, q(W_NS, "sectPr"))
        footer = ET.SubElement(section, q(W_NS, "footerReference"))
        footer.set(q(W_NS, "type"), "default")
        footer.set(q(R_NS, "id"), "rId2")
        size = ET.SubElement(section, q(W_NS, "pgSz"))
        size.set(q(W_NS, "w"), "11906")
        size.set(q(W_NS, "h"), "16838")
        margins = ET.SubElement(section, q(W_NS, "pgMar"))
        for name, value in (("top", "907"), ("right", "850"), ("bottom", "1020"), ("left", "850"), ("footer", "420")):
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
                "От API-ключей и промптов до прозрачных PNG, Pinterest и обработки готовых изображений.",
                "Subtitle",
            )
            builder.paragraph("Версия 3.0.7 · 30 августа 2026 года")
            builder.page_break()
        elif block.kind == "heading2":
            builder.paragraph(str(block.value), "Heading1")
        elif block.kind == "heading3":
            builder.paragraph(str(block.value), "Heading2")
        elif block.kind == "paragraph":
            builder.paragraph(str(block.value))
        elif block.kind in {"ordered", "unordered"}:
            start, items = block.value if block.kind == "ordered" else (1, block.value)
            for offset, item in enumerate(items):
                builder.list_item(item, ordered=block.kind == "ordered", number=start + offset)
        elif block.kind == "table":
            builder.table(block.value)
        elif block.kind == "code":
            builder.code(str(block.value))
        elif block.kind == "image":
            builder.image(resolve_asset(str(block.value)), block.extra)

    destination.parent.mkdir(parents=True, exist_ok=True)
    relationships = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>',
    ]
    for rel_id, kind, target, external in builder.relationships:
        mode = ' TargetMode="External"' if external else ""
        relationships.append(
            f'<Relationship Id="{rel_id}" Type="{kind}" Target="{html.escape(target, quote=True)}"{mode}/>'
        )
    package: dict[str, bytes] = {
        "[Content_Types].xml": xml_bytes("""
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
              <Default Extension="xml" ContentType="application/xml"/>
              <Default Extension="png" ContentType="image/png"/>
              <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
              <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
              <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
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
              <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Arial"/><w:sz w:val="20"/><w:color w:val="172033"/></w:rPr></w:rPrDefault></w:docDefaults>
              <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="110" w:line="285" w:lineRule="auto"/><w:widowControl/></w:pPr></w:style>
              <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="600" w:after="260"/></w:pPr><w:rPr><w:b/><w:color w:val="0D4F57"/><w:sz w:val="56"/></w:rPr></w:style>
              <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:rPr><w:color w:val="527274"/><w:sz w:val="29"/></w:rPr></w:style>
              <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:pageBreakBefore/><w:keepNext/><w:spacing w:before="180" w:after="140"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="0D4F57"/><w:sz w:val="36"/></w:rPr></w:style>
              <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="260" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:color w:val="14666B"/><w:sz w:val="27"/></w:rPr></w:style>
              <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:keepNext/></w:pPr><w:rPr><w:i/><w:color w:val="527274"/><w:sz w:val="18"/></w:rPr></w:style>
              <w:style w:type="paragraph" w:styleId="CodeBlock"><w:name w:val="Code Block"/><w:basedOn w:val="Normal"/><w:pPr><w:shd w:fill="EAF3F2"/><w:ind w:left="240" w:right="240"/><w:spacing w:before="100" w:after="160"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="18"/></w:rPr></w:style>
              <w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="C9D8D7"/><w:left w:val="single" w:sz="4" w:color="C9D8D7"/><w:bottom w:val="single" w:sz="4" w:color="C9D8D7"/><w:right w:val="single" w:sz="4" w:color="C9D8D7"/><w:insideH w:val="single" w:sz="4" w:color="C9D8D7"/><w:insideV w:val="single" w:sz="4" w:color="C9D8D7"/></w:tblBorders></w:tblPr></w:style>
            </w:styles>
        """),
        "word/footer1.xml": xml_bytes("""
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:pPr><w:jc w:val="right"/></w:pPr><w:r><w:rPr><w:color w:val="6B7F85"/><w:sz w:val="16"/></w:rPr><w:t>Vibix Images · Страница </w:t></w:r><w:fldSimple w:instr="PAGE"><w:r><w:rPr><w:color w:val="6B7F85"/><w:sz w:val="16"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>
        """),
        "docProps/core.xml": xml_bytes(f"""
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
              <dc:title>Vibix Images: полное руководство пользователя</dc:title><dc:creator>Vibix Images</dc:creator><dc:language>ru-RU</dc:language><dcterms:created xsi:type="dcterms:W3CDTF">{GUIDE_CREATED_AT}</dcterms:created>
            </cp:coreProperties>
        """),
        "docProps/app.xml": xml_bytes("""
            <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Vibix Images documentation generator</Application></Properties>
        """),
        **builder.media,
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in package.items():
            archive.writestr(name, payload)


def find_browser(explicit: str | None = None) -> str:
    requested = explicit or os.environ.get("VIBIX_DOC_BROWSER")
    if requested:
        executable = shutil.which(requested)
        if executable:
            return executable
        path = Path(requested).expanduser()
        if path.is_file():
            return str(path.resolve())
        raise RuntimeError(f"Browser executable not found: {requested}")

    for name in (
        "google-chrome",
        "chromium",
        "chromium-browser",
        "chrome",
        "chrome.exe",
        "msedge",
        "msedge.exe",
    ):
        executable = shutil.which(name)
        if executable:
            return executable

    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ]
    for environment_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(environment_name)
        if base:
            candidates.extend(
                (
                    Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                    Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                )
            )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError(
        "Chrome, Chromium, or Edge is required to create PDF; "
        "pass --browser PATH or set VIBIX_DOC_BROWSER"
    )


def build_pdf(document: str, destination: Path, *, browser: str | None = None) -> None:
    TEMP_HTML.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    TEMP_HTML.write_text(document, encoding="utf-8")
    environment = dict(os.environ)
    environment.setdefault("LANG", "C.UTF-8")
    subprocess.run(
        [
            find_browser(browser),
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


def validate_inputs(blocks: list[Block]) -> None:
    missing = [
        str(resolve_asset(str(block.value)))
        for block in blocks
        if block.kind == "image" and not resolve_asset(str(block.value)).is_file()
    ]
    if missing:
        raise FileNotFoundError("Missing guide images: " + ", ".join(missing))
    if len([block for block in blocks if block.kind == "image"]) < 10:
        raise RuntimeError("The illustrated guide must contain at least ten screenshots")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-html", action="store_true", help="Keep intermediate HTML")
    parser.add_argument(
        "--browser",
        help="Path to Chrome, Chromium, or Edge (also accepted via VIBIX_DOC_BROWSER)",
    )
    args = parser.parse_args()
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    blocks = parse_markdown(SOURCE.read_text(encoding="utf-8"))
    validate_inputs(blocks)
    build_docx(blocks, DOCX_OUTPUT)
    build_pdf(html_document(blocks), PDF_OUTPUT, browser=args.browser)
    if not args.keep_html:
        TEMP_HTML.unlink(missing_ok=True)
    print(PDF_OUTPUT)
    print(DOCX_OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
