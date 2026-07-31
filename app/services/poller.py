import json
import time
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Server, Instance
from app.encryption import decrypt_value
from app.services.admin_api import AdminAPISession
from app.config import ALERT_WEBHOOK_URL

logger = logging.getLogger("fleetmgr.poller")


def _health_status_from_health(health_data: dict) -> str:
    if health_data.get("error"):
        return "unreachable"
    # systemd is-active says "active" for a wedged worker that answers nothing.
    # /api/health's socket probe is the only thing that sees it - and it is the
    # state that produces the user-visible 5xx, so it is critical, not healthy.
    if health_data.get("wedged"):
        return "critical"
    status = health_data.get("status", "unknown")
    if status == "active":
        return "healthy"
    if status == "inactive" or status == "failed":
        return "critical"
    return "warning"


async def poll_server(server: Server, db: AsyncSession):
    api = AdminAPISession(
        base_url=server.base_url,
        username=server.admin_username or "",
        password=decrypt_value(server.admin_password_encrypted or ""),
    )

    try:
        health_data = await api.get_health()
    except Exception as e:
        health_data = {"error": str(e)}

    if health_data.get("error"):
        logger.warning("Server %s (%s): health poll failed: %s", server.name, server.base_url, health_data.get("error"))
        for inst in server.instances:
            inst.status = "unknown"
            inst.health_status = "unreachable"
            inst.last_polled_at = datetime.now(timezone.utc)
        server.last_seen_at = datetime.now(timezone.utc)
        await db.commit()
        return

    server.last_seen_at = datetime.now(timezone.utc)

    instances_health = health_data.get("instances", {})
    seen_names = set()

    for inst_name, inst_data in instances_health.items():
        seen_names.add(inst_name)
        inst_status = "wedged" if inst_data.get("wedged") else inst_data.get("status", "unknown")
        health_status = _health_status_from_health(inst_data)

        existing = None
        for inst in server.instances:
            if inst.instance_name == inst_name:
                existing = inst
                break

        raw_json = json.dumps(inst_data, default=str)

        if existing:
            existing.status = inst_status
            existing.health_status = health_status
            existing.domain = inst_data.get("domain")
            existing.broker = inst_data.get("broker")
            existing.flask_port = inst_data.get("port")
            existing.env_version = inst_data.get("env_version")
            existing.raw_json = raw_json
            existing.last_polled_at = datetime.now(timezone.utc)
        else:
            new_inst = Instance(
                server_id=server.id,
                instance_name=inst_name,
                domain=inst_data.get("domain"),
                broker=inst_data.get("broker"),
                flask_port=str(inst_data.get("port")) if inst_data.get("port") else None,
                status=inst_status,
                health_status=health_status,
                env_version=inst_data.get("env_version"),
                last_polled_at=datetime.now(timezone.utc),
                raw_json=raw_json,
            )
            db.add(new_inst)

    for inst in server.instances:
        if inst.instance_name not in seen_names:
            inst.status = "gone"
            inst.health_status = "gone"
            inst.last_polled_at = datetime.now(timezone.utc)

    await db.commit()


async def poll_all_servers(db: AsyncSession):
    result = await db.execute(select(Server))
    servers = result.scalars().all()
    logger.info("Polling %d servers", len(servers))

    critical_alerts = []

    for server in servers:
        if not server.admin_username or not server.admin_password_encrypted:
            logger.debug("Skipping server %s: no admin credentials", server.name)
            continue
        try:
            await poll_server(server, db)
        except Exception as e:
            logger.error("Poll failed for server %s: %s", server.name, e)

    await db.commit()

    for server in servers:
        for inst in server.instances:
            if inst.health_status in ("critical", "unreachable"):
                critical_alerts.append({
                    "server": server.name,
                    "instance": inst.instance_name,
                    "domain": inst.domain,
                    "health_status": inst.health_status,
                    "status": inst.status,
                    "last_polled": inst.last_polled_at.isoformat() if inst.last_polled_at else None,
                })

    if critical_alerts and ALERT_WEBHOOK_URL:
        _send_alert(critical_alerts)


def _send_alert(critical_instances: list[dict]):
    try:
        import httpx
        payload = {
            "service": "openalgo-fleet-manager",
            "severity": "critical",
            "message": f"{len(critical_instances)} instance(s) in critical/unreachable state",
            "instances": critical_instances,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        resp = httpx.post(ALERT_WEBHOOK_URL, json=payload, timeout=15)
        logger.info("Alert sent to webhook: %s", resp.status_code)
    except Exception as e:
        logger.error("Failed to send alert: %s", e)
