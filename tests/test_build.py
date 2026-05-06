"""
test_build.py
Tests for PIPE-03: build.py CLI entry point behaviors.
"""
import pytest
from click.testing import CliRunner
from src.build import build


def test_help_exits_zero():
    """--help should exit with code 0."""
    runner = CliRunner()
    result = runner.invoke(build, ["--help"])
    assert result.exit_code == 0


@pytest.mark.xfail(reason="Plan 02 adds EnvironmentError guard", strict=False)
def test_missing_api_key_exits_nonzero(monkeypatch):
    """Build without PORTAL_TRANSPARENCIA_API_KEY should exit non-zero."""
    monkeypatch.delenv("PORTAL_TRANSPARENCIA_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(build, [])
    assert result.exit_code != 0


@pytest.mark.xfail(reason="Plan 02 adds --backfill flag", strict=False)
def test_help_shows_backfill_flag():
    """--help output should mention --backfill flag (added in Plan 02)."""
    runner = CliRunner()
    result = runner.invoke(build, ["--help"])
    assert "--backfill" in result.output
