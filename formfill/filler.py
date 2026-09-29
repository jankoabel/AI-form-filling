"""Write collected values into the DOCX template.

Every field carries an :class:`~formfill.fields.Anchor` that references visible label
text, not XML positions, so the same code works for any Word form that follows the usual
"Label: ______" conventions. Rendering always starts from the pristine template, which
makes filling idempotent (corrections simply re-render).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.oxml.ns import qn

from . import document as D
from .fields import (ACADEMIC_YEAR, BOXES, LIST, MARK, ROW, STRIKE, TABLE, TEXT, WRITE_KINDS,
                     Anchor, Field, condition_holds)
from .validators import loose

log = logging.getLogger(__name__)

SPACE_PER_CHAR = 2.1  # value glyph (8.5pt Arial caps) ~ 2 spaces of the 11pt form font


@dataclass
class FillReport:
    written: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


class AnchorNotFound(LookupError):
    pass


# --------------------------------------------------------------------------- lookup


def label_pattern(label: str, colon: bool = True, flags: int = 0) -> re.Pattern:
    words = r"\s+".join(re.escape(w) for w in label.replace(D.NBSP, " ").split())
    tail = r"\s*(?:\d{1,2}\s*\))?\s*:" if colon else r"(?![^\W\d_])"
    return re.compile(rf"(?<!\w){words}{tail}", flags)


def _start(paras: list[D.Para], after: str | None) -> tuple[int, int]:
    if not after:
        return 0, 0
    for flags in (0, re.IGNORECASE):
        pat = label_pattern(after, colon=False, flags=flags)
        for para in paras:
            m = pat.search(para.text)
            if m:
                return para.index, m.end()
    raise AnchorNotFound(f"section marker '{after}' not found")


def find_label(paras: list[D.Para], anchor: Anchor) -> tuple[D.Para, re.Match]:
    """Locate the ``nth`` occurrence of ``anchor.label`` after ``anchor.after``.

    Matching is case-sensitive first (so "Priezvisko" does not hit "Rodné priezvisko")
    and falls back to case-insensitive.
    """
    start_idx, start_off = _start(paras, anchor.after)
    for flags in (0, re.IGNORECASE):
        pat = label_pattern(anchor.label, anchor.colon, flags)
        seen = 0
        for para in paras[start_idx:]:
            offset = start_off if para.index == start_idx else 0
            for m in pat.finditer(para.text, offset):
                if seen == anchor.nth:
                    return para, m
                seen += 1
    raise AnchorNotFound(f"label '{anchor.label}' (after={anchor.after}, nth={anchor.nth})")


# -------------------------------------------------------------------------- writers


def write_text(paras, anchor: Anchor, value: str) -> None:
    para, m = find_label(paras, anchor)
    _insert_after(para, m.end(), value)


def _insert_after(para: D.Para, pos: int, value: str) -> None:
    """Insert ``value`` after a label, eating the whitespace padding that reserves room
    for it so neighbouring labels in the same line keep their position."""
    text = para.text
    spaces = len(text[pos:]) - len(text[pos:].lstrip(" "))
    rest = text[pos + spaces:]
    if rest.strip():  # another label follows in the same line
        budget = round(SPACE_PER_CHAR * len(value)) + 2
        eat = max(0, min(spaces - 3, budget))
        suffix = " "
    else:  # trailing padding only
        eat, suffix = spaces, ""
    D.delete_range(para.p, pos, eat)
    D.insert_text(para.p, pos, f"  {value}{suffix}")


def write_boxes(paras, anchor: Anchor, value: str) -> None:
    para, m = find_label(paras, anchor)
    chars = [c for c in value if c.isalnum()]
    boxes = []
    if para.tc is not None:
        for tc in D.cells_after(para.tc):
            text = D.cell_text(tc)
            empty = D.is_empty_text(text)
            if D.is_box(tc) and empty:
                boxes.append(tc)
                if len(boxes) == len(chars):
                    break
            elif ":" in text or empty:  # next label or a wide filler cell ends the run
                break
            # otherwise a separator inside the run ("mesiac", "rok", "/") - skip it
    if chars and len(boxes) == len(chars):
        for tc, ch in zip(boxes, chars):
            D.write_cell(tc, ch)
    else:  # no box grid - write as plain text
        _insert_after(para, m.end(), value)


def write_mark(paras, f: Field, value: str) -> None:
    start_idx, _ = _start(paras, f.anchor.after)
    marker = paras[start_idx]
    scope = paras[start_idx:start_idx + 40]
    if marker.tc is not None:  # options live in the marker's table row
        tr = marker.tc.getparent()
        scope = [p for p in scope if p.tc is not None and p.tc.getparent() is tr]
    option_text = f.option_texts.get(value, value)
    pat = re.compile(rf"(?<!\w){re.escape(option_text)}(?![^\W\d_])", re.IGNORECASE)
    for para in scope:
        if pat.search(para.text):
            if para.tc is None:
                m = pat.search(para.text)
                D.insert_text(para.p, m.end(), " X")
                return
            if D.mark_shape(para.tc):  # drawn checkbox rectangle inside the cell
                return
            nxt = D.cells_after(para.tc)[:1]
            if nxt and D.is_box(nxt[0]) and D.is_empty_text(D.cell_text(nxt[0])):
                D.write_cell(nxt[0], "X")
            else:
                D.append_paragraph(para.tc, "X")
            return
    raise AnchorNotFound(f"option '{option_text}' after '{f.anchor.after}'")


def write_strike(paras, f: Field, value: str) -> None:
    """Strike through every option except the chosen one ("Nehodiace sa prečiarknite")."""
    texts = [f.option_texts.get(o, o) for o in f.options]
    for para in paras:
        t = para.text
        if all(x in t for x in texts):
            for option, x in zip(f.options, texts):
                if loose(option) != loose(value):
                    m = re.search(rf"(?<!\w){re.escape(x)}(?![^\W\d_])", t)
                    D.strike_range(para.p, m.start(), len(x))
            return
    raise AnchorNotFound(f"strike options {texts}")


def write_row(paras, anchor: Anchor, values: list[str]) -> None:
    para, _ = find_label(paras, anchor)
    if para.tc is None:
        raise AnchorNotFound(f"row label '{anchor.label}' is not in a table")
    cells = [tc for tc in D.cells_after(para.tc) if D.is_empty_text(D.cell_text(tc))]
    for tc, v in zip(cells, values):
        D.write_cell(tc, v)


def write_table(document, anchor: Anchor, rows: list[list[str]]) -> list[str]:
    key = loose(anchor.table)
    for tbl in document.element.body.iter(qn("w:tbl")):
        if any(loose(D.cell_text(tc)).startswith(key) for tc in tbl.iter(qn("w:tc"))):
            break
    else:
        raise AnchorNotFound(f"table with header '{anchor.table}'")
    empty_rows = [tr for tr in tbl.findall(qn("w:tr"))
                  if all(D.is_empty_text(D.cell_text(tc)) for tc in tr.findall(qn("w:tc")))]
    for tr, row in zip(empty_rows, rows):
        for col, (tc, v) in enumerate(zip(D.unique_cells(tr), row)):
            if v:
                D.write_cell(tc, v, center=col > 0)
    return [f"{len(rows) - len(empty_rows)} riadkov sa do tabuľky nezmestilo"] if len(rows) > len(empty_rows) else []


def write_list(paras, anchor: Anchor, items: list[str]) -> None:
    para, _ = find_label(paras, anchor)
    free = []
    for p in paras[para.index + 1:]:
        numbered = p.p.find(f"{qn('w:pPr')}/{qn('w:numPr')}") is not None
        if not numbered and p.text.strip():
            break
        if numbered and D.is_empty_text(p.text):
            free.append(p)
    for p, item in zip(free, items):
        D.insert_text(p.p, len(p.text), item)


def write_academic_year(paras, anchor: Anchor, value: str) -> None:
    para, m = find_label(paras, anchor)
    first, second = value[2:4], value[7:9]
    y = re.compile(r"20(\s*)/\s*20").search(para.text, m.end())
    if not y:
        return _insert_after(para, m.end(), value)
    # Right part first so that the left offset stays valid.
    D.insert_text(para.p, y.end(), second)
    spaces = len(y.group(1))
    D.delete_range(para.p, y.start() + 2, max(0, spaces - 4))
    D.insert_text(para.p, y.start() + 2, first + " ")


# ----------------------------------------------------------------------------- main


def active(f: Field, values: dict) -> bool:
    return condition_holds(f.when, values)


def _display(f: Field, value):
    def up(v):
        return v.upper() if f.uppercase and isinstance(v, str) else v

    if isinstance(value, list):
        return [[up(c) for c in row] if isinstance(row, list) else up(row) for row in value]
    return up(value)


def fill_document(template: str | Path, fields: list[Field], values: dict,
                  out_path: str | Path) -> FillReport:
    doc = docx.Document(str(template))
    report = FillReport()
    for f in fields:
        value = values.get(f.key)
        if f.kind not in WRITE_KINDS or value in (None, "", []) or not active(f, values):
            continue
        if f.kind != STRIKE and f.anchor is None:
            continue
        value = _display(f, value)
        paras = D.paragraphs(doc)  # re-read: previous edits change offsets
        try:
            if f.kind == TEXT:
                write_text(paras, f.anchor, value)
            elif f.kind == BOXES:
                write_boxes(paras, f.anchor, value)
            elif f.kind == MARK:
                write_mark(paras, f, values[f.key])
            elif f.kind == STRIKE:
                write_strike(paras, f, values[f.key])
            elif f.kind == ROW:
                write_row(paras, f.anchor, value if isinstance(value, list) else [value])
            elif f.kind == TABLE:
                for problem in write_table(doc, f.anchor, value):
                    report.skipped.append((f.key, problem))
            elif f.kind == LIST:
                write_list(paras, f.anchor, value if isinstance(value, list) else [value])
            elif f.kind == ACADEMIC_YEAR:
                write_academic_year(paras, f.anchor, value)
            report.written.append(f.key)
        except AnchorNotFound as exc:
            log.warning("Field %s not written: %s", f.key, exc)
            report.skipped.append((f.key, str(exc)))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return report
