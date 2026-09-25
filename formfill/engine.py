"""Conversation engine: decides what to ask, validates what the brain extracted and moves
the session through its phases.

    collecting  -> asking for missing fields
    review      -> summary shown, waiting for confirmation or corrections
    done        -> confirmed, PDF generated (further corrections go back to review)

The engine is pure logic over a JSON-serialisable :class:`ConversationState`; persistence
and PDF rendering live in :mod:`formfill.service`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .brains import SKIP_WORDS, TurnContext, TurnResult, match_option, question_for
from .fields import CONTROL, LIST, TABLE, Field, condition_holds
from .validators import ValidationError, loose, run_validator

COLLECTING, REVIEW, DONE = "collecting", "review", "done"
FOCUS_SIZE = 3


@dataclass
class ConversationState:
    values: dict = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    phase: str = COLLECTING

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "ConversationState":
        return cls(**data) if data else cls()


@dataclass
class Reply:
    text: str
    phase: str
    ready: bool = False  # all confirmed -> render the PDF
    source: str = "rule"
    errors: dict = field(default_factory=dict)


class ConversationEngine:
    def __init__(self, title: str, description: str, fields: list[Field],
                 derive: Callable[[dict], dict], brain):
        self.title = title
        self.description = description
        self.fields = fields
        self.by_key = {f.key: f for f in fields}
        self.derive = derive
        self.brain = brain

    # ------------------------------------------------------------------ queries
    def active(self, f: Field, values: dict) -> bool:
        return condition_holds(f.when, values)

    def askable(self, values: dict) -> list[Field]:
        return [f for f in self.fields if not f.derived and self.active(f, values)]

    def pending(self, state: ConversationState) -> list[Field]:
        return [f for f in self.askable(state.values)
                if f.key not in state.values and f.key not in state.skipped]

    def focus(self, state: ConversationState) -> list[Field]:
        pending = self.pending(state)
        if not pending:
            return []
        group = pending[0].group
        return [f for f in pending if f.group == group][:FOCUS_SIZE]

    def progress(self, state: ConversationState) -> dict:
        fields = self.askable(state.values)
        done = sum(1 for f in fields if f.key in state.values or f.key in state.skipped)
        return {"answered": done, "total": len(fields)}

    def summary(self, state: ConversationState) -> str:
        lines, group = [], None
        for f in self.fields:
            if not self.active(f, state.values) or f.key not in state.values:
                continue
            if f.group != group:
                group = f.group
                lines.append(f"\n**{group}**")
            lines.append(f"- {f.label}: {format_value(state.values[f.key])}")
        return "\n".join(lines).strip()

    # ------------------------------------------------------------------ turns
    def _context(self, state, history, message) -> TurnContext:
        public = {k: v for k, v in state.values.items() if not k.startswith("_")}
        return TurnContext(self.title, self.description, self.askable(state.values),
                           self.focus(state), public, history, message,
                           REVIEW if state.phase in (REVIEW, DONE) else COLLECTING,
                           list(state.asked))

    def start(self, state: ConversationState) -> Reply:
        result = self.brain.turn(self._context(state, [], None))
        intro = (f"Dobrý deň! Nahrali ste tlačivo **{self.title}**. {self.description}\n\n"
                 f"Postupne sa vás opýtam na potrebné údaje; kedykoľvek môžete ktorýkoľvek údaj "
                 f"opraviť alebo povedať viac údajov naraz. Nepovinné údaje môžete preskočiť "
                 f"odpoveďou „nie“.")
        question = self._next_question(state, result, [])
        return Reply(f"{intro}\n\n{question}", state.phase, source=result.source)

    def handle(self, state: ConversationState, history: list[dict], message: str) -> Reply:
        result = self.brain.turn(self._context(state, history, message))
        applied, errors, warnings = self._apply(state, result)
        parts: list[str] = []
        if errors:
            parts.append("Tieto údaje som nemohol prijať:\n" + "\n".join(
                f"- {self.by_key[k].label}: {msg}" for k, msg in errors.items()))
        parts.extend(f"⚠️ {w}" for w in warnings)

        ready = False
        pending = self.pending(state)
        if state.phase == COLLECTING:
            if pending:
                parts.append(self._next_question(state, result, list(errors)))
            else:
                state.phase = REVIEW
                state.asked = []
                parts.append(self._review_prompt(state))
        else:  # REVIEW or DONE
            if pending:  # a correction switched on new fields (e.g. correspondence address)
                state.phase = COLLECTING
                parts.append(self._next_question(state, result, list(errors)))
            elif result.confirmed and not applied and not errors:
                state.phase = DONE
                ready = True
                parts.append("Ďakujem, údaje sú potvrdené. Vypĺňam tlačivo a generujem PDF…")
            elif applied:
                state.phase = REVIEW
                changed = "\n".join(f"- {self.by_key[k].label}: {format_value(state.values[k])}"
                                    for k in applied if k in self.by_key)
                parts.append(f"Upravil som:\n{changed}\n\nJe teraz všetko v poriadku? "
                             f"Napíšte „áno“ a vygenerujem PDF, alebo pošlite ďalšiu opravu.")
            elif not errors:
                parts.append(result.reply or "Ak je všetko správne, napíšte „áno“ – vygenerujem "
                                             "PDF. Ak chcete niečo zmeniť, napíšte opravu, napr. "
                                             "„E-mail: novy@example.org“.")
        return Reply("\n\n".join(p for p in parts if p), state.phase, ready, result.source, errors)

    # ------------------------------------------------------------------ helpers
    def _next_question(self, state: ConversationState, result: TurnResult, errored: list[str]) -> str:
        pending = {f.key for f in self.pending(state)}
        if errored:
            fields = [self.by_key[k] for k in errored if k in pending]
            if fields:
                state.asked = [f.key for f in fields]
                return question_for(fields)
        # Only an LLM-phrased question is reused; rule-based questions are recomputed here,
        # because the answer just applied may have switched conditional fields on or off.
        asked = [k for k in result.asked if k in pending]
        if result.reply and asked and result.source == "llm":
            state.asked = asked
            return result.reply
        focus = self.focus(state)
        if result.reply and not result.asked and "?" in result.reply and result.source == "llm":
            state.asked = [f.key for f in focus]
            return result.reply
        state.asked = [focus[0].key] if focus else []
        return question_for(focus[:1]) if focus else ""

    def _review_prompt(self, state: ConversationState) -> str:
        return ("Mám všetky potrebné údaje. Tu je zhrnutie:\n\n" + self.summary(state) +
                "\n\nSkontrolujte ich prosím. Ak je všetko v poriadku, napíšte „áno“ a vygenerujem "
                "vyplnené tlačivo v PDF. Ak chcete niečo zmeniť, napíšte opravu.")

    def _apply(self, state: ConversationState, result: TurnResult) -> tuple[list[str], dict, list[str]]:
        applied, errors, warnings = [], {}, []
        order = {f.key: i for i, f in enumerate(self.fields)}
        for key in sorted(result.updates, key=lambda k: order.get(k, 1e9)):
            f = self.by_key.get(key)
            if f is None or f.derived:
                continue
            raw = result.updates[key]
            if isinstance(raw, str) and not f.required and loose(raw) in {loose(w) for w in SKIP_WORDS} \
                    and not (f.options and match_option(raw, f.options)):
                result.skipped.append(key)
                continue
            try:
                value = self._coerce(f, raw)
                value, warning = run_validator(f.validator, value, state.values, key)
            except ValidationError as exc:
                errors[key] = str(exc)
                continue
            if state.values.get(key) != value:
                applied.append(key)
            state.values[key] = value
            if key in state.skipped:
                state.skipped.remove(key)
            if warning:
                warnings.append(warning)
        for key in result.skipped:
            f = self.by_key.get(key)
            if f is not None and not f.required and key not in state.skipped:
                state.skipped.append(key)
                state.values.pop(key, None)
        state.values.update(self.derive(state.values))
        return applied, errors, warnings

    @staticmethod
    def _coerce(f: Field, raw: Any) -> Any:
        if f.options:
            if isinstance(raw, bool):
                raw = "áno" if raw else "nie"
            option = match_option(raw, f.options)
            if option is None:
                raise ValidationError(f"„{raw}“ nie je platná možnosť (možnosti: {', '.join(f.options)}).")
            return option
        if f.kind == LIST:
            if isinstance(raw, str):
                raw = [i.strip() for i in raw.replace(";", ",").split(",")]
            return [str(i).strip() for i in raw if str(i).strip()]
        if f.kind == TABLE:
            return raw
        if f.kind == CONTROL and isinstance(raw, bool):
            return "áno" if raw else "nie"
        if isinstance(raw, (list, dict)):
            if f.validator in ("averages",):
                return raw
            raise ValidationError("Očakávam jednu hodnotu, nie zoznam.")
        text = str(raw).strip()
        if not text:
            raise ValidationError("Hodnota je prázdna.")
        return text


def format_value(value: Any) -> str:
    if isinstance(value, list):
        if value and all(isinstance(r, list) for r in value):
            return "; ".join(
                f"{row[0]}: {', '.join(c for c in row[1:] if c)}" if len(row) > 1 and any(row[1:])
                else (row[0] if row else "") for row in value)
        return ", ".join(str(v) for v in value)
    return str(value)
