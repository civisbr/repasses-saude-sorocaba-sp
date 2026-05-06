"""
ibge_collector.py
Coleta dados populacionais do Censo Demográfico 2022 via IBGE Agregados API v3.

Endpoint: GET https://servicodados.ibge.gov.br/api/v3/agregados/9514/periodos/2022/variaveis/93
          ?localidades=N6[{code1},{code2},...]

Tabela 9514: "População residente, por sexo, idade e forma de declaração da idade"
Variável 93: "População residente"
Nível N6: Município

Sem autenticação — API pública do IBGE.
Dados do Censo 2022 são imutáveis — cache indefinido após primeira busca.
"""

import json
import requests
from pathlib import Path
from datetime import datetime
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from rich.console import Console

import src.config as cfg_module
from src.config import TODOS_MUNICIPIOS

IBGE_BASE_URL = "https://servicodados.ibge.gov.br"

console = Console()


class IBGECollector:
    """
    Coleta população municipal do Censo 2022 para os 6 municípios do projeto.

    Uma única requisição HTTP para todos os 6 municípios.
    Cache imutável: após a primeira busca bem-sucedida, nunca refaz HTTP.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "RepaseSUS/1.0 (civic tech; contato@civisbr.org)",
        })
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def _fetch_populacao_api(self) -> dict[str, int]:
        """Faz a requisição HTTP ao IBGE e retorna {ibge_code: populacao}."""
        codes = ",".join(TODOS_MUNICIPIOS.keys())
        url = (
            f"{IBGE_BASE_URL}/api/v3/agregados/9514"
            f"/periodos/2022/variaveis/93?localidades=N6[{codes}]"
        )
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return self._parse_ibge_response(response.json())

    @staticmethod
    def _parse_ibge_response(data: list[dict]) -> dict[str, int]:
        """Extrai {ibge_code: populacao} da resposta da API IBGE.

        Ignora valores "-" (dados suprimidos por privacidade).
        Todos os 6 municípios-alvo têm populações acima do limiar de supressão.
        """
        result: dict[str, int] = {}
        for variavel in data:
            for resultado in variavel.get("resultados", []):
                for series_item in resultado.get("series", []):
                    loc_id = series_item["localidade"]["id"]
                    pop_str = series_item["serie"].get("2022", "")
                    if pop_str and pop_str != "-":
                        result[loc_id] = int(pop_str)
        return result

    def coletar_populacao_censo2022(self) -> list[dict]:
        """Retorna população do Censo 2022 para os 6 municípios do projeto.

        Usa cache imutável: dados do Censo 2022 nunca mudam.
        Uma única requisição HTTP para todos os municípios.

        Returns:
            list[dict] com um item por município:
            {ibge, nome, populacao, fonte_pop, ano_pop}
        """
        # Compute cache path at runtime so CACHE_DIR patches in tests take effect
        cache_path = cfg_module.CACHE_DIR / "ibge_censo_2022_populacao.json"

        # Cache hit: Censo 2022 é imutável — se existe, usar sempre
        if cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            pop_map = {item["ibge"]: item["populacao"] for item in raw}
            return [
                {
                    "ibge": ibge_code,
                    "nome": TODOS_MUNICIPIOS.get(ibge_code, ibge_code),
                    "populacao": pop_map[ibge_code],
                    "fonte_pop": "Censo 2022",
                    "ano_pop": 2022,
                }
                for ibge_code in TODOS_MUNICIPIOS
                if ibge_code in pop_map
            ]

        try:
            pop_map = self._fetch_populacao_api()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            console.print(
                f"[yellow]Aviso:[/yellow] IBGE indisponível ({e}). "
                "Dados populacionais ausentes — per capita não será calculado."
            )
            return []

        # Persistir cache já no formato final
        cache_data = [
            {
                "ibge": ibge_code,
                "nome": TODOS_MUNICIPIOS.get(ibge_code, ibge_code),
                "populacao": pop,
                "fonte_pop": "Censo 2022",
                "ano_pop": 2022,
            }
            for ibge_code, pop in pop_map.items()
        ]
        cfg_module.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(cache_data, ensure_ascii=False), encoding="utf-8"
        )
        return cache_data
