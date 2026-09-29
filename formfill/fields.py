"""Form field model shared by known-form definitions, the LLM-derived generic schema,
the conversation engine and the DOCX filler.

Everything here is plain data (JSON-serialisable) so that a form schema can be stored
in the database next to the conversation and a session can be resumed after restart.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# How a value is written into the document.
TEXT = "text"  # value inserted right after a label ("Meno:  JANA")
BOXES = "boxes"  # one character per narrow box cell (dates, rodné číslo, codes)
MARK = "mark"  # "X" next to the chosen option (Pohlavie, typ strednej školy)
STRIKE = "strike"  # rejected options are struck through ("Nehodiace sa prečiarknite")
ROW = "row"  # list of values into consecutive empty cells after a label
TABLE = "table"  # list of rows into the empty rows of a table
LIST = "list"  # list of values into empty numbered lines (Prílohy)
ACADEMIC_YEAR = "academic_year"  # "Akademický rok: 20__ / 20__"
CONTROL = "control"  # asked in the conversation, never written (drives conditions)

WRITE_KINDS = {TEXT, BOXES, MARK, STRIKE, ROW, TABLE, LIST, ACADEMIC_YEAR}


@dataclass
class Anchor:
    """Where a value lives in the document.

    ``label``  label text without colon / footnote marker, e.g. "Ulica a číslo".
    ``after``  optional section marker; the label is searched only after it.
    ``nth``    which occurrence of the label (after the marker) to use.
    ``table``  for TABLE fields: text of a header cell identifying the table.
    """

    label: str | None = None
    after: str | None = None
    nth: int = 0
    table: str | None = None
    colon: bool = True


@dataclass
class Field:
    key: str
    label: str
    question: str
    group: str = "Všeobecné"
    kind: str = TEXT
    required: bool = True
    anchor: Anchor | None = None
    options: list[str] = field(default_factory=list)
    # Document text of each option, when it differs from the option value.
    option_texts: dict[str, str] = field(default_factory=dict)
    validator: str | None = None
    uppercase: bool = True
    when: dict | None = None  # condition, see ``condition_holds``
    help: str = ""
    columns: list[str] = field(default_factory=list)  # TABLE column names
    default: Any = None
    derived: bool = False  # filled automatically from other values, never asked

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Field":
        data = dict(data)
        anchor = data.pop("anchor", None)
        return cls(anchor=Anchor(**anchor) if anchor else None, **data)


def condition_holds(cond: dict | None, values: dict) -> bool:
    """Tiny, serialisable condition language.

    {"field": "k", "equals": v} | {"field": "k", "not_equals": v}
    {"field": "k", "in": [..]}   | {"field": "k", "not_in": [..]}
    {"field": "k", "filled": true}
    {"all": [cond, ...]}         | {"any": [cond, ...]}
    Comparisons of strings are case-insensitive.
    """
    if not cond:
        return True
    if "all" in cond:
        return all(condition_holds(c, values) for c in cond["all"])
    if "any" in cond:
        return any(condition_holds(c, values) for c in cond["any"])

    value = values.get(cond["field"])
    norm = _norm(value)
    if "equals" in cond:
        return norm == _norm(cond["equals"])
    if "not_equals" in cond:
        return value is not None and norm != _norm(cond["not_equals"])
    if "in" in cond:
        return norm in {_norm(v) for v in cond["in"]}
    if "not_in" in cond:
        return value is not None and norm not in {_norm(v) for v in cond["not_in"]}
    if "filled" in cond:
        return bool(value not in (None, "", [])) == bool(cond["filled"])
    raise ValueError(f"Unknown condition: {cond}")


def _norm(value: Any) -> Any:
    return value.strip().casefold() if isinstance(value, str) else value


def schema_to_json(fields: list[Field]) -> list[dict]:
    return [f.to_dict() for f in fields]


def schema_from_json(data: list[dict]) -> list[Field]:
    return [Field.from_dict(d) for d in data]
