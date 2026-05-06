"""
siops_collector.py
Coleta dados do SIOPS — quanto Sorocaba declarou gastar em saúde via LC 141/2012.

SIOPS: Sistema de Informações sobre Orçamentos Públicos em Saúde (DATASUS).
API: https://siops-consulta-publica-api.saude.gov.br
Endpoint: GET /v1/indicador/municipal/{co_municipio}/{ano}/{periodo}
Sem autenticação — API pública.

co_municipio: IBGE code sem o último dígito (ex: "3552205"[:-1] = "355220")
periodo=2: 6º bimestre = dado anual completo (usar sempre para dados anuais)
"""

import json
import time
import requests
import src.config as cfg_module
from datetime import datetime, timedelta
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from rich.console import Console

from src.config import (
    MUNICIPIO_PRINCIPAL,
    BACKFILL_START_YEAR,
)

console = Console()

SIOPS_BASE_URL = "https://siops-consulta-publica-api.saude.gov.br"
SIOPS_PERIODO_ANUAL = 2  # 6º bimestre = dado anual completo
SIOPS_RATE_LIMIT_SLEEP = 0.1  # segundos entre requests (API sem limite documentado)


def _siops_cache_path(ibge_code: str, ano: int):
    """Caminho do cache para um município e ano específicos.

    Usa cfg_module.CACHE_DIR para respeitar patches de teste.
    """
    return cfg_module.CACHE_DIR / f"siops_{ibge_code}_{ano}.json"


def _is_stable_year(ano: int) -> bool:
    """True se o ano encerrou há mais de 90 dias (prazo de homologação passou)."""
    cutoff = datetime.now() - timedelta(days=90)
    return datetime(ano, 12, 31) < cutoff


