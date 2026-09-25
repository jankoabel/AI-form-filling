from typer.testing import CliRunner

from formfill import cli
from formfill.api import create_app
from formfill.brains import RuleBrain
from formfill.service import FormService
from fastapi.testclient import TestClient

from .conftest import fake_converter

runner = CliRunner()


def test_cli_new_chat_list(monkeypatch, settings, form_path):
    app = create_app(FormService(settings, brain=RuleBrain(), converter=fake_converter))
    with TestClient(app) as test_client:
        monkeypatch.setattr(cli, "client", lambda: _NoClose(test_client))
        result = runner.invoke(cli.app, ["new", str(form_path)], input="bakalárske\n/koniec\n")
        assert result.exit_code == 0, result.output
        assert "akademický rok" in result.output and "formfill chat" in result.output

        sessions = test_client.get("/api/sessions").json()
        result = runner.invoke(cli.app, ["list"])
        assert result.exit_code == 0 and sessions[0]["id"][:8] in result.output

        result = runner.invoke(cli.app, ["chat", sessions[0]["id"]], input="2027/2028\n/koniec\n")
        assert result.exit_code == 0 and "vysokú školu" in result.output

        result = runner.invoke(cli.app, ["download", sessions[0]["id"]])
        assert result.exit_code == 1  # no PDF yet


class _NoClose:
    """Lets the CLI use ``with client() as c`` without closing the shared TestClient."""

    def __init__(self, inner):
        self.inner = inner

    def __enter__(self):
        return self.inner

    def __exit__(self, *exc):
        return False
