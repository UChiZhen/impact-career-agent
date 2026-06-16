from contextlib import redirect_stdout
from io import StringIO

from career_agent import __version__
from career_agent.cli.main import main


def test_version_command():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["version"])

    assert exit_code == 0
    assert __version__ in output.getvalue()


def test_demo_command():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["demo"])

    text = output.getvalue()
    assert exit_code == 0
    assert "Impact Career Agent demo digest" in text
    assert "not an external LLM" in text
