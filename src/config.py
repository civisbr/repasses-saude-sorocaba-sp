"""
config.py
Single source of truth for all RepaseSUS Sorocaba pipeline configuration.
Imported by build.py, fns_collector.py, and builder.py.
"""
from pathlib import Path

# --- Municipality configuration ---
MUNICIPIO_PRINCIPAL = {
    "ibge": "3552205",
    "nome": "Sorocaba",
}

MUNICIPIOS_COMPARAVEIS = {
    "3509502": "Campinas",
    "3549904": "São José dos Campos",
    "3538709": "Piracicaba",
    "3534401": "Osasco",
    "3543402": "Ribeirão Preto",
}

# All 6 municipalities (principal + comparáveis)
TODOS_MUNICIPIOS = {
    MUNICIPIO_PRINCIPAL["ibge"]: MUNICIPIO_PRINCIPAL["nome"],
    **MUNICIPIOS_COMPARAVEIS,
}

# --- API configuration ---
PORTAL_TRANSPARENCIA_BASE_URL = "https://api.portaldatransparencia.gov.br"
FUNCAO_SAUDE = 10           # funcao=10: Saúde — transferências mandatárias only
PAGE_SIZE = 500             # Portal da Transparência max records per page
RATE_LIMIT_SLEEP = 0.3      # seconds between API requests
BACKFILL_START_YEAR = 2019  # first year of historical data

# --- Directory structure ---
ROOT_DIR = Path(__file__).parent.parent
CACHE_DIR = ROOT_DIR / ".cache"
OUTPUT_DIR = ROOT_DIR / "public" / "data"
