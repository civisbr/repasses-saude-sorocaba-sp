"""
build.py
Ponto de entrada do pipeline de dados do RepaseSUS Sorocaba.
Rodado pelo GitHub Actions diariamente e manualmente quando necessário.

Uso:
    python src/build.py                          # Modo incremental (últimos 2 meses)
    python src/build.py --backfill               # Histórico completo desde 2019
    python src/build.py --backfill --since 202301 # Histórico a partir de jan/2023
    python src/build.py --ano 2023               # Re-processar apenas 2023
    python src/build.py --force                  # Ignorar cache e re-buscar tudo
"""

import os
import sys
import click
from pathlib import Path
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()
console = Console()

from src.config import BACKFILL_START_YEAR


def _build_month_list(
    backfill: bool,
    since: str | None,
    ano: int | None,
) -> list[tuple[int, int]]:
    """Gera lista de (ano, mes) com base nas flags CLI.

    Args:
        backfill: True = historico completo desde BACKFILL_START_YEAR
        since: Mes inicial no formato YYYYMM (apenas com backfill=True)
        ano: Ano especifico para reprocessar (tem prioridade sobre backfill)

    Returns:
        Lista de tuplas (ano, mes) ordenada cronologicamente.

    Raises:
        SystemExit(1): Se --since tiver formato invalido.
    """
    now = datetime.now()

    if ano is not None:
        return [(ano, m) for m in range(1, 13) if (ano, m) <= (now.year, now.month)]

    if backfill:
        if since is not None:
            try:
                start = datetime.strptime(since, "%Y%m")
            except ValueError:
                console.print(
                    f"[bold red]Erro:[/bold red] --since '{since}' tem formato invalido. "
                    "Use YYYYMM (ex: 202301).",
                    highlight=False,
                )
                raise SystemExit(1)
        else:
            start = datetime(BACKFILL_START_YEAR, 1, 1)

        resultado: list[tuple[int, int]] = []
        ano_iter = start.year
        mes_iter = start.month
        while (ano_iter, mes_iter) <= (now.year, now.month):
            resultado.append((ano_iter, mes_iter))
            if mes_iter == 12:
                ano_iter += 1
                mes_iter = 1
            else:
                mes_iter += 1
        return resultado

    # Modo incremental: mes atual + anterior
    primeiro_do_mes = now.replace(day=1)
    mes_anterior = primeiro_do_mes - timedelta(days=1)
    return [
        (mes_anterior.year, mes_anterior.month),
        (now.year, now.month),
    ]


