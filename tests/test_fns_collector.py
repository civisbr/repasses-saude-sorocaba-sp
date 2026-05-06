"""
test_fns_collector.py
Testes para FNSCollector -- COLL-01, COLL-02, COLL-05.
"""
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import responses as rsps_lib

# Fixture de resposta da API
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fns_sample_page1.json"
API_URL = "https://api.portaldatransparencia.gov.br/api-de-dados/transferencias-mandatarias"


@pytest.fixture
def sample_records():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# --- COLL-01: Paginacao e fetch -----------------------------------------------

@rsps_lib.activate
def test_fetch_paginates_correctly(sample_records, monkeypatch):
    """_fetch_paginated deve buscar todas as paginas ate lista vazia."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    # Pagina 1: PAGE_SIZE (500) registros simulados -- usar sample * 167 (501 registros) seria irreal
    # Simular: pagina 1 retorna 3 registros (< 500) -> stop imediato (single-page)
    rsps_lib.add(rsps_lib.GET, API_URL, json=sample_records, status=200, match_querystring=False)
    rsps_lib.add(rsps_lib.GET, API_URL, json=[], status=200, match_querystring=False)

    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()
    result = collector._fetch_paginated(ano=2023, mes=12)
    assert isinstance(result, list)
    assert len(result) == len(sample_records)


@rsps_lib.activate
def test_fetch_multi_page(sample_records, monkeypatch):
    """_fetch_paginated com PAGE_SIZE registros deve buscar pagina 2."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    # Pagina 1: exatamente PAGE_SIZE=500 registros -> deve buscar proxima
    page1 = sample_records * 167  # 501 registros, truncar para 500
    page1 = page1[:500]
    # Pagina 2: 3 registros -> stop
    rsps_lib.add(rsps_lib.GET, API_URL, json=page1, status=200, match_querystring=False)
    rsps_lib.add(rsps_lib.GET, API_URL, json=sample_records, status=200, match_querystring=False)
    rsps_lib.add(rsps_lib.GET, API_URL, json=[], status=200, match_querystring=False)

    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()
    result = collector._fetch_paginated(ano=2023, mes=12)
    assert len(result) == 503  # 500 + 3


@rsps_lib.activate
def test_empty_month_returns_empty_list(monkeypatch):
    """Mes sem repasses deve retornar [] -- nao erro."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    rsps_lib.add(rsps_lib.GET, API_URL, json=[], status=200, match_querystring=False)

    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()
    result = collector._fetch_paginated(ano=2019, mes=1)
    assert result == []


@rsps_lib.activate
def test_api_key_in_request_header(sample_records, monkeypatch):
    """Header chave-api-dados deve estar presente em toda requisicao."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "minha-chave-secreta")
    rsps_lib.add(rsps_lib.GET, API_URL, json=sample_records, status=200, match_querystring=False)
    rsps_lib.add(rsps_lib.GET, API_URL, json=[], status=200, match_querystring=False)

    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()
    collector._fetch_paginated(ano=2023, mes=12)

    # Verificar header na primeira chamada
    assert rsps_lib.calls[0].request.headers.get("chave-api-dados") == "minha-chave-secreta"


@rsps_lib.activate
def test_funcao_saude_filter_applied(sample_records, monkeypatch):
    """codigoFuncao=10 deve estar presente em toda query."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    rsps_lib.add(rsps_lib.GET, API_URL, json=sample_records, status=200, match_querystring=False)
    rsps_lib.add(rsps_lib.GET, API_URL, json=[], status=200, match_querystring=False)

    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()
    collector._fetch_paginated(ano=2023, mes=12)

    # Verificar query string da primeira chamada
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(rsps_lib.calls[0].request.url).query)
    assert qs.get("codigoFuncao") == ["10"]


# --- COLL-01: Normalizacao ----------------------------------------------------

@pytest.mark.xfail(reason="Plan 02-02 implementa normalizar_campos", strict=False)
def test_normalizar_campos_schema(sample_records, monkeypatch):
    """normalizar_campos deve produzir schema padrao com campos obrigatorios."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()
    result = collector.normalizar_campos(sample_records[0])
    assert "ano" in result
    assert "mes" in result
    assert "valor" in result
    assert "programa" in result
    assert "fonte" in result
    assert result["fonte"] == "portal_transparencia"
    assert result["ano"] == 2023
    assert result["mes"] == 12


# --- COLL-02: Cache guard -----------------------------------------------------

