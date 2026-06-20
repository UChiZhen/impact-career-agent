"""Google Sheets write-back sinks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from career_agent.applications.packet_outputs import PacketOutputResult
from career_agent.core import ApplicationPacket
from career_agent.sinks.google_drive import GoogleDriveUploadResult
from career_agent.sources.watchlist import JOB_RADAR_GOOGLE_SCOPES, resolve_path


APPLICATION_TRACKER_HEADERS = [
    "created_at",
    "packet_id",
    "candidate_name",
    "company",
    "job_title",
    "location",
    "fit_score",
    "recommended_action",
    "drive_folder_url",
    "resume_file",
    "cover_letter_file",
    "manifest_file",
    "job_url",
    "source",
]


@dataclass(frozen=True)
class GoogleSheetsTrackerConfig:
    """Configuration for application tracker write-back."""

    spreadsheet_id: str
    sheet_name: str = "Application Tracker"
    credentials_path: str | None = None
    token_path: str | None = None

    @property
    def header_range(self) -> str:
        return f"{quote_sheet_name(self.sheet_name)}!A1:N1"

    @property
    def append_range(self) -> str:
        return f"{quote_sheet_name(self.sheet_name)}!A:N"


@dataclass(frozen=True)
class TrackerWriteResult:
    """Result from writing an application tracker row."""

    spreadsheet_id: str
    sheet_name: str
    updated_range: str = ""
    rows_written: int = 0


class GoogleSheetsApplicationTracker:
    """Append application packet status rows to a Google Sheet."""

    def __init__(self, config: GoogleSheetsTrackerConfig):
        self.config = config

    def write_packet(
        self,
        packet: ApplicationPacket,
        *,
        output_result: PacketOutputResult | None = None,
        drive_result: GoogleDriveUploadResult | None = None,
        service: Any | None = None,
    ) -> TrackerWriteResult:
        """Ensure headers and append one application tracker row."""
        service = service or self.build_sheets_service()
        ensure_sheet_exists(service, self.config)
        ensure_application_tracker_header(service, self.config)
        row = application_tracker_row(
            packet,
            output_result=output_result,
            drive_result=drive_result,
        )
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.config.spreadsheet_id,
                range=self.config.append_range,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            )
            .execute()
        )
        updates = result.get("updates", {})
        return TrackerWriteResult(
            spreadsheet_id=self.config.spreadsheet_id,
            sheet_name=self.config.sheet_name,
            updated_range=updates.get("updatedRange", ""),
            rows_written=updates.get("updatedRows", 0),
        )

    def build_sheets_service(self):
        """Build a Google Sheets API service."""
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google Sheets write-back requires optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[google]'`."
            ) from exc

        credentials = self.get_credentials()
        return build("sheets", "v4", credentials=credentials)

    def get_credentials(self):
        """Load or refresh OAuth credentials for Sheets write-back."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise RuntimeError(
                "Google Sheets authentication requires optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[google]'`."
            ) from exc

        credentials_path = resolve_path(self.config.credentials_path)
        token_path = resolve_path(self.config.token_path)
        if credentials_path is None or token_path is None:
            raise FileNotFoundError("Google Sheets write-back needs credentials_path and token_path.")

        credentials = None
        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(
                str(token_path),
                JOB_RADAR_GOOGLE_SCOPES,
            )

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


def ensure_sheet_exists(service: Any, config: GoogleSheetsTrackerConfig) -> None:
    """Create the tracker tab when it is missing."""
    result = (
        service.spreadsheets()
        .get(
            spreadsheetId=config.spreadsheet_id,
            fields="sheets(properties(title))",
        )
        .execute()
    )
    titles = {
        sheet.get("properties", {}).get("title")
        for sheet in result.get("sheets", [])
    }
    if config.sheet_name in titles:
        return
    (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=config.spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": config.sheet_name}}}]},
        )
        .execute()
    )


def ensure_application_tracker_header(service: Any, config: GoogleSheetsTrackerConfig) -> None:
    """Write the tracker header row if the sheet range is empty."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=config.spreadsheet_id, range=config.header_range)
        .execute()
    )
    values = result.get("values", [])
    if values and any(str(value).strip() for value in values[0]):
        return
    (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=config.spreadsheet_id,
            range=config.header_range,
            valueInputOption="RAW",
            body={"values": [APPLICATION_TRACKER_HEADERS]},
        )
        .execute()
    )


def application_tracker_row(
    packet: ApplicationPacket,
    *,
    output_result: PacketOutputResult | None = None,
    drive_result: GoogleDriveUploadResult | None = None,
) -> list[str | int]:
    """Build one tracker row from an application packet."""
    opportunity = packet.opportunity
    fit = opportunity.fit
    files = [path.name for path in output_result.files] if output_result else []
    if drive_result:
        files.extend(item.get("name", "") for item in drive_result.files)
    return [
        packet.created_at.isoformat(),
        packet.packet_id,
        packet.candidate_name,
        opportunity.company,
        opportunity.job_title,
        opportunity.location,
        fit.total if fit else "",
        fit.recommended_action if fit else "",
        drive_result.folder_url if drive_result else "",
        first_file_name(files, ".docx", "resume"),
        first_file_name(files, ".docx", "cover"),
        "manifest.json" if "manifest.json" in files else "",
        opportunity.job_url or "",
        opportunity.source,
    ]


def first_file_name(files: list[str], suffix: str, contains: str) -> str:
    """Find the first matching filename."""
    for file_name in files:
        normalized = file_name.lower()
        if normalized.endswith(suffix) and contains in normalized:
            return file_name
    return ""


def quote_sheet_name(sheet_name: str) -> str:
    """Quote a sheet name for A1 notation."""
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'"