@click.command()
@click.option(
    "--backfill",
    is_flag=True,
    default=False,
    help="Busca histórico completo desde 2019. Use apenas na primeira execução.",
)
@click.option(
    "--since",
    default=None,
    metavar="YYYYMM",
    help="Reprocessar a partir de um mês específico (ex: 202301). Requer --backfill.",
)
@click.option(
    "--ano",
    default=None,
    type=int,
    help="Processar apenas um ano específico (ex: 2023).",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Ignorar cache e re-buscar dados já coletados.",
)
def build(backfill: bool, since: str | None, ano: int | None, force: bool) -> None:
    """Atualiza os dados do dashboard RepaseSUS Sorocaba.

    Modo padrão (sem flags): busca apenas os 2 últimos meses.
    Use --backfill na primeira execução para carregar o histórico completo.
    """
    # ─────────────────────────────────────────────
    # VALIDAÇÃO: variável de ambiente obrigatória
    # ─────────────────────────────────────────────
    api_key = os.getenv("PORTAL_TRANSPARENCIA_API_KEY")
    if not api_key:
        console.print(
            Panel(
                "[bold red]Erro:[/bold red] PORTAL_TRANSPARENCIA_API_KEY não definida.\n\n"
                "Registre sua chave gratuita em:\n"
                "[cyan]https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email[/cyan]\n\n"
                "Depois configure:\n"
                "  [dim]export PORTAL_TRANSPARENCIA_API_KEY=sua_chave_aqui[/dim]",
                title="Chave de API ausente",
                border_style="red",
            )
        )
        sys.exit(1)

    # ─────────────────────────────────────────────
    # INÍCIO DO PIPELINE
    # ─────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            "[bold cyan]RepaseSUS Sorocaba[/bold cyan] — Atualizando dados...",
            border_style="cyan",
        )
    )

    if backfill:
        modo = f"[yellow]backfill[/yellow] desde {'2019-01' if not since else since}"
    elif ano:
        modo = f"[yellow]ano específico[/yellow]: {ano}"
    else:
        modo = "[dim]incremental[/dim] (últimos 2 meses)"
    console.print(f"Modo: {modo}\n")

    from src.collectors.fns_collector import FNSCollector
    from src.collectors.siops_collector import SIOPSCollector
    from src.collectors.ibge_collector import IBGECollector
    from src.processors.builder import DashboardBuilder

    # ─────────────────────────────────────────────
    # ETAPA 1: COLETA — Portal da Transparência
    # ─────────────────────────────────────────────
    console.print("[bold]1/4[/bold] Coletando repasses do Portal da Transparência Federal...")
    meses = _build_month_list(backfill=backfill, since=since, ano=ano)
    console.print(
        f"     Periodo: {meses[0][0]}-{meses[0][1]:02d} -> "
        f"{meses[-1][0]}-{meses[-1][1]:02d} ({len(meses)} meses)"
    )

    fns = FNSCollector()
    if force:
        import src.config as cfg_module
        from src.cache import _cache_path
        # Limpar cache FNS
        for a, m in meses:
            p = _cache_path(a, m)
            if p.exists():
                p.unlink()
        # Limpar cache SIOPS
        for p in cfg_module.CACHE_DIR.glob("siops_*.json"):
            p.unlink()
        # Limpar cache IBGE (será re-buscado na próxima chamada)
        ibge_cache = cfg_module.CACHE_DIR / "ibge_censo_2022_populacao.json"
        if ibge_cache.exists():
            ibge_cache.unlink()
    repasses_raw = fns.coletar_historico(meses=meses)
    df_repasses = repasses_raw  # compatibilidade com Phase 4 — DashboardBuilder ainda usa df_repasses
    console.print(f"     [green]✓[/green] {len(df_repasses)} repasses coletados")

    # ─────────────────────────────────────────────
    # ETAPA 2: COLETA — SIOPS
    # ─────────────────────────────────────────────
    console.print("[bold]2/4[/bold] Coletando dados do SIOPS...")
    siops = SIOPSCollector()
    df_siops = siops.coletar_execucao_orcamentaria()
    console.print(f"     [green]✓[/green] SIOPS coletado ({len(df_siops)} anos)")

    # ─────────────────────────────────────────────
    # ETAPA 3: COLETA — Municípios comparáveis
    # ─────────────────────────────────────────────
    console.print("[bold]3/4[/bold] Coletando população (IBGE Censo 2022)...")
    ibge = IBGECollector()
    populacao = ibge.coletar_populacao_censo2022()
    console.print(f"     [green]✓[/green] {len(populacao)} municípios coletados (Censo 2022)")

    # ─────────────────────────────────────────────
    # ETAPA 3b: COLETA — SIOPS dos municípios comparáveis (para municipios.json)
    # ─────────────────────────────────────────────
    console.print("[bold]3b/4[/bold] Coletando SIOPS para municípios comparáveis...")
    import time as _time
    from src.config import TODOS_MUNICIPIOS, RATE_LIMIT_SLEEP

    # Determinar ano de referência: último ano com dados homologados em Sorocaba
    filed = [r for r in df_siops if r.get("data_status") == "filed"]
    ano_ref = max(r["ano"] for r in filed) if filed else datetime.now().year - 1

    siops_comparaveis: dict[str, dict] = {}
    todos_items = list(TODOS_MUNICIPIOS.items())
    for i, (ibge_code, nome) in enumerate(todos_items):
        try:
            registro = siops._fetch_ano(ibge_code, ano_ref)
            siops_comparaveis[ibge_code] = registro
        except Exception as e:
            console.print(
                f"     [yellow]Aviso:[/yellow] SIOPS indisponível para {nome} ({e})"
            )
            siops_comparaveis[ibge_code] = {}
        if i < len(todos_items) - 1:
            _time.sleep(RATE_LIMIT_SLEEP)  # 0.3s entre requests — CLAUDE.md constraint

    console.print(
        f"     [green]✓[/green] SIOPS dos comparáveis coletado "
        f"({sum(1 for v in siops_comparaveis.values() if v)} de {len(todos_items)} municípios)"
    )

    # ─────────────────────────────────────────────
    # ETAPA 3c: COLETA — Repasses FNS dos municípios comparáveis (para ranking per capita)
    # ─────────────────────────────────────────────
    console.print("[bold]3c/4[/bold] Coletando repasses FNS para municípios comparáveis...")
    from src.config import MUNICIPIOS_COMPARAVEIS

    repasses_comparaveis: dict[str, list[dict]] = {}
    comparaveis_items = list(MUNICIPIOS_COMPARAVEIS.items())
    for i, (ibge_code, nome) in enumerate(comparaveis_items):
        console.print(f"     Coletando {nome} ({ano_ref})...")
        repasses_comparaveis[ibge_code] = fns.coletar_historico_comparaveis(ibge_code, ano_ref)
        console.print(
            f"     [green]✓[/green] {nome}: {len(repasses_comparaveis[ibge_code])} repasses"
        )

    console.print(
        f"     [green]✓[/green] Repasses dos comparáveis coletados "
        f"({sum(1 for v in repasses_comparaveis.values() if v)} de {len(comparaveis_items)} municípios)"
    )

    # ─────────────────────────────────────────────
    # ETAPA 4: BUILD — Geração dos JSONs
    # ─────────────────────────────────────────────
    console.print("[bold]4/4[/bold] Gerando arquivos do dashboard...")
    builder = DashboardBuilder()
    builder.build_all(df_repasses, df_siops, populacao, siops_comparaveis, repasses_comparaveis)
    console.print("     [green]✓[/green] JSONs gerados")

    console.print()
    console.print(
        Panel(
            "[bold green]Dashboard atualizado com sucesso![/bold green]\n\n"
            "  Abrir:  [cyan]public/index.html[/cyan]\n"
            "  Servir: [cyan]cd public && python -m http.server 8000[/cyan]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    build()
