import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

logger = logging.getLogger("fleetmgr.audit")


async def write_audit_log(
    db: AsyncSession,
    actor: str,
    action: str,
    server_id: int | None = None,
    instance_name: str | None = None,
    detail: dict | None = None,
):
    entry = AuditLog(
        actor=actor,
        action=action,
        server_id=server_id,
        instance_name=instance_name,
        detail_json=json.dumps(detail) if detail else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.commit()
    logger.info("Audit: %s by %s (server=%s, instance=%s)", action, actor, server_id, instance_name)
