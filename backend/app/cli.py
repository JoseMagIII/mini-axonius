import argparse
import json
from dataclasses import asdict

from app.adapters import docker_hosts, nvd
from app.config import get_settings
from app.db import init_db
from app.sync import run_sync


def save_nvd_fallback() -> None:
    """Saves today's NVD results so a sync still works if NVD is down during the demo."""
    settings = get_settings()
    fleet = json.loads((settings.data_dir / "fleet.json").read_text())
    versions = sorted({docker_hosts.parse_image(server["image"]) for server in fleet.values()})
    client = nvd.NvdClient(settings.nvd_api_key)
    saved = {}
    for software, version in versions:
        if not version or not nvd.cpe_for(software, version):
            continue
        vulns = client.vulnerabilities(nvd.cpe_for(software, version))
        saved[f"{software}:{version}"] = [asdict(v) for v in vulns]
        print(f"{software}:{version}: {len(vulns)} CVEs")
    path = settings.data_dir / "nvd_fallback.json"
    path.write_text(json.dumps(saved, indent=2) + "\n")
    print(f"Saved {path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="mini-axonius")
    commands = {
        "init-db": init_db,
        "sync": lambda: print(json.dumps(run_sync(), indent=2)),
        "save-nvd-fallback": save_nvd_fallback,
    }
    parser.add_argument("command", choices=commands)
    commands[parser.parse_args().command]()


if __name__ == "__main__":
    main()
