"""Run: python tests/test_partner_api.py

/api/partner/* is the one surface reachable without a fleet operator session —
the simplifyed.in client area calls it with a shared key. Two things can go
wrong here quietly, so both are pinned:

  * an unconfigured key silently accepting everyone, and
  * a field added to the Server or Instance model leaking onto a
    customer-facing response because the payload was a model dump.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PARTNER_API_KEY"] = "s3cret-key"
os.environ.setdefault("FERNET_KEY", "PjRPmYIfRUEZ0Xh9EEgnjLQ0-CvEFDKcNJqZ3Vp2Y5A=")

from app.encryption import check_partner_key
import app.encryption

# --- the key ---------------------------------------------------------------

assert check_partner_key("s3cret-key") is True
assert check_partner_key("wrong") is False
assert check_partner_key("s3cret-ke") is False    # a prefix is not enough
assert check_partner_key("") is False
assert check_partner_key(None) is False           # header absent entirely

# Unset key: closed, not open. Comparing against "" would do the opposite.
app.encryption.PARTNER_API_KEY = ""
assert check_partner_key("") is False
assert check_partner_key("anything") is False
assert check_partner_key(None) is False
app.encryption.PARTNER_API_KEY = "s3cret-key"

# --- the payload -----------------------------------------------------------

import json
from types import SimpleNamespace
from app.routers.partner_router import _server_payload

server = SimpleNamespace(
    id=1,
    name="admin-jabez",
    last_seen_at=None,
    base_url="https://admin-jabez.simplifyed.in",
    ssh_host="203.0.113.9",
    ssh_key_encrypted="ENCRYPTED_SSH_KEY",
    admin_username="oa",
    admin_password_encrypted="ENCRYPTED_ADMIN_PASSWORD",
    notes="internal note",
    instances=[
        SimpleNamespace(instance_name="jzkotak", domain="jzkotak.simplifyed.in", broker="kotak",
                        status="active", health_status="healthy", last_polled_at=None,
                        raw_json='{"internal": "probe detail"}', flask_port="5001", env_version="1.2"),
        SimpleNamespace(instance_name="fyers", domain="fyers.simplifyed.in", broker="fyers",
                        status="active", health_status="healthy", last_polled_at=None,
                        raw_json='{"internal": "probe detail"}', flask_port="5002", env_version="1.2"),
    ],
)

out = _server_payload(server)
assert [i["instance_name"] for i in out["instances"]] == ["fyers", "jzkotak"]  # sorted, not insertion order
assert out["server_id"] == 1 and out["name"] == "admin-jabez"

blob = json.dumps(out)
for secret in ("ENCRYPTED_SSH_KEY", "ENCRYPTED_ADMIN_PASSWORD", "203.0.113.9",
               "admin-jabez.simplifyed.in", "probe detail", "internal note"):
    assert secret not in blob, f"{secret!r} leaked to the partner API"

# An instance the poller has not named yet must not crash the sort.
server.instances[0].instance_name = None
_server_payload(server)

print("ok")
