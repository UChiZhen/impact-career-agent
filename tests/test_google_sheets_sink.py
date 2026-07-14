from types import SimpleNamespace

from career_agent.core import ApplicationPacket, FitScore, GeneratedDocument, Opportunity
from career_agent.sinks.google_sheets import (
    APPLICATION_TRACKER_HEADERS,
    GoogleSheetsApplicationTracker,
    GoogleSheetsTrackerConfig,
    application_tracker_row,
    ensure_application_tracker_header,
    ensure_sheet_exists,
    quote_sheet_name,
)


def demo_packet(*, jd_content_hash=""):
    return ApplicationPacket(
        candidate_name="Jane Doe",
        opportunity=Opportunity(
            source="manual",
            company="Example Impact Fund",
            job_title="Impact Investment Analyst",
            location="Chicago, IL",
            job_url="https://example.org/jobs/123",
            metadata={"jd_content_hash": jd_content_hash} if jd_content_hash else {},
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
    assert row[11] == ""
    assert row[14] == ""
    assert row[15] == "materials_ready"


def test_ensure_application_tracker_header_writes_when_empty():
    service = FakeSheetsService(header_values=[])
    config = GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")

    ensure_application_tracker_header(service, config)

    assert service.get_requests == [
        {"spreadsheetId": "sheet-1", "range": "'Application Tracker'!A1:P1"}
    ]
    assert service.update_requests[0]["body"] == {"values": [APPLICATION_TRACKER_HEADERS]}


def test_ensure_application_tracker_header_extends_supported_prefix():
    service = FakeSheetsService(header_values=[["created_at", "packet_id"]])
    config = GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")

    ensure_application_tracker_header(service, config)

    assert service.update_requests[0]["body"] == {"values": [APPLICATION_TRACKER_HEADERS]}


def test_ensure_application_tracker_header_keeps_current_header():
    service = FakeSheetsService(header_values=[APPLICATION_TRACKER_HEADERS])
    config = GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")

    ensure_application_tracker_header(service, config)

    assert not service.update_requests


def test_ensure_application_tracker_header_extends_legacy_schema():
    service = FakeSheetsService(header_values=[APPLICATION_TRACKER_HEADERS[:14]])
    config = GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")

    ensure_application_tracker_header(service, config)

    assert service.update_requests[0]["range"] == "'Application Tracker'!A1:P1"
    assert service.update_requests[0]["body"] == {"values": [APPLICATION_TRACKER_HEADERS]}


def test_ensure_sheet_exists_creates_missing_tracker_tab():
    service = FakeSheetsService(header_values=[], sheet_titles=["Sheet1"])
    config = GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")

    ensure_sheet_exists(service, config)

    assert service.batch_update_requests == [
        {
            "spreadsheetId": "sheet-1",
            "body": {
                "requests": [
                    {"addSheet": {"properties": {"title": "Application Tracker"}}}
                ]
            },
        }
    ]


def test_ensure_sheet_exists_reuses_existing_tracker_tab():
    service = FakeSheetsService(header_values=[], sheet_titles=["Application Tracker"])
    config = GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")

    ensure_sheet_exists(service, config)

    assert not service.batch_update_requests


def test_google_sheets_application_tracker_appends_packet_row():
    service = FakeSheetsService(
        header_values=[APPLICATION_TRACKER_HEADERS],
        sheet_titles=["Applications"],
    )
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
    assert service.append_requests[0]["range"] == "'Applications'!A:P"
    assert service.append_requests[0]["body"]["values"][0][3] == "Example Impact Fund"
    assert result.action == "appended"
    assert result.row_number == 2


def test_google_sheets_application_tracker_reads_existing_packet_state():
    packet = demo_packet(jd_content_hash="jd-v1")
    row = application_tracker_row(packet)
    row[8] = "https://drive/folder-existing"
    service = FakeSheetsService(
        header_values=[APPLICATION_TRACKER_HEADERS],
        data_values=[row],
    )
    tracker = GoogleSheetsApplicationTracker(
        GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")
    )

    state = tracker.find_packet(packet.packet_id, service=service)

    assert state is not None
    assert state.row_number == 2
    assert state.jd_content_hash == "jd-v1"
    assert state.drive_folder_url == "https://drive/folder-existing"


def test_google_sheets_application_tracker_skips_same_jd_version():
    packet = demo_packet(jd_content_hash="jd-v1")
    service = FakeSheetsService(
        header_values=[APPLICATION_TRACKER_HEADERS],
        data_values=[application_tracker_row(packet)],
    )
    tracker = GoogleSheetsApplicationTracker(
        GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")
    )

    result = tracker.write_packet(packet, service=service)

    assert result.action == "skipped"
    assert result.rows_written == 0
    assert not service.append_requests
    assert not service.update_requests


def test_google_sheets_application_tracker_updates_changed_jd_version():
    old_packet = demo_packet(jd_content_hash="jd-v1")
    new_packet = demo_packet(jd_content_hash="jd-v2")
    service = FakeSheetsService(
        header_values=[APPLICATION_TRACKER_HEADERS],
        data_values=[application_tracker_row(old_packet)],
    )
    tracker = GoogleSheetsApplicationTracker(
        GoogleSheetsTrackerConfig(spreadsheet_id="sheet-1")
    )

    result = tracker.write_packet(new_packet, service=service)

    assert result.action == "updated"
    assert result.row_number == 2
    assert service.update_requests[0]["range"] == "'Application Tracker'!A2:P2"
    assert service.update_requests[0]["body"]["values"][0][14] == "jd-v2"
    assert not service.append_requests


class FakeSheetsService:
    def __init__(self, *, header_values, data_values=None, sheet_titles=None):
        self.header_values = header_values
        self.data_values = data_values or []
        self.sheet_titles = sheet_titles or ["Application Tracker"]
        self.get_requests = []
        self.update_requests = []
        self.append_requests = []
        self.batch_update_requests = []

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, **kwargs):
        self.get_requests.append(kwargs)
        if "fields" in kwargs:
            return FakeExecute(
                {
                    "sheets": [
                        {"properties": {"title": title}}
                        for title in self.sheet_titles
                    ]
                }
            )
        if kwargs.get("range", "").endswith("!A2:P"):
            return FakeExecute({"values": self.data_values})
        return FakeExecute({"values": self.header_values})

    def batchUpdate(self, **kwargs):
        self.batch_update_requests.append(kwargs)
        return FakeExecute({"replies": [{"addSheet": {"properties": {"sheetId": 1}}}]})

    def update(self, **kwargs):
        self.update_requests.append(kwargs)
        return FakeExecute({"updatedRange": kwargs["range"], "updatedRows": 1})

    def append(self, **kwargs):
        self.append_requests.append(kwargs)
        return FakeExecute({"updates": {"updatedRange": "Applications!A2:P2", "updatedRows": 1}})


class FakeExecute:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload
