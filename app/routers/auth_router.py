from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import FleetUser
from app.encryption import verify_password, hash_password, create_session, validate_session, destroy_session
from app.auth import SESSION_COOKIE, check_bootstrap, bootstrap_admin, check_rate_limit, record_failed_attempt, clear_rate_limit
from app.services.audit import write_audit_log

router = APIRouter(tags=["auth"])

LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpenAlgo Fleet Manager - Login</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body class="login-page">
<div class="card login-card">
<h1><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3 8 4-16 3 8h4"/></svg>Fleet Manager</h1>
<p class="sub">OpenAlgo Fleet Dashboard</p>
{error_html}{info_html}
<form method="POST" action="/login-submit">
<div>
<label class="reset-field-label">Username</label>
<input class="reset-input" type="text" name="username" autocomplete="username" autofocus required>
</div>
<div>
<label class="reset-field-label">Password</label>
<input class="reset-input" type="password" name="password" autocomplete="current-password" required>
</div>
<input type="hidden" name="next" value="{next_path}">
<button type="submit" class="btn btn-accent">Sign in</button>
</form>
</div>
</body>
</html>"""


def _esc(s):
    return (s or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    next_path = request.query_params.get("next", "/")

    is_bootstrap = await check_bootstrap(db)
    if is_bootstrap:
        info = '<div class="login-info">First-run setup. Use the initial password to sign in, then you will be prompted to change it.</div>'
        error_html = ""
    else:
        info = ""
        error_html = ""

    html = LOGIN_TEMPLATE.format(
        error_html=error_html,
        info_html=info,
        next_path=_esc(next_path),
    )
    return HTMLResponse(content=html)


@router.post("/login-submit")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"

    if not check_rate_limit(username, client_ip):
        html = LOGIN_TEMPLATE.format(
            error_html='<div class="login-error">Too many failed attempts. Try again in 15 minutes.</div>',
            info_html='',
            next_path=_esc(next),
        )
        return HTMLResponse(content=html, status_code=429)

    result = await db.execute(select(FleetUser).where(FleetUser.username == username))
    user = result.scalar_one_or_none()

    is_bootstrap = await check_bootstrap(db)

    if is_bootstrap and not user:
        await bootstrap_admin(db)
        info = '<div class="login-info">First-run setup complete. Sign in with username <strong>admin</strong> and the bootstrap password set in your environment.</div>'
        html = LOGIN_TEMPLATE.format(
            error_html='',
            info_html=info,
            next_path=_esc(next),
        )
        return HTMLResponse(content=html)

    if not user or not verify_password(password, user.password_hash):
        record_failed_attempt(username, client_ip)
        html = LOGIN_TEMPLATE.format(
            error_html='<div class="login-error">Invalid username or password.</div>',
            info_html='',
            next_path=_esc(next),
        )
        return HTMLResponse(content=html, status_code=401)

    clear_rate_limit(username, client_ip)

    token = create_session()
    request.session["user_id"] = user.id
    request.session["username"] = user.username

    resp = RedirectResponse(url=next if (next.startswith("/") and not next.startswith("//")) else "/", status_code=302)
    cookie = f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; Max-Age={12 * 3600}; SameSite=Lax"
    if request.headers.get("x-forwarded-proto", "").lower() == "https":
        cookie += "; Secure"
    resp.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        max_age=12 * 3600,
        samesite="lax",
        secure=request.headers.get("x-forwarded-proto", "").lower() == "https",
    )

    await write_audit_log(db, actor=username, action="login")
    await db.commit()

    return resp


@router.get("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    username = request.session.get("username", "unknown")
    if token:
        destroy_session(token)
        request.session.clear()

    await write_audit_log(db, actor=username, action="logout")
    await db.commit()

    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@router.get("/force-change-password", response_class=HTMLResponse)
async def force_change_password_page(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token or not validate_session(token):
        return RedirectResponse(url="/login", status_code=302)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Change Password - Fleet Manager</title>
<style>
:root{
--bg:#0a0e17;--bg-elev:#0e1420;--surface:#121a29;--surface-2:#182135;--border:#232e44;--text:#e8ecf5;--text-dim:#94a2b9;
--accent:#5b8cff;--danger:#f4586e;--danger-soft:rgba(244,88,110,.12);
--radius:12px;--radius-sm:8px;
--shadow:0 1px 2px rgba(0,0,0,.35),0 12px 28px -12px rgba(0,0,0,.55);
--font:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--font);background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow)}
.cpw-card{width:100%;max-width:380px;padding:28px;margin:20px}
.cpw-card h1{font-size:16px;font-weight:650;margin-bottom:16px}
.error{background:var(--danger-soft);color:var(--danger);border:1px solid rgba(244,88,110,.35);border-radius:var(--radius-sm);padding:9px 12px;font-size:12.5px;margin-bottom:14px}
label{display:block;font-size:12.5px;margin-bottom:5px;color:var(--text-dim)}
input{width:100%;padding:9px 10px;margin-bottom:12px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--text);font-size:13px;font-family:inherit}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:8px 14px;border-radius:var(--radius-sm);font-size:13px;font-weight:500;border:1px solid var(--border);background:var(--surface-2);color:var(--text);cursor:pointer;font-family:inherit;width:100%}
.btn-accent{background:var(--accent);border-color:var(--accent);color:#fff}
</style>
</head>
<body>
<div class="card cpw-card">
<h1>Change Password Required</h1>
<div id="error" class="error" style="display:none"></div>
<form id="cpw-form" onsubmit="changePassword(event)">
<label>New Password</label>
<input type="password" id="new-pw" required minlength="8">
<label>Confirm New Password</label>
<input type="password" id="confirm-pw" required minlength="8">
<button type="submit" class="btn btn-accent">Change Password</button>
</form>
</div>
<script>
async function changePassword(e){
e.preventDefault();
const np=document.getElementById('new-pw').value;
const cp=document.getElementById('confirm-pw').value;
const errEl=document.getElementById('error');
if(np!==cp){errEl.style.display='block';errEl.textContent='Passwords do not match';return;}
try{
const r=await fetch('/api/change-password',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({new_password:np})
});
const d=await r.json();
if(r.ok){window.location.href='/';}
else{errEl.style.display='block';errEl.textContent=d.error||d.detail||'Failed';}
}catch(ex){errEl.style.display='block';errEl.textContent='Network error';}
}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.post("/api/change-password")
async def change_password(request: Request, db: AsyncSession = Depends(get_db)):
    import json as _json
    body = await request.body()
    data = _json.loads(body)
    new_password = data.get("new_password", "")

    if not new_password or len(new_password) < 8:
        return {"error": "Password must be at least 8 characters"}

    user_id = request.session.get("user_id")
    if not user_id:
        return {"error": "Not authenticated"}

    result = await db.execute(select(FleetUser).where(FleetUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"error": "User not found"}

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    await db.commit()

    await write_audit_log(db, actor=user.username, action="change_password")
    await db.commit()

    return {"status": "success", "message": "Password changed"}
