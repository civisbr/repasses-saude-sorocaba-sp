/**
 * RepaseSUS Sorocaba — app.js
 * Carrega os JSONs estáticos e renderiza o dashboard.
 */

// ─── Configuração ─────────────────────────────────────────────
const DATA_BASE = "./data";

// ─── Estado de módulo (filtros e paginação) ────────────────────
let todosRepasses = [];        // Dataset completo reconstruído de por_mes[]
let repassesFiltrados = [];    // Após aplicarFiltros()
let paginaAtual = 1;
const REGISTROS_POR_PAGINA = 50;
let filtroAno = "todos";
let filtroProg = "todos";
let filtroMes = "todos";
let filtroTexto = "";
let chartSerieTemporal = null;  // Referência para destroy() ao re-renderizar
let chartMunicipios = null;     // Referência para destroy()
let chartMinimo = null;         // Referência para destroy()

// ─── Utilitários ──────────────────────────────────────────────

// Escapa caracteres especiais HTML para evitar XSS em innerHTML (CR-01)
function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Sanitiza célula CSV contra injeção de fórmulas Excel/Calc (CR-03)
function sanitizeCsvCell(s) {
  const str = String(s);
  if (/^[=+\-@\t\r]/.test(str)) return `\t${str}`;
  return str.replace(/"/g, '""');
}

const fmt = {
  moeda: (v) => new Intl.NumberFormat("pt-BR", {
    style: "currency", currency: "BRL", maximumFractionDigits: 0
  }).format(v),

  moedaCompact: (v) => {
    if (v >= 1e9) return `R$ ${(v / 1e9).toFixed(1)}bi`;
    if (v >= 1e6) return `R$ ${(v / 1e6).toFixed(1)}mi`;
    if (v >= 1e3) return `R$ ${(v / 1e3).toFixed(0)}mil`;
    return fmt.moeda(v);
  },

  pct: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`,

  data: (s) => new Date(s).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric"
  }),

  mesAno: (s) => {
    const [ano, mes] = s.split("-");
    const meses = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
    return `${meses[parseInt(mes) - 1]}/${ano.slice(2)}`;
  }
};

// --- Glossario de siglas de programas de saude (UX-01) ---
const GLOSSARIO = {
  PAB:      "Piso de Atencao Basica — transferencia constitucional para atencao primaria a saude",
  CAPS:     "Centro de Atencao Psicossocial — rede de saude mental do SUS",
  SAMU:     "Servico de Atendimento Movel de Urgencia — urgencias e emergencias medicas",
  NASF:     "Nucleo de Apoio a Saude da Familia — equipes multiprofissionais de atencao basica",
  CEO:      "Centro de Especialidades Odontologicas — servicos odontologicos especializados do SUS",
  UPA:      "Unidade de Pronto Atendimento — atendimento de urgencia de medio porte",
  PSF:      "Programa de Saude da Familia — modelo de atencao basica por equipes de saude",
  ESF:      "Estrategia Saude da Familia — atencao primaria com equipes multidisciplinares",
  AMAMENTA: "Rede Amamenta e Alimenta Brasil — incentivo ao aleitamento materno",
  PACS:     "Programa de Agentes Comunitarios de Saude — ACS na atencao basica",
  MAC:      "Media e Alta Complexidade — procedimentos hospitalares e especializados",
  PMAQ:     "Programa Nacional de Melhoria do Acesso e da Qualidade",
  ACADEMIA: "Academia da Saude — equipamentos para promocao de atividade fisica",
  CRACK:    "Programa Crack e Possivel Vencer — tratamento de dependencia quimica",
};

// Envolve siglas curtas em <abbr> com tooltip — aplica apenas se definicao existe no GLOSSARIO e programa.length <= 10
function wrapSigla(programa) {
  const definicao = GLOSSARIO[programa];
  if (!definicao || programa.length > 10) return escHtml(programa);
  return `<abbr class="sigla-tooltip" tabindex="0" data-sigla="${escHtml(programa)}" title="${escHtml(definicao)}">${escHtml(programa)}</abbr>`;
}

// --- Tooltip singleton (UX-01) ---
const tooltipEl = document.createElement("span");
tooltipEl.id = "sigla-tooltip-singleton";
tooltipEl.className = "tooltip";
tooltipEl.setAttribute("role", "tooltip");
tooltipEl.hidden = true;
document.body.appendChild(tooltipEl);

function mostrarTooltip(trigger, texto) {
  tooltipEl.textContent = texto;
  tooltipEl.hidden = false;
  const rect = trigger.getBoundingClientRect();
  const top = rect.bottom + window.scrollY + 4;
  let left = rect.left + window.scrollX;
  const maxLeft = window.innerWidth - 288;
  tooltipEl.style.top = top + "px";
  tooltipEl.style.left = Math.min(left, maxLeft) + "px";
}

function ocultarTooltip() {
  tooltipEl.hidden = true;
}

function registrarTooltipsSiglas() {
  document.querySelectorAll(".sigla-tooltip").forEach(el => {
    if (el.dataset.tooltipRegistered) return;
    el.dataset.tooltipRegistered = "1";
    const sigla = el.dataset.sigla;
    const definicao = GLOSSARIO[sigla] || el.textContent;
    el.setAttribute("aria-describedby", "sigla-tooltip-singleton");
    el.addEventListener("mouseenter", () => mostrarTooltip(el, definicao));
    el.addEventListener("mouseleave", ocultarTooltip);
    el.addEventListener("focus", () => mostrarTooltip(el, definicao));
    el.addEventListener("blur", ocultarTooltip);
    el.addEventListener("keydown", e => { if (e.key === "Escape") ocultarTooltip(); });
  });
}

// --- Card de alerta de atraso (UX-02) ---
function verificarAtrasoRepasse(repasses) {
  const porMes = repasses.por_mes;
  if (!porMes || porMes.length === 0) return;

  const ultimaMes = porMes.reduce((max, m) => m.data > max.data ? m : max, porMes[0]);
  const [ano, mes] = ultimaMes.data.split("-").map(Number);
  const ultimoDiaMes = new Date(ano, mes, 0);
  const hoje = new Date();
  const diasDesde = Math.floor((hoje - ultimoDiaMes) / (1000 * 60 * 60 * 24));

  if (diasDesde > 30) {
    const card = document.getElementById("alerta-atraso");
    const dataEl = document.getElementById("alerta-data-ultimo");
    if (card && dataEl) {
      dataEl.textContent = fmt.mesAno(ultimaMes.data);
      card.classList.remove("alert-card--oculto");
    }
  }
}

// ─── Carregamento de dados ─────────────────────────────────────
async function carregarJSON(arquivo) {
  const resp = await fetch(`${DATA_BASE}/${arquivo}`);
  if (!resp.ok) throw new Error(`Erro ao carregar ${arquivo}: ${resp.status}`);
  return resp.json();
}

// ─── Inicialização ─────────────────────────────────────────────
async function init() {
  try {
    // Aplicar skeleton loading antes de qualquer fetch
    document.querySelectorAll(".metric-value, .metric-value--sm").forEach(el => {
      el.classList.add("skeleton");
      el.textContent = " "; // espaço non-breaking para manter altura
    });

    // Carregar todos os dados em paralelo — incluindo populacao.json
    const [repasses, siops, municipios, metadata, populacaoData] = await Promise.all([
      carregarJSON("repasses.json"),
      carregarJSON("siops.json"),
      carregarJSON("municipios.json"),
      carregarJSON("metadata.json"),
      carregarJSON("populacao.json"),
    ]);

    // Remover skeleton loading
    document.querySelectorAll(".metric-value, .metric-value--sm").forEach(el => {
      el.classList.remove("skeleton");
    });

    // Extrair população de Sorocaba do Censo 2022
    const popSorocaba = populacaoData.municipios
      .find(m => m.ibge === "3552205")?.populacao ?? 695000;

    // Atualizar data de última atualização
    document.getElementById("ultima-atualizacao").textContent =
      fmt.data(metadata.ultima_atualizacao);

    // Ano atual nos cards
    const anoAtual = new Date().getFullYear();
    document.getElementById("ano-atual").textContent = anoAtual;

    // Renderizar cada seção
    renderizarMetricCards(repasses, siops, anoAtual, popSorocaba);
    verificarAtrasoRepasse(repasses);
    renderizarSerieTemporal(repasses);
    renderizarTabelaProgramas(repasses, anoAtual);
    renderizarComparativoMunicipios(municipios);
    renderizarMinimoConstitucional(siops, municipios);
    renderizarTabelaCompleta(repasses);
    configurarDownloadCSV();

  } catch (err) {
    console.error("Erro ao carregar dados:", err);
    // CR-02: usar textContent para err.message para evitar XSS via innerHTML
    const mainEl = document.querySelector("main");
    mainEl.innerHTML = `
      <div style="text-align:center;padding:60px 20px;color:var(--text-secondary)">
        <h2 style="margin-bottom:16px">Erro ao carregar os dados do dashboard</h2>
        <p id="err-msg-placeholder"></p>
        <p style="font-size:12px;margin-top:16px">Não foi possível carregar os dados. Se estiver testando localmente, execute primeiro: <code>python src/build.py</code></p>
      </div>
    `;
    mainEl.querySelector("#err-msg-placeholder").textContent = err.message;
  }
}

// ─── Cards de métricas ─────────────────────────────────────────
function renderizarMetricCards(repasses, siops, anoAtual, popSorocaba) {
  const totaisAno = repasses.totais_por_ano;
  const anoAtualData = totaisAno?.find(t => t.ano === anoAtual);
  const anoAnteriorData = totaisAno?.find(t => t.ano === anoAtual - 1);

  // Card: Total repassado no ano
  if (anoAtualData) {
    document.getElementById("total-ano").textContent =
      fmt.moedaCompact(anoAtualData.total);

    // Variação anual
    if (anoAnteriorData) {
      const variacao = ((anoAtualData.total - anoAnteriorData.total) / anoAnteriorData.total) * 100;
      const el = document.getElementById("variacao-ano");
      el.textContent = `${fmt.pct(variacao)} em relação a ${anoAtual - 1}`;
      el.className = `metric-sub ${variacao >= 0 ? "variacao-positiva" : "variacao-negativa"}`;
    }

    // Per capita com população real do Censo 2022
    document.getElementById("per-capita").textContent =
      fmt.moeda(anoAtualData.total / popSorocaba);
  } else {
    document.getElementById("total-ano").textContent = "—";
    document.getElementById("per-capita").textContent = "—";
  }

  // Card: Último repasse recebido
  // WR-03: usar reduce para encontrar o mês mais recente — não assume ordenação de por_mes
  const porMes = repasses.por_mes;
  if (porMes && porMes.length > 0) {
    const ultimaMes = porMes.reduce((max, m) => m.data > max.data ? m : max, porMes[0]);
    document.getElementById("ultimo-repasse").textContent =
      fmt.moedaCompact(ultimaMes.valor_total);
    document.getElementById("ultimo-repasse-data").textContent =
      fmt.mesAno(ultimaMes.data);
  }

  // Card: SIOPS — com null-guard completo
  const statusSiops = siops?.status_atual;
  if (statusSiops && statusSiops.percentual != null) {
    document.getElementById("pct-saude").textContent =
      `${statusSiops.percentual.toFixed(1)}%`;
    const statusEl = document.getElementById("status-minimo");
    if (statusSiops.status === "ACIMA_DO_MINIMO") {
      statusEl.textContent = "Acima do mínimo de 15%";
      statusEl.className = "metric-sub variacao-positiva";
    } else {
      statusEl.textContent = "Abaixo do mínimo de 15%";
      statusEl.className = "metric-sub variacao-negativa";
    }
    const cardMinimo = document.getElementById("card-minimo");
    if (cardMinimo) {
      cardMinimo.classList.add(
        statusSiops.status === "ACIMA_DO_MINIMO" ? "status-ok" : "status-danger"
      );
    }
  } else {
    document.getElementById("pct-saude").textContent = "—";
    const statusEl = document.getElementById("status-minimo");
    statusEl.textContent = "Dados não disponíveis (SIOPS pendente)";
    statusEl.className = "metric-sub siops-unfiled";
  }
}

// ─── Hachura para barras de baixo valor (WCAG 1.4.1) ─────────
function criarPadraoHachura(cor) {
  const canvas = document.createElement("canvas");
  canvas.width = 8;
  canvas.height = 8;
  const ctx = canvas.getContext("2d");
  ctx.strokeStyle = cor;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(0, 8);
  ctx.lineTo(8, 0);
  ctx.stroke();
  return canvas;
}

function dadosParaChart(repasses, programaSelecionado) {
  const meses = repasses.por_mes.slice(-60); // últimos 60 meses (5 anos)
  if (programaSelecionado && programaSelecionado !== "todos") {
    return {
      labels: meses.map(m => fmt.mesAno(m.data)),
      valores: meses.map(m => m.programas?.[programaSelecionado] ?? 0),
    };
  }
  return {
    labels: meses.map(m => fmt.mesAno(m.data)),
    valores: meses.map(m => m.valor_total),
  };
}

// ─── Gráfico: Série Temporal ───────────────────────────────────
function renderizarSerieTemporal(repasses) {
  const canvasEl = document.getElementById("chart-serie-temporal");
  if (!canvasEl || !repasses.por_mes) return;

  // WR-01: usar data-listener-attached para evitar re-registro frágil via options.length
  const select = document.getElementById("programa-filter");
  if (select && select.options.length <= 1) {
    repasses.por_programa.forEach(prog => {
      const opt = document.createElement("option");
      opt.value = prog.programa;
      opt.textContent = prog.programa;
      select.appendChild(opt);
    });
  }
  if (select && !select.dataset.listenerAttached) {
    select.addEventListener("change", () => renderizarSerieTemporal(repasses));
    select.dataset.listenerAttached = "1";
  }

  const programaSelecionado = select?.value ?? "todos";
  const { labels, valores } = dadosParaChart(repasses, programaSelecionado);

  const media = valores.length > 0
    ? valores.reduce((a, b) => a + b, 0) / valores.length
    : 0;

  // CanvasPattern para barras abaixo de 50% da média (WCAG 1.4.1)
  const chartCtx = canvasEl.getContext("2d");
  const bgColors = valores.map(v => {
    if (media > 0 && v < media * 0.5) {
      return chartCtx.createPattern(criarPadraoHachura("#ef4444"), "repeat");
    }
    return "#2563eb"; // --chart-blue
  });

  // Destruir instância anterior para evitar "Canvas already in use"
  if (chartSerieTemporal) {
    chartSerieTemporal.destroy();
    chartSerieTemporal = null;
  }

  chartSerieTemporal = new Chart(canvasEl, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Repasse mensal",
        data: valores,
        backgroundColor: bgColors,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const val = fmt.moeda(ctx.raw);
              const idx = ctx.dataIndex;
              if (media > 0 && valores[idx] < media * 0.5) {
                return [val, "Valor abaixo de 50% da média do período"];
              }
              return val;
            }
          }
        }
      },
      scales: {
        y: {
          ticks: {
            callback: (v) => fmt.moedaCompact(v),
            font: { family: "'DM Sans', sans-serif", size: 12 },
          },
          grid: { color: "rgba(0,0,0,0.05)" }
        },
        x: {
          ticks: {
            maxTicksLimit: 20,
            font: { family: "'DM Sans', sans-serif", size: 12 },
          },
          grid: { display: false }
        }
      }
    }
  });
}

// ─── Tabela: Programas ─────────────────────────────────────────
function renderizarTabelaProgramas(repasses, anoAtual) {
  const tbody = document.getElementById("tabela-programas-body");
  if (!tbody || !repasses.por_programa) return;

  tbody.innerHTML = repasses.por_programa.map(prog => {
    // Null-guard para variacao_pct — evita vermelho incorreto em programas novos
    const varClass = (prog.variacao_pct === null || prog.variacao_pct === undefined)
      ? "variacao-neutra"
      : prog.variacao_pct >= 0 ? "variacao-positiva" : "variacao-negativa";
    const varTexto = (prog.variacao_pct === null || prog.variacao_pct === undefined)
      ? "—"
      : fmt.pct(prog.variacao_pct);
    const anoAntTexto = (prog.valor_ano_anterior === null || prog.valor_ano_anterior === undefined)
      ? "—"
      : fmt.moeda(prog.valor_ano_anterior);

    // CR-01: escapar prog.subfuncao para evitar XSS; prog.programa via wrapSigla (UX-01)
    return `
      <tr>
        <td><strong>${wrapSigla(prog.programa)}</strong></td>
        <td style="color:var(--text-secondary)">${escHtml(prog.subfuncao || "—")}</td>
        <td class="text-right">${fmt.moeda(prog.valor_ano_atual)}</td>
        <td class="text-right" style="color:var(--text-muted)">${anoAntTexto}</td>
        <td class="text-right ${varClass}">${varTexto}</td>
      </tr>
    `;
  }).join("");
  registrarTooltipsSiglas();
}

// ─── Gráfico: Comparativo de Municípios ────────────────────────
function renderizarComparativoMunicipios(municipios) {
  const canvasEl = document.getElementById("chart-municipios");
  if (!canvasEl || !municipios.ranking_repasse_per_capita) return;

  const ranking = municipios.ranking_repasse_per_capita;
  const labels = ranking.map(m => m.municipio);
  const valores = ranking.map(m => m.per_capita);
  const cores = ranking.map(m =>
    m.municipio === "Sorocaba" ? "#2563eb" : "#94a3b8"
  );

  // WR-04: verificar antes de append para evitar acúmulo de <p> em re-renders
  if (ranking.length === 1 && !canvasEl.parentElement.querySelector(".ranking-note")) {
    const notaEl = document.createElement("p");
    notaEl.className = "section-desc ranking-note";
    notaEl.style.marginTop = "8px";
    notaEl.textContent =
      "Dados de repasse per capita disponíveis apenas para Sorocaba " +
      "(cobertura do Portal da Transparência). Comparativo por % do orçamento em saúde abaixo.";
    canvasEl.parentElement.appendChild(notaEl);
  }

  if (chartMunicipios) {
    chartMunicipios.destroy();
    chartMunicipios = null;
  }

  chartMunicipios = new Chart(canvasEl, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Repasse per capita (R$/hab)",
        data: valores,
        backgroundColor: cores,
        borderRadius: 4,
      }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `R$ ${ctx.raw.toFixed(0)}/hab`
          }
        }
      },
      scales: {
        x: {
          ticks: {
            callback: (v) => `R$ ${v}`,
            font: { family: "'DM Sans', sans-serif", size: 12 },
          },
          grid: { color: "rgba(0,0,0,0.05)" }
        },
        y: {
          ticks: { font: { family: "'DM Sans', sans-serif", size: 12 } },
          grid: { display: false }
        }
      }
    }
  });
}

// ─── Gráfico: Mínimo Constitucional ───────────────────────────
function renderizarMinimoConstitucional(siops, municipios) {
  const canvasEl = document.getElementById("chart-minimo");
  if (!canvasEl) return;

  // Usar ranking_percentual_saude de municipios.json para comparativo
  const rankingSaude = municipios?.ranking_percentual_saude ?? [];
  const labels = rankingSaude.length > 0
    ? rankingSaude.map(m => m.municipio)
    : (siops?.historico ?? []).map(h => String(h.ano));

  const valores = rankingSaude.length > 0
    ? rankingSaude.map(m => m.percentual)
    : (siops?.historico ?? []).map(h => h.percentual_aplicado);

  const cores = rankingSaude.length > 0
    ? rankingSaude.map(m => {
        if (m.municipio === "Sorocaba") return "#2563eb";
        return m.cumpriu === false ? "#ef4444" : "#94a3b8";
      })
    : ["#2563eb"];

  if (chartMinimo) {
    chartMinimo.destroy();
    chartMinimo = null;
  }

  chartMinimo = new Chart(canvasEl, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "% aplicado em saúde",
          data: valores,
          backgroundColor: cores,
          borderRadius: 4,
        },
        {
          label: "Mínimo constitucional (15%)",
          data: labels.map(() => 15),
          type: "line",
          borderColor: "#ef4444",
          borderDash: [5, 5],
          pointRadius: 0,
          borderWidth: 1.5,
          fill: false,
        }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.label === "Mínimo constitucional (15%)") return null;
              return `${ctx.raw.toFixed(1)}%`;
            }
          }
        }
      },
      scales: {
        y: {
          min: 0,
          ticks: {
            callback: (v) => `${v}%`,
            font: { family: "'DM Sans', sans-serif", size: 12 },
          },
          grid: { color: "rgba(0,0,0,0.05)" }
        },
        x: {
          ticks: { font: { family: "'DM Sans', sans-serif", size: 12 } },
          grid: { display: false }
        }
      }
    }
  });
}

// ─── Reconstrução do dataset linha por linha ──────────────────
function reconstruirLinhasRepasses(repasses) {
  // Mapa programa → subfuncao para lookup rápido
  const subfuncaoPorPrograma = {};
  (repasses.por_programa || []).forEach(p => {
    subfuncaoPorPrograma[p.programa] = p.subfuncao || "—";
  });

  const linhas = [];
  (repasses.por_mes || []).forEach(mes => {
    Object.entries(mes.programas || {}).forEach(([programa, valor]) => {
      linhas.push({
        data: mes.data,                                      // "2022-01"
        programa,
        subfuncao: subfuncaoPorPrograma[programa] || "—",
        valor,
      });
    });
  });
  return linhas; // ordenado por data (herda ordem de por_mes[])
}

function aplicarFiltros() {
  repassesFiltrados = todosRepasses.filter(linha => {
    // Filtro por ano (extrai ano de "2022-01")
    if (filtroAno !== "todos" && !linha.data.startsWith(filtroAno)) return false;
    // Filtro por programa
    if (filtroProg !== "todos" && linha.programa !== filtroProg) return false;
    // Filtro por mês (extrai mês de "2022-01" → "01" → parseInt = 1)
    if (filtroMes !== "todos") {
      const mesLinha = parseInt(linha.data.split("-")[1], 10);
      if (mesLinha !== parseInt(filtroMes, 10)) return false;
    }
    // WR-02: normalizar filtroTexto em ambos os lados para evitar mismatch de case
    if (filtroTexto && !linha.programa.toLowerCase().includes(filtroTexto.toLowerCase())) return false;
    return true;
  });

  paginaAtual = 1; // Sempre resetar para a página 1 ao filtrar
  renderizarPagina(1);
}

// ─── Tabela Completa ───────────────────────────────────────────
function renderizarTabelaCompleta(repasses) {
  const tbody = document.getElementById("tabela-repasses-body");
  if (!tbody) return;

  // WR-05: evitar re-registro de event listeners se já inicializado
  if (document.getElementById("ano-filter")?.dataset.init) return;

  // Reconstruir o dataset completo e armazenar na variável de módulo
  todosRepasses = reconstruirLinhasRepasses(repasses);
  repassesFiltrados = [...todosRepasses];

  // Popular select de anos a partir dos dados
  const anoSelect = document.getElementById("ano-filter");
  if (anoSelect) {
    const anosUnicos = [...new Set(todosRepasses.map(l => l.data.slice(0, 4)))].sort().reverse();
    anoSelect.innerHTML = '<option value="todos">Todos os anos</option>';
    anosUnicos.forEach(ano => {
      const opt = document.createElement("option");
      opt.value = ano;
      opt.textContent = ano;
      anoSelect.appendChild(opt);
    });
    // Padrão: ano mais recente
    if (anosUnicos.length > 0) {
      anoSelect.value = anosUnicos[0];
      filtroAno = anosUnicos[0];
    }
    anoSelect.addEventListener("change", () => {
      filtroAno = anoSelect.value;
      aplicarFiltros();
    });
  }

  // Popular select de programas
  const progSelect = document.getElementById("programa-filter-table");
  if (progSelect) {
    const progsUnicos = [...new Set(todosRepasses.map(l => l.programa))].sort();
    // Manter <option value="todos"> já existente no HTML, adicionar programas
    progsUnicos.forEach(prog => {
      const opt = document.createElement("option");
      opt.value = prog;
      opt.textContent = prog;
      progSelect.appendChild(opt);
    });
    progSelect.addEventListener("change", () => {
      filtroProg = progSelect.value;
      aplicarFiltros();
    });
  }

  // Filtro de mês (opções já no HTML de 05-01)
  const mesSelect = document.getElementById("mes-filter");
  if (mesSelect) {
    mesSelect.addEventListener("change", () => {
      filtroMes = mesSelect.value;
      aplicarFiltros();
    });
  }

  // Busca de texto com debounce 200ms
  const searchInput = document.getElementById("search-repasses");
  let debounceTimer;
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        filtroTexto = searchInput.value.trim().toLowerCase();
        aplicarFiltros();
      }, 200);
    });
  }

  // WR-05: marcar como inicializado para evitar re-registro em chamadas futuras
  if (anoSelect) anoSelect.dataset.init = "1";

  // Renderizar página inicial com filtro de ano mais recente aplicado
  aplicarFiltros();
}

// ─── Paginação ─────────────────────────────────────────────────
function renderizarControlesPaginacao(totalPaginas) {
  const container = document.getElementById("pagination-repasses");
  if (!container) return;
  container.innerHTML = "";

  if (totalPaginas <= 1) return; // Sem paginação para resultado único

  const btnAnterior = document.createElement("button");
  btnAnterior.className = "pagination-btn";
  btnAnterior.textContent = "← Anterior";
  btnAnterior.disabled = paginaAtual === 1;
  btnAnterior.addEventListener("click", () => {
    if (paginaAtual > 1) { paginaAtual--; renderizarPagina(paginaAtual); }
  });
  container.appendChild(btnAnterior);

  // Botões de página (máx 7, janela deslizante)
  const MAX_BOTOES = 7;
  let inicio = Math.max(1, paginaAtual - 3);
  let fim = Math.min(totalPaginas, inicio + MAX_BOTOES - 1);
  if (fim - inicio < MAX_BOTOES - 1) inicio = Math.max(1, fim - MAX_BOTOES + 1);

  for (let p = inicio; p <= fim; p++) {
    const btn = document.createElement("button");
    btn.className = "pagination-btn";
    btn.textContent = p;
    if (p === paginaAtual) btn.setAttribute("aria-current", "page");
    btn.addEventListener("click", () => { paginaAtual = p; renderizarPagina(p); });
    container.appendChild(btn);
  }

  const btnProxima = document.createElement("button");
  btnProxima.className = "pagination-btn";
  btnProxima.textContent = "Próxima →";
  btnProxima.disabled = paginaAtual === totalPaginas;
  btnProxima.addEventListener("click", () => {
    if (paginaAtual < totalPaginas) { paginaAtual++; renderizarPagina(paginaAtual); }
  });
  container.appendChild(btnProxima);
}

function renderizarPagina(pagina) {
  const tbody = document.getElementById("tabela-repasses-body");
  const countEl = document.getElementById("count-repasses");
  if (!tbody) return;

  const total = repassesFiltrados.length;
  const totalPaginas = Math.max(1, Math.ceil(total / REGISTROS_POR_PAGINA));
  paginaAtual = Math.min(pagina, totalPaginas);

  const inicio = (paginaAtual - 1) * REGISTROS_POR_PAGINA;
  const fim = Math.min(inicio + REGISTROS_POR_PAGINA, total);
  const fatia = repassesFiltrados.slice(inicio, fim);

  if (total === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align:center;padding:40px;color:var(--text-muted)">
          <strong>Nenhum registro encontrado</strong><br>
          <span style="font-size:13px">Nenhum repasse corresponde aos filtros selecionados. Tente ampliar os critérios de busca.</span>
        </td>
      </tr>
    `;
    if (countEl) countEl.textContent = "0 registros";
    renderizarControlesPaginacao(1);
    return;
  }

  // CR-01: escapar linha.data e linha.subfuncao; linha.programa via wrapSigla (UX-01)
  tbody.innerHTML = fatia.map(linha => `
    <tr>
      <td>${escHtml(linha.data)}</td>
      <td><strong>${wrapSigla(linha.programa)}</strong></td>
      <td style="color:var(--text-secondary)">${escHtml(linha.subfuncao)}</td>
      <td class="text-right">${fmt.moeda(linha.valor)}</td>
    </tr>
  `).join("");
  registrarTooltipsSiglas();

  if (countEl) {
    countEl.textContent = `Exibindo ${inicio + 1}–${fim} de ${total} registros`;
  }

  renderizarControlesPaginacao(totalPaginas);
}

// ─── Download CSV ──────────────────────────────────────────────
function gerarCSV(linhas, filtroAnoAtivo) {
  const bom = "﻿"; // UTF-8 BOM — garante abertura correta no Excel pt-BR
  const header = "Data,Programa,Subfuncao,Valor\n";
  // CR-03: sanitizar células para evitar injeção de fórmulas CSV
  const rows = linhas.map(r =>
    `${r.data},"${sanitizeCsvCell(r.programa)}","${sanitizeCsvCell(r.subfuncao)}",${r.valor.toFixed(2)}`
  ).join("\n");

  const blob = new Blob([bom + header + rows], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const nome = (filtroAnoAtivo && filtroAnoAtivo !== "todos")
    ? `repasses-sorocaba-${filtroAnoAtivo}.csv`
    : "repasses-sorocaba-todos.csv";
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function configurarDownloadCSV() {
  const btn = document.getElementById("btn-download-csv");
  if (!btn) return;

  btn.addEventListener("click", () => {
    if (repassesFiltrados.length === 0) return;
    gerarCSV(repassesFiltrados, filtroAno);
  });
}

// ─── Start ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);
