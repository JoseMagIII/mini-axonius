import argparse
import json
from dataclasses import asdict

from app.adapters import nvd
from app.config import get_settings
from app.db import init_db
from app.sync import run_sync

# Software versions the Terraform fleet runs; the fallback covers the ones NVD tracks.
FALLBACK_VERSIONS = [("nginx", "1.21.6"), ("nginx", "1.29.1"), ("redis", "6.0.20")]


def save_nvd_fallback() -> None:
    """Saves today's NVD results so a sync still works if NVD is down during the demo."""
    settings = get_settings()
    client = nvd.NvdClient(settings.nvd_api_key)
    saved = {}
    for software, version in FALLBACK_VERSIONS:
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
