"""
test_siops_collector.py
Testes para SIOPSCollector — COLL-03.
Todos marcados xfail: Wave 1 (03-01-PLAN.md) implementa a classe.
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests
import responses as rsps_lib

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "siops_sample_response.json"
SIOPS_BASE_URL = "https://siops-consulta-publica-api.saude.gov.br"
SOROCABA_SIOPS_CODE = "355220"  # ibge 3552205 com último dígito removido


@pytest.fixture
def sample_indicadores():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# --- COLL-03: Fetch e parse de indicador 3.2 ----------------------------------

@rsps_lib.activate
def test_fetch_indicator_32(sample_indicadores):
    """_fetch_indicadores deve retornar lista com indicador 3.2 para ano/periodo válidos."""
    url = f"{SIOPS_BASE_URL}/v1/indicador/municipal/{SOROCABA_SIOPS_CODE}/2024/2"
    rsps_lib.add(rsps_lib.GET, url, json=sample_indicadores, status=200, match_querystring=False)

    from src.collectors.siops_collector import SIOPSCollector
    collector = SIOPSCollector()
    result = collector._fetch_indicadores(SOROCABA_SIOPS_CODE, ano=2024, periodo=2)

    assert isinstance(result, list)
    assert any(ind["numero_indicador"] == "3.2" for ind in result)


def test_parse_percentual(sample_indicadores):
    """parse_percentual deve converter '27,58 %' para float 27.58."""
    from src.collectors.siops_collector import SIOPSCollector
    collector = SIOPSCollector()
    ind32 = next(x for x in sample_indicadores if x["numero_indicador"] == "3.2")
    result = collector._parse_percentual(ind32["indicador_calculado"])
    assert result == pytest.approx(27.58, rel=1e-3)


# --- COLL-03: data_status unfiled --------------------------------------------

@rsps_lib.activate
def test_unfiled_returns_status():
    """HTTP 404 com body de não homologação deve produzir data_status='unfiled', sem exceção."""
    url = f"{SIOPS_BASE_URL}/v1/indicador/municipal/{SOROCABA_SIOPS_CODE}/2026/2"
    rsps_lib.add(
        rsps_lib.GET,
        url,
        json=[{"error": "msg03", "message": "Dados não homologado(s)."}],
        status=404,
        match_querystring=False,
    )

    from src.collectors.siops_collector import SIOPSCollector
    collector = SIOPSCollector()
    # coletar_execucao_orcamentaria deve retornar registro com data_status="unfiled" para 2026
    result = collector.coletar_execucao_orcamentaria(anos=[2026])
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["data_status"] == "unfiled"
    assert result[0]["percentual_aplicado"] is None


# --- COLL-03: Graceful degradation ------------------------------------------

def test_graceful_degradation(tmp_path):
    """ConnectionError deve retornar fallback do siops.json commitado, sem exceção, exit code 0."""
    # Montar siops.json de fallback em tmp_path/public/data/siops.json
    fallback_data = {
        "historico": [{"ano": 2024, "percentual_aplicado": 27.58, "data_status": "filed"}],
        "fonte": "SIOPS/DATASUS",
        "ultima_atualizacao": "2026-01-01",
    }
    output_dir = tmp_path / "public" / "data"
    output_dir.mkdir(parents=True)
    (output_dir / "siops.json").write_text(
        json.dumps(fallback_data), encoding="utf-8"
    )

    from src.collectors.siops_collector import SIOPSCollector
    import src.config as cfg_module

    with patch.object(cfg_module, "OUTPUT_DIR", output_dir):
        collector = SIOPSCollector()
        with patch.object(collector.session, "get", side_effect=requests.ConnectionError("timeout")):
            result = collector.coletar_execucao_orcamentaria(anos=[2024])

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["percentual_aplicado"] == pytest.approx(27.58)


# --- COLL-03: Cache guard ---------------------------------------------------

def test_cache_guard_skips_http(tmp_path, sample_indicadores):
    """Ano estável com cache HIT não deve fazer chamada HTTP."""
    from src.collectors.siops_collector import SIOPSCollector
    import src.config as cfg_module

    cache_file = tmp_path / f"siops_3552205_2023.json"
    cache_file.write_text(json.dumps(sample_indicadores), encoding="utf-8")

    with patch.object(cfg_module, "CACHE_DIR", tmp_path):
        collector = SIOPSCollector()
        with patch.object(collector.session, "get") as mock_get:
            collector.coletar_execucao_orcamentaria(anos=[2023])
            mock_get.assert_not_called()


# --- COLL-03: Range de anos -------------------------------------------------

@rsps_lib.activate
def test_coletar_historico_range(sample_indicadores, tmp_path):
    """coletar_execucao_orcamentaria sem args deve coletar de 2019 até ano atual."""
    from datetime import datetime
    ano_atual = datetime.now().year

    # Registrar respostas para todos os anos de 2019 até ano atual
    for ano in range(2019, ano_atual + 1):
        url = f"{SIOPS_BASE_URL}/v1/indicador/municipal/{SOROCABA_SIOPS_CODE}/{ano}/2"
        rsps_lib.add(rsps_lib.GET, url, json=sample_indicadores, status=200, match_querystring=False)

    # Patch CACHE_DIR to an empty tmp_path so stable years go through HTTP
    # instead of loading from real .cache/ files
    import src.config as cfg_module
    with patch.object(cfg_module, "CACHE_DIR", tmp_path):
        from src.collectors.siops_collector import SIOPSCollector
        collector = SIOPSCollector()
        result = collector.coletar_execucao_orcamentaria()

    assert isinstance(result, list)
    anos_retornados = [r["ano"] for r in result]
    assert 2022 in anos_retornados
    assert 2024 in anos_retornados
    assert len(result) >= 4  # mínimo 2022-2025
