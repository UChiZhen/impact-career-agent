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
    "jd_content_hash",
    "application_status",
]
LEGACY_APPLICATION_TRACKER_HEADERS = APPLICATION_TRACKER_HEADERS[:14]


@dataclass(frozen=True)
class GoogleSheetsTrackerConfig:
    """Configuration for application tracker write-back."""

    spreadsheet_id: str
    sheet_name: str = "Application Tracker"
    credentials_path: str | None = None
    token_path: str | None = None

    @property
    def header_range(self) -> str:
        return f"{quote_sheet_name(self.sheet_name)}!A1:P1"

    @property
    def append_range(self) -> str:
        return f"{quote_sheet_name(self.sheet_name)}!A:P"

    @property
    def data_range(self) -> str:
        return f"{quote_sheet_name(self.sheet_name)}!A2:P"


@dataclass(frozen=True)
class TrackerPacketState:
    """Existing application packet state read from the tracker."""

    packet_id: str
    row_number: int
    jd_content_hash: str = ""
    drive_folder_url: str = ""
    application_status: str = ""


@dataclass(frozen=True)
class TrackerWriteResult:
    """Result from writing an application tracker row."""

    spreadsheet_id: str
    sheet_name: str
    updated_range: str = ""
    rows_written: int = 0
    action: str = "appended"
    row_number: int | None = None


class GoogleSheetsApplicationTracker:
    """Read and upsert application packet status rows in a Google Sheet."""

    def __init__(self, config: GoogleSheetsTrackerConfig):
        self.config = config

    def write_packet(
        self,
        packet: ApplicationPacket,
        *,
        output_result: PacketOutputResult | None = None,
        drive_result: GoogleDriveUploadResult | None = None,
        service: Any | None = None,
        force: bool = False,
    ) -> TrackerWriteResult:
        """Append a new packet or update the existing packet row."""
        service = service or self.build_sheets_service()
        packets = self.list_packets(service=service)
        existing = packets.get(packet.packet_id)
        row = application_tracker_row(
            packet,
            output_result=output_result,
            drive_result=drive_result,
        )
        jd_content_hash = str(packet.opportunity.metadata.get("jd_content_hash", ""))
        if (
            existing
            and jd_content_hash
            and existing.jd_content_hash == jd_content_hash
            and not force
        ):
            return TrackerWriteResult(
                spreadsheet_id=self.config.spreadsheet_id,
                sheet_name=self.config.sheet_name,
                action="skipped",
                row_number=existing.row_number,
            )

        if existing:
            row_range = (
                f"{quote_sheet_name(self.config.sheet_name)}!"
                f"A{existing.row_number}:P{existing.row_number}"
            )
            result = (
                service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.config.spreadsheet_id,
                    range=row_range,
                    valueInputOption="USER_ENTERED",
                    body={"values": [row]},
                )
                .execute()
            )
            return TrackerWriteResult(
                spreadsheet_id=self.config.spreadsheet_id,
                sheet_name=self.config.sheet_name,
                updated_range=result.get("updatedRange", row_range),
                rows_written=result.get("updatedRows", 0),
                action="updated",
                row_number=existing.row_number,
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
            action="appended",
            row_number=parse_row_number(updates.get("updatedRange", "")),
        )

    def list_packets(
        self,
        *,
        service: Any | None = None,
    ) -> dict[str, TrackerPacketState]:
        """Return tracker rows keyed by stable packet ID."""
        service = service or self.build_sheets_service()
        ensure_sheet_exists(service, self.config)
        ensure_application_tracker_header(service, self.config)
        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.config.spreadsheet_id,
                range=self.config.data_range,
            )
            .execute()
        )
        packets = {}
        for row_number, row in enumerate(result.get("values", []), start=2):
            packet_id = row_value(row, 1)
            if not packet_id:
                continue
            packets[packet_id] = TrackerPacketState(
                packet_id=packet_id,
                row_number=row_number,
                drive_folder_url=row_value(row, 8),
                jd_content_hash=row_value(row, 14),
                application_status=row_value(row, 15),
            )
        return packets

    def find_packet(
        self,
        packet_id: str,
        *,
        service: Any | None = None,
    ) -> TrackerPacketState | None:
        """Find one stable packet ID in the tracker."""
        return self.list_packets(service=service).get(packet_id)

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
    """Create or safely extend the tracker header row."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=config.spreadsheet_id, range=config.header_range)
        .execute()
    )
    values = result.get("values", [])
    existing = [str(value).strip() for value in values[0]] if values else []
    if existing == APPLICATION_TRACKER_HEADERS:
        return
    if existing and existing != LEGACY_APPLICATION_TRACKER_HEADERS:
        if existing != APPLICATION_TRACKER_HEADERS[: len(existing)]:
            raise ValueError(
                "Application tracker header does not match the supported schema; "
                "refusing to overwrite custom columns."
            )
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
        opportunity.metadata.get("jd_content_hash", ""),
        opportunity.metadata.get("application_status", "") or "materials_ready",
    ]


def row_value(row: list[Any], index: int) -> str:
    """Read one optional Sheets cell as a trimmed string."""
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def parse_row_number(updated_range: str) -> int | None:
    """Extract the first row number from a Sheets updated range."""
    import re

    match = re.search(r"![A-Z]+(\d+)", updated_range)
    return int(match.group(1)) if match else None


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
