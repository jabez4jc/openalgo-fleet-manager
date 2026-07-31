import json
import html as _html

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import AuditLog
from app.routers.dashboard_router import BASE_TEMPLATE_START, BASE_TEMPLATE_END


def _esc(s: str | None) -> str:
    return _html.escape(s or "")

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_class=HTMLResponse)
async def audit_log_page(
    request: Request,
    search: str = Query(None),
    action_filter: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog).order_by(desc(AuditLog.id)).limit(200)
    if action_filter:
        query = query.where(AuditLog.action == action_filter)
    if search:
        query = query.where(
            (AuditLog.actor.ilike(f"%{search}%"))
            | (AuditLog.action.ilike(f"%{search}%"))
            | (AuditLog.instance_name.ilike(f"%{search}%"))
        )

    result = await db.execute(query)
    entries = result.scalars().all()

    html = BASE_TEMPLATE_START
    html += f"""
<div class="page-intro">
<div><div class="eyebrow">Governance</div><h1>Audit log</h1><p>Review every sign-in, change, and fleet action.</p></div>
</div>
<div class="card">
<div class="card-head"><div><h2>Activity history</h2><div class="card-subtitle">Latest 200 recorded events</div></div></div>
<div class="filter-bar">
<form method="GET" action="/audit">
<input type="text" name="search" value="{_esc(search)}" placeholder="Search actor, action, instance...">
<select name="action_filter" onchange="this.form.submit()">
<option value="">All actions</option>
<option value="login" {'selected' if action_filter=='login' else ''}>login</option>
<option value="logout" {'selected' if action_filter=='logout' else ''}>logout</option>
<option value="add_server" {'selected' if action_filter=='add_server' else ''}>add_server</option>
<option value="edit_server" {'selected' if action_filter=='edit_server' else ''}>edit_server</option>
<option value="restart_instance" {'selected' if action_filter=='restart_instance' else ''}>restart_instance</option>
<option value="stop_instance" {'selected' if action_filter=='stop_instance' else ''}>stop_instance</option>
<option value="start_instance" {'selected' if action_filter=='start_instance' else ''}>start_instance</option>
<option value="restart_all" {'selected' if action_filter=='restart_all' else ''}>restart_all</option>
<option value="health_check" {'selected' if action_filter=='health_check' else ''}>health_check</option>
<option value="update" {'selected' if action_filter=='update' else ''}>update</option>
<option value="reboot_server" {'selected' if action_filter=='reboot_server' else ''}>reboot_server</option>
<option value="change_password" {'selected' if action_filter=='change_password' else ''}>change_password</option>
<option value="provision_instance" {'selected' if action_filter=='provision_instance' else ''}>provision_instance</option>
<option value="provision_server" {'selected' if action_filter=='provision_server' else ''}>provision_server</option>
</select>
<button type="submit" class="btn btn-sm">Filter</button>
</form>
</div>
"""
    if not entries:
        html += '<div class="empty-state">No audit log entries.</div>'
    else:
        html += '<div class="table-wrap"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Server</th><th>Instance</th><th>Details</th></tr></thead><tbody>'
        for entry in entries:
            detail_str = ""
            if entry.detail_json:
                try:
                    d = json.loads(entry.detail_json)
                    detail_str = ", ".join(f"{k}={v}" for k, v in d.items())[:100]
                except Exception:
                    detail_str = entry.detail_json[:100]

            em = "\u2014"
            actor = _esc(entry.actor) or em
            instance_name = _esc(entry.instance_name) or em
            server_id = str(entry.server_id) if entry.server_id else em
            escaped_detail = _esc(detail_str)
            html += f"""<tr>
<td style="font-size:12px;color:var(--text-muted);white-space:nowrap">{entry.created_at.strftime('%Y-%m-%d %H:%M:%S') if entry.created_at else ''}</td>
<td style="font-weight:500">{actor}</td>
<td style="font-weight:600">{_esc(entry.action)}</td>
<td style="font-size:12px;color:var(--text-secondary)">{server_id}</td>
<td style="color:var(--text-secondary)">{instance_name}</td>
<td style="font-size:11px;color:var(--text-muted);max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{escaped_detail}">{escaped_detail}</td>
</tr>"""
        html += '</tbody></table></div>'
    html += '</div>' + BASE_TEMPLATE_END
    return HTMLResponse(content=html)
