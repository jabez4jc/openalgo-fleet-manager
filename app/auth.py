from fastapi import Request, HTTPException, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import FleetUser
from app.encryption import validate_session
from app.config import FLEET_ADMIN_BOOTSTRAP_PASSWORD

SESSION_COOKIE = "fm_session"
EXEMPT_PATHS = {"/login", "/login-submit", "/health"}


def _is_exempt(path: str) -> bool:
    normalized = path.rstrip("/")
    return normalized in EXEMPT_PATHS


def get_session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> FleetUser | None:
    token = get_session_token(request)
    if not token:
        return None
    if not validate_session(token):
        return None

    session_data = request.session
    user_id = session_data.get("user_id")
    if not user_id:
        return None

    result = await db.execute(select(FleetUser).where(FleetUser.id == user_id))
    return result.scalar_one_or_none()


async def auth_required(request: Request):
    if _is_exempt(request.url.path):
        return True

    token = get_session_token(request)
    if not token or not validate_session(token):
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Authentication required")
        redirect_url = str(request.url)
        return RedirectResponse(url=f"/login?next={redirect_url}", status_code=302)

    session_data = request.session
    if not session_data.get("user_id"):
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Authentication required")
        return RedirectResponse(url="/login", status_code=302)

    return True


async def check_bootstrap(db: AsyncSession) -> bool:
    result = await db.execute(select(FleetUser))
    users = result.scalars().all()
    return len(users) == 0


async def bootstrap_admin(db: AsyncSession):
    from app.encryption import hash_password

    password = FLEET_ADMIN_BOOTSTRAP_PASSWORD
    if not password:
        import secrets
        password = secrets.token_urlsafe(16)

    user = FleetUser(
        username="admin",
        password_hash=hash_password(password),
        must_change_password=True,
    )
    db.add(user)
    await db.commit()
    return password
