import json
from types import SimpleNamespace

import httpx
import pytest
import respx

from app.adapters import docker_hosts, files, nvd
from tests.conftest import fake_container


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("nginx:1.21.6", ("nginx", "1.21.6")),
        ("alpine", ("alpine", None)),
        ("docker.io/library/redis:6.0.20", ("redis", "6.0.20")),
        ("registry.local:5000/team/api", ("api", None)),
        ("registry.local:5000/team/api:2.1", ("api", "2.1")),
        ("nginx:1.27@sha256:abc123", ("nginx", "1.27")),
    ],
)
def test_parse_image(image, expected):
    assert docker_hosts.parse_image(image) == expected


def test_docker_container_becomes_an_observation():
    observation = docker_hosts.to_observation(fake_container("web-01"))
    assert observation.source == "docker"
    assert observation.source_id == "web-01000000"
    assert (observation.hostname, observation.ip_address, observation.state) == ("web-01", "172.20.0.9", "running")
    assert (observation.software, observation.software_version) == ("nginx", "1.21.6")
    assert (observation.owner, observation.environment) == ("alice", "prod")
    assert observation.raw["name"] == "acme-web-01"


def test_stopped_container_has_no_ip():
    stopped = fake_container("web-01", status="exited")
    observation = docker_hosts.to_observation(stopped)
    assert observation.ip_address is None
    assert observation.state == "exited"


def test_collect_asks_docker_only_for_acme_containers():
    class FakeContainers:
        def list(self, **kwargs):
            self.kwargs = kwargs
            return [SimpleNamespace(attrs=fake_container("web-01"))]

    class FakeClient:
        containers = FakeContainers()

    client = FakeClient()
    assert len(docker_hosts.collect(client)) == 1
    assert client.containers.kwargs == {"all": True, "filters": {"label": docker_hosts.MANAGED_LABEL}}


def test_edr_export_keeps_vendor_hostnames(tmp_path):
    path = tmp_path / "edr.json"
    path.write_text(
        json.dumps([{"agent_id": "edr-1", "hostname": "WEB-01.acme.local", "os": "Linux", "status": "online"}])
    )
    [observation] = files.collect_edr(path)
    assert (observation.source, observation.hostname, observation.state) == ("edr", "WEB-01.acme.local", "online")


def test_identity_export(tmp_path):
    path = tmp_path / "users.json"
    path.write_text(json.dumps([{"username": "dave", "status": "disabled", "mfa_enabled": True}]))
    [identity] = files.collect_identities(path)
    assert (identity.username, identity.status, identity.mfa_enabled, identity.email) == (
        "dave",
        "disabled",
        True,
        None,
    )


def cve(cve_id, score=7.5, severity="HIGH", metric="cvssMetricV31"):
    return {
        "cve": {
            "id": cve_id,
            "published": "2022-10-19T22:15:00.000",
            "descriptions": [{"lang": "es", "value": "otro"}, {"lang": "en", "value": f"{cve_id} summary"}],
            "metrics": {metric: [{"cvssData": {"baseScore": score, "baseSeverity": severity}}]},
        }
    }


def page(items, total, per_page):
    return {"totalResults": total, "resultsPerPage": per_page, "vulnerabilities": items}


def test_cpe_names_only_for_tracked_software():
    assert nvd.cpe_for("nginx", "1.21.6") == "cpe:2.3:a:f5:nginx:1.21.6:*:*:*:*:*:*:*"
    assert nvd.cpe_for("alpine", "3.22") is None


def test_parse_cve_prefers_newest_cvss_and_english_text():
    parsed = nvd.parse_cve(cve("CVE-2022-41741", 7.8))
    assert (parsed.cve_id, parsed.cvss_score, parsed.severity, parsed.summary) == (
        "CVE-2022-41741",
        7.8,
        "HIGH",
        "CVE-2022-41741 summary",
    )


def test_parse_cve_reads_cvss_v2_severity_from_the_metric():
    item = {
        "cve": {
            "id": "CVE-2010-1",
            "metrics": {"cvssMetricV2": [{"cvssData": {"baseScore": 5.0}, "baseSeverity": "MEDIUM"}]},
        }
    }
    assert nvd.parse_cve(item).severity == "MEDIUM"


def test_parse_cve_without_metrics():
    parsed = nvd.parse_cve({"cve": {"id": "CVE-2026-0001"}})
    assert (parsed.cvss_score, parsed.severity, parsed.summary) == (None, None, None)


@respx.mock
def test_client_follows_pagination():
    route = respx.get(nvd.NVD_URL).mock(
        side_effect=[
            httpx.Response(200, json=page([cve("CVE-1"), cve("CVE-2")], total=3, per_page=2)),
            httpx.Response(200, json=page([cve("CVE-3")], total=3, per_page=1)),
        ]
    )
    results = nvd.NvdClient(backoff=0).vulnerabilities("cpe:x")
    assert [v.cve_id for v in results] == ["CVE-1", "CVE-2", "CVE-3"]
    assert [call.request.url.params["startIndex"] for call in route.calls] == ["0", "2"]


@respx.mock
def test_client_retries_rate_limits_then_succeeds():
    respx.get(nvd.NVD_URL).mock(
        side_effect=[httpx.Response(403), httpx.Response(503), httpx.Response(200, json=page([], total=0, per_page=0))]
    )
    assert nvd.NvdClient(backoff=0).vulnerabilities("cpe:x") == []


@respx.mock
def test_client_gives_up_after_max_attempts():
    respx.get(nvd.NVD_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(nvd.NvdUnavailable, match="3 attempts"):
        nvd.NvdClient(max_attempts=3, backoff=0).vulnerabilities("cpe:x")


@respx.mock
def test_client_retries_network_errors():
    respx.get(nvd.NVD_URL).mock(side_effect=[httpx.ConnectError("down"), httpx.Response(200, json=page([], 0, 0))])
    assert nvd.NvdClient(backoff=0).vulnerabilities("cpe:x") == []


@respx.mock
def test_client_does_not_retry_bad_requests():
    route = respx.get(nvd.NVD_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(nvd.NvdUnavailable, match="404"):
        nvd.NvdClient(backoff=0).vulnerabilities("cpe:x")
    assert route.call_count == 1


@respx.mock
def test_client_sends_the_api_key_header():
    route = respx.get(nvd.NVD_URL).mock(return_value=httpx.Response(200, json=page([], 0, 0)))
    nvd.NvdClient(api_key="secret").vulnerabilities("cpe:x")
    assert route.calls[0].request.headers["apiKey"] == "secret"


def test_fallback_file(tmp_path):
    path = tmp_path / "fallback.json"
    saved = {"cve_id": "CVE-1", "severity": "HIGH", "cvss_score": 7.5, "published_at": None, "summary": None}
    path.write_text(json.dumps({"nginx:1.21.6": [saved]}))
    assert nvd.load_fallback(path, "nginx", "1.21.6")[0].cve_id == "CVE-1"
    assert nvd.load_fallback(path, "redis", "6.0.20") is None
    assert nvd.load_fallback(tmp_path / "missing.json", "nginx", "1.21.6") is None
