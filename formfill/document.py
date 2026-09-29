"""Low-level DOCX helpers built on python-docx / lxml.

The form keeps labels and answers in the *same* table cell ("Meno:        Priezvisko:"),
uses narrow bordered cells as character boxes (dates, rodné číslo, codes) and marks
choices with an "X". These helpers expose the document as an ordered list of
paragraphs (body and table cells alike) and allow precise run-level edits at character
offsets while preserving the original formatting.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

NBSP = " "
BOX_MAX_WIDTH = 500  # twips; character boxes in the form are ~270-350 twips wide
VALUE_FONT = "Arial"
VALUE_SIZE_HALF_POINTS = 17  # 8.5 pt
VALUE_COLOR = "1F3A93"  # dark blue, like the reference samples

_RUN_XPATH = "./w:r | ./w:hyperlink/w:r | ./w:smartTag/w:r | ./w:ins/w:r"


# ----------------------------------------------------------------------------- text


def run_text(r) -> str:
    parts = []
    for child in r:
        if child.tag == qn("w:t"):
            parts.append(child.text or "")
        elif child.tag == qn("w:tab"):
            parts.append("\t")
        elif child.tag in (qn("w:br"), qn("w:cr")):
            parts.append("\n")
        elif child.tag == qn("w:noBreakHyphen"):
            parts.append("-")
    return "".join(parts)


def runs(p) -> list:
    return list(p.xpath(_RUN_XPATH))


def para_text(p) -> str:
    """Paragraph text with NBSP normalised to a space (same length, so offsets hold)."""
    return "".join(run_text(r) for r in runs(p)).replace(NBSP, " ")


def cell_text(tc) -> str:
    return "\n".join(para_text(p) for p in tc.iter(qn("w:p")))


def is_empty_text(text: str) -> bool:
    return not re.sub(r"[\s_.…]", "", text)


def set_run_text(r, text: str) -> None:
    """Replace a run's content, keeping its rPr; tabs/newlines become real elements."""
    for child in list(r):
        if child.tag != qn("w:rPr"):
            r.remove(child)
    for i, line in enumerate(text.split("\n")):
        if i:
            r.append(OxmlElement("w:br"))
        for j, seg in enumerate(line.split("\t")):
            if j:
                r.append(OxmlElement("w:tab"))
            if seg:
                t = OxmlElement("w:t")
                t.text = seg
                t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                r.append(t)


# ----------------------------------------------------------------------- structure


@dataclass
class Para:
    """A paragraph in document order, with its table cell (if any)."""

    index: int
    p: object
    tc: object | None

    @property
    def text(self) -> str:
        return para_text(self.p)


def paragraphs(document) -> list[Para]:
    out = []
    for p in document.element.body.iter(qn("w:p")):
        # Skip paragraphs inside text boxes: their position in reading order is undefined.
        if any(a.tag == qn("w:txbxContent") for a in p.iterancestors()):
            continue
        tc = next((a for a in p.iterancestors() if a.tag == qn("w:tc")), None)
        out.append(Para(len(out), p, tc))
    return out


def row_cells(tc) -> list:
    return tc.getparent().findall(qn("w:tc"))


def cells_after(tc) -> list:
    cells = row_cells(tc)
    return cells[cells.index(tc) + 1:]


def cell_width(tc) -> int:
    w = tc.find(f"{qn('w:tcPr')}/{qn('w:tcW')}")
    try:
        return int(w.get(qn("w:w"))) if w is not None else 10_000
    except (TypeError, ValueError):
        return 10_000


def is_box(tc) -> bool:
    return cell_width(tc) <= BOX_MAX_WIDTH


def table_of(tc):
    return next(a for a in tc.iterancestors() if a.tag == qn("w:tbl"))


def unique_cells(tr) -> list:
    """Cells of a row that are not vertical-merge continuations."""
    out = []
    for tc in tr.findall(qn("w:tc")):
        vm = tc.find(f"{qn('w:tcPr')}/{qn('w:vMerge')}")
        if vm is not None and vm.get(qn("w:val")) in (None, "continue"):
            continue
        out.append(tc)
    return out


# --------------------------------------------------------------------- run editing


def split_at(p, offset: int) -> int:
    """Ensure a run boundary at ``offset``; return index of the run starting there
    (== len(runs) when the offset is at the end of the paragraph)."""
    pos = 0
    for i, r in enumerate(runs(p)):
        text = run_text(r)
        if offset == pos:
            return i
        if pos < offset < pos + len(text):
            cut = offset - pos
            right = copy.deepcopy(r)
            set_run_text(r, text[:cut])
            set_run_text(right, text[cut:])
            r.addnext(right)
            return i + 1
        pos += len(text)
    return len(runs(p))


