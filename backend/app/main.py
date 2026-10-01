import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

import docker
from docker.errors import DockerException
from fastapi import FastAPI, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app import risk
from app.agent import build_agent, events_from_update
from app.config import get_settings
from app.db import GAPS, init_db, query
from app.sync import SyncInProgress, run_sync

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="mini-axonius", lifespan=lifespan)


@lru_cache
def get_agent():
    return build_agent()


@lru_cache
def docker_client() -> docker.DockerClient:
    return docker.from_env()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str = Field(min_length=1, max_length=100)


@app.get("/api/health")
def health() -> dict:
    try:
        docker_client().ping()
        docker_ok = True
    except DockerException:
        docker_ok = False
    return {
        "database": bool(query("SELECT 1 AS ok")),
        "docker": docker_ok,
        "claude": bool(get_settings().anthropic_api_key),
    }


@app.get("/api/summary")
def summary() -> dict:
    last_sync = query("SELECT id, status, started_at, finished_at, error FROM sync_runs ORDER BY id DESC LIMIT 1")
    counts = query(
        """SELECT
             (SELECT count(*) FROM assets_unified) AS assets,
             (SELECT count(*) FROM assets_unified WHERE in_docker) AS in_docker,
             (SELECT count(*) FROM assets_unified WHERE has_edr) AS with_edr,
             (SELECT count(*) FROM latest_identities) AS identities,
             (SELECT count(*) FROM latest_identities
               WHERE status = 'active' AND NOT mfa_enabled) AS active_without_mfa"""
    )[0]
    gaps = query(" UNION ALL ".join(f"SELECT '{gap}' AS gap, count(*) FROM gap_{gap}" for gap in GAPS))
    gaps = {row["gap"]: row["count"] for row in gaps}
    return {"last_sync": last_sync[0] if last_sync else None, "counts": counts, "gaps": gaps}


@app.get("/api/assets")
def assets() -> list[dict]:
    return query("SELECT * FROM assets_unified ORDER BY hostname")


@app.get("/api/gaps/{name}")
def gap(name: str) -> list[dict]:
    if name not in GAPS:
        raise HTTPException(404, f"Unknown gap: {name}")
    return query(f"SELECT * FROM gap_{name}")


@app.post("/api/sync")
def sync() -> dict:
    try:
        return run_sync()
    except SyncInProgress as error:
        raise HTTPException(409, str(error)) from error
    except DockerException as error:
        log.exception("Sync failed")
        raise HTTPException(502, f"Couldn't reach Docker: {error}") from error


@app.post("/api/risk-summary")
async def risk_summary() -> risk.RiskReport:
    try:
        return await risk.summarize()
    except risk.RiskSummaryError as error:
        raise HTTPException(error.status_code, str(error)) from error


@app.post("/api/chat", response_class=EventSourceResponse)
async def chat(request: ChatRequest) -> AsyncIterator[ServerSentEvent]:
    if not get_settings().anthropic_api_key:
        yield ServerSentEvent(
            data={"type": "error", "message": "Add ANTHROPIC_API_KEY to .env to chat with the agent."}
        )
        yield ServerSentEvent(data={"type": "done"})
        return
    config = {"configurable": {"thread_id": request.thread_id}}
    try:
        stream = get_agent().astream(
            {"messages": [HumanMessage(request.message)], "steps": 0}, config, stream_mode="updates"
        )
        async for update in stream:
            for delta in update.values():
                for event in events_from_update(delta):
                    yield ServerSentEvent(data=event)
    except Exception as error:  # Surface agent failures in the chat instead of dropping the stream.
        log.exception("Agent failed")
        yield ServerSentEvent(data={"type": "error", "message": f"The agent failed: {error}"})
    yield ServerSentEvent(data={"type": "done"})
