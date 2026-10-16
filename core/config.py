import os
from pathlib import Path
from dotenv import load_dotenv

# Prioritaskan .env di root repo
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

# =====================================================================
# Database Config
# =====================================================================
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "intransit_agent")
DB_SOURCE_NAME = os.environ.get("DB_SOURCE_NAME", "admin_dashboard3")

# =====================================================================
# IIA Config
# =====================================================================
IIA_BASE_URL = os.environ.get("IIA_BASE_URL", "http://10.254.137.47/IIAWeb").rstrip("/")
IIA_LOGIN_URL = os.environ.get("IIA_LOGIN_URL", f"{IIA_BASE_URL}/Account/Login")
IIA_USERNAME = os.environ.get("IIA_USERNAME", "")
IIA_PASSWORD = os.environ.get("IIA_PASSWORD", "")
IIA_RESP_ID = os.environ.get("IIA_RESP_ID", "91")
IIA_MENU_ID = os.environ.get("IIA_MENU_ID", "14")
IIA_FIELD_USER = os.environ.get("IIA_FIELD_USER", "UserName")
IIA_FIELD_PASS = os.environ.get("IIA_FIELD_PASS", "Password")

# =====================================================================
# Evolution API (WhatsApp) Config
# =====================================================================
EVO_URL = os.environ.get("EVO_URL", "http://localhost:8080").rstrip("/")
EVO_APIKEY = os.environ.get("EVO_APIKEY", "")
EVO_INSTANCE = os.environ.get("EVO_INSTANCE", "rekap_intransit")
OWNER_WA = os.environ.get("OWNER_WA", "")
TARGET_GROUP_JIDS = [
    jid.strip() for jid in os.environ.get("TARGET_GROUP_JIDS", "").split(",") if jid.strip()
]

# =====================================================================
# LLM Config (9router / OpenAI-Compatible)
# =====================================================================
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL_CHEAP = os.environ.get("LLM_MODEL_CHEAP", "gpt-4o-mini")
LLM_MODEL_SMART = os.environ.get("LLM_MODEL_SMART", "gpt-4o")
LLM_DAILY_TOKEN_BUDGET = int(os.environ.get("LLM_DAILY_TOKEN_BUDGET", 500000))

# =====================================================================
# Business Constants
# =====================================================================
AMBANG_INTRANSIT_HARI = int(os.environ.get("AMBANG_INTRANSIT_HARI", 3))
DEFAULT_PRICELIST_ID = int(os.environ.get("DEFAULT_PRICELIST_ID", 80))
