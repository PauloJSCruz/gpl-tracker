"""Configuration settings for GPL Tracker."""
import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database path
DB_PATH = DATA_DIR / "gpl_tracker.db"
# Database path (SQLite file stored in persistent volume)
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "gpl_tracker.db"))

# Default vehicle settings if none configured yet
DEFAULT_CONVERSION_COST = 1500.0  # €
DEFAULT_LPG_INCREASE_PERCENT = 20.0  # 20% increase
DEFAULT_PETROL_CONSUMPTION = 7.0  # L/100 km

# DGEG API settings
DGEG_BASE_URL = "https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb"
DGEG_TIMEOUT_SECONDS = 4.0
DGEG_BASE_URL = os.environ.get("DGEG_BASE_URL", "https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb")
DGEG_TIMEOUT_SECONDS = float(os.environ.get("DGEG_TIMEOUT_SECONDS", 4.0))

# API Aberta URL
API_ABERTA_URL = "https://api.apiaberta.pt/v1/fuel/prices"
API_ABERTA_URL = os.environ.get("API_ABERTA_URL", "https://api.apiaberta.pt/v1/fuel/prices")

# Server configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
# Server configuration (0.0.0.0 allows access in Docker and local network)
SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("SERVER_PORT", 8000))

