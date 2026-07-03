"""Google Drive output sink for application packets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from career_agent.sources.watchlist import JOB_RADAR_GOOGLE_SCOPES, resolve_path


DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class GoogleDriveConfig:
    """Configuration for Google Drive packet uploads."""

    credentials_path: str | None = None
    token_path: str | None = None
    root_folder_name: str = "Impact Career Agent"
    applications_folder_name: str = "Applications"
    replace_existing: bool = False


@dataclass
class GoogleDriveUploadResult:
    """Result returned after uploading a packet folder."""

    folder_id: str
    folder_url: str
    files: list[dict[str, str]] = field(default_factory=list)


class GoogleDrivePacketSink:
    """Upload rendered application packet files to Google Drive."""

    def __init__(self, config: GoogleDriveConfig):
        self.config = config

    def upload_packet_folder(
        self,
        folder: Path,
        files: list[Path],
        service: Any | None = None,
    ) -> GoogleDriveUploadResult:
        """Create Drive folders and upload selected packet files."""
        service = service or self.build_drive_service()
        root_id = ensure_drive_folder(
            service,
            self.config.root_folder_name,
        )
        applications_id = ensure_drive_folder(
            service,
            self.config.applications_folder_name,
            parent_id=root_id,
        )
        packet_folder_id = ensure_drive_folder(
            service,
            Path(folder).name,
            parent_id=applications_id,
        )
        uploaded_files = [
            upload_drive_file(
                service,
                Path(file_path),
                parent_id=packet_folder_id,
                replace_existing=self.config.replace_existing,
            )
            for file_path in files
            if should_upload_to_drive(Path(file_path))
        ]
        return GoogleDriveUploadResult(
            folder_id=packet_folder_id,
            folder_url=drive_folder_url(packet_folder_id),
            files=uploaded_files,
        )

    def build_drive_service(self):
        """Build a Google Drive API service."""
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google Drive uploads require optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[google]'`."
            ) from exc

        credentials = self.get_credentials()
        return build("drive", "v3", credentials=credentials)

    def get_credentials(self):
        """Load or refresh OAuth credentials for Drive uploads."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise RuntimeError(
                "Google Drive authentication requires optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[google]'`."
            ) from exc

        credentials_path = resolve_path(self.config.credentials_path)
        token_path = resolve_path(self.config.token_path)
        if credentials_path is None or token_path is None:
            raise FileNotFoundError("Google Drive uploads need credentials_path and token_path.")

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


def ensure_drive_folder(service: Any, name: str, parent_id: str | None = None) -> str:
    """Find or create a Drive folder by name and parent."""
    existing = find_drive_folder(service, name=name, parent_id=parent_id)
    if existing:
        return existing["id"]

    body: dict[str, Any] = {
        "name": name,
        "mimeType": DRIVE_FOLDER_MIME_TYPE,
    }
    if parent_id:
        body["parents"] = [parent_id]
    created = (
        service.files()
        .create(body=body, fields="id,name,webViewLink", supportsAllDrives=True)
        .execute()
    )
    return created["id"]


def find_drive_folder(
    service: Any,
    *,
    name: str,
    parent_id: str | None = None,
) -> dict[str, str] | None:
    """Find a Drive folder by exact name."""
    query = [
        f"name = '{escape_drive_query_value(name)}'",
        f"mimeType = '{DRIVE_FOLDER_MIME_TYPE}'",
        "trashed = false",
    ]
    if parent_id:
        query.append(f"'{escape_drive_query_value(parent_id)}' in parents")
    result = (
        service.files()
        .list(
            q=" and ".join(query),
            spaces="drive",
            fields="files(id,name,webViewLink)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = result.get("files", [])
    return files[0] if files else None


def find_drive_file(
    service: Any,
    *,
    name: str,
    parent_id: str,
) -> dict[str, str] | None:
    """Find a Drive file by exact name and parent."""
    query = [
        f"name = '{escape_drive_query_value(name)}'",
        f"'{escape_drive_query_value(parent_id)}' in parents",
        "trashed = false",
    ]
    result = (
        service.files()
        .list(
            q=" and ".join(query),
            spaces="drive",
            fields="files(id,name,webViewLink,mimeType)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = result.get("files", [])
    return files[0] if files else None


def upload_drive_file(
    service: Any,
    path: Path,
    *,
    parent_id: str,
    replace_existing: bool = False,
) -> dict[str, str]:
    """Upload one local file to Drive."""
    media_body = media_file_upload(str(path), resumable=False)
    existing = (
        find_drive_file(service, name=path.name, parent_id=parent_id)
        if replace_existing
        else None
    )
    if existing:
        uploaded = (
            service.files()
            .update(
                fileId=existing["id"],
                body={"name": path.name},
                media_body=media_body,
                fields="id,name,webViewLink,mimeType",
                supportsAllDrives=True,
            )
            .execute()
        )
        action = "updated"
    else:
        uploaded = (
            service.files()
            .create(
                body={"name": path.name, "parents": [parent_id]},
                media_body=media_body,
                fields="id,name,webViewLink,mimeType",
                supportsAllDrives=True,
            )
            .execute()
        )
        action = "created"
    return {
        "id": uploaded.get("id", ""),
        "name": uploaded.get("name", path.name),
        "url": uploaded.get("webViewLink", drive_file_url(uploaded.get("id", ""))),
        "mime_type": uploaded.get("mimeType", ""),
        "action": action,
    }


def media_file_upload(filename: str, *, resumable: bool = False):
    """Create a Google API media upload object with lazy optional imports."""
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "Google Drive uploads require google-api-python-client."
        ) from exc
    return MediaFileUpload(filename, resumable=resumable)


def should_upload_to_drive(path: Path) -> bool:
    """Return whether a packet file should be uploaded to Drive."""
    if path.name == "manifest.json":
        return True
    return path.suffix.lower() in {".docx", ".pdf"}


def drive_folder_url(folder_id: str) -> str:
    """Build a human-friendly Drive folder URL."""
    return f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else ""


def drive_file_url(file_id: str) -> str:
    """Build a human-friendly Drive file URL."""
    return f"https://drive.google.com/file/d/{file_id}/view" if file_id else ""


def escape_drive_query_value(value: str) -> str:
    """Escape single quotes and backslashes in Drive query strings."""
    return value.replace("\\", "\\\\").replace("'", "\\'")
