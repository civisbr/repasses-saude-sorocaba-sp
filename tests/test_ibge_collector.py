"""
test_ibge_collector.py
Testes para IBGECollector — COLL-04.
Todos marcados xfail: Wave 2 (03-02-PLAN.md) implementa a classe.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import responses as rsps_lib

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ibge_censo2022_sample.json"
IBGE_BASE_URL = "https://servicodados.ibge.gov.br"


@pytest.fixture
def sample_ibge_response():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# --- COLL-04: Fetch de população Censo 2022 ----------------------------------

@rsps_lib.activate
def test_fetch_census_population(sample_ibge_response, tmp_path):
    """coletar_populacao_censo2022 deve retornar lista com 6 municípios e populações corretas."""
    rsps_lib.add(
        rsps_lib.GET,
        f"{IBGE_BASE_URL}/api/v3/agregados/9514/periodos/2022/variaveis/93",
        json=sample_ibge_response,
        status=200,
        match_querystring=False,
    )

    import src.config as cfg_module
    with patch.object(cfg_module, "CACHE_DIR", tmp_path):
        from src.collectors.ibge_collector import IBGECollector
        collector = IBGECollector()
        result = collector.coletar_populacao_censo2022()

    assert isinstance(result, list)
    assert len(result) == 6
    sorocaba = next(r for r in result if r["ibge"] == "3552205")
    assert sorocaba["populacao"] == 723682


@rsps_lib.activate
def test_output_schema(sample_ibge_response, tmp_path):
    """Cada registro deve ter ibge, nome, populacao, fonte_pop='Censo 2022', ano_pop=2022."""
    rsps_lib.add(
        rsps_lib.GET,
        f"{IBGE_BASE_URL}/api/v3/agregados/9514/periodos/2022/variaveis/93",
        json=sample_ibge_response,
        status=200,
        match_querystring=False,
    )

    import src.config as cfg_module
    with patch.object(cfg_module, "CACHE_DIR", tmp_path):
        from src.collectors.ibge_collector import IBGECollector
        collector = IBGECollector()
        result = collector.coletar_populacao_censo2022()

    for rec in result:
        assert "ibge" in rec, f"Campo ibge ausente: {rec}"
        assert "nome" in rec, f"Campo nome ausente: {rec}"
        assert "populacao" in rec, f"Campo populacao ausente: {rec}"
        assert rec["fonte_pop"] == "Censo 2022", f"fonte_pop incorreto: {rec}"
        assert rec["ano_pop"] == 2022, f"ano_pop incorreto: {rec}"
        assert isinstance(rec["populacao"], int), f"populacao deve ser int: {rec}"


@rsps_lib.activate
def test_all_six_municipalities_present(sample_ibge_response, tmp_path):
    """Todos os 6 municípios corretos devem estar presentes, incluindo Piracicaba (3538709) e Osasco (3534401)."""
    rsps_lib.add(
        rsps_lib.GET,
        f"{IBGE_BASE_URL}/api/v3/agregados/9514/periodos/2022/variaveis/93",
        json=sample_ibge_response,
        status=200,
        match_querystring=False,
    )

    import src.config as cfg_module
    with patch.object(cfg_module, "CACHE_DIR", tmp_path):
        from src.collectors.ibge_collector import IBGECollector
        collector = IBGECollector()
        result = collector.coletar_populacao_censo2022()

    ibge_codes = {r["ibge"] for r in result}
    expected_codes = {"3552205", "3509502", "3549904", "3538709", "3534401", "3543402"}
    assert ibge_codes == expected_codes, f"Municípios inesperados: {ibge_codes.symmetric_difference(expected_codes)}"

    # Verificar populações específicas (valores do Censo 2022 verificados ao vivo)
    pop_map = {r["ibge"]: r["populacao"] for r in result}
    assert pop_map["3552205"] >= 650000 and pop_map["3552205"] <= 750000, "Sorocaba fora do range esperado"
    assert pop_map["3538709"] == 423323, "Piracicaba com código ou população errada"
    assert pop_map["3534401"] == 728615, "Osasco com código ou população errada"
