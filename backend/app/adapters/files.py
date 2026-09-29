import json
from pathlib import Path

from app.adapters import Identity, Observation


def collect_edr(path: Path) -> list[Observation]:
    """Reads the EDR vendor's agent export. Hostnames stay exactly as the vendor reports them."""
    agents = json.loads(path.read_text())
    return [
        Observation(
            source="edr",
            source_id=agent["agent_id"],
            hostname=agent["hostname"],
            os=agent.get("os"),
            state=agent["status"],
            raw=agent,
        )
        for agent in agents
    ]


def collect_identities(path: Path) -> list[Identity]:
    users = json.loads(path.read_text())
    return [
        Identity(
            source="idp",
            username=user["username"],
            email=user.get("email"),
            full_name=user.get("full_name"),
            department=user.get("department"),
            status=user["status"],
            mfa_enabled=user["mfa_enabled"],
        )
        for user in users
    ]
