"""
test_config.py
Tests for PIPE-01: config module constants and migration readiness.
"""
import pytest
from pathlib import Path


def test_all_constants_exported():
    """All 11 constants must be importable from src.config without ImportError."""
    from src.config import (
        MUNICIPIO_PRINCIPAL,
        MUNICIPIOS_COMPARAVEIS,
        TODOS_MUNICIPIOS,
        CACHE_DIR,
        OUTPUT_DIR,
        PORTAL_TRANSPARENCIA_BASE_URL,
        FUNCAO_SAUDE,
        PAGE_SIZE,
        RATE_LIMIT_SLEEP,
        BACKFILL_START_YEAR,
        ROOT_DIR,
    )
    # If we got here, import succeeded
    assert True


def test_municipio_principal_is_sorocaba():
    from src.config import MUNICIPIO_PRINCIPAL
    assert MUNICIPIO_PRINCIPAL["ibge"] == "3552205"
    assert MUNICIPIO_PRINCIPAL["nome"] == "Sorocaba"


def test_five_municipios_comparaveis():
    from src.config import MUNICIPIOS_COMPARAVEIS
    assert len(MUNICIPIOS_COMPARAVEIS) == 5
    expected_codes = {"3509502", "3549904", "3538709", "3534401", "3543402"}
    assert set(MUNICIPIOS_COMPARAVEIS.keys()) == expected_codes


def test_todos_municipios_has_six():
    from src.config import TODOS_MUNICIPIOS
    assert len(TODOS_MUNICIPIOS) == 6


def test_funcao_saude_is_10():
    from src.config import FUNCAO_SAUDE
    assert FUNCAO_SAUDE == 10


def test_cache_dir_uses_pathlib():
    from src.config import CACHE_DIR
    assert isinstance(CACHE_DIR, Path)


@pytest.mark.xfail(reason="Plan 02 will migrate imports", strict=False)
def test_no_hardcoded_ibge_in_fns_collector():
    """fns_collector.py should not have os.getenv for MUNICIPIO_IBGE_CODE after Plan 02."""
    source = Path("src/collectors/fns_collector.py").read_text()
    assert 'os.getenv("MUNICIPIO_IBGE_CODE"' not in source


@pytest.mark.xfail(reason="Plan 02 will migrate imports", strict=False)
def test_no_hardcoded_municipios_in_builder():
    """builder.py should not have a hardcoded MUNICIPIOS_COMPARAVEIS dict after Plan 02."""
    source = Path("src/processors/builder.py").read_text()
    assert "MUNICIPIOS_COMPARAVEIS = {" not in source
