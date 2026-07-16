"""Shared Google OAuth credential loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_stored_google_credentials(credentials_type: Any, token_path: Path):
    """Load a token without replacing its stored cross-service scopes."""
    return credentials_type.from_authorized_user_file(str(token_path))
