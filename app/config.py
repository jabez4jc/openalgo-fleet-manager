import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://fleetmgr:changeme@localhost:5432/fleetmgr")
FERNET_KEY = os.getenv("FERNET_KEY", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
FLEET_ADMIN_BOOTSTRAP_PASSWORD = os.getenv("FLEET_ADMIN_BOOTSTRAP_PASSWORD", "")
SCRIPTS_REF = os.getenv("SCRIPTS_REF", "main")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
# Shared secret for /api/partner/* — the surface the simplifyed.in client area
# calls. Unset closes that surface rather than opening it; see auth.check_partner_key.
PARTNER_API_KEY = os.getenv("PARTNER_API_KEY", "")
SSL_VERIFY = os.getenv("SSL_VERIFY", "false").lower() == "true"
SCRIPTS_REPO_URL = "https://github.com/jabez4jc/Simplifyed-Scripts.git"
SCRIPTS_REPO_PATH = "/opt/openalgo-scripts"
