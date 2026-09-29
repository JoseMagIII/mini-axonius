import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.adapters import nvd

ADMIN_URL = os.environ.get("DATABASE_URL", "postgresql://admin:acme-admin@localhost:5544/assets")
TEST_DB = "assets_test"

# The Acme fleet as Terraform creates it, so the SQL views are tested against the demo's story.
FLEET = {
    "web-01": ("nginx:1.21.6", "alice", "prod"),
    "web-02": ("nginx:1.29.1", "alice", "prod"),
    "cache-01": ("redis:6.0.20", "bob", "prod"),
    "api-01": ("alpine:3.22", "bob", "prod"),
    "api-02": ("alpine:3.22", "carol", "staging"),
    "worker-01": ("alpine:3.22", "carol", "prod"),
    "jump-01": ("alpine:3.22", "dave", "prod"),
    "build-01": ("alpine:3.22", "erin", "dev"),
}


def fake_container(hostname, image, owner, env, status="running"):
    return {
        "Id": f"{hostname:0<12}"[:12] + "ffff",
        "Name": f"/acme-{hostname}",
        "Config": {"Hostname": hostname, "Image": image, "Labels": {"acme.owner": owner, "acme.env": env}},
        "State": {"Status": status},
        "NetworkSettings": {"Networks": {"acme-net": {"IPAddress": "" if status != "running" else "172.20.0.9"}}},
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
            type(
                "Container",
                (),
                {"attrs": fake_container(h, *spec, status="exited" if h in self.stopped else "running")},
            )()
            for h, spec in self.fleet.items()
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

    params = conninfo_to_dict(ADMIN_URL)
    os.environ["DATABASE_URL"] = (
        f"postgresql://{params['user']}:{params['password']}@{params['host']}:{params['port']}/{TEST_DB}"
    )
    os.environ["NVD_CACHE_HOURS"] = "24"

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
