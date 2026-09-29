"""FastAPI application: REST API + static web chat."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings
from .service import FormService, InvalidDocument, NotFound

STATIC = Path(__file__).parent / "static"


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


def create_app(service: FormService | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = service or FormService(Settings.from_env())
        yield

    app = FastAPI(title="AI Form Filler", version="1.0.0", lifespan=lifespan,
                  description="Nahrajte .docx tlačivo, AI asistent sa opýta na údaje a vráti vyplnené PDF.")

    def svc() -> FormService:
        return app.state.service

    @app.get("/api/health")
    def health():
        s = svc()
        return {"status": "ok", "llm": s.settings.llm_provider,
                "model": s.settings.llm_model if s.settings.llm_provider != "mock" else None}

    @app.post("/api/sessions", status_code=201)
    async def create_session(file: UploadFile = File(...)):
        if not (file.filename or "").lower().endswith(".docx"):
            raise HTTPException(415, "Nahrajte dokument vo formáte .docx.")
        content = await file.read()
        try:
            # LLM + document parsing are blocking: keep them off the event loop.
            return await run_in_threadpool(svc().create_session, file.filename, content)
        except InvalidDocument as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/sessions")
    def list_sessions():
        return svc().list_sessions()

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str):
        try:
            return svc().get_session(session_id)
        except NotFound as exc:
            raise HTTPException(404, "Konverzácia neexistuje.") from exc

    @app.post("/api/sessions/{session_id}/messages")
    def send_message(session_id: str, body: MessageIn):
        try:
            return svc().send_message(session_id, body.content)
        except NotFound as exc:
            raise HTTPException(404, "Konverzácia neexistuje.") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/sessions/{session_id}/pdf")
    def download_pdf(session_id: str):
        try:
            path = svc().pdf_path(session_id)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        return FileResponse(path, media_type="application/pdf", filename="vyplnene_tlacivo.pdf")

    @app.post("/api/sessions/{session_id}/pdf")
    def rerender_pdf(session_id: str):
        try:
            svc().render_pdf(session_id)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"pdf_url": f"/api/sessions/{session_id}/pdf"}

    @app.delete("/api/sessions/{session_id}", status_code=204)
    def delete_session(session_id: str):
        try:
            svc().delete_session(session_id)
        except NotFound as exc:
            raise HTTPException(404, "Konverzácia neexistuje.") from exc

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
    return app


app = create_app()