@pytest.mark.xfail(reason="Plan 02-02 implementa coletar_mes com cache guard", strict=False)
def test_cache_hit_skips_http(monkeypatch, tmp_path):
    """_read_cache HIT deve impedir qualquer chamada HTTP."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    import src.cache as cache_module
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)

    # Escrever dado em cache para mes estavel (2020-01)
    from src.cache import _write_cache
    _write_cache(2020, 1, [{"valorTransferido": 999.0}])

    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()

    with patch.object(collector, "_fetch_paginated") as mock_fetch:
        result = collector.coletar_mes(ano=2020, mes=1)
        mock_fetch.assert_not_called()
    assert result == [{"valorTransferido": 999.0}]


@pytest.mark.xfail(reason="Plan 02-02 implementa coletar_mes", strict=False)
def test_write_cache_after_fetch(sample_records, monkeypatch, tmp_path):
    """_write_cache deve ser chamado apos fetch bem-sucedido."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    import src.cache as cache_module
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)

    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()

    with patch.object(collector, "_fetch_paginated", return_value=sample_records):
        collector.coletar_mes(ano=2020, mes=1)

    from src.cache import _cache_path
    import src.cache as _cm
    _cm.CACHE_DIR = tmp_path
    cache_file = tmp_path / "repasses_2020_01.json"
    assert cache_file.exists()


# --- COLL-02 / COLL-05: Modo backfill e incremental --------------------------

@pytest.mark.xfail(reason="Plan 02-03 implementa coletar_historico", strict=False)
def test_backfill_month_range(monkeypatch):
    """coletar_historico(meses=all) deve cobrir 2019-01 ate o mes atual."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    from datetime import datetime
    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()

    chamados = []
    with patch.object(collector, "coletar_mes", side_effect=lambda ano, mes: chamados.append((ano, mes)) or []):
        collector.coletar_historico(meses=None)  # None = backfill completo

    assert (2019, 1) in chamados
    now = datetime.now()
    assert (now.year, now.month) in chamados
    assert len(chamados) >= 89  # 2019-01 ate 2026-05 = 89+ meses


@pytest.mark.xfail(reason="Plan 02-03 implementa modo incremental", strict=False)
def test_incremental_mode_fetches_two_months(monkeypatch):
    """Modo incremental (meses fornecidos externamente) deve processar exatamente 2 meses."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    from datetime import datetime
    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()

    # build.py fornece lista de 2 meses no modo incremental
    now = datetime.now()
    if now.month == 1:
        dois_meses = [(now.year - 1, 12), (now.year, 1)]
    else:
        dois_meses = [(now.year, now.month - 1), (now.year, now.month)]

    chamados = []
    with patch.object(collector, "coletar_mes", side_effect=lambda ano, mes: chamados.append((ano, mes)) or []):
        collector.coletar_historico(meses=dois_meses)

    assert len(chamados) == 2


@pytest.mark.xfail(reason="Plan 02-03 implementa coletar_historico com cache guard", strict=False)
def test_stable_months_skipped_in_incremental(monkeypatch):
    """Quando coletar_historico recebe 2 meses com cache HIT em ambos, _fetch_paginated nao e chamado."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    from src.collectors.fns_collector import FNSCollector
    collector = FNSCollector()

    # Ambos os meses tem cache hit
    with patch.object(collector, "_fetch_paginated", return_value=[]) as mock_fetch:
        with patch("src.cache._read_cache", return_value=[{"valorTransferido": 100}]):
            collector.coletar_historico(meses=[(2024, 1), (2024, 2)])

    mock_fetch.assert_not_called()


# --- Retry --------------------------------------------------------------------

@pytest.mark.xfail(reason="Plan 02-01 T2 implementa Retry na session", strict=False)
def test_retry_on_429(monkeypatch):
    """HTTP 429 seguido de 200 deve ser recuperado automaticamente sem levantar excecao."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    from src.collectors.fns_collector import FNSCollector

    @rsps_lib.activate
    def _run():
        rsps_lib.add(
            rsps_lib.GET,
            API_URL,
            status=429,
        )
        rsps_lib.add(
            rsps_lib.GET,
            API_URL,
            json=[],
            status=200,
        )
        collector = FNSCollector()
        # Nao deve levantar excecao -- retry deve absorver o 429
        result = collector._fetch_paginated(2024, 1)
        assert result == []

    _run()


def test_retry_configured_on_session(monkeypatch):
    """Session deve ter HTTPAdapter com Retry montado em https://."""
    monkeypatch.setenv("PORTAL_TRANSPARENCIA_API_KEY", "test-key")
    from src.collectors.fns_collector import FNSCollector
    from requests.adapters import HTTPAdapter
    collector = FNSCollector()
    adapter = collector.session.get_adapter("https://api.portaldatransparencia.gov.br")
    assert isinstance(adapter, HTTPAdapter)
    assert adapter.max_retries is not None
    assert 429 in adapter.max_retries.status_forcelist
