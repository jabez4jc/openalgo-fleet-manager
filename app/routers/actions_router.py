from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Server
from app.encryption import encrypt_value, decrypt_value
from app.services.admin_api import AdminAPISession
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/servers", tags=["actions"])


def _get_api_for_server(server: Server) -> AdminAPISession:
    return AdminAPISession(
        base_url=server.base_url,
        username=server.admin_username or "",
        password=decrypt_value(server.admin_password_encrypted or ""),
    )


@router.post("/{server_id}/restart-instance")
async def restart_instance(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    instance = body.get("instance", "")
    if not instance:
        return JSONResponse({"error": "Missing instance"}, status_code=400)

    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="restart_instance", server_id=server_id, instance_name=instance)
    await db.commit()

    api = _get_api_for_server(server)
    result = await api.restart_instance(instance)
    return JSONResponse(result)


@router.post("/{server_id}/stop-instance")
async def stop_instance(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    instance = body.get("instance", "")
    if not instance:
        return JSONResponse({"error": "Missing instance"}, status_code=400)

    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="stop_instance", server_id=server_id, instance_name=instance)
    await db.commit()

    api = _get_api_for_server(server)
    result = await api.stop_instance(instance)
    return JSONResponse(result)


@router.post("/{server_id}/start-instance")
async def start_instance(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    instance = body.get("instance", "")
    if not instance:
        return JSONResponse({"error": "Missing instance"}, status_code=400)

    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="start_instance", server_id=server_id, instance_name=instance)
    await db.commit()

    api = _get_api_for_server(server)
    result = await api.start_instance(instance)
    return JSONResponse(result)


@router.post("/{server_id}/restart-all")
async def restart_all(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="restart_all", server_id=server_id)
    await db.commit()

    api = _get_api_for_server(server)
    result = await api.restart_all()
    return JSONResponse(result)


@router.post("/{server_id}/health-check")
async def health_check(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    scope = body.get("scope", "all")
    instance = body.get("instance")

    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="health_check", server_id=server_id, instance_name=instance)
    await db.commit()

    api = _get_api_for_server(server)
    result = await api.health_check(scope=scope, instance=instance)

    job_id = result.get("job_id")
    if job_id:
        return JSONResponse({"job_id": job_id, "status": "queued", "server_id": server_id})

    return JSONResponse(result)


@router.post("/{server_id}/update")
async def update_instances(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    scope = body.get("scope", "all")
    instance = body.get("instance")

    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="update", server_id=server_id, instance_name=instance)
    await db.commit()

    api = _get_api_for_server(server)
    result = await api.update(scope=scope, instance=instance)

    job_id = result.get("job_id")
    if job_id:
        return JSONResponse({"job_id": job_id, "status": "queued", "server_id": server_id})

    return JSONResponse(result)


@router.post("/{server_id}/reboot-server")
async def reboot_server(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="reboot_server", server_id=server_id)
    await db.commit()

    api = _get_api_for_server(server)
    result = await api.reboot_server()
    return JSONResponse(result)


@router.get("/{server_id}/logs/{instance}")
async def get_instance_logs(request: Request, server_id: int, instance: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    api = _get_api_for_server(server)
    result = await api.get_logs(instance)
    return JSONResponse(result)


async def _load_server(db: AsyncSession, server_id: int) -> Server | None:
    result = await db.execute(select(Server).where(Server.id == server_id))
    return result.scalar_one_or_none()


@router.post("/{server_id}/invalidate-session")
async def invalidate_session(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    instance = body.get("instance", "")
    if not instance:
        return JSONResponse({"error": "Missing instance"}, status_code=400)
    server = await _load_server(db, server_id)
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="invalidate_session", server_id=server_id, instance_name=instance)
    await db.commit()

    return JSONResponse(await _get_api_for_server(server).invalidate_session(instance))


RESET_BROKER_FIELDS = ("broker", "broker_api_key", "broker_api_secret", "broker_api_key_market", "broker_api_secret_market")


@router.post("/{server_id}/reset-admin-user")
async def reset_admin_user(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    instance = body.get("instance", "")
    if not instance:
        return JSONResponse({"error": "Missing instance"}, status_code=400)
    server = await _load_server(db, server_id)
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    # Blank fields are dropped so the server keeps the current broker / keys.
    broker_fields = {k: str(body[k]).strip() for k in RESET_BROKER_FIELDS if str(body.get(k) or "").strip()}
    username = request.session.get("username", "unknown")
    # Never audit the keys themselves - only which ones were changed.
    await write_audit_log(db, actor=username, action="reset_admin_user", server_id=server_id, instance_name=instance,
                          detail={"broker": broker_fields.get("broker"), "fields_changed": sorted(broker_fields)} if broker_fields else None)
    await db.commit()

    return JSONResponse(await _get_api_for_server(server).reset_admin_user(instance, broker_fields))


TERMINAL_FIELDS = ("action", "instance", "lines", "db", "query")


@router.post("/{server_id}/terminal/run")
async def terminal_run(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    fields = {k: str(body[k]) for k in TERMINAL_FIELDS if body.get(k)}
    if not fields.get("action"):
        return JSONResponse({"error": "Missing action"}, status_code=400)
    server = await _load_server(db, server_id)
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    # Read-only on the server, but a SELECT can still read instance data, so it is audited.
    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="terminal_run", server_id=server_id, instance_name=fields.get("instance"),
                          detail={k: v for k, v in fields.items() if k != "instance"})
    await db.commit()

    return JSONResponse(await _get_api_for_server(server).terminal_run(fields))


@router.get("/{server_id}/terminal/dbs")
async def terminal_dbs(server_id: int, instance: str, db: AsyncSession = Depends(get_db)):
    server = await _load_server(db, server_id)
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)
    return JSONResponse(await _get_api_for_server(server).terminal_dbs(instance))


@router.get("/{server_id}/telegram")
async def get_telegram(server_id: int, db: AsyncSession = Depends(get_db)):
    server = await _load_server(db, server_id)
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)
    return JSONResponse(await _get_api_for_server(server).get_telegram())


@router.post("/{server_id}/telegram")
async def set_telegram(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    token = str(body.get("token") or "").strip()
    if not token:
        return JSONResponse({"error": "Paste the bot token from @BotFather"}, status_code=400)
    server = await _load_server(db, server_id)
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="set_telegram", server_id=server_id)
    await db.commit()

    return JSONResponse(await _get_api_for_server(server).set_telegram(token, str(body.get("chat_id") or "").strip()))


@router.post("/{server_id}/change-password")
async def change_password(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    new_password = str(body.get("new_password") or "")
    if len(new_password) < 8:
        return JSONResponse({"error": "New password must be at least 8 characters"}, status_code=400)
    server = await _load_server(db, server_id)
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    username = request.session.get("username", "unknown")
    await write_audit_log(db, actor=username, action="change_admin_password", server_id=server_id)
    await db.commit()

    # The fleet manager logs in with the stored password, so it is the "current"
    # one, and the new one must be stored the moment the server accepts it -
    # otherwise the poller is locked out of this server.
    current = decrypt_value(server.admin_password_encrypted or "")
    result = await _get_api_for_server(server).change_password(current, new_password)
    if result.get("status") == "success":
        server.admin_password_encrypted = encrypt_value(new_password)
        await db.commit()
    return JSONResponse(result)
