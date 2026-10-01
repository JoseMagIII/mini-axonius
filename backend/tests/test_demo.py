import pytest

from app import sync
from app.db import query
from app.demo import reset_demo
from tests.conftest import FakeDocker, FakeNvd

pytestmark = pytest.mark.integration


def test_reset_restores_the_planted_state(clean_db):
    docker = FakeDocker()
    sync.run_sync(docker, FakeNvd())
    docker.stopped.add("web-02")
    docker.fleet["rogue-01"] = {"image": "alpine:3.22", "owner": "mallory", "env": "prod"}
    sync.run_sync(docker, FakeNvd())

    result = reset_demo(docker, FakeNvd())

    assert result["started"] == ["web-02"]
    assert result["removed"] == ["rogue-01"]
    assert result["missing"] == []
    assert result["sync"]["run_id"] == 1  # History starts over
    assert query("SELECT count(*) AS n FROM sync_runs")[0]["n"] == 1
    assert [r["hostname"] for r in query("SELECT hostname FROM gap_ghost_assets")] == ["legacy-ftp-01"]
    assert [r["hostname"] for r in query("SELECT hostname FROM gap_missing_edr ORDER BY 1")] == ["api-02", "jump-01"]


def test_reset_reports_fleet_servers_that_no_longer_exist(clean_db):
    docker = FakeDocker()
    del docker.fleet["build-01"]
    assert reset_demo(docker, FakeNvd())["missing"] == ["build-01"]


def test_reset_keeps_the_nvd_cache(clean_db):
    sync.run_sync(FakeDocker(), FakeNvd())
    client = FakeNvd()
    result = reset_demo(FakeDocker(), client)
    assert client.calls == []
    assert result["sync"]["vulnerability_sources"]["nginx:1.21.6"] == "cached"
