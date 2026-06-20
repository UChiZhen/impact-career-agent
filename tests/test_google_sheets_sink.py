from types import SimpleNamespace

from career_agent.core import ApplicationPacket, FitScore, GeneratedDocument, Opportunity
from career_agent.sinks.google_sheets import (
    APPLICATION_TRACKER_HEADERS,
    GoogleSheetsApplicationTracker,
    GoogleSheetsTrackerConfig,
    application_tracker_row,
    ensure_application_tracker_header,
    quote_sheet_name,
)


def demo_packet():
    return ApplicationPacket(
        candidate_name="Jane Doe",
        opportunity=Opportunity(
            source="manual",
            company="Example Impact Fund",
            job_title="Impact Investment Analyst",
            location="Chicago, IL",
            job_url="https://example.org/jobs/123",
            fit=FitScore(
                total=88,
                recommended_action="apply_now",
                resume_angle="Lead with impact finance analytics.",
            ),
        ),
        documents=[
            GeneratedDocument(document_type="resume", content="{}", format="json"),
            GeneratedDocument(document_type="cover_letter", content="{}", format="json"),
        ],
    )


def test_quote_sheet_name_escapes_single_quotes():
    assert quote_sheet_name("Zhen's Tracker") == "'Zhen''s Tracker'"


def test_application_tracker_row_uses_drive_file_names():
    packet = demo_packet()
    drive_result = SimpleNamespace(
        folder_url="https://drive.google.com/folders/folder-1",
        files=[
            {"name": "Resume - Example Impact Fund - Impact Investment Analyst.docx"},
            {"name": "Cover Letter - Example Impact Fund - Impact Investment Analyst.docx"},
            {"name": "manifest.json"},
        ],
    )

    row = application_tracker_row(packet, drive_result=drive_result)

    assert row[1] == packet.packet_id
    assert row[3] == "Example Impact Fund"
    assert row[6] == 88
    assert row[7] == "apply_now"
    assert row[8] == "https://drive.google.com/folders/folder-1"
    assert row[9].startswith("Resume - Example Impact Fund")
    assert row[10].startswith("Cover Letter - Example Impact Fund")
    assert row[11] == "manifest.json"


def test_ensure_application_tracker_header_writes_when_empty():
    service = FakeSheetsService(header_values=[])
    config = GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")

    ensure_application_tracker_header(service, config)

    assert service.get_requests == [
        {"spreadsheetId": "sheet-1", "range": "'Application Tracker'!A1:N1"}
    ]
    assert service.update_requests[0]["body"] == {"values": [APPLICATION_TRACKER_HEADERS]}


def test_ensure_application_tracker_header_keeps_existing_header():
    service = FakeSheetsService(header_values=[["created_at", "packet_id"]])
    config = GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")

    ensure_application_tracker_header(service, config)

    assert not service.update_requests


def test_google_sheets_application_tracker_appends_packet_row():
    service = FakeSheetsService(header_values=[["created_at", "packet_id"]])
    config = GoogleSheetsTrackerConfig(
        spreadsheet_id="sheet-1",
        sheet_name="Applications",
    )
    tracker = GoogleSheetsApplicationTracker(config)

    result = tracker.write_packet(
        demo_packet(),
        drive_result=SimpleNamespace(folder_url="https://drive/folder", files=[]),
        service=service,
    )

    assert result.rows_written == 1
    assert service.append_requests[0]["range"] == "'Applications'!A:N"
    assert service.append_requests[0]["body"]["values"][0][3] == "Example Impact Fund"


class FakeSheetsService:
    def __init__(self, *, header_values):
        self.header_values = header_values
        self.get_requests = []
        self.update_requests = []
        self.append_requests = []

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, **kwargs):
        self.get_requests.append(kwargs)
        return FakeExecute({"values": self.header_values})

    def update(self, **kwargs):
        self.update_requests.append(kwargs)
        return FakeExecute({"updatedRows": 1})

    def append(self, **kwargs):
        self.append_requests.append(kwargs)
        return FakeExecute({"updates": {"updatedRange": "Applications!A2:N2", "updatedRows": 1}})


class FakeExecute:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload
