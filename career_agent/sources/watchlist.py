"""Private organization watchlist loaders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from career_agent.google_auth import load_stored_google_credentials
from career_agent.sources.opportunities import Organization


JOB_RADAR_GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
)


@dataclass(frozen=True)
class GoogleSheetsWatchlistConfig:
    """Configuration for a private Google Sheets organization watchlist."""

    spreadsheet_id: str
    sheet_name: str = "Organizations"
    credentials_path: str | None = None
    token_path: str | None = None
    range_columns: str = "A:J"

    @property
    def read_range(self) -> str:
        return f"{self.sheet_name}!{self.range_columns}"


class GoogleSheetsOrganizationSource:
    """Load target organizations from a private Google Sheet.

    This ports the read-only watchlist behavior from
    `jobsearch/job-radar/src/sheets.py` without assuming that any user's
    organization list is public fixture data.
    """

    def __init__(self, config: GoogleSheetsWatchlistConfig):
        self.config = config

    def fetch(self) -> list[Organization]:
        service = self.build_sheets_service()
        return self.fetch_from_service(service)

    def fetch_from_service(self, service: Any) -> list[Organization]:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=self.config.spreadsheet_id, range=self.config.read_range)
            .execute()
        )
        return organizations_from_sheet_values(result.get("values", []))

    def build_sheets_service(self):
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google Sheets watchlist requires optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[gmail]'`."
            ) from exc

        credentials = self.get_credentials()
        return build("sheets", "v4", credentials=credentials)

    def get_credentials(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise RuntimeError(
                "Google Sheets authentication requires optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[gmail]'`."
            ) from exc

        credentials_path = resolve_path(self.config.credentials_path)
        token_path = resolve_path(self.config.token_path)
        if credentials_path is None or token_path is None:
            raise FileNotFoundError("Google Sheets watchlist needs credentials_path and token_path.")

        credentials = None
        if token_path.exists():
            credentials = load_stored_google_credentials(Credentials, token_path)

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(f"OAuth credentials not found at {credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path),
                JOB_RADAR_GOOGLE_SCOPES,
            )
            credentials = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
        return credentials


def organizations_from_sheet_values(values: list[list[str]]) -> list[Organization]:
    """Map Job Radar-style sheet rows into `Organization` objects."""
    if not values:
        return []

    headers = [normalize_header(header) for header in values[0]]
    organizations: list[Organization] = []

    for row in values[1:]:
        padded_row = row + [""] * (len(headers) - len(row))
        item = dict(zip(headers, padded_row))
        organization = organization_from_sheet_row(item)
        if organization:
            organizations.append(organization)

    return organizations


def organization_from_sheet_row(row: dict[str, str]) -> Organization | None:
    """Map one normalized Google Sheets row into an organization."""
    name = first_value(row, "organizations", "organization", "name")
    career_url = first_value(row, "website", "career_url", "careers_url", "url")
    if not name or not career_url:
        return None

    tags = first_value(row, "tags", "tag")
    return Organization(
        name=name,
        career_url=career_url,
        location=first_value(row, "locations", "location"),
        industry=first_value(row, "relevant_industry", "industry"),
        priority=parse_priority(first_value(row, "priority")),
        tags=tuple(split_tags(tags)),
    )


def normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def first_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key, "")
        if value:
            return value.strip()
    return ""


def split_tags(value: str) -> list[str]:
    if not value:
        return []
    return [tag.strip() for tag in value.replace(";", ",").split(",") if tag.strip()]


def parse_priority(value: str) -> int:
    if not value:
        return 3
    try:
        return int(value)
    except ValueError:
        return 3


def resolve_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser()
