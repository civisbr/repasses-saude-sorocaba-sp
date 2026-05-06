"""
test_workflow.py
Tests for PIPE-04: GitHub Actions workflow correctness.
"""
from pathlib import Path
import pytest


WORKFLOW_PATH = Path(".github/workflows/update-data.yml")


def test_pip_cache_step_present():
    """Workflow should have a pip caching step using actions/cache."""
    content = WORKFLOW_PATH.read_text()
    assert "actions/cache" in content


def test_concurrency_guard_present():
    """Workflow should have a top-level concurrency key to prevent overlapping runs."""
    content = WORKFLOW_PATH.read_text()
    assert "concurrency:" in content