class SIOPSCollector:
    """
    Coleta dados do SIOPS — execução orçamentária municipal em saúde.

    Retorna list[dict] com percentual_aplicado, data_status, cumpriu_minimo_15pct
    para cada ano solicitado. Graceful degradation quando API indisponível.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "RepaseSUS/1.0 (civic tech; contato@civisbr.org)",
        })
        retry_strategy = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    @staticmethod
    def _ibge_to_siops_code(ibge_code: str) -> str:
        """Remove o último dígito do código IBGE para obter o código SIOPS."""
        return ibge_code[:-1]

    @staticmethod
    def _parse_percentual(value: str) -> float:
        """Converte string brasileira de percentual para float.

        Exemplos:
            "27,58 %" -> 27.58
            "15,00 %" -> 15.0
        """
        return float(value.replace(",", ".").replace("%", "").strip())

    @staticmethod
    def _parse_valor(value: str) -> float:
        """Converte string numérica brasileira para float.

        Exemplos:
            "1.535,00" -> 1535.0   (ponto=milhar, vírgula=decimal)
            "755166232,41" -> 755166232.41
        """
        # Remover pontos de milhar, substituir vírgula por ponto decimal
        cleaned = value.strip().replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def _fetch_indicadores(self, siops_code: str, ano: int, periodo: int = SIOPS_PERIODO_ANUAL) -> list[dict]:
        """Busca indicadores SIOPS para um município/ano/periodo.

        Returns:
            Lista de indicadores se data_status == "filed".

        Raises:
            requests.HTTPError: Para status != 200 e != 404.
            requests.HTTPError (404): Quando dados não homologados — caller deve capturar.
        """
        url = f"{SIOPS_BASE_URL}/v1/indicador/municipal/{siops_code}/{ano}/{periodo}"
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def _build_registro(self, ano: int, indicadores: list[dict]) -> dict:
        """Monta um registro normalizado a partir da lista de indicadores SIOPS."""
        ind32 = next((x for x in indicadores if x["numero_indicador"] == "3.2"), None)
        ind21 = next((x for x in indicadores if x["numero_indicador"] == "2.1"), None)

        # Guard: ind32 ausente OU indicador_calculado nulo => unfiled
        if ind32 is None or not ind32.get("indicador_calculado"):
            return {
                "ano": ano,
                "percentual_aplicado": None,
                "numerador": None,
                "denominador": None,
                "cumpriu_minimo_15pct": None,
                "per_capita": None,
                "data_status": "unfiled",
            }

        try:
            percentual = self._parse_percentual(ind32["indicador_calculado"])
        except (ValueError, AttributeError):
            return {
                "ano": ano,
                "percentual_aplicado": None,
                "numerador": None,
                "denominador": None,
                "cumpriu_minimo_15pct": None,
                "per_capita": None,
                "data_status": "unfiled",
            }
        numerador = ind32.get("numerador")
        denominador = ind32.get("denominador")

        per_capita = None
        if ind21 is not None and ind21.get("indicador_calculado"):
            try:
                per_capita = self._parse_valor(ind21["indicador_calculado"])
            except (ValueError, AttributeError):
                per_capita = None

        return {
            "ano": ano,
            "percentual_aplicado": percentual,
            "numerador": numerador,
            "denominador": denominador,
            "cumpriu_minimo_15pct": percentual >= 15.0,
            "per_capita": per_capita,
            "data_status": "filed",
        }

    def _fetch_ano(self, ibge_code: str, ano: int) -> dict:
        """Busca dados de um ano — com cache guard e tratamento de HTTP 404."""
        siops_code = self._ibge_to_siops_code(ibge_code)

        # Cache guard: anos estáveis não refazem HTTP
        cache_path = _siops_cache_path(ibge_code, ano)
        if cache_path.exists() and _is_stable_year(ano):
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            return self._build_registro(ano, raw)

        try:
            indicadores = self._fetch_indicadores(siops_code, ano)
            # Persistir em cache se o ano for estável
            if _is_stable_year(ano):
                cfg_module.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(indicadores, ensure_ascii=False), encoding="utf-8"
                )
            return self._build_registro(ano, indicadores)

        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return {
                    "ano": ano,
                    "percentual_aplicado": None,
                    "numerador": None,
                    "denominador": None,
                    "cumpriu_minimo_15pct": None,
                    "per_capita": None,
                    "data_status": "unfiled",
                }
            raise  # Re-raise para degradação tratar 5xx

    def _load_fallback(self) -> list[dict]:
        """Retorna historico do siops.json commitado como fallback.

        Usa cfg_module.OUTPUT_DIR para respeitar patches de teste.
        """
        fallback_path = cfg_module.OUTPUT_DIR / "siops.json"
        if fallback_path.exists():
            data = json.loads(fallback_path.read_text(encoding="utf-8"))
            return data.get("historico", [])
        return []

    def coletar_execucao_orcamentaria(self, anos: list[int] | None = None) -> list[dict]:
        """Coleta execução orçamentária em saúde para Sorocaba por ano.

        Args:
            anos: Lista de anos a coletar. None = BACKFILL_START_YEAR até ano atual.

        Returns:
            list[dict] com um registro por ano. Campos: ano, percentual_aplicado,
            numerador, denominador, cumpriu_minimo_15pct, per_capita, data_status.

        Graceful degradation: ConnectionError ou Timeout retorna último siops.json
        commitado e loga aviso. Pipeline continua com exit code 0.
        """
        if anos is None:
            ano_atual = datetime.now().year
            anos = list(range(BACKFILL_START_YEAR, ano_atual + 1))

        ibge_code = MUNICIPIO_PRINCIPAL["ibge"]

        try:
            resultado: list[dict] = []
            for i, ano in enumerate(anos):
                registro = self._fetch_ano(ibge_code, ano)
                resultado.append(registro)
                # Rate limiting entre requests (exceto após o último)
                if i < len(anos) - 1:
                    time.sleep(SIOPS_RATE_LIMIT_SLEEP)
            return resultado

        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            console.print(
                f"[yellow]Aviso:[/yellow] SIOPS indisponível ({type(e).__name__}: {e}). "
                f"{'Usando dados parciais.' if resultado else 'Usando dados anteriores.'}"
            )
            return resultado if resultado else self._load_fallback()
