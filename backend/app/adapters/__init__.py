from dataclasses import dataclass, field


@dataclass(frozen=True)
class Observation:
    """One source's view of one asset. Every adapter returns this shape."""

    source: str
    source_id: str
    hostname: str
    ip_address: str | None = None
    os: str | None = None
    software: str | None = None
    software_version: str | None = None
    owner: str | None = None
    environment: str | None = None
    state: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Identity:
    source: str
    username: str
    email: str | None
    full_name: str | None
    department: str | None
    status: str
    mfa_enabled: bool
