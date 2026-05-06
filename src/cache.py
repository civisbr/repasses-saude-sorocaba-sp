"""
cache.py
File-based date-keyed cache for raw API responses.
Collectors use these helpers — never call the API for stable historical months.
"""
from pathlib import Path
from datetime import datetime, timedelta
import json
from src.config import CACHE_DIR


def _cache_path(ano: int, mes: int) -> Path:
    return CACHE_DIR / f"repasses_{ano}_{mes:02d}.json"


def _is_stable_month(ano: int, mes: int) -> bool:
    """Returns True if the month is far enough in the past to be considered stable.
    Stable = more than 60 days before the first day of the current month.
    Current and previous month are always re-fetched from the API.
    """
    cutoff = datetime.now().replace(day=1) - timedelta(days=60)
    return datetime(ano, mes, 1) < cutoff


def _read_cache(ano: int, mes: int) -> list[dict] | None:
    """Return cached data if file exists and month is stable; else None."""
    path = _cache_path(ano, mes)
    if path.exists() and _is_stable_month(ano, mes):
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _write_cache(ano: int, mes: int, data: list[dict]) -> None:
    """Write raw API response to cache. Creates .cache/ dir if needed."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(ano, mes).write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
