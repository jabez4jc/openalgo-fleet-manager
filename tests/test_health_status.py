"""Run: python tests/test_health_status.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.poller import _health_status_from_health as h

# A wedged instance is "active" to systemd and dead to every user.
assert h({"status": "active", "wedged": True, "serving": False}) == "critical"
assert h({"status": "active", "wedged": False, "serving": True}) == "healthy"
assert h({"status": "active"}) == "healthy"          # older API, no probe fields
assert h({"status": "inactive"}) == "critical"
assert h({"error": "connection_failed"}) == "unreachable"
print("ok")
