"""Command-line client for the FastAPI service.

    formfill new formular.docx     upload a form and start chatting
    formfill chat <id>             continue a saved conversation (also after restart)
    formfill list                  list conversations
    formfill download <id>         download the filled PDF
    formfill demo vzor2            render a sample answer set without a conversation
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

app = typer.Typer(help="AI asistent na vypĺňanie tlačív (CLI klient).", no_args_is_help=True)
console = Console()
API = os.getenv("FORMFILL_API", "http://localhost:8000")
EXIT = {"/koniec", "/exit", "/quit", "/q"}


def client() -> httpx.Client:
    return httpx.Client(base_url=API, timeout=300)


def _fail(resp: httpx.Response) -> None:
    if resp.is_error:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = resp.text
        console.print(f"[red]Chyba {resp.status_code}: {detail}[/red]")
        raise typer.Exit(1)


def _say(text: str) -> None:
    console.print(Markdown(text), style="cyan")
    console.print()


def _progress(session: dict) -> str:
    p = session["progress"]
    return f"[dim]{p['answered']}/{p['total']} · {session['phase']}[/dim]"


def _chat_loop(c: httpx.Client, session_id: str, output: Path | None) -> None:
    console.print(f"[dim]ID konverzácie: {session_id} – pokračovať neskôr: formfill chat {session_id}. "
                  f"Ukončiť: /koniec[/dim]\n")
    while True:
        try:
            text = console.input("[bold green]Vy> [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            text = "/koniec"
        if text in EXIT:
            console.print(f"[dim]Konverzácia je uložená. Pokračujte: formfill chat {session_id}[/dim]")
            return
        if not text:
            continue
        with console.status("Asistent premýšľa…"):
            resp = c.post(f"/api/sessions/{session_id}/messages", json={"content": text})
        _fail(resp)
        data = resp.json()
        _say(data["reply"])
        console.print(_progress(data["session"]))
        if data["session"]["pdf_ready"] and data["session"]["phase"] == "done":
            _download(c, session_id, output or Path(f"vyplnene_{session_id[:8]}.pdf"))


def _download(c: httpx.Client, session_id: str, output: Path) -> None:
    resp = c.get(f"/api/sessions/{session_id}/pdf")
    _fail(resp)
    output.write_bytes(resp.content)
    console.print(f"[bold]📄 PDF uložené: {output.resolve()}[/bold]")


@app.command()
def new(form: Path = typer.Argument(..., exists=True, dir_okay=False, help="Tlačivo .docx"),
        output: Path = typer.Option(None, "--output", "-o", help="Kam uložiť PDF")):
    """Nahrá tlačivo a začne konverzáciu."""
    with client() as c:
        with console.status("Analyzujem tlačivo…"):
            resp = c.post("/api/sessions", files={"file": (form.name, form.read_bytes(),
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        _fail(resp)
        data = resp.json()
        _say(data["reply"])
        _chat_loop(c, data["session"]["id"], output)


@app.command()
def chat(session_id: str, output: Path = typer.Option(None, "--output", "-o")):
    """Pokračuje v uloženej konverzácii."""
    with client() as c:
        resp = c.get(f"/api/sessions/{session_id}")
        _fail(resp)
        data = resp.json()
        console.print(f"[bold]{data['title']}[/bold] {_progress(data)}\n")
        for m in data["messages"][-4:]:
            if m["role"] == "user":
                console.print(f"[green]Vy> {m['content']}[/green]")
            else:
                _say(m["content"])
        _chat_loop(c, session_id, output)


@app.command("list")
def list_sessions():
    """Zoznam konverzácií."""
    with client() as c:
        resp = c.get("/api/sessions")
        _fail(resp)
        table = Table("ID", "Tlačivo", "Stav", "Postup", "Upravené")
        for s in resp.json():
            p = s["progress"]
            table.add_row(s["id"], s["title"][:50], s["phase"], f"{p['answered']}/{p['total']}",
                          s["updated_at"][:16].replace("T", " "))
        console.print(table)


@app.command()
def download(session_id: str, output: Path = typer.Option(Path("vyplnene_tlacivo.pdf"), "--output", "-o")):
    """Stiahne vyplnené PDF."""
    with client() as c:
        _download(c, session_id, output)


@app.command()
def demo(sample: str = typer.Argument("vzor2", help="vzor1 | vzor2 | vzor3"),
         form: Path = typer.Option(Path("forms/formular.docx"), exists=True),
         output: Path = typer.Option(None, "--output", "-o")):
    """Vyplní tlačivo vzorovými údajmi (bez LLM a servera) – rýchla kontrola výstupu."""
    from .devtools.samples import SAMPLES
    from .filler import fill_document
    from .forms import prihlaska
    from .pdf import docx_to_pdf

    values = dict(SAMPLES[sample])
    values.update(prihlaska.derive(values))
    target = (output or Path(f"{sample}_vyplnene.pdf")).with_suffix(".docx")
    report = fill_document(form, prihlaska.FIELDS, values, target)
    pdf = docx_to_pdf(target)
    target.unlink(missing_ok=True)
    console.print(f"Zapísaných polí: {len(report.written)}, preskočených: {report.skipped or 0}")
    console.print(f"[bold]📄 {pdf.resolve()}[/bold]")


if __name__ == "__main__":
    app()
