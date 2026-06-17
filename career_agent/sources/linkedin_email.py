"""Live LinkedIn alert email source connector boundary.

This module is the future home for the working Gmail parser currently in:

- `linkedin_email/src/gmail_reader.py`

The legacy source searches Gmail using:

`from:jobalerts-noreply@linkedin.com after:YYYY/MM/DD`
"""

from __future__ import annotations

from dataclasses import dataclass

from career_agent.core import Opportunity
from career_agent.sources.opportunities import LINKEDIN_ALERT_SENDER


@dataclass(frozen=True)
class LinkedInEmailSourceConfig:
    """Configuration for LinkedIn job alert emails."""

    sender: str = LINKEDIN_ALERT_SENDER
    hours_back: int = 26
    max_results: int = 20
    credentials_path: str | None = None
    token_path: str | None = None

    def gmail_query(self, after_date: str) -> str:
        """Build the Gmail query used by the legacy parser."""
        return f"from:{self.sender} after:{after_date}"


class LinkedInEmailSource:
    """Live source for LinkedIn alert emails in Gmail."""

    source_name = "linkedin_email"

    def __init__(self, config: LinkedInEmailSourceConfig):
        self.config = config

    def fetch(self) -> list[Opportunity]:
        """Fetch opportunities from LinkedIn alert emails.

        Porting target:
        1. Authenticate with Gmail readonly scope.
        2. Search for `config.gmail_query(after_date)`.
        3. Parse HTML job cards and `/jobs/view/` links.
        4. Normalize each result into `Opportunity(source="linkedin_email")`.
        """
        raise NotImplementedError("Live LinkedIn email parsing will be ported after v0.1 fixtures")
