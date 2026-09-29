"""HTTP API: upload, chat, persistence across restarts, PDF download."""

from fastapi.testclient import TestClient

from formfill.api import create_app
from formfill.brains import RuleBrain
from formfill.devtools.samples import VZOR1
from formfill.service import FormService

from .conftest import fake_converter

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def client_for(settings):
    return TestClient(create_app(FormService(settings, brain=RuleBrain(), converter=fake_converter)))


def as_answer(value):
    if isinstance(value, list):
        if value and isinstance(value[0], list):
            return "\n".join(f"{row[0]}: {', '.join(row[1:])}" for row in value)
        return "; ".join(value)
    return value


def test_health(settings):
    with client_for(settings) as c:
        assert c.get("/api/health").json()["llm"] == "mock"


def test_rejects_non_docx(settings):
    with client_for(settings) as c:
        assert c.post("/api/sessions", files={"file": ("x.pdf", b"%PDF", "application/pdf")}).status_code == 415
        assert c.post("/api/sessions", files={"file": ("x.docx", b"garbage", DOCX)}).status_code == 422


def test_full_conversation_survives_restart(settings, form_bytes):
    with client_for(settings) as c:
        r = c.post("/api/sessions", files={"file": ("formular.docx", form_bytes, DOCX)})
        assert r.status_code == 201
        data = r.json()
        sid = data["session"]["id"]
        assert data["session"]["form_id"] == "prihlaska_vs_bc"
        assert "Prihláška na vysokoškolské štúdium" in data["reply"]
        c.post(f"/api/sessions/{sid}/messages", json={"content": "bakalárske"})

    # "Restart": a brand-new app + service over the same database.
    with client_for(settings) as c:
        detail = c.get(f"/api/sessions/{sid}").json()
        assert detail["values"]["study_level"] == "bakalárske"
        assert [m["role"] for m in detail["messages"]] == ["assistant", "user", "assistant"]
        assert c.get(f"/api/sessions/{sid}/pdf").status_code == 404

        service = c.app.state.service
        for _ in range(100):
            state = service.get_session(sid)
            if state["phase"] != "collecting":
                break
            from formfill.db import FormSession
            with service.Session() as db:
                asked = db.get(FormSession, sid).state["asked"][0]
            r = c.post(f"/api/sessions/{sid}/messages", json={"content": as_answer(VZOR1.get(asked, "nie"))})
            assert r.status_code == 200
        assert state["phase"] == "review"
        r = c.post(f"/api/sessions/{sid}/messages", json={"content": "áno"}).json()
        assert r["session"]["phase"] == "done" and r["session"]["pdf_ready"]
        pdf = c.get(f"/api/sessions/{sid}/pdf")
        assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
        assert [s["id"] for s in c.get("/api/sessions").json()] == [sid]


def test_unknown_session_and_empty_message(settings):
    with client_for(settings) as c:
        assert c.get("/api/sessions/nope").status_code == 404
        assert c.post("/api/sessions/nope/messages", json={"content": "x"}).status_code == 404
        assert c.post("/api/sessions/nope/messages", json={"content": ""}).status_code == 422


def test_delete_session(settings, form_bytes):
    with client_for(settings) as c:
        sid = c.post("/api/sessions", files={"file": ("f.docx", form_bytes, DOCX)}).json()["session"]["id"]
        assert c.delete(f"/api/sessions/{sid}").status_code == 204
        assert c.get(f"/api/sessions/{sid}").status_code == 404


def test_frontend_is_served(settings):
    with client_for(settings) as c:
        assert "AI vypĺňanie tlačív" in c.get("/").text


def test_document_without_fields_is_rejected(settings, tmp_path):
    import docx
    d = docx.Document()
    d.add_paragraph("Lorem ipsum dolor sit amet, consectetur adipiscing elit.")
    path = tmp_path / "lorem.docx"
    d.save(path)
    with client_for(settings) as c:
        r = c.post("/api/sessions", files={"file": ("lorem.docx", path.read_bytes(), DOCX)})
        assert r.status_code == 422 and "nenašiel žiadne polia" in r.json()["detail"]
        assert c.get("/api/sessions").json() == []
