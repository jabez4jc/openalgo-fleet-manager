"""Read-mostly surface for the simplifyed.in client area.

Why this exists at all: clients need to see (and restart) the instances they
own, and the only alternative was giving the website its own copy of every
server's admin credentials. Credentials, the poller cache and the audit log
stay here; the website holds one shared key and no passwords.

Two rules shape everything below:

  * **This endpoint does not authorise anyone.** It has no idea which client
    owns what — the caller passes a key that means "you are the website", not
    "you are a customer". Mapping a person to an instance is the website's
    job, and doing it in one place there is what makes it testable.
  * **Restart is the only write verb.** Stop, start, update, reboot and
    provisioning stay operator-only and unreachable with a partner key. A
    client cannot take a live trading instance down from the website.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Server
from app.routers.actions_router import _get_api_for_server
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/partner", tags=["partner"])


def _server_payload(s) -> dict:
    """An explicit whitelist, never a model dump.

    Kept a separate pure function so it can be tested without a database: the
    failure that matters here is silent (a field added to the model appearing
    on a customer-facing endpoint), so it needs a test that names what may
    cross. base_url, ssh_host, ssh_key_encrypted, admin_password_encrypted and
    an instance's raw_json must never appear below.
    """
    return {
        "server_id": s.id,
        "name": s.name,
        "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
        "instances": [
            {
                "instance_name": i.instance_name,
                "domain": i.domain,
                "broker": i.broker,
                "status": i.status,
                "health_status": i.health_status,
                "last_polled_at": i.last_polled_at.isoformat() if i.last_polled_at else None,
            }
            for i in sorted(s.instances, key=lambda i: i.instance_name or "")
        ],
    }


@router.get("/instances")
async def list_instances(db: AsyncSession = Depends(get_db)):
    """Every server and its instances, from the poller's cache.

    Deliberately not a live fan-out: the poller already refreshes this every
    POLL_INTERVAL_SECONDS, and /api/health can cost up to 5s per unresponsive
    instance. A client page load must not be able to trigger that across the
    whole fleet.
    """
    result = await db.execute(select(Server).order_by(Server.name))
    return JSONResponse({"servers": [_server_payload(s) for s in result.scalars().all()]})


@router.post("/restart")
async def restart_instance(request: Request, db: AsyncSession = Depends(get_db)):
    """Restart one instance on behalf of a named client.

    `actor` is required and recorded as "client:<who>" so a customer-initiated
    restart is never mistaken for an operator one when reading the audit log
    back. It is a label, not a credential — the website has already decided
    this person may touch this instance.
    """
    body = await request.json()
    instance = (body.get("instance") or "").strip()
    actor = (body.get("actor") or "").strip()
    server_id = body.get("server_id")

    if not instance or not actor or not isinstance(server_id, int):
        return JSONResponse({"error": "server_id (int), instance and actor are required"}, status_code=400)

    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    # An instance name the poller has never seen is a bug or a probe, not a
    # restart. Passing it through would hand an arbitrary string to the
    # server's admin API.
    if not any(i.instance_name == instance for i in server.instances):
        return JSONResponse({"error": "Instance not found on this server"}, status_code=404)

    await write_audit_log(
        db,
        actor=f"client:{actor}"[:128],
        action="restart_instance",
        server_id=server_id,
        instance_name=instance,
        detail={"via": "partner_api"},
    )
    await db.commit()

    api = _get_api_for_server(server)
    return JSONResponse(await api.restart_instance(instance))
