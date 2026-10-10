# -*- coding: utf-8 -*-
"""Markdown → PDF 本地转换器（零外部依赖：markdown-it-py + reportlab）。

用法：
    python scripts/md2pdf_local.py <input.md> <output.pdf>

设计要点：
- CJK 字体自动探测：优先托管运行时 runtime/python/fonts/NotoSansSC-*.ttf
  （正文 Regular、标题/粗体 Bold）；可用 MD2PDF_FONT_REGULAR / MD2PDF_FONT_BOLD
  环境变量覆盖；
- 标题 h1-h4 字号递减 + 藏青 #2B1665 主色（NCB 风格），h1 前给红色小方块；
- 表格：按内容宽度自适应列宽（上限内取最宽单元格），单元格用 Paragraph
  自动换行防溢出，表头藏青底白字、跨页重复表头；
- 代码块：浅灰底圆角感（表格模拟），按实际字宽精确折行，CJK 不丢字
  （等宽字体无中文字形，故代码也用 CJK 字体，牺牲等宽换取不丢内容）；
- 支持：粗体/斜体/行内代码/链接、有序无序列表（含嵌套缩进）、引用块
  （左侧红色竖条）、分割线、页脚页码。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from markdown_it import MarkdownIt
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily, stringWidth
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ------------------------------------------------------------------ 字体

NAVY = HexColor("#2B1665")
RED = HexColor("#E30000")
BODY_COLOR = HexColor("#1F2D3D")
GRAY_TEXT = HexColor("#5E6D82")
CODE_BG = HexColor("#F5F4F8")
CODE_BORDER = HexColor("#DDD9E8")
ROW_ALT = HexColor("#F7F5FB")
GRID = HexColor("#C9C3DA")


def _runtime_font_dir() -> Path:
    """托管运行时字体目录：runtime/python/fonts（sys.executable 在 .venv/Scripts 下）。"""
    return Path(sys.executable).resolve().parent.parent.parent / "fonts"


def register_cjk_fonts() -> tuple[str, str]:
    font_dir = _runtime_font_dir()
    regular = os.environ.get("MD2PDF_FONT_REGULAR") or str(font_dir / "NotoSansSC-Regular.ttf")
    bold = os.environ.get("MD2PDF_FONT_BOLD") or str(font_dir / "NotoSansSC-Bold.ttf")
    for path in (regular, bold):
        if not Path(path).exists():
            raise FileNotFoundError(
                f"CJK 字体不存在: {path}（可用 MD2PDF_FONT_REGULAR/BOLD 指定）")
    pdfmetrics.registerFont(TTFont("CJK", regular))
    pdfmetrics.registerFont(TTFont("CJK-Bold", bold))
    registerFontFamily("CJK", normal="CJK", bold="CJK-Bold",
                       italic="CJK", boldItalic="CJK-Bold")
    return "CJK", "CJK-Bold"


# ------------------------------------------------------------------ 样式

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
AVAIL_W = PAGE_W - 2 * MARGIN


def _st(name: str, **kw) -> ParagraphStyle:
    """默认值 + 覆盖合并（避免 **base 与显式 kwargs 重复传参）。"""
    d = dict(fontName="CJK", textColor=BODY_COLOR, fontSize=9.5, leading=15.5)
    d.update(kw)
    return ParagraphStyle(name, **d)


def build_styles() -> dict[str, ParagraphStyle]:
    return {
        "body": _st("body", spaceAfter=5),
        "h1": _st("h1", fontName="CJK-Bold", fontSize=19, leading=25,
                  textColor=NAVY, spaceBefore=6, spaceAfter=10),
        "h2": _st("h2", fontName="CJK-Bold", fontSize=14.5, leading=20,
                  textColor=NAVY, spaceBefore=12, spaceAfter=6, keepWithNext=1),
        "h3": _st("h3", fontName="CJK-Bold", fontSize=12, leading=17,
                  textColor=NAVY, spaceBefore=9, spaceAfter=4, keepWithNext=1),
        "h4": _st("h4", fontName="CJK-Bold", fontSize=10.5, leading=15,
                  textColor=NAVY, spaceBefore=7, spaceAfter=3, keepWithNext=1),
        "code": _st("code", fontSize=8, leading=11, textColor=HexColor("#333A4D")),
        "cell": _st("cell", fontSize=8.5, leading=12),
        "cell_head": _st("cell_head", fontName="CJK-Bold", fontSize=8.5,
                         leading=12, textColor=HexColor("#FFFFFF")),
        "quote": _st("quote", textColor=GRAY_TEXT, spaceAfter=4),
        "item": _st("item", leftIndent=14, spaceAfter=2),
    }


# ------------------------------------------------------------------ 行内元素 → reportlab 迷你 HTML

def inline_html(children) -> str:
    out: list[str] = []
    for c in children or []:
        if c.type == "text":
            out.append(escape(c.content))
        elif c.type == "strong_open":
            out.append("<b>")
        elif c.type == "strong_close":
            out.append("</b>")
        elif c.type == "em_open":
            out.append("<i>")
        elif c.type == "em_close":
            out.append("</i>")
        elif c.type == "code_inline":
            out.append('<font backColor="#F0EDF7" color="#B30000">'
                       + escape(c.content) + "</font>")
        elif c.type in ("softbreak", "hardbreak"):
            out.append("<br/>")
        elif c.type == "link_open":
            out.append('<font color="#2B1665"><u>')
        elif c.type == "link_close":
            out.append("</u></font>")
        elif c.type == "image":
            out.append(escape(c.content or c.attrs.get("src", "")))
    return "".join(out)


_TAG_RE = re.compile(r"<[^>]+>")


def _plain(html: str) -> str:
    return _TAG_RE.sub("", html).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


# ------------------------------------------------------------------ 代码块：按字宽精确折行 + 浅灰底

def _wrap_by_width(line: str, font: str, size: float, width: float) -> list[str]:
    """按实际渲染宽度折行（CJK 全宽、ASCII 半宽混合也准确）。"""
    if not line:
        return [" "]
    out, buf = [], ""
    for ch in line:
        if stringWidth(buf + ch, font, size) > width:
            out.append(buf or ch)
            buf = "" if buf else ""
            if stringWidth(buf + ch, font, size) > width and not buf:
                # 单字符即超宽（极端），硬塞
                out.append(ch)
                continue
            buf = ch
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out or [" "]


def code_flowable(content: str, styles: dict) -> Table:
    pad = 6
    inner_w = AVAIL_W - 2 * pad
    rows: list[list[Paragraph]] = []
    for raw in content.rstrip("\n").split("\n"):
        for piece in _wrap_by_width(raw, "CJK", 8, inner_w):
            html = escape(piece).replace(" ", "&nbsp;")
            rows.append([Paragraph(html, styles["code"])])
    tbl = Table(rows, colWidths=[AVAIL_W])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.6, CODE_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ]))
    return tbl


# ------------------------------------------------------------------ 表格

def parse_table(tokens, i, styles) -> tuple[Table, int]:
    header: list[str] = []
    rows: list[list[str]] = []
    i += 1  # skip table_open
    while tokens[i].type != "table_close":
        t = tokens[i]
        if t.type == "tr_open":
            cells: list[str] = []
            i += 1
            while tokens[i].type != "tr_close":
                if tokens[i].type in ("th_open", "td_open"):
                    cells.append(inline_html(tokens[i + 1].children))
                    i += 3
                else:
                    i += 1
            rows.append(cells)
        i += 1
    # 区分表头：GFM 表格第一行必然在 thead 内
    header, rows = rows[0], rows[1:]
    ncol = max(1, len(header))
    # 列宽：按单元格纯文本最宽值（封顶 0.45 * AVAIL_W），再归一到可用宽
    widths = []
    for c in range(ncol):
        texts = [_plain(header[c]) if c < len(header) else ""]
        texts += [_plain(r[c]) for r in rows if c < len(r)]
        w = max((stringWidth(t, "CJK-Bold", 8.5) for t in texts), default=30)
        widths.append(min(w + 12, AVAIL_W * 0.45))
    scale = AVAIL_W / max(sum(widths), 1)
    widths = [w * scale for w in widths]

    data = [[Paragraph(h, styles["cell_head"]) for h in header]]
    data += [[Paragraph(c, styles["cell"]) for c in r] for r in rows]
    tbl = Table(data, colWidths=widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), ROW_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tbl, i + 1


# ------------------------------------------------------------------ 列表 / 引用

def parse_list(tokens, i, styles) -> tuple[list, int]:
    ordered = tokens[i].type == "ordered_list_open"
    end = "ordered_list_close" if ordered else "bullet_list_close"
    start = 1
    if tokens[i].attrs:
        start = int(dict(tokens[i].attrs).get("start", 1))
    flows: list = []
    n = start
    i += 1
    while tokens[i].type != end:
        if tokens[i].type == "list_item_open":
            inner, i = parse_blocks(tokens, i + 1, "list_item_close")
            marker = f"{n}." if ordered else "•"
            if inner and isinstance(inner[0], Paragraph):
                inner[0] = Paragraph(inner[0].text, styles["item"], bulletText=marker)
                flows.extend(inner)
            else:
                flows.append(Paragraph("", styles["item"], bulletText=marker))
                flows.extend(inner)
            n += 1
        else:
            i += 1
    return flows, i + 1


def quote_wrap(inner: list, styles: dict) -> Table:
    tbl = Table([[inner]], colWidths=[AVAIL_W])
    tbl.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, RED),
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#FBFAFD")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


# ------------------------------------------------------------------ 块级递归解析

def parse_blocks(tokens, i: int, end: str | None = None) -> tuple[list, int]:
    styles = parse_blocks.styles
    flows: list = []
    while i < len(tokens):
        t = tokens[i]
        if end and t.type == end:
            return flows, i + 1
        if t.type == "heading_open":
            flows.append(Paragraph(inline_html(tokens[i + 1].children), styles[t.tag]))
            i += 3
        elif t.type == "paragraph_open":
            flows.append(Paragraph(inline_html(tokens[i + 1].children), styles["body"]))
            i += 3
        elif t.type == "fence":
            flows.append(Spacer(1, 2))
            flows.append(code_flowable(t.content, styles))
            flows.append(Spacer(1, 4))
            i += 1
        elif t.type == "table_open":
            tbl, i = parse_table(tokens, i, styles)
            flows.append(Spacer(1, 2))
            flows.append(tbl)
            flows.append(Spacer(1, 6))
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            items, i = parse_list(tokens, i, styles)
            flows.extend(items)
            flows.append(Spacer(1, 3))
        elif t.type == "blockquote_open":
            inner, i = parse_blocks(tokens, i + 1, "blockquote_close")
            flows.append(quote_wrap(inner, styles))
            flows.append(Spacer(1, 5))
        elif t.type == "hr":
            flows.append(Spacer(1, 4))
            flows.append(HRFlowable(width="100%", thickness=0.7, color=GRID))
            flows.append(Spacer(1, 6))
            i += 1
        else:
            i += 1
    return flows, i


# ------------------------------------------------------------------ 入口

def convert(md_path: str, pdf_path: str) -> None:
    register_cjk_fonts()
    styles = build_styles()
    parse_blocks.styles = styles  # 递归共享，避免层层传参

    text = Path(md_path).read_text(encoding="utf-8")
    md = MarkdownIt("commonmark").enable("table")
    tokens = md.parse(text)
    flows, _ = parse_blocks(tokens, 0)

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("CJK", 7.5)
        canvas.setFillColor(HexColor("#8A97A8"))
        canvas.drawCentredString(PAGE_W / 2, 10 * mm,
                                 f"南洋商业银行 · 智能信贷平台 — 第 {doc.page} 页")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=15 * mm, bottomMargin=16 * mm,
        title=Path(md_path).stem, author="credit-agent-platform",
    )
    doc.build(flows, onFirstPage=_footer, onLaterPages=_footer)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("用法: python md2pdf_local.py <input.md> <output.pdf>")
    convert(sys.argv[1], sys.argv[2])
    size_kb = Path(sys.argv[2]).stat().st_size // 1024
    print(f"[md2pdf] {sys.argv[1]} -> {sys.argv[2]} ({size_kb} KB)")
