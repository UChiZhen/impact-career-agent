from pathlib import Path

from career_agent.sinks.google_drive import (
    GoogleDriveConfig,
    GoogleDrivePacketSink,
    ensure_drive_folder,
    escape_drive_query_value,
    should_upload_to_drive,
)


def test_should_upload_to_drive_only_user_facing_files():
    assert should_upload_to_drive(Path("resume.docx"))
    assert should_upload_to_drive(Path("resume.pdf"))
    assert should_upload_to_drive(Path("manifest.json"))
    assert not should_upload_to_drive(Path("resume.json"))
    assert not should_upload_to_drive(Path("audit_notes.txt"))


def test_escape_drive_query_value_handles_quotes_and_backslashes():
    assert escape_drive_query_value("Impact's \\ Folder") == "Impact\\'s \\\\ Folder"


def test_ensure_drive_folder_reuses_existing_folder():
    service = FakeDriveService(
        list_results=[
            {"files": [{"id": "folder-1", "name": "Impact Career Agent"}]},
        ]
    )

    folder_id = ensure_drive_folder(service, "Impact Career Agent")

    assert folder_id == "folder-1"
    assert not service.created


def test_ensure_drive_folder_creates_missing_folder_under_parent():
    service = FakeDriveService(list_results=[{"files": []}])

    folder_id = ensure_drive_folder(service, "Applications", parent_id="root-1")

    assert folder_id == "created-1"
    assert service.created[0]["body"] == {
        "name": "Applications",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": ["root-1"],
    }


def test_drive_packet_sink_creates_folder_tree_and_uploads_filtered_files(tmp_path, monkeypatch):
    folder = tmp_path / "2026-06-19__example__role__hash"
    folder.mkdir()
    resume = folder / "resume.docx"
    cover = folder / "cover_letter.docx"
    manifest = folder / "manifest.json"
    debug = folder / "resume.json"
    for path in (resume, cover, manifest, debug):
        path.write_text("x", encoding="utf-8")

    service = FakeDriveService(
        list_results=[
            {"files": []},
            {"files": []},
            {"files": []},
        ]
    )
    uploaded = []

    def fake_upload(service_arg, path, *, parent_id):
        uploaded.append({"name": path.name, "parent_id": parent_id})
        return {"id": f"file-{len(uploaded)}", "name": path.name, "url": "https://drive/file"}

    monkeypatch.setattr("career_agent.sinks.google_drive.upload_drive_file", fake_upload)
    sink = GoogleDrivePacketSink(GoogleDriveConfig())

    result = sink.upload_packet_folder(
        folder,
        [resume, cover, manifest, debug],
        service=service,
    )

    assert result.folder_id == "created-3"
    assert result.folder_url.endswith("/created-3")
    assert [item["name"] for item in uploaded] == [
        "resume.docx",
        "cover_letter.docx",
        "manifest.json",
    ]
    assert all(item["parent_id"] == "created-3" for item in uploaded)
    assert [created["body"]["name"] for created in service.created] == [
        "Impact Career Agent",
        "Applications",
        folder.name,
    ]


class FakeDriveService:
    def __init__(self, list_results):
        self.list_results = list(list_results)
        self.created = []

    def files(self):
        return self

    def list(self, **kwargs):
        self.last_list = kwargs
        return FakeExecute(self.list_results.pop(0))

    def create(self, **kwargs):
        self.created.append(kwargs)
        is_folder = kwargs.get("body", {}).get("mimeType") == "application/vnd.google-apps.folder"
        if is_folder:
            payload = {
                "id": f"created-{len(self.created)}",
                "name": kwargs["body"]["name"],
                "webViewLink": "https://drive/folder",
            }
        else:
            payload = {
                "id": f"file-{len(self.created)}",
                "name": kwargs["body"]["name"],
                "webViewLink": "https://drive/file",
            }
        return FakeExecute(payload)


class FakeExecute:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload
