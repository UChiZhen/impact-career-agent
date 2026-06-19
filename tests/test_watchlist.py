from career_agent.sources.watchlist import (
    GoogleSheetsOrganizationSource,
    GoogleSheetsWatchlistConfig,
    organizations_from_sheet_values,
)


def test_organizations_from_job_radar_sheet_values():
    values = [
        ["Organizations", "Website", "Locations", "Relevant Industry", "Priority", "Tags"],
        [
            "Example Impact Fund",
            "https://example.org/careers",
            "United States",
            "impact investing",
            "1",
            "fund, climate",
        ],
        ["Missing URL", "", "United States", "philanthropy"],
    ]

    organizations = organizations_from_sheet_values(values)

    assert len(organizations) == 1
    assert organizations[0].name == "Example Impact Fund"
    assert organizations[0].career_url == "https://example.org/careers"
    assert organizations[0].location == "United States"
    assert organizations[0].industry == "impact investing"
    assert organizations[0].priority == 1
    assert organizations[0].tags == ("fund", "climate")


def test_google_sheets_organization_source_fetches_from_service_boundary():
    service = FakeSheetsService(
        values=[
            ["Organizations", "Website", "Locations", "Relevant Industry"],
            ["Example Green Bank", "https://green.example/careers", "Chicago", "climate finance"],
        ]
    )
    source = GoogleSheetsOrganizationSource(
        GoogleSheetsWatchlistConfig(
            spreadsheet_id="sheet-123",
            sheet_name="Organizations",
            credentials_path="~/credentials.json",
            token_path="~/token.json",
        )
    )

    organizations = source.fetch_from_service(service)

    assert service.request == {
        "spreadsheetId": "sheet-123",
        "range": "Organizations!A:J",
    }
    assert len(organizations) == 1
    assert organizations[0].name == "Example Green Bank"


class FakeExecutable:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeValuesResource:
    def __init__(self, service):
        self.service = service

    def get(self, *, spreadsheetId, range):
        self.service.request = {
            "spreadsheetId": spreadsheetId,
            "range": range,
        }
        return FakeExecutable({"values": self.service.values})


class FakeSpreadsheetsResource:
    def __init__(self, service):
        self.service = service

    def values(self):
        return FakeValuesResource(self.service)


class FakeSheetsService:
    def __init__(self, *, values):
        self.values = values
        self.request = None

    def spreadsheets(self):
        return FakeSpreadsheetsResource(self)
