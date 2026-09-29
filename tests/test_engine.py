"""Conversation engine with the rule brain (mock LLM) and with a scripted fake LLM."""

import json

from formfill.brains import LLMBrain, RuleBrain
from formfill.engine import COLLECTING, DONE, REVIEW, ConversationEngine, ConversationState
from formfill.fields import CONTROL, Field
from formfill.forms import prihlaska
from formfill.llm.client import LLMError

SMALL = [
    Field("name", "Meno", "Ako sa voláte?", "Osobné"),
    Field("email", "E-mail", "Váš e-mail?", "Osobné", validator="email", uppercase=False),
    Field("has_pet", "Má zviera", "Máte zviera?", "Iné", kind=CONTROL, options=["áno", "nie"]),
    Field("pet", "Zviera", "Aké zviera?", "Iné", when={"field": "has_pet", "equals": "áno"}),
    Field("note", "Poznámka", "Poznámka?", "Iné", required=False),
]


def engine(brain=None, fields=SMALL, derive=lambda v: {}):
    return ConversationEngine("Test", "Testovacie tlačivo.", fields, derive, brain or RuleBrain())


def test_rule_flow_to_done():
    e, st = engine(), ConversationState()
    assert "Ako sa voláte?" in e.start(st).text
    e.handle(st, [], "Jana")
    e.handle(st, [], "jana@example.org")
    r = e.handle(st, [], "áno")
    assert "Aké zviera?" in r.text  # conditional field activated
    e.handle(st, [], "mačka")
    r = e.handle(st, [], "nie")  # optional note skipped
    assert st.phase == REVIEW and "zhrnutie" in r.text and "mačka" in r.text
    assert st.skipped == ["note"]
    r = e.handle(st, [], "áno")
    assert r.ready and st.phase == DONE


def test_invalid_value_is_rejected_and_asked_again():
    e, st = engine(), ConversationState()
    e.start(st)
    e.handle(st, [], "Jana")
    r = e.handle(st, [], "zly-email")
    assert "email" not in st.values
    assert "nemohol prijať" in r.text and "Váš e-mail?" in r.text
    assert st.asked == ["email"]


def test_condition_off_hides_field():
    e, st = engine(), ConversationState(values={"name": "J", "email": "a@b.sk", "has_pet": "nie"})
    assert [f.key for f in e.pending(st)] == ["note"]


def test_review_correction_and_new_field_activation():
    st = ConversationState(values={"name": "J", "email": "a@b.sk", "has_pet": "nie"},
                           skipped=["note"], phase=REVIEW)
    e = engine()
    r = e.handle(st, [], "E-mail: novy@example.org")
    assert st.values["email"] == "novy@example.org" and "Upravil som" in r.text and st.phase == REVIEW
    r = e.handle(st, [], "Má zviera: áno")  # switches on "pet" -> back to collecting
    assert st.phase == COLLECTING and "Aké zviera?" in r.text


def test_state_roundtrip():
    st = ConversationState(values={"a": 1}, skipped=["b"], asked=["c"], phase=REVIEW)
    assert ConversationState.from_dict(json.loads(json.dumps(st.to_dict()))) == st


def test_prihlaska_asks_rodne_cislo_only_for_slovaks():
    e = engine(fields=prihlaska.FIELDS, derive=prihlaska.derive)
    st = ConversationState(values={"citizenship": "ukrajinské", **prihlaska.derive({"citizenship": "ukrajinské"})})
    keys = [f.key for f in e.pending(st)]
    assert "rodne_cislo" not in keys and "rodne_cislo_foreigner" in keys and "stay_street" in keys


# ------------------------------------------------------------------ LLM brain


class FakeChat:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, *, json_mode=True):
        self.calls.append(messages)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)


def test_llm_extracts_several_fields_at_once():
    chat = FakeChat(
        {"updates": {}, "asked": ["name", "email"], "reply": "Ako sa voláte a aký máte e-mail?"},
        "```json\n" + json.dumps({"updates": {"name": "Jana", "email": "JANA@example.org", "bogus": 1},
                                  "asked": ["has_pet"], "reply": "Ďakujem! Máte zviera?"}) + "\n```",
    )
    e, st = engine(LLMBrain(chat)), ConversationState()
    assert "Ako sa voláte a aký máte e-mail?" in e.start(st).text
    r = e.handle(st, [], "Som Jana, jana@example.org")
    assert st.values == {"name": "Jana", "email": "jana@example.org"}  # validated, unknown key dropped
    assert r.text == "Ďakujem! Máte zviera?" and st.asked == ["has_pet"]
    prompt = chat.calls[1][1]["content"]
    assert '"FOCUS"' in prompt and "Som Jana" in prompt


def test_llm_invalid_value_triggers_deterministic_reask():
    chat = FakeChat({"updates": {"email": "nope"}, "asked": ["has_pet"], "reply": "Máte zviera?"})
    st = ConversationState(values={"name": "J"}, asked=["email"])
    r = engine(LLMBrain(chat)).handle(st, [], "nope")
    assert "Váš e-mail?" in r.text and "email" not in st.values


def test_llm_failure_falls_back_to_rules():
    chat = FakeChat(LLMError("503"), "not json at all")
    e, st = engine(LLMBrain(chat)), ConversationState()
    r = e.start(st)
    assert r.source == "rule-fallback" and "Ako sa voláte?" in r.text
    e.handle(st, [], "Jana")
    assert st.values["name"] == "Jana"


def test_llm_confirmation_in_review():
    chat = FakeChat({"updates": {}, "confirmed": True, "reply": "Super."})
    st = ConversationState(values={"name": "J", "email": "a@b.sk", "has_pet": "nie"}, skipped=["note"], phase=REVIEW)
    assert engine(LLMBrain(chat)).handle(st, [], "všetko sedí").ready


def test_after_done_questions_get_download_hint_not_confusion():
    st = ConversationState(values={"name": "J", "email": "a@b.sk", "has_pet": "nie"},
                           skipped=["note"], phase=DONE)
    r = engine().handle(st, [], "where is the pdf")
    assert "Stiahnuť PDF" in r.text and "Nerozumiem" not in r.text
    assert st.phase == DONE and not r.ready
