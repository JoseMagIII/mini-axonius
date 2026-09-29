import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
PAGE_SIZE = 2000
RETRY_STATUSES = {403, 429, 500, 502, 503, 504}

# NVD identifies products by CPE name, not by Docker image name.
CPE_TEMPLATES = {
    "nginx": "cpe:2.3:a:f5:nginx:{version}:*:*:*:*:*:*:*",
    "redis": "cpe:2.3:a:redis:redis:{version}:*:*:*:*:*:*:*",
}


@dataclass(frozen=True)
class Vulnerability:
    cve_id: str
    severity: str | None
    cvss_score: float | None
    published_at: str | None
    summary: str | None


class NvdUnavailable(Exception):
    pass


def cpe_for(software: str, version: str) -> str | None:
    template = CPE_TEMPLATES.get(software)
    return template.format(version=version) if template else None


def parse_cve(item: dict) -> Vulnerability:
    cve = item["cve"]
    metrics = cve.get("metrics", {})
    # Prefer the newest CVSS version NVD has scored.
    scored = next(
        (metrics[k][0] for k in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2") if metrics.get(k)),
        None,
    )
    data = scored["cvssData"] if scored else {}
    summary = next((d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"), None)
    return Vulnerability(
        cve_id=cve["id"],
        severity=data.get("baseSeverity") or (scored or {}).get("baseSeverity"),
        cvss_score=data.get("baseScore"),
        published_at=cve.get("published"),
        summary=summary,
    )


class NvdClient:
    """Pages through NVD results and backs off on rate limits (5 requests per 30s without a key)."""

    def __init__(
        self, api_key: str | None = None, http: httpx.Client | None = None, max_attempts: int = 3, backoff: float = 2.0
    ):
        headers = {"apiKey": api_key} if api_key else {}
        self.http = http or httpx.Client(timeout=10, headers=headers)
        self.max_attempts = max_attempts
        self.backoff = backoff

    def _get_page(self, cpe: str, start: int) -> dict:
        params = {"cpeName": cpe, "startIndex": start, "resultsPerPage": PAGE_SIZE}
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.http.get(NVD_URL, params=params)
            except httpx.TransportError as error:
                last_error = f"network error: {error}"
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code not in RETRY_STATUSES:
                    raise NvdUnavailable(f"NVD returned {response.status_code}")
                last_error = f"NVD returned {response.status_code}"
            if attempt < self.max_attempts:
                time.sleep(self.backoff * attempt)
        raise NvdUnavailable(f"gave up after {self.max_attempts} attempts ({last_error})")

    def vulnerabilities(self, cpe: str) -> list[Vulnerability]:
        results, start, total = [], 0, None
        while total is None or start < total:
            page = self._get_page(cpe, start)
            total = page["totalResults"]
            results.extend(parse_cve(item) for item in page["vulnerabilities"])
            start += page["resultsPerPage"] or PAGE_SIZE
        return results


def load_fallback(path: Path, software: str, version: str) -> list[Vulnerability] | None:
    """Returns the saved copy for this version, or None if the file doesn't have one."""
    if not path.exists():
        return None
    saved = json.loads(path.read_text()).get(f"{software}:{version}")
    return None if saved is None else [Vulnerability(**v) for v in saved]
