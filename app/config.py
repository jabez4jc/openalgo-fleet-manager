import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://fleetmgr:changeme@localhost:5432/fleetmgr")
FERNET_KEY = os.getenv("FERNET_KEY", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
FLEET_ADMIN_BOOTSTRAP_PASSWORD = os.getenv("FLEET_ADMIN_BOOTSTRAP_PASSWORD", "")
SCRIPTS_REF = os.getenv("SCRIPTS_REF", "main")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
SCRIPTS_REPO_URL = "https://github.com/jabez4jc/Simplifyed-Scripts.git"
SCRIPTS_REPO_PATH = "/opt/openalgo-scripts"
