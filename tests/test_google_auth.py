from pathlib import Path

from career_agent.google_auth import load_stored_google_credentials


def test_load_stored_google_credentials_preserves_token_scopes():
    calls = []
    expected = object()

    class FakeCredentials:
        @classmethod
        def from_authorized_user_file(cls, path, *args, **kwargs):
            calls.append((path, args, kwargs))
            return expected

    result = load_stored_google_credentials(
        FakeCredentials,
        Path("private/google-token.json"),
    )

    assert result is expected
    assert calls == [("private/google-token.json", (), {})]
