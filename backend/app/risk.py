import json
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db import query

Severity = Literal["critical", "high", "medium", "low"]

SYSTEM_PROMPT = """You are a security analyst writing a short risk briefing for Acme's IT leadership. \
You get Acme's current security gaps as JSON. Rank the findings by real-world risk: exposure in \
production, exploitable CVEs, and accounts nobody is accountable for matter most. Keep every field short \
and plain. Only use hostnames and CVE IDs that appear in the data."""


class Finding(BaseModel):
    title: str = Field(description="Under 10 words")
    severity: Severity
    hostnames: list[str]
    why_it_matters: str = Field(description="One sentence")
    recommended_action: str = Field(description="One sentence, starting with a verb")


class RiskReport(BaseModel):
    overall_risk: Severity
    headline: str = Field(description="One sentence summary for an executive")
    findings: list[Finding] = Field(description="At most 5, most urgent first")


class RiskSummaryError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


GAP_VIEWS = {
    "missing_edr": "gap_missing_edr",
    "vulnerable_software": "gap_vulnerable_software",
    "orphaned_owner": "gap_orphaned_owner",
    "ghost_assets": "gap_ghost_assets",
}


def current_gaps() -> dict:
    return {name: query(f"SELECT * FROM {view}") for name, view in GAP_VIEWS.items()}


async def summarize(client: anthropic.AsyncAnthropic | None = None) -> RiskReport:
    """Makes one direct Claude API call that returns a validated RiskReport."""
    settings = get_settings()
    if client is None:
        if not settings.anthropic_api_key:
            raise RiskSummaryError("Add ANTHROPIC_API_KEY to .env to generate a risk summary.", 503)
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    gaps = json.dumps(current_gaps(), default=str)
    try:
        response = await client.messages.parse(
            model=settings.claude_model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Current security gaps:\n{gaps}"}],
            output_format=RiskReport,
        )
    except anthropic.AuthenticationError as error:
        raise RiskSummaryError("Claude rejected the API key. Check ANTHROPIC_API_KEY in .env.", 502) from error
    except anthropic.RateLimitError as error:
        raise RiskSummaryError("Claude is rate limiting requests. Try again in a minute.", 429) from error
    except anthropic.APIStatusError as error:
        raise RiskSummaryError(f"Claude returned an error ({error.status_code}): {error.message}", 502) from error
    except anthropic.APIConnectionError as error:
        raise RiskSummaryError("Couldn't reach the Claude API. Check your network.", 502) from error

    if response.parsed_output is None:
        raise RiskSummaryError(f"Claude didn't return a report (stop reason: {response.stop_reason}).", 502)
    return response.parsed_output
