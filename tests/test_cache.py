"""
test_cache.py
Tests for PIPE-02: file-based cache helpers in src/cache.py.
"""
import json
from pathlib import Path
from datetime import datetime
import pytest

import src.cache as cache_module
from src.cache import _cache_path, _read_cache, _write_cache


def test_cache_path_format():
    """_cache_path(2023, 3) should return a Path ending in repasses_2023_03.json."""
    result = _cache_path(2023, 3)
    assert isinstance(result, Path)
    assert result.name == "repasses_2023_03.json"


def test_write_creates_file(tmp_path, monkeypatch):
    """_write_cache should create the JSON file in the cache directory."""
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    data = [{"id": 1}]
    _write_cache(2020, 1, data)
    expected = tmp_path / "repasses_2020_01.json"
    assert expected.exists()
    assert json.loads(expected.read_text(encoding="utf-8")) == data


def test_read_stable_month_returns_data(tmp_path, monkeypatch):
    """_read_cache for a stable (old) month should return the cached data."""
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    # Write fixture directly — 2020-01 is stable (>60 days ago)
    fixture_data = [{"id": 42, "valor": 100.0}]
    cache_file = tmp_path / "repasses_2020_01.json"
    cache_file.write_text(json.dumps(fixture_data, ensure_ascii=False), encoding="utf-8")
    result = _read_cache(2020, 1)
    assert result == fixture_data


def test_current_month_not_cached(tmp_path, monkeypatch):
    """_read_cache for the current month should return None even if file exists."""
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    now = datetime.now()
    year, month = now.year, now.month
    # Create the file as if it existed
    cache_file = tmp_path / f"repasses_{year}_{month:02d}.json"
    cache_file.write_text(json.dumps([{"id": 99}]), encoding="utf-8")
    result = _read_cache(year, month)
    assert result is None
