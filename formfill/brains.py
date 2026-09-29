"""The two "brains" behind the assistant.

``LLMBrain`` asks a chat model (Gemma via OpenRouter by default) to extract values from
the user's message and to phrase the next question. ``RuleBrain`` is a deterministic,
offline implementation of the same interface: it serves as the mock LLM for tests and
local use without an API key, and as an automatic fallback when the LLM call fails, so
a conversation never dead-ends on a flaky free-tier endpoint.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .fields import CONTROL, LIST, TABLE, Anchor, Field
from .llm.client import ChatModel, LLMError, extract_json
from .validators import loose

log = logging.getLogger(__name__)

SKIP_WORDS = {"nie", "nemam", "nemám", "-", "—", "ziadne", "žiadne", "ziadny", "žiadny",
              "preskoc", "preskoč", "preskocit", "preskočiť", "neuvadzam", "neuvádzam", "nechcem",
              "no", "none", "skip", "n/a", "x"}
YES_WORDS = {"ano", "áno", "a", "jo", "hej", "ok", "okej", "yes", "y", "suhlasim", "súhlasím",
             "potvrdzujem", "spravne", "správne", "je to spravne", "je to správne", "sedi", "sedí",
             "v poriadku", "vsetko sedi", "všetko sedí", "generuj", "vygeneruj"}


@dataclass
class TurnContext:
    form_title: str
    form_description: str
    fields: list[Field]  # active, askable fields (whole schema, for free-form answers)
    focus: list[Field]  # what should be asked next
    values: dict
    history: list[dict]
    user_message: str | None
    phase: str  # "collecting" | "review"
    last_asked: list[str] = field(default_factory=list)


@dataclass
class TurnResult:
    updates: dict = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    confirmed: bool = False
    asked: list[str] = field(default_factory=list)
    reply: str = ""
    source: str = "rule"


@dataclass
class DocumentOutline:
    text: str  # beginning of the document text, for context
    slots: list[dict]  # {"id", "label", "nth", "context"}


def question_for(fields: list[Field]) -> str:
    lines = []
    for f in fields:
        q = f.question
        if f.options and f.kind != TABLE:
            q += f" (možnosti: {', '.join(f.options)})"
        if not f.required:
            q += " – nepovinné"
        lines.append(q)
    return lines[0] if len(lines) == 1 else "\n".join(f"• {line}" for line in lines)


def match_option(value: Any, options: list[str]) -> str | None:
    key = loose(value)
    if not key:
        return None
    for opt in options:
        if loose(opt) == key:
            return opt
    hits = [o for o in options if loose(o).startswith(key) or key.startswith(loose(o))]
    return hits[0] if len(hits) == 1 else None


# ------------------------------------------------------------------------ RuleBrain


class RuleBrain:
    """Deterministic assistant: one question at a time, answer maps to the asked field."""

    name = "rule"

    def turn(self, ctx: TurnContext) -> TurnResult:
        result = TurnResult(source=self.name)
        msg = (ctx.user_message or "").strip()
        if ctx.phase == "review":
            if loose(msg).rstrip(".!") in YES_WORDS:
                result.confirmed = True
            else:
                result.updates.update(self._parse_corrections(msg, ctx.fields))
                if not result.updates:
                    result.reply = ("Nerozumiem, čo chcete zmeniť. Napíšte napr. „email: novy@mail.sk“, "
                                    "alebo „áno“ ak je všetko správne.")
            return result

        if msg and ctx.last_asked:
            asked = next((f for f in ctx.fields if f.key == ctx.last_asked[0]), None)
            if asked is not None:
                self._interpret(asked, msg, result)
        if ctx.focus:
            nxt = [f for f in ctx.focus if f.key not in result.updates and f.key not in result.skipped]
            if nxt:
                result.asked = [nxt[0].key]
                result.reply = question_for(nxt[:1])
        return result

    @staticmethod
    def _interpret(f: Field, msg: str, result: TurnResult) -> None:
        low = loose(msg).rstrip(".!")
        if not f.required and low in {loose(w) for w in SKIP_WORDS} and not (
                f.options and match_option(msg, f.options)):
            result.skipped.append(f.key)
            return
        if f.options:
            if low in {"", "ok", "predvolene"} and f.default:
                result.updates[f.key] = f.default
            else:
                result.updates[f.key] = match_option(msg, f.options) or msg
        elif f.kind == TABLE:
            rows = []
            for line in re.split(r"[\n;]+", msg):
                if not line.strip():
                    continue
                if ":" in line:
                    name, rest = line.split(":", 1)
                    rows.append([name.strip()] + [c.strip() for c in re.split(r"[,\s]+", rest) if c.strip()])
                else:
                    rows.append([c.strip() for c in line.split(",")])
            result.updates[f.key] = rows
        elif f.kind == LIST:
            result.updates[f.key] = [i.strip() for i in re.split(r"[\n;,]+", msg) if i.strip()]
        else:
            result.updates[f.key] = msg

    @staticmethod
    def _parse_corrections(msg: str, fields: list[Field]) -> dict:
        """Understand "label: value" / "key = value" lines during review."""
        updates = {}
        for line in msg.splitlines():
            m = re.match(r"\s*([^:=]+?)\s*[:=]\s*(.+)$", line)
            if not m:
                continue
            name, value = loose(m.group(1)), m.group(2).strip()
            for f in fields:
                if name in (loose(f.key), loose(f.label)) or loose(f.label).endswith(name):
                    updates[f.key] = value
                    break
        return updates

    def derive_fields(self, outline: DocumentOutline) -> tuple[str, str, list[Field]]:
        fields = [Field(key=f"field_{s['id']}", label=s["label"], question=f"Uveďte: {s['label']}",
                        group=s.get("context") or "Údaje", required=False,
                        anchor=Anchor(s["label"], nth=s["nth"]))
                  for s in outline.slots]
        first_line = next((ln for ln in outline.text.splitlines() if ln.strip()), "Tlačivo")
        return first_line.strip()[:120], "Neznáme tlačivo – vyplním polia podľa ich popisov.", fields


# ------------------------------------------------------------------------- LLMBrain

TURN_SYSTEM = """Si priateľský asistent, ktorý pomáha používateľovi vyplniť tlačivo „{title}“.
O tlačive: {description}

Tvoja úloha v každom kroku:
1. Z poslednej správy používateľa vytiahni hodnoty pre ĽUBOVOĽNÉ polia zo zoznamu FIELDS (nielen pre tie, na ktoré si sa pýtal). Nikdy si nič nevymýšľaj a nedopĺňaj hodnoty, ktoré používateľ nepovedal.
2. Polia s "options" vyplň presne jednou z uvedených možností. Tabuľky (kind="table") zapíš ako zoznam riadkov, každý riadok je zoznam reťazcov v poradí "columns". Zoznamy (kind="list") ako JSON pole reťazcov. Dátumy vo formáte DD.MM.RRRR. Pole kind="control" je otázka áno/nie.
3. Ak používateľ pri nepovinnom poli povie, že údaj nemá alebo ho nechce uviesť, pridaj kľúč do "skipped".
4. Do "reply" napíš krátku odpoveď po slovensky (alebo jazykom používateľa): prípadne krátko potvrď prijaté údaje a opýtaj sa na ďalšie chýbajúce polia – prednostne na tie zo zoznamu FOCUS, ktoré po tvojej extrakcii ešte ostanú nevyplnené, naraz najviac 3 súvisiace. Nepýtaj sa na polia, ktoré už majú hodnotu. Ak pole má "default", môžeš ho ponúknuť. Ak treba, stručne vysvetli, čo sa do poľa píše (pole "help").
5. Do "asked" daj kľúče polí, na ktoré sa v "reply" pýtaš.
6. V režime REVIEW používateľ kontroluje zhrnutie: ak potvrdí, že je všetko správne, nastav "confirmed": true; ak niečo opravuje, zapíš opravu do "updates" a "confirmed" nechaj false.

Odpovedz VÝHRADNE jedným JSON objektom v tvare:
{{"updates": {{"kluc": "hodnota"}}, "skipped": [], "confirmed": false, "asked": [], "reply": "..."}}"""

SCHEMA_SYSTEM = """Analyzuješ prázdne tlačivo (formulár) vo formáte Word. Dostaneš začiatok jeho textu a zoznam
nájdených popisov polí (label) s identifikátorom "slot". Urči, o aký dokument ide, a pre každý slot, ktorý má
vyplniť žiadateľ (nie úrad, škola, komisia ani podpis), vytvor pole formulára.
Odpovedz VÝHRADNE JSON objektom:
{"title": "názov tlačiva", "description": "1-2 vety o účele tlačiva",
 "fields": [{"slot": 3, "key": "snake_case_kluc", "label": "zrozumiteľný názov", "question": "otázka pre používateľa po slovensky",
             "group": "sekcia", "required": true, "validator": null}]}
