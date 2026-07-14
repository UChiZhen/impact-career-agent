"""Output sink connectors."""

from career_agent.sinks.email import (
    GmailEmailSender,
    GmailSenderConfig,
    build_digest_subject,
    config_from_env,
    render_job_digest,
)
from career_agent.sinks.google_drive import (
    GoogleDriveConfig,
    GoogleDrivePacketSink,
    GoogleDriveUploadResult,
)
from career_agent.sinks.google_sheets import (
    GoogleSheetsApplicationTracker,
    GoogleSheetsTrackerConfig,
    TrackerPacketState,
    TrackerWriteResult,
)

__all__ = [
    "GmailEmailSender",
    "GmailSenderConfig",
    "GoogleDriveConfig",
    "GoogleDrivePacketSink",
    "GoogleDriveUploadResult",
    "GoogleSheetsApplicationTracker",
    "GoogleSheetsTrackerConfig",
    "TrackerPacketState",
    "TrackerWriteResult",
    "build_digest_subject",
    "config_from_env",
    "render_job_digest",
]
