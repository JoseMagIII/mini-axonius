import psycopg
import pytest

from app import sync
from app.db import query, reader_connection
from tests.conftest import FakeDocker, FakeNvd

pytestmark = pytest.mark.integration


def hostnames(view):
    return [row["hostname"] for row in query(f"SELECT hostname FROM {view} ORDER BY hostname")]


def test_sync_records_every_source(clean_db):
    result = sync.run_sync(FakeDocker(), FakeNvd())
    assert result["observations"] == {"docker": 8, "edr": 7}
    assert result["identities"] == 5
    assert result["vulnerability_sources"] == {
        "alpine:3.22": "not tracked",
        "nginx:1.21.6": "nvd",
        "nginx:1.29.1": "nvd",
        "redis:6.0.20": "nvd",
    }
    assert query("SELECT status FROM sync_runs")[0]["status"] == "succeeded"


def test_messy_edr_hostnames_merge_with_docker(clean_db):
    sync.run_sync(FakeDocker(), FakeNvd())
    rows = {r["hostname"]: r for r in query("SELECT * FROM assets_unified")}
    assert len(rows) == 9  # 8 containers plus the EDR-only legacy host
    assert rows["web-01"]["sources"] == ["docker", "edr"]
    assert rows["worker-01"]["has_edr"] and rows["worker-01"]["in_docker"]
    assert rows["legacy-ftp-01"]["sources"] == ["edr"]


def test_gap_views_tell_the_demo_story(clean_db):
    sync.run_sync(FakeDocker(), FakeNvd())
    assert hostnames("gap_missing_edr") == ["api-02", "jump-01"]
    [ghost] = query("SELECT hostname, edr_last_checkin FROM gap_ghost_assets")
    assert ghost["hostname"] == "legacy-ftp-01"
    assert ghost["edr_last_checkin"].isoformat() == "2026-06-14T22:10:41+00:00"  # From the EDR, not our sync time
    assert query("SELECT hostname, reason FROM gap_orphaned_owner") == [
        {"hostname": "jump-01", "reason": "Owner account is disabled"}
    ]
    vulnerable = query("SELECT hostname, cve_count, high_or_critical, max_cvss FROM gap_vulnerable_software")
    assert [(r["hostname"], r["cve_count"], float(r["max_cvss"])) for r in vulnerable] == [
        ("cache-01", 1, 9.8),
        ("web-01", 2, 7.8),
    ]


def test_stopping_a_server_turns_it_into_a_ghost(clean_db):
    docker = FakeDocker()
    sync.run_sync(docker, FakeNvd())
    docker.stopped.add("web-02")
    sync.run_sync(docker, FakeNvd())
    ghosts = {r["hostname"]: r["reason"] for r in query("SELECT * FROM gap_ghost_assets")}
    assert ghosts == {"legacy-ftp-01": "Not found in Docker", "web-02": "Container is exited"}


def test_rogue_server_shows_up_in_two_gaps(clean_db):
    docker = FakeDocker()
    docker.fleet["rogue-01"] = ("alpine:3.22", "mallory", "prod")
    sync.run_sync(docker, FakeNvd())
    assert "rogue-01" in hostnames("gap_missing_edr")
    orphaned = {r["hostname"]: r["reason"] for r in query("SELECT * FROM gap_orphaned_owner")}
    assert orphaned["rogue-01"] == "Owner not in identity provider"


def test_views_only_read_the_latest_sync_but_keep_history(clean_db):
    docker = FakeDocker()
    sync.run_sync(docker, FakeNvd())
    first_seen = query("SELECT first_seen FROM assets_unified WHERE hostname = 'api-01'")[0]["first_seen"]
    del docker.fleet["build-01"]
    sync.run_sync(docker, FakeNvd())
    assert "build-01" in hostnames("gap_ghost_assets")  # EDR still reports it, Docker doesn't
    row = query("SELECT first_seen, last_seen FROM assets_unified WHERE hostname = 'api-01'")[0]
    assert row["first_seen"] == first_seen < row["last_seen"]


def test_nvd_results_are_cached_between_syncs(clean_db):
    client = FakeNvd()
    sync.run_sync(FakeDocker(), client)
    calls_after_first_sync = len(client.calls)
    result = sync.run_sync(FakeDocker(), client)
    assert len(client.calls) == calls_after_first_sync
    assert result["vulnerability_sources"]["nginx:1.21.6"] == "cached"


def test_nvd_outage_uses_the_saved_fallback(clean_db):
    result = sync.run_sync(FakeDocker(), FakeNvd(fail=True))
    assert result["vulnerability_sources"]["nginx:1.21.6"] == "fallback"
    assert query("SELECT origin FROM nvd_lookups WHERE software_version = '1.21.6'")[0]["origin"] == "fallback"
    assert "web-01" in hostnames("gap_vulnerable_software")


def test_a_failed_sync_keeps_the_last_good_data(clean_db):
    sync.run_sync(FakeDocker(), FakeNvd())

    class BrokenDocker:
        @property
        def containers(self):
            raise RuntimeError("Docker daemon unreachable")

    with pytest.raises(RuntimeError):
        sync.run_sync(BrokenDocker(), FakeNvd())
    assert [r["status"] for r in query("SELECT status FROM sync_runs ORDER BY id")] == ["succeeded", "failed"]
    assert hostnames("gap_missing_edr") == ["api-02", "jump-01"]


def test_only_one_sync_runs_at_a_time(clean_db):
    sync._lock.acquire()
    try:
        with pytest.raises(sync.SyncInProgress):
            sync.run_sync(FakeDocker(), FakeNvd())
    finally:
        sync._lock.release()


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM identities",
        "DROP VIEW gap_missing_edr",
        "CREATE TABLE sneaky (id int)",
        "UPDATE sync_runs SET status = 'failed'",
    ],
)
def test_reader_role_cannot_write(clean_db, statement):
    sync.run_sync(FakeDocker(), FakeNvd())
    with reader_connection() as conn, pytest.raises(psycopg.errors.Error):
        conn.execute(statement)
    assert query("SELECT count(*) AS n FROM identities")[0]["n"] == 5


def test_reader_role_can_read_views(clean_db):
    sync.run_sync(FakeDocker(), FakeNvd())
    with reader_connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM assets_unified").fetchone()["n"] == 9