def delete_range(p, start: int, length: int) -> None:
    if length <= 0:
        return
    first = split_at(p, start)
    last = split_at(p, start + length)
    for r in runs(p)[first:last]:
        r.getparent().remove(r)


def value_run(text: str, template_run=None, bold: bool = False):
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        fonts.set(qn(attr), VALUE_FONT)
    rpr.append(fonts)
    if bold:
        rpr.append(OxmlElement("w:b"))
    color = OxmlElement("w:color")
    color.set(qn("w:val"), VALUE_COLOR)
    rpr.append(color)
    for tag in ("w:sz", "w:szCs"):
        sz = OxmlElement(tag)
        sz.set(qn("w:val"), str(VALUE_SIZE_HALF_POINTS))
        rpr.append(sz)
    r.append(rpr)
    set_run_text(r, text)
    return r


def insert_text(p, offset: int, text: str) -> None:
    idx = split_at(p, offset)
    rs = runs(p)
    new = value_run(text)
    if idx < len(rs):
        rs[idx].addprevious(new)
    elif rs:
        rs[-1].addnext(new)
    else:
        ppr = p.find(qn("w:pPr"))
        if ppr is not None:
            ppr.addnext(new)
        else:
            p.insert(0, new)


def strike_range(p, start: int, length: int) -> None:
    first = split_at(p, start)
    last = split_at(p, start + length)
    for r in runs(p)[first:last]:
        rpr = r.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            r.insert(0, rpr)
        if rpr.find(qn("w:strike")) is None:
            rpr.append(OxmlElement("w:strike"))


def _center(p) -> None:
    ppr = p.find(qn("w:pPr"))
    if ppr is None:
        ppr = OxmlElement("w:pPr")
        p.insert(0, ppr)
    jc = ppr.find(qn("w:jc"))
    if jc is None:
        jc = OxmlElement("w:jc")
        ppr.append(jc)
    jc.set(qn("w:val"), "center")


def write_cell(tc, text: str, center: bool = True) -> None:
    """Write a value into an (empty) cell's first paragraph."""
    p = tc.find(qn("w:p"))
    if p is None:
        p = OxmlElement("w:p")
        tc.append(p)
    if center:
        _center(p)
    insert_text(p, len(para_text(p)), text)


def append_paragraph(tc, text: str, center: bool = True) -> None:
    """Add a new paragraph (formatted like the cell's last one) holding ``text``."""
    last = tc.findall(qn("w:p"))[-1]
    p = copy.deepcopy(last)
    for r in runs(p):
        r.getparent().remove(r)
    last.addnext(p)
    if center:
        _center(p)
    insert_text(p, 0, text)


WPS_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
VML_NS = "urn:schemas-microsoft-com:vml"


def _mark_paragraph():
    p = OxmlElement("w:p")
    _center(p)
    r = value_run("X", bold=True)
    sz = r.find(qn("w:rPr")).find(qn("w:sz"))
    sz.set(qn("w:val"), "20")
    p.append(r)
    return p


def mark_shape(tc) -> bool:
    """Put an "X" inside a drawn checkbox rectangle in ``tc`` (DrawingML + VML fallback).

    Returns False when the cell has no such shape."""
    shapes = list(tc.iter(f"{{{WPS_NS}}}wsp"))
    rects = list(tc.iter(f"{{{VML_NS}}}rect"))
    if not shapes and not rects:
        return False
    for wsp in shapes:
        body = wsp.find(f"{{{WPS_NS}}}bodyPr")
        txbx = etree.SubElement(wsp, f"{{{WPS_NS}}}txbx")
        content = etree.SubElement(txbx, qn("w:txbxContent"))
        content.append(_mark_paragraph())
        if body is not None:  # bodyPr must follow txbx; zero insets, centred text
            wsp.remove(body)
            for side in ("lIns", "tIns", "rIns", "bIns"):
                body.set(side, "0")
            body.set("anchor", "ctr")
            wsp.append(body)
    for rect in rects:
        box = etree.SubElement(rect, f"{{{VML_NS}}}textbox")
        box.set("inset", "0,0,0,0")
        content = etree.SubElement(box, qn("w:txbxContent"))
        content.append(_mark_paragraph())
    return True


def dump(el) -> str:  # debugging helper
    return etree.tostring(el, pretty_print=True, encoding="unicode")