Povolené hodnoty "validator": null, "date", "email", "phone", "zip", "rodne_cislo", "year"."""


class LLMBrain:
    name = "llm"

    def __init__(self, chat: ChatModel, fallback: RuleBrain | None = None, history_turns: int = 10):
        self.chat = chat
        self.fallback = fallback or RuleBrain()
        self.history_turns = history_turns

    # ---- conversation turn
    def turn(self, ctx: TurnContext) -> TurnResult:
        try:
            data = extract_json(self.chat.complete(self._turn_messages(ctx)))
            return self._parse_turn(data, ctx)
        except (LLMError, TypeError, ValueError) as exc:
            log.warning("LLM turn failed, using rule-based fallback: %s", exc)
            result = self.fallback.turn(ctx)
            result.source = "rule-fallback"
            return result

    def _turn_messages(self, ctx: TurnContext) -> list[dict]:
        def describe(f: Field) -> dict:
            d: dict[str, Any] = {"key": f.key, "label": f.label, "kind": f.kind,
                                 "required": f.required, "group": f.group}
            for attr in ("options", "columns", "help", "default"):
                if getattr(f, attr):
                    d[attr] = getattr(f, attr)
            if f.key in ctx.values:
                d["value"] = ctx.values[f.key]
            return d

        history = "\n".join(f"{'Používateľ' if m['role'] == 'user' else 'Asistent'}: {m['content']}"
                            for m in ctx.history[-self.history_turns:])
        state = {
            "PHASE": ctx.phase.upper(),
            "FOCUS": [{"key": f.key, "question": f.question} for f in ctx.focus],
            "FIELDS": [describe(f) for f in ctx.fields],
        }
        user = (f"STAV:\n{json.dumps(state, ensure_ascii=False)}\n\n"
                f"HISTÓRIA KONVERZÁCIE:\n{history or '(zatiaľ žiadna)'}\n\n"
                f"POSLEDNÁ SPRÁVA POUŽÍVATEĽA:\n{ctx.user_message or '(začiatok konverzácie – úvodný pozdrav už zaznel, polož len prvú otázku)'}")
        return [{"role": "system", "content": TURN_SYSTEM.format(title=ctx.form_title,
                                                                 description=ctx.form_description)},
                {"role": "user", "content": user}]

    @staticmethod
    def _parse_turn(data: dict, ctx: TurnContext) -> TurnResult:
        known = {f.key for f in ctx.fields}
        updates = data.get("updates") or {}
        if not isinstance(updates, dict):
            raise ValueError("updates must be an object")
        return TurnResult(
            updates={k: v for k, v in updates.items() if k in known and v not in (None, "")},
            skipped=[k for k in data.get("skipped") or [] if k in known],
            confirmed=bool(data.get("confirmed")) and ctx.phase == "review",
            asked=[k for k in data.get("asked") or [] if k in known],
            reply=str(data.get("reply") or "").strip(),
            source="llm",
        )

    # ---- schema of an unknown form
    def derive_fields(self, outline: DocumentOutline) -> tuple[str, str, list[Field]]:
        try:
            user = json.dumps({"text": outline.text[:4000],
                               "slots": [{"slot": s["id"], "label": s["label"], "context": s["context"]}
                                         for s in outline.slots]}, ensure_ascii=False)
            data = extract_json(self.chat.complete([{"role": "system", "content": SCHEMA_SYSTEM},
                                                    {"role": "user", "content": user}]))
            slots = {s["id"]: s for s in outline.slots}
            fields, seen = [], set()
            for item in data.get("fields") or []:
                slot = slots.get(item.get("slot"))
                key = re.sub(r"\W+", "_", str(item.get("key") or "")).strip("_").lower()
                if not slot or not key or key in seen:
                    continue
                seen.add(key)
                validator = item.get("validator")
                fields.append(Field(
                    key=key, label=str(item.get("label") or slot["label"]),
                    question=str(item.get("question") or f"Uveďte: {slot['label']}"),
                    group=str(item.get("group") or slot["context"] or "Údaje"),
                    required=bool(item.get("required", True)),
                    validator=validator if validator in {"date", "email", "phone", "zip",
                                                         "rodne_cislo", "year"} else None,
                    uppercase=validator != "email",
                    anchor=Anchor(slot["label"], nth=slot["nth"])))
            if not fields:
                raise ValueError("LLM returned no usable fields")
            return str(data.get("title") or "Tlačivo"), str(data.get("description") or ""), fields
        except (LLMError, TypeError, ValueError, AttributeError) as exc:
            log.warning("LLM schema derivation failed, using rule-based fallback: %s", exc)
            return self.fallback.derive_fields(outline)
