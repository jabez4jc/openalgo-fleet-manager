from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Server
from app.encryption import decrypt_value
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
