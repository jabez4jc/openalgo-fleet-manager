from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Server, FleetUser

router = APIRouter(tags=["dashboard"])


async def _check_password_change(request: Request, db: AsyncSession):
    user_id = request.session.get("user_id")
    if user_id:
        result = await db.execute(select(FleetUser).where(FleetUser.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.must_change_password:
            return True
    return False


BASE_TEMPLATE_START = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpenAlgo Fleet Manager</title>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.8/dist/cdn.min.js"></script>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="topbar">
<div class="brand"><b>OpenAlgo Fleet Manager</b></div>
<div class="topbar-right">
<a href="/" class="nav-link active">Dashboard</a>
<a href="/servers" class="nav-link">Servers</a>
<a href="/jobs" class="nav-link">Jobs</a>
<a href="/audit" class="nav-link">Audit Log</a>
<a href="/logout" class="nav-link">Logout</a>
<span class="live"><span class="dot pulse"></span><span id="last-updated">Loading...</span></span>
</div>
</div>
<div id="toasts" role="status" aria-live="polite"></div>
<main>
"""

BASE_TEMPLATE_END = """
</main>
<script>
function showToast(msg,type){
const list=document.getElementById('toasts');
const t=document.createElement('div');
t.className='toast '+type;
const icons={success:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9 12l2 2 4-4"/></svg>',
error:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>'};
t.innerHTML=(icons[type]||'')+'<span class="toast-msg"></span><button class="toast-close" onclick="this.parentElement.remove()">×</button>';
t.querySelector('.toast-msg').textContent=msg;
list.appendChild(t);
if(type!=='error')setTimeout(()=>t.remove(),4000);
}
function fmtTime(iso){
if(!iso)return'never';
const d=new Date(iso);
return d.toLocaleString();
}
function escHtml(s){
const m={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'};
return String(s||'').replace(/[&<>"']/g,c=>m[c]);
}
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    needs_pw = await _check_password_change(request, db)
    if needs_pw:
        return RedirectResponse(url="/force-change-password", status_code=302)

    result = await db.execute(select(Server).order_by(Server.name))
    servers = result.scalars().all()

    total_instances = 0
    healthy_count = 0
    warning_count = 0
    critical_count = 0

    server_rows = []
    for srv in servers:
        insts = srv.instances
        srv_healthy = sum(1 for i in insts if i.health_status == "healthy")
        srv_warning = sum(1 for i in insts if i.health_status == "warning")
        srv_critical = sum(1 for i in insts if i.health_status in ("critical", "inactive", "failed"))
        srv_unreachable = sum(1 for i in insts if i.health_status == "unreachable")
        srv_unknown = sum(1 for i in insts if i.health_status not in ("healthy", "warning", "critical", "inactive", "failed", "unreachable", "gone"))
        srv_gone = sum(1 for i in insts if i.health_status == "gone")

        total_instances += len(insts)
        healthy_count += srv_healthy
        warning_count += srv_warning + srv_unknown
        critical_count += srv_critical + srv_unreachable + srv_gone

        last_seen = srv.last_seen_at.isoformat() if srv.last_seen_at else None
        server_rows.append({
            "id": srv.id,
            "name": srv.name,
            "base_url": srv.base_url,
            "instance_count": len(insts),
            "healthy": srv_healthy,
            "warning": srv_warning + srv_unknown,
            "critical": srv_critical + srv_unreachable + srv_gone,
            "last_seen": last_seen,
        })

    html = BASE_TEMPLATE_START
    html += f"""
<div class="card">
<div class="card-head"><h2>Fleet Overview</h2>
<div style="display:flex;gap:8px">
<a href="/servers/add" class="btn btn-accent btn-sm">Add Server</a>
<button class="btn btn-sm" onclick="location.reload()">Refresh</button>
</div>
</div>
<div class="kpi-row">
<div class="kpi"><div class="kpi-label">Servers</div><div class="kpi-value">{len(servers)}</div></div>
<div class="kpi"><div class="kpi-label">Instances</div><div class="kpi-value">{total_instances}</div></div>
<div class="kpi"><div class="kpi-label">Healthy</div><div class="kpi-value" style="color:var(--success)">{healthy_count}</div></div>
<div class="kpi"><div class="kpi-label">Warning</div><div class="kpi-value" style="color:var(--warning)">{warning_count}</div></div>
<div class="kpi"><div class="kpi-label">Critical</div><div class="kpi-value" style="color:var(--danger)">{critical_count}</div></div>
</div>
</div>
"""
    if not servers:
        html += '<div class="card"><div class="empty-state">No servers registered. <a href="/servers/add" style="color:var(--accent)">Add your first server</a>.</div></div>'
    else:
        html += '<div class="card"><div class="card-head"><h2>Servers</h2></div><table><thead><tr><th>Server</th><th>URL</th><th>Instances</th><th>Healthy</th><th>Warning</th><th>Critical</th><th>Last Seen</th><th></th></tr></thead><tbody>'
        for row in server_rows:
            html += f"""<tr>
<td><a href="/servers/{row['id']}" style="color:var(--accent);text-decoration:none;font-weight:600">{row['name']}</a></td>
<td class="mono" style="font-size:12px">{row['base_url']}</td>
<td>{row['instance_count']}</td>
<td><span class="badge badge-healthy">{row['healthy']}</span></td>
<td><span class="badge badge-warning">{row['warning']}</span></td>
<td><span class="badge badge-critical">{row['critical']}</span></td>
<td style="font-size:12px;color:var(--text-faint)">{'<script>document.write(fmtTime("'+row['last_seen']+'"))</script>' if row['last_seen'] else 'never'}</td>
<td><a href="/servers/{row['id']}" class="btn btn-sm">View</a></td>
</tr>"""
        html += '</tbody></table></div>'

    html += BASE_TEMPLATE_END
    return HTMLResponse(content=html)


@router.get("/health", response_class=HTMLResponse)
async def health():
    return HTMLResponse(content='{"status":"healthy","service":"OpenAlgo Fleet Manager"}', media_type="application/json")
