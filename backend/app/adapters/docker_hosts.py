import docker

from app.adapters import Observation

MANAGED_LABEL = "acme.managed=true"


def parse_image(image: str) -> tuple[str, str | None]:
    """Splits "nginx:1.21.6" into ("nginx", "1.21.6"); registry prefixes and digests are dropped."""
    ref = image.split("@")[0]
    name, colon, tag = ref.rpartition(":")
    if not colon or "/" in tag:  # No tag, or the colon belonged to a registry port.
        name, tag = ref, ""
    return name.rsplit("/", 1)[-1], tag or None


def to_observation(container: dict) -> Observation:
    config = container["Config"]
    labels = config.get("Labels") or {}
    networks = container["NetworkSettings"].get("Networks") or {}
    ip = next((n["IPAddress"] for n in networks.values() if n.get("IPAddress")), None)
    software, version = parse_image(config["Image"])

    return Observation(
        source="docker",
        source_id=container["Id"][:12],
        hostname=config["Hostname"],
        ip_address=ip,
        os="Linux",
        software=software,
        software_version=version,
        owner=labels.get("acme.owner"),
        environment=labels.get("acme.env"),
        state=container["State"]["Status"],
        raw={"name": container["Name"].lstrip("/"), "image": config["Image"], "labels": labels},
    )


def collect(client: docker.DockerClient | None = None) -> list[Observation]:
    """Lists every Acme-labeled container, including stopped ones, from the Docker Engine API."""
    client = client or docker.from_env()
    containers = client.containers.list(all=True, filters={"label": MANAGED_LABEL})
    return [to_observation(c.attrs) for c in containers]
