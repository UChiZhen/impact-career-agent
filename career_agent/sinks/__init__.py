"""Output sink connectors."""

from career_agent.sinks.email import (
    GmailEmailSender,
    GmailSenderConfig,
    build_digest_subject,
    config_from_env,
    render_job_digest,
)

__all__ = [
    "GmailEmailSender",
    "GmailSenderConfig",
    "build_digest_subject",
    "config_from_env",
    "render_job_digest",
]
