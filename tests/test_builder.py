"""
test_builder.py
Testes para DashboardBuilder — BUILD-01, BUILD-02, BUILD-03, BUILD-04.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fns_sample_multiplos_meses.json"

from src.processors.builder import DashboardBuilder


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_repasses():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def sample_siops_filed():
    return [
        {
            "ano": 2023,
            "percentual_aplicado": 27.58,
            "cumpriu_minimo_15pct": True,
            "per_capita": 1535.0,
            "data_status": "filed",
            "numerador": 755166232.41,
            "denominador": 2737420508.21,
        }
    ]


@pytest.fixture
def sample_siops_unfiled():
    return [
        {
            "ano": 2024,
            "percentual_aplicado": None,
            "cumpriu_minimo_15pct": None,
            "per_capita": None,
            "data_status": "unfiled",
            "numerador": None,
            "denominador": None,
        }
    ]


@pytest.fixture
def sample_populacao():
    return [
        {"ibge": "3552205", "nome": "Sorocaba", "populacao": 723682,
         "fonte_pop": "Censo 2022", "ano_pop": 2022},
        {"ibge": "3509502", "nome": "Campinas", "populacao": 1139047,
         "fonte_pop": "Censo 2022", "ano_pop": 2022},
    ]


# ── BUILD-01: build_repasses_json ─────────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="BUILD-01: build_repasses_json not implemented")
def test_build_repasses_json(sample_repasses):
    """build_repasses_json deve retornar dict com chaves por_mes, por_programa, totais_por_ano."""
    builder = DashboardBuilder.__new__(DashboardBuilder)
    result = builder.build_repasses_json(sample_repasses)
    assert "por_mes" in result
    assert "por_programa" in result
    assert "totais_por_ano" in result


@pytest.mark.xfail(strict=False, reason="BUILD-01: por_mes aggregation not implemented")
def test_por_mes_aggregation(sample_repasses):
    """por_mes deve agregar valores por mês com data no formato YYYY-MM."""
    builder = DashboardBuilder.__new__(DashboardBuilder)
    result = builder.build_repasses_json(sample_repasses)
    assert len(result["por_mes"]) >= 2
    # Primeiro mês deve ser 2022-01
    assert result["por_mes"][0]["data"] == "2022-01"
    assert result["por_mes"][0]["valor_total"] == pytest.approx(1000000.0)


@pytest.mark.xfail(strict=False, reason="BUILD-01: por_programa YoY not implemented")
def test_por_programa_yoy(sample_repasses):
    """por_programa deve ter campos valor_ano_atual e valor_ano_anterior (não valor_2023/valor_2022)."""
    builder = DashboardBuilder.__new__(DashboardBuilder)
    result = builder.build_repasses_json(sample_repasses)
    pab = next(p for p in result["por_programa"] if p["programa"] == "PAB")
    assert "valor_ano_atual" in pab, "campo deve ser valor_ano_atual, nao valor_2023"
    assert "valor_ano_anterior" in pab, "campo deve ser valor_ano_anterior, nao valor_2022"
    assert pab["variacao_pct"] is not None


# ── BUILD-02: build_siops_json ────────────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="BUILD-02: siops unfiled preservation not verified")
def test_siops_unfiled_preserved(sample_siops_unfiled, sample_siops_filed):
    """Registro unfiled em historico deve ter percentual_aplicado is None, nunca 0.0."""
    builder = DashboardBuilder.__new__(DashboardBuilder)
    siops_mix = sample_siops_unfiled + sample_siops_filed
    result = builder.build_siops_json(siops_mix)
    unfiled = next(h for h in result["historico"] if h["data_status"] == "unfiled")
    assert unfiled["percentual_aplicado"] is None  # NUNCA converter para 0.0


@pytest.mark.xfail(strict=False, reason="BUILD-02: status_atual field not implemented")
def test_siops_status_atual(sample_siops_filed):
    """build_siops_json deve retornar status_atual com percentual e status string."""
    builder = DashboardBuilder.__new__(DashboardBuilder)
    result = builder.build_siops_json(sample_siops_filed)
    assert "status_atual" in result
    assert result["status_atual"]["percentual"] == pytest.approx(27.58)
    assert result["status_atual"]["status"] == "ACIMA_DO_MINIMO"
    assert result["status_atual"]["ano"] == 2023


# ── BUILD-03: build_municipios_json ───────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="BUILD-03: build_municipios_json not implemented")
def test_municipios_per_capita(sample_populacao, sample_repasses, sample_siops_filed):
    """ranking_repasse_per_capita deve ter fonte_pop e ano_pop em cada item."""
    builder = DashboardBuilder.__new__(DashboardBuilder)
    siops_comparaveis = {"3552205": sample_siops_filed[0]}
    result = builder.build_municipios_json(sample_populacao, sample_repasses, siops_comparaveis)
    assert "ranking_repasse_per_capita" in result
    assert len(result["ranking_repasse_per_capita"]) >= 1
    sorocaba_item = result["ranking_repasse_per_capita"][0]
    assert "fonte_pop" in sorocaba_item, "fonte_pop obrigatorio por BUILD-03"
    assert "ano_pop" in sorocaba_item, "ano_pop obrigatorio por BUILD-03"


@pytest.mark.xfail(strict=False, reason="BUILD-03: build_municipios_json not implemented")
def test_municipios_pct_saude(sample_populacao, sample_repasses, sample_siops_filed):
    """ranking_percentual_saude deve ser lista nao-vazia com municipio e percentual."""
    builder = DashboardBuilder.__new__(DashboardBuilder)
    siops_comparaveis = {"3552205": sample_siops_filed[0]}
    result = builder.build_municipios_json(sample_populacao, sample_repasses, siops_comparaveis)
    assert "ranking_percentual_saude" in result
    assert len(result["ranking_percentual_saude"]) >= 1
    item = result["ranking_percentual_saude"][0]
    assert "municipio" in item
    assert "percentual" in item


# ── BUILD-04: build_metadata_json ─────────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="BUILD-04: total_registros_coletados not implemented")
def test_metadata_total_registros(sample_repasses):
    """build_metadata_json deve retornar total_registros_coletados igual ao len da fixture."""
    builder = DashboardBuilder.__new__(DashboardBuilder)
    result = builder.build_metadata_json(total_registros=len(sample_repasses))
    assert result["total_registros_coletados"] == len(sample_repasses)


@pytest.mark.xfail(strict=False, reason="BUILD-04: metodologia sem funcao=10")
def test_metadata_metodologia(sample_repasses):
    """build_metadata_json deve mencionar funcao=10 na string metodologia."""
    builder = DashboardBuilder.__new__(DashboardBuilder)
    result = builder.build_metadata_json(total_registros=len(sample_repasses))
    assert "funcao=10" in result["metodologia"]


# ── Integration: build_all ────────────────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="BUILD-01..04: build_all integration not fully implemented")
def test_build_all_integration(tmp_path, sample_repasses, sample_siops_filed, sample_populacao):
    """build_all deve salvar os 4 JSONs em OUTPUT_DIR."""
    import src.config as cfg_module
    siops_comparaveis = {"3552205": sample_siops_filed[0]}
    with patch.object(cfg_module, "OUTPUT_DIR", tmp_path):
        builder = DashboardBuilder()
        builder.build_all(
            df_repasses=sample_repasses,
            df_siops=sample_siops_filed,
            populacao=sample_populacao,
            siops_comparaveis=siops_comparaveis,
        )
    assert (tmp_path / "repasses.json").exists()
    assert (tmp_path / "siops.json").exists()
    assert (tmp_path / "municipios.json").exists()
    assert (tmp_path / "metadata.json").exists()
