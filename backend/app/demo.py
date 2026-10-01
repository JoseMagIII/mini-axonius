import json

import docker

from app.adapters import docker_hosts
from app.config import get_settings
from app.db import connect
from app.sync import run_sync


def reset_demo(client: docker.DockerClient | None = None, nvd_client=None) -> dict:
    """Restores the planted demo state: fleet servers running, extra servers removed, sync history cleared."""
    client = client or docker.from_env()
    fleet = json.loads((get_settings().data_dir / "fleet.json").read_text())
    started, removed, present = [], [], set()
    for container in client.containers.list(all=True, filters={"label": docker_hosts.MANAGED_LABEL}):
        hostname = container.attrs["Config"]["Hostname"]
        if hostname not in fleet:
            container.remove(force=True)
            removed.append(hostname)
            continue
        present.add(hostname)
        if container.status != "running":
            container.start()
            started.append(hostname)

    # The NVD cache survives, so the fresh sync doesn't wait on the API.
    with connect(autocommit=True) as conn:
        conn.execute("TRUNCATE sync_runs RESTART IDENTITY CASCADE")

    return {
        "started": sorted(started),
        "removed": sorted(removed),
        "missing": sorted(set(fleet) - present),
        "sync": run_sync(client, nvd_client),
    }
