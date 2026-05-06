# 🏥 RepaseSUS Sorocaba — Painel de Repasses Federais em Saúde

> Dashboard público que monitora os repasses do governo federal para a saúde de Sorocaba, exibindo quanto foi repassado, quando, por qual programa e se os recursos foram aplicados corretamente — comparando com histórico e municípios similares.

**Deploy:** GitHub Pages — zero custo, zero servidor, atualização automática via GitHub Actions.

---

## 🎯 Objetivo

Criar uma página pública, acessível a qualquer cidadão, que responda às perguntas:
- Quanto o governo federal repassou para saúde de Sorocaba este ano?
- Esses repasses chegaram e foram aplicados?
- Sorocaba aplica o mínimo constitucional de 15% em saúde?
- Como estamos comparados com Campinas, São José dos Campos, Ribeirão Preto?
- Quais programas federais financiam a saúde local (CAPS, UBS, SAMU, etc.)?

---

## 🏗️ Estrutura do Projeto

```
repasses-saude-sorocaba/
│
├── README.md
├── .github/
│   └── workflows/
│       └── update-data.yml      ← GitHub Actions: atualiza dados automaticamente
│
├── src/
│   ├── collectors/
│   │   ├── fns_collector.py     ← Coleta dados do Fundo Nacional de Saúde (FNS)
│   │   ├── siops_collector.py   ← Coleta dados do SIOPS (gastos municipais em saúde)
│   │   └── portal_federal.py    ← Coleta repasses do Portal da Transparência Federal
│   └── processors/
│       ├── aggregator.py        ← Agrega e normaliza os dados coletados
│       └── builder.py           ← Gera os arquivos JSON estáticos para o dashboard
│
├── public/                      ← Pasta servida pelo GitHub Pages
│   ├── index.html               ← Dashboard principal (single page, sem framework)
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── app.js               ← Carrega os JSONs e renderiza os gráficos
│   └── data/                    ← JSONs estáticos gerados pelo pipeline Python
│       ├── repasses.json        ← Série histórica de repasses por programa
│       ├── siops.json           ← Execução orçamentária de saúde por ano
│       ├── municipios.json      ← Dados de municípios comparáveis
│       └── metadata.json        ← Data de atualização, fontes, metodologia
│
└── docs/
    ├── FONTES.md                ← Documentação das APIs
    └── COMO_ATUALIZAR.md        ← Como rodar o pipeline manualmente
```

---

## 📡 Fontes de Dados

### 1. Fundo Nacional de Saúde (FNS) — **Principal**
- **Portal:** `https://consultafns.saude.gov.br/`
- **API:** `https://apifns.saude.gov.br/api/`
- **O que traz:** Repasses federais por programa (PAB, CAPS, SAMU, Farmácia Básica, etc.), mês a mês
- **Campos:** data_repasse, programa, valor, banco, agencia, conta, situacao
- **Filtro:** `municipio_ibge=3552205` (código IBGE de Sorocaba)

### 2. SIOPS — Sistema de Informações sobre Orçamentos Públicos em Saúde
- **Portal:** `https://siops.datasus.gov.br/`
- **Download:** CSV ou API no DATASUS
- **O que traz:** Quanto Sorocaba declarou gastar em saúde, receita total, % aplicado
- **Periodicidade:** Bimestral (atualização mais lenta)

### 3. Portal da Transparência Federal
- **API:** `https://api.portaldatransparencia.gov.br/api-de-dados/`
- **Endpoint:** `/transferencias-voluntarias` com filtro por município
- **Documentação:** Requer cadastro gratuito para obter API key
- **O que traz:** Convênios, transferências voluntárias, emendas parlamentares

### 4. IBGE — Para comparação entre municípios
- **API:** `https://servicodados.ibge.gov.br/api/v3/`
- **O que precisamos:** população atual de Sorocaba e municípios comparáveis
- **Uso:** Calcular repasse per capita para comparações justas

---

