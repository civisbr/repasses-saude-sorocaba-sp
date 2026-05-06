"""
fns_collector.py
Coleta repasses federais mandatórios de saúde (funcao=10) para Sorocaba via
API Portal da Transparência Federal.

Endpoint: GET /api-de-dados/transferencias-mandatarias
"""

import json
import os
import time
import requests
from pathlib import Path
from datetime import datetime
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from src.config import (
    MUNICIPIO_PRINCIPAL,
    PORTAL_TRANSPARENCIA_BASE_URL,
    FUNCAO_SAUDE,
    PAGE_SIZE,
    RATE_LIMIT_SLEEP,
    BACKFILL_START_YEAR,
)
from src.cache import _read_cache, _write_cache, _is_stable_month


class FNSCollector:
    """
    Coleta repasses federais em saúde para Sorocaba via Portal da Transparência.

    Fluxo principal:
      coletar_historico → coletar_mes → _fetch_paginated (+ cache guard)
      coletar_mes retorna dados RAW; normalizar_campos converte para schema padrão.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "RepaseSUS/1.0 (civic tech; contato@civisbr.org)",
            "chave-api-dados": os.getenv("PORTAL_TRANSPARENCIA_API_KEY", ""),
        })
        retry_strategy = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def _fetch_paginated(self, ano: int, mes: int) -> list[dict]:
        """Busca todos os registros de um mês com loop de paginação completa.

        Incrementa pagina até resposta vazia ou parcial (< PAGE_SIZE).
        Aplica sleep(RATE_LIMIT_SLEEP) após cada página exceto a última.
        """
        ano_mes = ano * 100 + mes
        todos: list[dict] = []
        pagina = 1
        while True:
            params = {
                "codigoIbge": MUNICIPIO_PRINCIPAL["ibge"],
                "anoMes": ano_mes,
                "codigoFuncao": str(FUNCAO_SAUDE),
                "pagina": pagina,
            }
            response = self.session.get(
                f"{PORTAL_TRANSPARENCIA_BASE_URL}/api-de-dados/transferencias-mandatarias",
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            page_data = response.json()
            if not page_data:
                break
            todos.extend(page_data)
            if len(page_data) < PAGE_SIZE:
                break
            pagina += 1
            time.sleep(RATE_LIMIT_SLEEP)
        return todos

    def coletar_mes(self, ano: int, mes: int) -> list[dict]:
        """Retorna dados RAW da API para um mês (com cache guard).

        A normalização é responsabilidade de coletar_historico (Plano 02-03).
        """
        cached = _read_cache(ano, mes)
        if cached is not None:
            return cached
        raw = self._fetch_paginated(ano, mes)
        _write_cache(ano, mes, raw)
        return raw

    def normalizar_campos(self, item: dict) -> dict:
        """Normaliza registro raw da API Portal da Transparência para schema padrão.

        Campos de entrada (camelCase da API):
            anoMes, codigoFuncao, nomeFuncao, codigoSubfuncao, nomeSubfuncao,
            codigoPrograma, nomePrograma, codigoAcao, nomeAcao,
            codigoIbge, nomeIbge, valorTransferido

        Campos de saída (schema padrão do projeto):
            ano, mes, funcao, funcao_nome, subfuncao, programa, acao,
            municipio_ibge, municipio_nome, valor, fonte

        Raises:
            KeyError: se campo obrigatório (anoMes, codigoFuncao, valorTransferido) estiver ausente
            ValueError: se valorTransferido não puder ser convertido para float
        """
        ano_mes = int(item["anoMes"])
        return {
            "ano": ano_mes // 100,
            "mes": ano_mes % 100,
            "funcao": str(item["codigoFuncao"]),
            "funcao_nome": item.get("nomeFuncao", ""),
            "subfuncao": item.get("nomeSubfuncao", ""),
            "programa": item.get("nomePrograma", ""),
            "acao": item.get("nomeAcao", ""),
            "municipio_ibge": str(item.get("codigoIbge", "")),
            "municipio_nome": item.get("nomeIbge", ""),
            "valor": float(item["valorTransferido"]),
            "fonte": "portal_transparencia",
        }

    def coletar_via_portal_transparencia(self, ano: int, mes: int) -> list[dict]:
        """Busca paginada + normalização para um mês específico.

        Não usa cache — use coletar_mes para a versão com cache guard.

        Args:
            ano: Ano do período (ex: 2023)
            mes: Mês do período (1-12)

        Returns:
            list[dict] com registros normalizados no schema padrão do projeto
        """
        raw = self._fetch_paginated(ano=ano, mes=mes)
        return [self.normalizar_campos(r) for r in raw]

    def coletar_historico(self, meses: list[tuple[int, int]] | None = None) -> list[dict]:
        """Coleta repasses para lista de meses fornecida ou backfill completo.

        Args:
            meses: Lista de (ano, mes) a coletar. None = backfill completo desde
                   BACKFILL_START_YEAR (2019) ate o mes atual inclusive.

        Returns:
            list[dict] com todos os registros normalizados de todos os meses.
            Meses com cache hit nao fazem HTTP; meses sem repasses contribuem [].
        """
        if meses is None:
            now = datetime.now()
            meses_lista: list[tuple[int, int]] = []
            ano_iter = BACKFILL_START_YEAR
            mes_iter = 1
            while (ano_iter, mes_iter) <= (now.year, now.month):
                meses_lista.append((ano_iter, mes_iter))
                if mes_iter == 12:
                    ano_iter += 1
                    mes_iter = 1
                else:
                    mes_iter += 1
            meses = meses_lista

        todos: list[dict] = []
        for ano, mes in meses:
            raw = self.coletar_mes(ano=ano, mes=mes)
            normalizado = [self.normalizar_campos(r) for r in raw]
            todos.extend(normalizado)

        return todos

    def coletar_historico_comparaveis(
        self,
        ibge_code: str,
        ano_ref: int,
    ) -> list[dict]:
        """Busca repasses do Portal da Transparência para um município comparável.

        Args:
            ibge_code: Código IBGE de 7 dígitos do município comparável.
            ano_ref: Ano de referência para o comparativo (último ano com dados SIOPS).

        Returns:
            list[dict] com repasses normalizados do ano_ref para o município.
            Retorna [] em caso de erro (degradação graciosa — não bloqueia o pipeline).

        Cache: .cache/repasses_comparavel_{ibge_code}_{ano_ref}.json
        Imutável para anos passados (ano < ano_atual).
        """
        import src.config as _cfg

        cache_path = _cfg.CACHE_DIR / f"repasses_comparavel_{ibge_code}_{ano_ref}.json"
        ano_atual = datetime.now().year
        is_stable = ano_ref < ano_atual

        if cache_path.exists() and is_stable:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            return [self.normalizar_campos(r) for r in raw]

        todos: list[dict] = []
        for mes in range(1, 13):
            params = {
                "codigoIbge": ibge_code,
                "anoMes": ano_ref * 100 + mes,
                "codigoFuncao": str(FUNCAO_SAUDE),
                "pagina": 1,
            }
            try:
                response = self.session.get(
                    f"{PORTAL_TRANSPARENCIA_BASE_URL}/api-de-dados/transferencias-mandatarias",
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                page_data = response.json()
                todos.extend(page_data)
            except Exception:
                pass  # degradação graciosa — mes sem dados não bloqueia
            time.sleep(RATE_LIMIT_SLEEP)

        if is_stable and todos:
            _cfg.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(todos, ensure_ascii=False), encoding="utf-8")

        return [self.normalizar_campos(r) for r in todos]


class SIOPSCollector:
    """
    Coleta dados do SIOPS — quanto Sorocaba declarou gastar em saúde.

    O SIOPS (Sistema de Informações sobre Orçamentos Públicos em Saúde)
    registra a execução orçamentária municipal em saúde.

    Acesso: https://siops.datasus.gov.br/
    """

    def coletar_execucao_orcamentaria(self, anos: list[int] = None):
        raise NotImplementedError("TODO: Implementar coleta do SIOPS (Fase 3)")
