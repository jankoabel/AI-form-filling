"""Unknown forms (generic path) and the real LibreOffice conversion."""

import pytest

from formfill.brains import LLMBrain, RuleBrain
from formfill.forms import registry
from formfill.pdf import docx_to_pdf, soffice_binary

from .test_engine import FakeChat


def test_known_form_detected(form_path):
    form = registry.detect_known_form(registry.document_text(form_path))
    assert form is not None and form.form_id == "prihlaska_vs_bc"


def test_unknown_form_outline(generic_form):
    assert registry.detect_known_form(registry.document_text(generic_form)) is None
    labels = [s["label"] for s in registry.outline(generic_form).slots]
    assert labels == ["Meno a priezvisko", "Adresa", "EČV vozidla", "Dátum", "Podpis"]


def test_llm_derives_schema_for_unknown_form(generic_form):
    outline = registry.outline(generic_form)
    chat = FakeChat({"title": "Žiadosť o parkovaciu kartu", "description": "Žiadosť rezidenta.",
                     "fields": [{"slot": 0, "key": "full name", "label": "Meno", "question": "Meno?"},
                                {"slot": 3, "key": "date", "label": "Dátum", "question": "Dátum?",
                                 "validator": "date"},
                                {"slot": 99, "key": "ghost"}]})
    title, _, fields = LLMBrain(chat).derive_fields(outline)
    assert title == "Žiadosť o parkovaciu kartu"
    assert [(f.key, f.anchor.label, f.validator) for f in fields] == [
        ("full_name", "Meno a priezvisko", None), ("date", "Dátum", "date")]


def test_generic_session_end_to_end(service, generic_form, tmp_path):
    data = service.create_session("ziadost.docx", generic_form.read_bytes())
    sid = data["session"]["id"]
    assert data["session"]["form_id"] is None
    for answer in ["Ján Novák", "Hlavná 1, Bratislava", "BA123XY", "1.1.2027", "nie"]:
        service.send_message(sid, answer)
    assert service.send_message(sid, "áno")["session"]["pdf_ready"]
    import docx
    filled = docx.Document(str(service.pdf_path(sid)))  # fake converter copies the DOCX
    text = "\n".join(p.text for p in filled.paragraphs)
    assert "Meno a priezvisko:  JÁN NOVÁK" in text and "BA123XY" in text


@pytest.mark.skipif(not soffice_binary(), reason="LibreOffice not installed")
def test_real_pdf_conversion(tmp_path, form_path):
    from formfill.devtools.samples import VZOR2
    from formfill.filler import fill_document
    from formfill.forms import prihlaska
    values = {**VZOR2, **prihlaska.derive(VZOR2)}
    out = tmp_path / "out.docx"
    fill_document(form_path, prihlaska.FIELDS, values, out)
    pdf = docx_to_pdf(out)
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 10_000