## 🔄 Pipeline de Atualização (GitHub Actions)

O GitHub Actions roda automaticamente todo dia às 06h (horário de Brasília):

```yaml
# .github/workflows/update-data.yml
schedule:
  - cron: '0 9 * * *'   # 09:00 UTC = 06:00 BRT

steps:
  - Coletar dados novos das APIs (FNS, SIOPS, Portal Federal)
  - Processar e agregar os dados
  - Gerar/atualizar os JSONs em public/data/
  - Commit e push automático → GitHub Pages atualiza automaticamente
```

**Resultado:** O dashboard sempre mostra dados frescos sem intervenção manual.

---

## 🚀 Setup e Execução

### Pré-requisitos
```bash
python >= 3.10
pip install -r requirements.txt

# Opcional: chave da API do Portal da Transparência Federal
# Obtida gratuitamente em: https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email
```

### Configuração
```bash
cp .env.example .env
# Editar com as variáveis necessárias
```

### Atualização manual dos dados
```bash
python src/build.py
# Gera/atualiza todos os JSONs em public/data/
```

### Desenvolvimento local
```bash
# Servir o dashboard localmente
cd public
python -m http.server 8000
# Acessar: http://localhost:8000
```

### Deploy no GitHub Pages
```bash
# 1. Criar repositório no GitHub
git init
git remote add origin https://github.com/SEU_USUARIO/repasses-saude-sorocaba.git

# 2. Nas configurações do repositório:
#    Settings → Pages → Source: Deploy from branch → Branch: main → Folder: /public

# 3. Push inicial (inclui os JSONs de dados já gerados)
git add .
git commit -m "Deploy inicial — RepaseSUS Sorocaba"
git push origin main

# A partir daí, o GitHub Actions cuida das atualizações diárias.
```

---

## 📊 O que o Dashboard Mostra

### Seção 1 — Cards de Resumo (topo)
| Card | Descrição |
|---|---|
| Total repassado (ano atual) | Soma de todos os repasses federais em saúde para Sorocaba no ano |
| Repasse per capita | Total / população de Sorocaba |
| % do orçamento em saúde | Baseado no SIOPS — mínimo constitucional é 15% |
| Último repasse recebido | Data e valor do repasse mais recente |

### Seção 2 — Gráfico de Série Temporal
- Repasses mensais dos últimos 5 anos (barras)
- Linha de tendência
- Destaque visual para meses sem repasse (possível atraso ou problema)

### Seção 3 — Repasses por Programa
- Tabela com todos os programas federais que repassam para Sorocaba
- Exemplos: PAB (Piso da Atenção Básica), CAPS, SAMU, Farmácia Popular, Atenção Especializada
- Valor total por programa no ano, comparado com ano anterior

### Seção 4 — Comparação com Municípios Similares
- Repasse per capita: Sorocaba vs Campinas, São José dos Campos, Ribeirão Preto, Piracicaba
- % do orçamento em saúde (quem aplica mais?)
- Ranking visual simples

### Seção 5 — Tabela Completa de Repasses
- Todos os repasses individuais, com filtro por ano, programa e mês
- Download CSV

---

## 🎨 Identidade Visual

Dashboard público e sério — não precisa ser chamativo, precisa ser **claro e confiável**.

Paleta sugerida (já usada no seu projeto do dojo — adaptar conforme preferir):
- Fundo: `#0a0e1a` (navy escuro) ou branco limpo
- Acento principal: `#00b4d8` (cyan)
- Texto: `#e8eaf0`
- Alertas: `#f72585` (vermelho vibrante para meses com problema)
- Positivo: `#06d6a0` (verde teal para meses acima da média)

Tipografia: **Space Grotesk** (dados/números) + **Inter** (corpo de texto)

---

## ⚖️ Aviso Legal

Dados obtidos exclusivamente de fontes governamentais oficiais. Projeto sem fins lucrativos, sob licença MIT. Não representa posição política ou partidária.
