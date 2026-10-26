"""Run: python tests/test_server_tools.py

Two server actions can quietly do damage, so both are pinned:
- change-password: the fleet manager logs in with the stored password, so it
  must store the new one exactly when the server accepts it - never otherwise.
- factory reset: blank broker fields must not reach the server (they would
  overwrite keys), and broker secrets must never land in the audit log.
"""
import asyncio, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("FERNET_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
# Never connected to; only has to be an async driver URL so app.database imports.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test@localhost/test"

from app.encryption import encrypt_value, decrypt_value
import importlib
actions_router = importlib.import_module("app.routers.actions_router")  # the package re-exports the router object under this name
from app.services.admin_api import AdminAPISession


class FakeResult:
    def __init__(self, obj): self.obj = obj
    def scalar_one_or_none(self): return self.obj


class FakeDB:
    def __init__(self, server): self.server, self.added = server, []
    async def execute(self, _): return FakeResult(self.server)
    def add(self, obj): self.added.append(obj)
    async def flush(self): pass
    async def commit(self): pass


class FakeRequest:
    def __init__(self, body): self.body, self.session = body, {"username": "op"}
    async def json(self): return self.body


class FakeServer:
    id, base_url, admin_username = 1, "https://x", "admin"
    admin_password_encrypted = encrypt_value("old-password")


def run(coro): return json.loads(asyncio.run(coro).body)


calls = []
def fake(result):
    async def method(self, *args):
        calls.append(args)
        return result
    return method

# Server accepts the change: new password stored, old one sent as "current".
server, calls = FakeServer(), []
AdminAPISession.change_password = fake({"status": "success"})
run(actions_router.change_password(FakeRequest({"new_password": "new-password"}), 1, FakeDB(server)))
assert calls == [("old-password", "new-password")]
assert decrypt_value(server.admin_password_encrypted) == "new-password"

# Server refuses: stored password unchanged.
server = FakeServer()
AdminAPISession.change_password = fake({"error": "Current password is incorrect"})
run(actions_router.change_password(FakeRequest({"new_password": "new-password"}), 1, FakeDB(server)))
assert decrypt_value(server.admin_password_encrypted) == "old-password"

# Too short never reaches the server.
calls = []
assert "error" in run(actions_router.change_password(FakeRequest({"new_password": "short"}), 1, FakeDB(FakeServer())))
assert calls == []

# Factory reset: blanks dropped, secrets kept out of the audit log.
calls, db = [], FakeDB(FakeServer())
AdminAPISession.reset_admin_user = fake({"status": "success"})
run(actions_router.reset_admin_user(FakeRequest({
    "instance": "openalgo1", "broker": "zerodha", "broker_api_key": "KEY123",
    "broker_api_secret": "SECRET456", "broker_api_key_market": "", "broker_api_secret_market": "  ",
}), 1, db))
assert calls == [("openalgo1", {"broker": "zerodha", "broker_api_key": "KEY123", "broker_api_secret": "SECRET456"})]
audit = db.added[0].detail_json
assert "KEY123" not in audit and "SECRET456" not in audit and "zerodha" in audit
print("ok")
