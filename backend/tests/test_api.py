import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app import main, risk, sync
from app.agent import build_agent
from app.config import get_settings
from tests.conftest import FakeDocker, FakeNvd
from tests.test_agent import calls, scripted

pytestmark = pytest.mark.integration


@pytest.fixture
def client(clean_db, monkeypatch):
    monkeypatch.setattr(main, "run_sync", lambda: sync.run_sync(FakeDocker(), FakeNvd()))
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")


def sse_events(response) -> list[dict]:
    return [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")]


def test_summary_before_the_first_sync(client):
    body = client.get("/api/summary").json()
    assert body["last_sync"] is None
    assert body["counts"]["assets"] == 0


def test_sync_then_summary(client):
    assert client.post("/api/sync").json()["observations"] == {"docker": 8, "edr": 7}
    body = client.get("/api/summary").json()
    assert body["last_sync"]["status"] == "succeeded"
    assert body["gaps"] == {"missing-edr": 2, "vulnerable-software": 2, "orphaned-owner": 1, "ghost-assets": 1}
    assert body["counts"] == {"assets": 9, "in_docker": 8, "with_edr": 7, "identities": 5, "active_without_mfa": 1}


def test_assets_and_gaps(client):
    client.post("/api/sync")
    assert len(client.get("/api/assets").json()) == 9
    assert [r["hostname"] for r in client.get("/api/gaps/missing-edr").json()] == ["jump-01", "api-02"]
    assert client.get("/api/gaps/ghost-assets").json()[0]["hostname"] == "legacy-ftp-01"
    assert client.get("/api/gaps/not-a-gap").status_code == 422


def test_sync_conflict_returns_409(client):
    sync._lock.acquire()
    try:
        response = client.post("/api/sync")
    finally:
        sync._lock.release()
    assert response.status_code == 409


def test_health(client):
    body = client.get("/api/health").json()
    assert body["database"] is True
    assert body["claude"] is False


def test_chat_without_a_key_explains_what_to_do(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    events = sse_events(client.post("/api/chat", json={"message": "hi", "thread_id": "t"}))
    assert events[0]["type"] == "error" and "ANTHROPIC_API_KEY" in events[0]["message"]
    assert events[-1] == {"type": "done"}


def test_chat_streams_agent_steps(client, with_key, monkeypatch):
    client.post("/api/sync")
    model = scripted(calls(("run_sql", {"sql": "SELECT hostname FROM gap_ghost_assets"})), AIMessage("legacy-ftp-01."))
    monkeypatch.setattr(main, "get_agent", lambda: build_agent(model))
    response = client.post("/api/chat", json={"message": "Any ghosts?", "thread_id": "t"})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [e["type"] for e in sse_events(response)] == ["tool_call", "result", "answer", "done"]


def test_chat_reports_agent_crashes(client, with_key, monkeypatch):
    class Broken:
        def astream(self, *args, **kwargs):
            raise RuntimeError("model exploded")

    monkeypatch.setattr(main, "get_agent", lambda: Broken())
    events = sse_events(client.post("/api/chat", json={"message": "hi", "thread_id": "t"}))
    assert events[0]["type"] == "error" and "model exploded" in events[0]["message"]


def test_chat_rejects_empty_messages(client):
    assert client.post("/api/chat", json={"message": "", "thread_id": "t"}).status_code == 422


def test_risk_summary_without_a_key(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    response = client.post("/api/risk-summary")
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


class FakeAnthropic:
    def __init__(self, result=None, error=None):
        self.sent = None
        self.result, self.error = result, error
        self.messages = self

    async def parse(self, **kwargs):
        self.sent = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(parsed_output=self.result, stop_reason="end_turn")


REPORT = risk.RiskReport(
    overall_risk="high",
    headline="Two prod servers lack EDR and cache-01 runs a critical Redis CVE.",
    findings=[
        risk.Finding(
            title="Critical Redis CVE",
            severity="critical",
            hostnames=["cache-01"],
            why_it_matters="Remote code execution.",
            recommended_action="Upgrade Redis.",
        )
    ],
)


async def test_risk_summary_sends_current_gaps(clean_db):
    sync.run_sync(FakeDocker(), FakeNvd())
    fake = FakeAnthropic(result=REPORT)
    assert await risk.summarize(fake) == REPORT
    assert fake.sent["output_format"] is risk.RiskReport
    assert fake.sent["model"] == get_settings().claude_model
    prompt = fake.sent["messages"][0]["content"]
    assert "jump-01" in prompt and "legacy-ftp-01" in prompt and "CVE-2022-24735" in prompt


def api_error(cls, status):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


@pytest.mark.parametrize(
    ("error", "status", "text"),
    [
        (api_error(anthropic.AuthenticationError, 401), 502, "API key"),
        (api_error(anthropic.RateLimitError, 429), 429, "rate limiting"),
        (api_error(anthropic.InternalServerError, 500), 502, "(500)"),
        (anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")), 502, "reach"),
    ],
)
async def test_risk_summary_maps_claude_errors(clean_db, error, status, text):
    with pytest.raises(risk.RiskSummaryError) as raised:
        await risk.summarize(FakeAnthropic(error=error))
    assert raised.value.status_code == status
    assert text in str(raised.value)


async def test_risk_summary_without_parsed_output(clean_db):
    with pytest.raises(risk.RiskSummaryError, match="didn't return"):
        await risk.summarize(FakeAnthropic(result=None))


def test_risk_summary_endpoint_returns_the_report(client, monkeypatch):
    async def fake_summarize():
        return REPORT

    monkeypatch.setattr(risk, "summarize", fake_summarize)
    assert client.post("/api/risk-summary").json()["overall_risk"] == "high"
