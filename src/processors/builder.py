"""
builder.py
Gera os arquivos JSON estáticos em public/data/ que o dashboard consome.

Rodado pelo GitHub Actions diariamente.
Pode ser rodado manualmente com: python src/build.py
"""

import json
import time
from collections import defaultdict
from datetime import datetime
from rich.console import Console
import src.config as _cfg
from src.config import MUNICIPIO_PRINCIPAL, MUNICIPIOS_COMPARAVEIS, TODOS_MUNICIPIOS


class DashboardBuilder:
    """
    Agrega e transforma os dados coletados nos JSONs estáticos do dashboard.

    Cada JSON tem um propósito específico para o dashboard:
    - repasses.json: série histórica de repasses
    - siops.json: execução orçamentária (% em saúde)
    - municipios.json: comparativo com municípios similares
    - metadata.json: quando foi atualizado, fontes, etc.
    """

    def __init__(self):
        _cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def build_repasses_json(self, df_repasses: list[dict]) -> dict:
        """
        Gera repasses.json — série temporal de repasses para o dashboard.

        Args:
            df_repasses: list[dict] normalizado por FNSCollector.normalizar_campos()
                         Campos usados: ano (int), mes (int), programa (str),
                                        subfuncao (str), valor (float)

        Returns:
            dict com chaves: por_mes, por_programa, totais_por_ano.
            Schema consumido pelo app.js — campos valor_ano_atual e valor_ano_anterior
            (NÃO valor_2023/valor_2022).
        """
        if not df_repasses:
            return {"por_mes": [], "por_programa": [], "totais_por_ano": []}

        # 1. Totais por mês
        valor_por_mes: dict[str, float] = defaultdict(float)
        programas_por_mes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for r in df_repasses:
            chave = f"{r['ano']}-{r['mes']:02d}"
            valor_por_mes[chave] += r["valor"]
            programas_por_mes[chave][r["programa"]] += r["valor"]

        por_mes = [
            {
                "data": k,
                "valor_total": round(v, 2),
                "programas": dict(programas_por_mes[k]),
            }
            for k, v in sorted(valor_por_mes.items())
        ]

        # 2. Totais por ano
        valor_por_ano: dict[int, float] = defaultdict(float)
        for r in df_repasses:
            valor_por_ano[r["ano"]] += r["valor"]

        totais_por_ano = [
            {"ano": ano, "total": round(total, 2)}
            for ano, total in sorted(valor_por_ano.items())
        ]

        # 3. Por programa com YoY — usar dois anos mais recentes dos dados
        # "ano atual" = último ano no dataset (não datetime.now().year)
        anos_disponiveis = sorted(valor_por_ano.keys(), reverse=True)
        ano_atual_num = anos_disponiveis[0] if anos_disponiveis else None
        ano_anterior_num = anos_disponiveis[1] if len(anos_disponiveis) > 1 else None

        valor_por_programa_por_ano: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        subfuncao_por_programa: dict[str, str] = {}
        for r in df_repasses:
            valor_por_programa_por_ano[r["programa"]][r["ano"]] += r["valor"]
            subfuncao_por_programa[r["programa"]] = r.get("subfuncao", "")

        por_programa = []
        for prog, valores_anos in sorted(valor_por_programa_por_ano.items()):
            val_atual = valores_anos.get(ano_atual_num, 0.0) if ano_atual_num else 0.0
            val_anterior = valores_anos.get(ano_anterior_num, 0.0) if ano_anterior_num else None
            variacao = None
            if val_anterior:
                variacao = round(((val_atual - val_anterior) / val_anterior) * 100, 2)
            por_programa.append({
                "programa": prog,
                "subfuncao": subfuncao_por_programa.get(prog, ""),
                "valor_ano_atual": round(val_atual, 2),
                "valor_ano_anterior": round(val_anterior, 2) if val_anterior else None,
                "variacao_pct": variacao,
            })

        # Ordenar por valor_ano_atual descrescente
        por_programa.sort(key=lambda x: x["valor_ano_atual"], reverse=True)

        return {"por_mes": por_mes, "por_programa": por_programa, "totais_por_ano": totais_por_ano}

    def build_siops_json(self, df_siops: list[dict]) -> dict:
        """
        Gera siops.json — execução orçamentária municipal em saúde.

        Args:
            df_siops: list[dict] retornado por SIOPSCollector.coletar_execucao_orcamentaria()
                      Campos: ano, percentual_aplicado, numerador, denominador,
                              cumpriu_minimo_15pct, per_capita, data_status

        Returns:
            dict com estrutura compatível com public/data/siops.json.
            Inclui campo status_atual lido por app.js.renderizarMetricCards.
        """
        # Ordenar por ano crescente
        historico = sorted(df_siops, key=lambda x: x["ano"])

        # Não transformar os dados do historico — preservar None para unfiled
        # NUNCA fazer: r.get("percentual_aplicado") or 0.0 → distorce gráfico

        # Derivar status_atual do último ano com dados homologados
        filed_anos = [r for r in historico if r.get("data_status") == "filed"]
        status_atual = None
        if filed_anos:
            ultimo = max(filed_anos, key=lambda x: x["ano"])
            status_atual = {
                "ano": ultimo["ano"],
                "percentual": ultimo["percentual_aplicado"],
                "status": "ACIMA_DO_MINIMO" if ultimo["cumpriu_minimo_15pct"] else "ABAIXO_DO_MINIMO",
                "mensagem": (
                    f"Sorocaba aplicou {ultimo['percentual_aplicado']:.2f}% em saúde "
                    f"em {ultimo['ano']}, "
                    f"{'acima' if ultimo['cumpriu_minimo_15pct'] else 'abaixo'} "
                    "do mínimo constitucional de 15%"
                ),
            }

        return {
            "historico": historico,
            "status_atual": status_atual,
            "fonte": "SIOPS/DATASUS",
            "ultima_atualizacao": datetime.now().strftime("%Y-%m-%d"),
        }

    def build_populacao_json(self, populacao: list[dict]) -> dict:
        """
        Gera populacao.json — população Censo 2022 para os 6 municípios.

        Args:
            populacao: list[dict] retornado por IBGECollector.coletar_populacao_censo2022()
                       Campos: ibge, nome, populacao, fonte_pop, ano_pop

        Returns:
            dict com estrutura compatível com public/data/populacao.json
        """
        return {
            "municipios": populacao,
            "ultima_atualizacao": datetime.now().strftime("%Y-%m-%d"),
        }

    def build_municipios_json(
        self,
        populacao: list[dict],
        df_repasses: list[dict],
        siops_comparaveis: dict[str, dict],
        repasses_comparaveis: dict[str, list[dict]] | None = None,
    ) -> dict:
        """
        Gera municipios.json — comparativo com municípios similares.

        Args:
            populacao: list[dict] de IBGECollector.coletar_populacao_censo2022()
                       Campos: ibge, nome, populacao, fonte_pop, ano_pop
            df_repasses: list[dict] de FNSCollector — repasses de Sorocaba (codigoIbge=3552205)
            siops_comparaveis: {ibge_code: registro_siops} para todos os municípios.
                               Registro: {percentual_aplicado, cumpriu_minimo_15pct, ...}
            repasses_comparaveis: {ibge_code: list[dict]} repasses normalizados dos
                                  5 municípios comparáveis via coletar_historico_comparaveis.
                                  None ou {} = apenas Sorocaba no ranking per capita.

        Returns:
            dict com ranking_repasse_per_capita (Sorocaba + comparáveis quando disponíveis)
            e ranking_percentual_saude (municípios com dados SIOPS).
        """
        pop_map = {m["ibge"]: m for m in populacao}

        # ── Repasse per capita — Sorocaba + comparáveis (se repasses_comparaveis fornecido) ──
        ranking_per_capita = []
        municipios_para_ranking = list(TODOS_MUNICIPIOS.items())

        for idx, (ibge_code, nome) in enumerate(municipios_para_ranking):
            if ibge_code == MUNICIPIO_PRINCIPAL["ibge"]:
                repasses_mun = df_repasses
            else:
                repasses_mun = (repasses_comparaveis or {}).get(ibge_code, [])

            total_mun = sum(r["valor"] for r in repasses_mun)
            pop_data = pop_map.get(ibge_code, {})
            pop_mun = pop_data.get("populacao", 0)
            per_capita_mun = round(total_mun / pop_mun, 2) if pop_mun and total_mun else None

            if per_capita_mun is not None:
                ranking_per_capita.append({
                    "municipio": nome,
                    "ibge": ibge_code,
                    "per_capita": per_capita_mun,
                    "fonte_pop": pop_data.get("fonte_pop", "Censo 2022"),
                    "ano_pop": pop_data.get("ano_pop", 2022),
                })

        ranking_per_capita.sort(key=lambda x: x["per_capita"], reverse=True)
        for i, item in enumerate(ranking_per_capita):
            item["posicao"] = i + 1

        # ── % Saúde — todos os municípios via siops_comparaveis ─────────────────
        ranking_pct_saude = []
        for ibge_code, nome in TODOS_MUNICIPIOS.items():
            siops_data = siops_comparaveis.get(ibge_code, {})
            percentual = siops_data.get("percentual_aplicado")
            cumpriu = siops_data.get("cumpriu_minimo_15pct")
            if percentual is not None:
                ranking_pct_saude.append({
                    "municipio": nome,
                    "ibge": ibge_code,
                    "percentual": percentual,
                    "cumpriu": cumpriu,
                })

        ranking_pct_saude.sort(key=lambda x: x["percentual"], reverse=True)

        return {
            "ranking_repasse_per_capita": ranking_per_capita,
            "ranking_percentual_saude": ranking_pct_saude,
        }

    def build_metadata_json(self, total_registros: int = 0) -> dict:
        """Gera metadata.json com informações sobre a atualização mais recente."""
        metadata = {
            "ultima_atualizacao": datetime.now().isoformat(),
            "municipio": MUNICIPIO_PRINCIPAL["nome"],
            "ibge_code": MUNICIPIO_PRINCIPAL["ibge"],
            "fontes": [
                {
                    "nome": "Portal da Transparência Federal",
                    "url": "https://portaldatransparencia.gov.br",
                    "dados": "Repasses federais para saúde"
                },
                {
                    "nome": "SIOPS/DATASUS",
                    "url": "https://siops.datasus.gov.br",
                    "dados": "Execução orçamentária municipal em saúde"
                },
                {
                    "nome": "IBGE",
                    "url": "https://servicodados.ibge.gov.br",
                    "dados": "Dados populacionais"
                }
            ],
            "metodologia": (
                "Dados coletados automaticamente via API de fontes governamentais oficiais. "
                "Repasses federais limitados a transferências mandatárias (funcao=10 — Saúde). "
                "Repasses per capita calculados com base no Censo Demográfico 2022 (IBGE)."
            ),
            "aviso": "Este painel é um projeto de civic tech sem fins lucrativos. Não representa posição política ou governamental.",
            "codigo_fonte": "https://github.com/civisbr/repasses-saude-sorocaba-sp",
            "total_registros_coletados": total_registros,
        }
        return metadata

    def salvar(self, dados: dict, filename: str):
        """Salva um dict como JSON em public/data/."""
        output_path = _cfg.OUTPUT_DIR / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        print(f"✅ {filename} salvo ({output_path})")

    def build_all(
        self,
        df_repasses: list[dict],
        df_siops: list[dict],
        populacao: list[dict],
        siops_comparaveis: dict[str, dict],
        repasses_comparaveis: dict[str, list[dict]] | None = None,
    ) -> None:
        """Executa todos os builders e salva os JSONs em public/data/."""
        console = Console()
        console.print("Gerando arquivos do dashboard...")

        self.salvar(self.build_siops_json(df_siops), "siops.json")
        self.salvar(self.build_populacao_json(populacao), "populacao.json")
        self.salvar(self.build_repasses_json(df_repasses), "repasses.json")
        self.salvar(
            self.build_municipios_json(populacao, df_repasses, siops_comparaveis, repasses_comparaveis),
            "municipios.json",
        )
        self.salvar(self.build_metadata_json(total_registros=len(df_repasses)), "metadata.json")
