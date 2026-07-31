from html import escape as _esc

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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;650;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.8/dist/cdn.min.js"></script>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="app-shell">
<aside class="sidebar" id="sidebar">
<div class="brand">
<div class="brand-mark"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M5 12h14M12 5v14"/></svg></div>
<div><b>OpenAlgo Fleet</b><small>Operations console</small></div>
</div>
<div class="sidebar-section-label">Operate</div>
<nav class="sidebar-nav" aria-label="Primary navigation">
<a href="/" class="nav-link" data-route="/"><span>Overview</span></a>
<a href="/servers" class="nav-link" data-route="/servers"><span>Servers</span></a>
<a href="/provision" class="nav-link" data-route="/provision"><span>Provision</span></a>
<a href="/jobs" class="nav-link" data-route="/jobs"><span>Jobs</span></a>
<div class="sidebar-section-label" style="margin-top:25px">Governance</div>
<a href="/audit" class="nav-link" data-route="/audit"><span>Audit log</span></a>
</nav>
<div class="sidebar-footer">
<div class="sidebar-status"><span class="dot pulse"></span><span>Monitoring active</span></div>
<a href="/logout" class="nav-link"><span>Sign out</span></a>
</div>
</aside>
<div class="app-main">
<header class="topbar">
<div class="topbar-left">
<button class="menu-toggle" type="button" aria-label="Open navigation" onclick="document.body.classList.toggle('sidebar-open')">☰</button>
<div class="breadcrumb"><span>OpenAlgo</span><strong>Fleet Manager</strong></div>
</div>
<div class="topbar-right">
<span class="live"><span class="dot pulse"></span><span id="last-updated">Poller live</span></span>
<div class="user-chip"><span class="user-avatar">FM</span><span>Operations</span></div>
</div>
</header>
<div id="toasts" role="status" aria-live="polite"></div>
<main>
"""

BASE_TEMPLATE_END = """
</main>
</div>
</div>
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
const currentPath=window.location.pathname;
document.querySelectorAll('[data-route]').forEach(link=>{
const route=link.dataset.route;
if(currentPath===route||(route!=='/'&&currentPath.startsWith(route))){link.classList.add('active');link.setAttribute('aria-current','page');}
});
const updatedEl=document.getElementById('last-updated');
if(updatedEl)updatedEl.textContent='Live · '+new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
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
            "status": "critical" if (srv_critical + srv_unreachable + srv_gone) else ("warning" if (srv_warning + srv_unknown) else "healthy"),
        })

    html = BASE_TEMPLATE_START
    html += f"""
<div class="page-intro">
<div><div class="eyebrow">OpenAlgo fleet</div><h1>Fleet overview</h1><p>{len(servers)} servers · {total_instances} instances · live health monitoring</p></div>
<div class="page-actions"><a href="/servers/add" class="btn btn-accent">Add server</a><button class="btn btn-ghost" onclick="location.reload()">Refresh data</button></div>
</div>
"""
    html += f"""
<div class="card">
<div class="card-head"><div><h2>Fleet overview</h2><div class="card-subtitle">Current status across registered environments</div></div></div>
<div class="kpi-row">
<div class="kpi"><div class="kpi-label">Servers</div><div class="kpi-value">{len(servers)}</div><div class="kpi-detail">registered environments</div></div>
<div class="kpi"><div class="kpi-label">Instances</div><div class="kpi-value">{total_instances}</div><div class="kpi-detail">discovered workloads</div></div>
<div class="kpi"><div class="kpi-label">Healthy</div><div class="kpi-value" style="color:var(--success)">{healthy_count}</div><div class="kpi-detail">operating normally</div></div>
<div class="kpi"><div class="kpi-label">Warning</div><div class="kpi-value" style="color:var(--warning)">{warning_count}</div><div class="kpi-detail">needs attention</div></div>
<div class="kpi"><div class="kpi-label">Critical</div><div class="kpi-value" style="color:var(--danger)">{critical_count}</div><div class="kpi-detail">requires action</div></div>
</div>
</div>
"""
    if not servers:
        html += '<div class="card"><div class="empty-state">No servers registered. <a href="/servers/add" style="color:var(--accent)">Add your first server</a>.</div></div>'
    else:
        html += '<div class="card"><div class="card-head"><div><h2>Server health</h2><div class="card-subtitle">At-a-glance state of each registered host</div></div><a href="/servers" class="btn btn-sm btn-ghost">Manage servers</a></div><div class="server-card-grid">'
        for row in server_rows:
            bar_count = max(6, min(12, row["instance_count"] or 6))
            bars = []
            for idx in range(bar_count):
                if row["critical"] and idx == bar_count - 1:
                    bar_class = "critical"
                elif row["warning"] and idx >= bar_count - 2:
                    bar_class = "warning"
                elif row["healthy"] and idx < min(row["healthy"], bar_count):
                    bar_class = "healthy"
                else:
                    bar_class = "muted"
                bars.append(f'<span class="server-bar {bar_class}"></span>')
            html += f"""<a class="server-card" href="/servers/{row['id']}">
<div class="server-card-top"><strong>{_esc(row['name'])}</strong><span class="badge badge-{row['status']}">{row['status']}</span></div>
<div class="server-card-host">{_esc(row['base_url'])}</div>
<div class="server-bars" aria-label="{row['healthy']} healthy, {row['warning']} warning, {row['critical']} critical">{''.join(bars)}</div>
<div class="server-card-bottom"><span>{row['instance_count']} instance{'s' if row['instance_count'] != 1 else ''}</span><span class="mono">{row['healthy']} healthy</span></div>
</a>"""
        html += '</div></div>'
        html += '<div class="card"><div class="card-head"><div><h2>Registered servers</h2><div class="card-subtitle">A live inventory of your OpenAlgo control plane</div></div><a href="/servers" class="btn btn-sm btn-ghost">View all servers</a></div><div class="table-wrap"><table><thead><tr><th>Server</th><th>URL</th><th>Instances</th><th>Healthy</th><th>Warning</th><th>Critical</th><th>Last Seen</th><th></th></tr></thead><tbody>'
        for row in server_rows:
            html += f"""<tr>
<td><a href="/servers/{row['id']}" class="mono">{_esc(row['name'])}</a></td>
<td class="mono">{_esc(row['base_url'])}</td>
<td style="font-weight:600">{row['instance_count']}</td>
<td><span class="badge badge-healthy">{row['healthy']}</span></td>
<td><span class="badge badge-warning">{row['warning']}</span></td>
<td><span class="badge badge-critical">{row['critical']}</span></td>
<td style="font-size:12px;color:var(--text-muted)">{_esc(row['last_seen']) if row['last_seen'] else 'never'}</td>
<td><a href="/servers/{row['id']}" class="btn btn-sm btn-ghost">View</a></td>
</tr>"""
        html += '</tbody></table></div></div>'

    html += BASE_TEMPLATE_END
    return HTMLResponse(content=html)


@router.get("/health", response_class=HTMLResponse)
async def health():
    return HTMLResponse(content='{"status":"healthy","service":"OpenAlgo Fleet Manager"}', media_type="application/json")
