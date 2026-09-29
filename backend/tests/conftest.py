import json
import os
from itertools import count
from types import SimpleNamespace

import psycopg
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from psycopg.conninfo import make_conninfo

from app.adapters import nvd
from app.config import ROOT, Settings

ADMIN_URL = os.environ.get("DATABASE_URL", Settings().database_url)
TEST_DB = "assets_test"

# The same fleet Terraform creates, so the SQL views are tested against the demo's story.
FLEET = json.loads((ROOT / "data" / "fleet.json").read_text())


def fake_container(hostname, image="nginx:1.21.6", owner="alice", env="prod", status="running", **_):
    return {
        "Id": f"{hostname:0<12}"[:12] + "ffff",
        "Name": f"/acme-{hostname}",
        "Config": {"Hostname": hostname, "Image": image, "Labels": {"acme.owner": owner, "acme.env": env}},
        "State": {"Status": status},
        "NetworkSettings": {"Networks": {"acme-net": {"IPAddress": "172.20.0.9" if status == "running" else ""}}},
    }


class FakeDocker:
    """Stands in for docker.DockerClient; tests change `fleet` and `stopped` between syncs."""

    def __init__(self):
        self.fleet = dict(FLEET)
        self.stopped = set()

    @property
    def containers(self):
        return self

    def list(self, **_):
        return [
            SimpleNamespace(attrs=fake_container(host, **spec, status="exited" if host in self.stopped else "running"))
            for host, spec in self.fleet.items()
        ]


class FakeNvd:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def vulnerabilities(self, cpe):
        self.calls.append(cpe)
        if self.fail:
            raise nvd.NvdUnavailable("NVD is down")
        if "nginx:1.21.6" in cpe:
            return [
                nvd.Vulnerability("CVE-2022-41741", "HIGH", 7.8, None, None),
                nvd.Vulnerability("CVE-2023-44487", "HIGH", 7.5, None, None),
            ]
        if "redis:6.0.20" in cpe:
            return [nvd.Vulnerability("CVE-2022-24735", "CRITICAL", 9.8, None, None)]
        return []


@pytest.fixture(scope="session")
def database():
    """Creates a throwaway database next to the demo one and points the app at it."""
    maintenance = make_conninfo(ADMIN_URL, dbname="postgres")
    try:
        admin = psycopg.connect(maintenance, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres isn't running; start it with `make infra`")
    with admin:
        admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {TEST_DB}")

    os.environ["DATABASE_URL"] = make_conninfo(ADMIN_URL, dbname=TEST_DB)

    from app.config import get_settings
    from app.db import init_db

    get_settings.cache_clear()
    init_db()
    yield os.environ["DATABASE_URL"]


@pytest.fixture
def clean_db(database):
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("TRUNCATE sync_runs, nvd_lookups RESTART IDENTITY CASCADE")
    return database


_ids = count()


class ScriptedModel(GenericFakeChatModel):
    """Plays back a fixed list of Claude replies and records what it was sent."""

    seen: list = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, *args, **kwargs)


def scripted(*replies):
    return ScriptedModel(messages=iter(replies), seen=[])


def calls(*pairs):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"call_{next(_ids)}"} for name, args in pairs])
