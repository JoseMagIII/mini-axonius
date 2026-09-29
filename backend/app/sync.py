import logging
import threading
import time
from collections import Counter
from dataclasses import asdict

import psycopg
from psycopg.types.json import Jsonb

from app.adapters import Identity, Observation, docker_hosts, files, nvd
from app.config import get_settings
from app.db import connect

log = logging.getLogger(__name__)
_lock = threading.Lock()


class SyncInProgress(Exception):
    pass


def _insert_observations(conn: psycopg.Connection, run_id: int, observations: list[Observation]) -> None:
    rows = [{**asdict(o), "raw": Jsonb(o.raw), "run_id": run_id} for o in observations]
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO asset_observations
               (sync_run_id, source, source_id, hostname, ip_address, os, software, software_version,
                owner, environment, state, raw)
               VALUES (%(run_id)s, %(source)s, %(source_id)s, %(hostname)s, %(ip_address)s, %(os)s,
                       %(software)s, %(software_version)s, %(owner)s, %(environment)s, %(state)s, %(raw)s)""",
            rows,
        )


def _insert_identities(conn: psycopg.Connection, run_id: int, identities: list[Identity]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO identities
               (sync_run_id, source, username, email, full_name, department, status, mfa_enabled)
               VALUES (%(run_id)s, %(source)s, %(username)s, %(email)s, %(full_name)s, %(department)s,
                       %(status)s, %(mfa_enabled)s)""",
            [{**asdict(i), "run_id": run_id} for i in identities],
        )


def _save_vulnerabilities(
    conn: psycopg.Connection, software: str, version: str, origin: str, vulns: list[nvd.Vulnerability]
) -> None:
    with conn.transaction():
        conn.execute("DELETE FROM nvd_lookups WHERE software = %s AND software_version = %s", [software, version])
        conn.execute(
            "INSERT INTO nvd_lookups (software, software_version, origin, total_results) VALUES (%s, %s, %s, %s)",
            [software, version, origin, len(vulns)],
        )
        conn.cursor().executemany(
            """INSERT INTO vulnerabilities
               (software, software_version, cve_id, severity, cvss_score, published_at, summary)
               VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            [(software, version, v.cve_id, v.severity, v.cvss_score, v.published_at, v.summary) for v in vulns],
        )


def refresh_vulnerabilities(
    conn: psycopg.Connection, versions: set[tuple[str, str]], client: nvd.NvdClient
) -> dict[str, str]:
    """Looks up each software version in NVD unless a fresh cached copy exists. Returns where each came from."""
    settings = get_settings()
    outcome = {}
    nvd_down = False
    for software, version in sorted(versions):
        key = f"{software}:{version}"
        cpe = nvd.cpe_for(software, version)
        if cpe is None:
            outcome[key] = "not tracked"
            continue
        # Fallback copies are retried hourly so an outage doesn't slow every sync.
        cached = conn.execute(
            """SELECT origin, fetched_at > now() - CASE origin WHEN 'nvd' THEN make_interval(hours => %s)
                                                              ELSE interval '1 hour' END AS fresh
               FROM nvd_lookups WHERE software = %s AND software_version = %s""",
            [settings.nvd_cache_hours, software, version],
        ).fetchone()
        if cached and cached["fresh"]:
            outcome[key] = "cached"
            continue
        if not nvd_down:
            try:
                _save_vulnerabilities(conn, software, version, "nvd", client.vulnerabilities(cpe))
                outcome[key] = "nvd"
                continue
            except nvd.NvdUnavailable as error:
                log.warning("NVD lookup for %s failed, skipping NVD for the rest of this sync: %s", key, error)
                nvd_down = True
        if cached:
            outcome[key] = "stale cache"
            continue
        saved = nvd.load_fallback(settings.data_dir / "nvd_fallback.json", software, version)
        if saved is None:
            outcome[key] = "unavailable"
        else:
            _save_vulnerabilities(conn, software, version, "fallback", saved)
            outcome[key] = "fallback"
    return outcome


def run_sync(docker_client=None, nvd_client: nvd.NvdClient | None = None) -> dict:
    """Runs every adapter and records the results as one sync run."""
    if not _lock.acquire(blocking=False):
        raise SyncInProgress("A sync is already running")
    settings = get_settings()
    started = time.monotonic()
    try:
        with connect(autocommit=True) as conn:
            run_id = conn.execute("INSERT INTO sync_runs DEFAULT VALUES RETURNING id").fetchone()["id"]
            try:
                observations = docker_hosts.collect(docker_client) + files.collect_edr(
                    settings.data_dir / "edr_agents.json"
                )
                identities = files.collect_identities(settings.data_dir / "identities.json")
                versions = {(o.software, o.software_version) for o in observations if o.software and o.software_version}
                # NVD can take seconds per lookup, so it runs outside the transaction and caches its own results.
                client = nvd_client or nvd.NvdClient(settings.nvd_api_key)
                vulnerability_sources = refresh_vulnerabilities(conn, versions, client)
                with conn.transaction():
                    _insert_observations(conn, run_id, observations)
                    _insert_identities(conn, run_id, identities)
            except Exception as error:
                conn.execute(
                    "UPDATE sync_runs SET status = 'failed', finished_at = now(), error = %s WHERE id = %s",
                    [str(error), run_id],
                )
                raise
            conn.execute("UPDATE sync_runs SET status = 'succeeded', finished_at = now() WHERE id = %s", [run_id])
    finally:
        _lock.release()

    return {
        "run_id": run_id,
        "observations": dict(Counter(o.source for o in observations)),
        "identities": len(identities),
        "vulnerability_sources": vulnerability_sources,
        "seconds": round(time.monotonic() - started, 2),
    }
