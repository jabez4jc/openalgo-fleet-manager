import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import POLL_INTERVAL_SECONDS, SESSION_SECRET
from app.database import init_db, get_db, async_session_factory
from app.auth import auth_required, get_session_token, _is_exempt
from app.routers import auth_router, dashboard_router, servers_router, actions_router, jobs_router, audit_router, provisioning_router
from app.models import FleetUser
from app.services.poller import poll_all_servers

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("fleetmgr")


@asynccontextmanager
async def lifespan(app: FastAPI):
    retries = 0
    max_retries = 30
    while retries < max_retries:
        try:
            await init_db()
            break
        except Exception as e:
            retries += 1
            logger.warning("Database not ready (attempt %d/%d): %s", retries, max_retries, e)
            if retries == max_retries:
                logger.error("Database never became available after %d attempts — exiting", max_retries)
                raise
            await asyncio.sleep(2)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_poll,
        "interval",
        seconds=POLL_INTERVAL_SECONDS,
        id="poll_servers",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Fleet Manager started, polling every %ds", POLL_INTERVAL_SECONDS)
    yield
    scheduler.shutdown(wait=False)


async def scheduled_poll():
    async with async_session_factory() as db:
        await poll_all_servers(db)


app = FastAPI(title="OpenAlgo Fleet Manager", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, session_cookie="fm_session_data", max_age=12 * 3600, same_site="lax", https_only=False)

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "static")), name="static")


@app.middleware("http")
async def global_auth_middleware(request: Request, call_next):
    path = request.url.path

    if _is_exempt(path):
        return await call_next(request)

    if path.startswith("/static/"):
        return await call_next(request)

    token = request.cookies.get("fm_session")
    from app.encryption import validate_session

    if not token or not validate_session(token):
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"error": "Authentication required"})
        return RedirectResponse(url=f"/login?next={str(request.url)}", status_code=302)

    return await call_next(request)


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    """Served from the root so the worker's scope covers the whole app.

    Under /static/ it could only control /static/ - which is the one part of the
    app that does not need it.
    """
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "..", "static", "sw.js"),
        media_type="text/javascript",
        headers={"Cache-Control": "no-cache"},
    )


app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(servers_router)
app.include_router(actions_router)
app.include_router(jobs_router)
app.include_router(audit_router)
app.include_router(provisioning_router)
