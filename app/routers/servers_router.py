import json
import html as _html

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Server, Instance
from app.encryption import encrypt_value, decrypt_value
from app.services.audit import write_audit_log
from app.routers.dashboard_router import BASE_TEMPLATE_START, BASE_TEMPLATE_END

router = APIRouter(prefix="/servers", tags=["servers"])


def _esc(value: object, quote: bool = True) -> str:
    return _html.escape(str(value or ""), quote=quote)


def _js_arg(value: str | None) -> str:
    """Encode a string for a quoted inline handler without breaking the page."""
    return _esc(json.dumps(value or ""), quote=True)


def _format_dt(value: object, fmt: str, fallback: str = "never") -> str:
    if not value:
        return fallback
    formatter = getattr(value, "strftime", None)
    return formatter(fmt) if formatter else _esc(value)


@router.get("", response_class=HTMLResponse)
async def servers_list(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).order_by(Server.name))
    servers = result.scalars().all()

    html = BASE_TEMPLATE_START
    html += """
<div class="page-intro">
<div><div class="eyebrow">Infrastructure</div><h1>Servers</h1><p>Manage access, connectivity, and the instances running on each host.</p></div>
<div class="page-actions"><a href="/servers/add" class="btn btn-accent">Add server</a></div>
</div>
<div class="card">
<div class="card-head"><div><h2>Registered servers</h2><div class="card-subtitle">Credentials are encrypted at rest</div></div></div>
"""
    if not servers:
        html += '<div class="empty-state">No servers registered yet.</div>'
    else:
        html += '<div class="table-wrap"><table><thead><tr><th>Name</th><th>URL</th><th>SSH Host</th><th>Instances</th><th>Last Seen</th><th></th></tr></thead><tbody>'
        for srv in servers:
            inst_count = len(srv.instances)
            last_seen = srv.last_seen_at.strftime("%Y-%m-%d %H:%M:%S") if srv.last_seen_at else "never"
            ssh_info = f"{srv.ssh_user}@{srv.ssh_host}:{srv.ssh_port}" if srv.ssh_host else "\u2014"
            html += f"""<tr>
<td style="font-weight:600"><a href="/servers/{srv.id}">{_esc(srv.name)}</a></td>
<td class="mono">{_esc(srv.base_url)}</td>
<td class="mono">{_esc(ssh_info)}</td>
<td style="font-weight:600">{inst_count}</td>
<td style="font-size:12px;color:var(--text-muted)">{_esc(last_seen)}</td>
<td><div style="display:flex;gap:6px">
<a href="/servers/{srv.id}" class="btn btn-sm btn-ghost">View</a>
<a href="/servers/{srv.id}/edit" class="btn btn-sm btn-ghost">Edit</a>
</div></td>
</tr>"""
        html += '</tbody></table></div>'
    html += '</div>' + BASE_TEMPLATE_END
    return HTMLResponse(content=html)


@router.get("/add", response_class=HTMLResponse)
async def add_server_form(request: Request, db: AsyncSession = Depends(get_db)):
    html = BASE_TEMPLATE_START
    html += """
<div class="card">
<div class="card-head"><h2>Add Server</h2></div>
<div style="padding:20px">
<form method="POST" action="/servers/add">
<label class="reset-field-label">Name</label>
<input class="reset-input" type="text" name="name" required placeholder="e.g. prod-server-1">
<label class="reset-field-label">Admin API URL</label>
<input class="reset-input" type="text" name="base_url" required placeholder="https://server-ip:8888">
<label class="reset-field-label">Admin Username</label>
<input class="reset-input" type="text" name="admin_username" required placeholder="fleetmgr">
<label class="reset-field-label">Admin Password</label>
<input class="reset-input" type="password" name="admin_password" required>
<hr style="border-color:var(--border);margin:16px 0">
<p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">SSH details are optional - required for provisioning.</p>
<label class="reset-field-label">SSH Host</label>
<input class="reset-input" type="text" name="ssh_host" placeholder="192.168.1.10">
<label class="reset-field-label">SSH Port</label>
<input class="reset-input" type="number" name="ssh_port" value="22" placeholder="22">
<label class="reset-field-label">SSH User</label>
<input class="reset-input" type="text" name="ssh_user" placeholder="ubuntu">
<label class="reset-field-label">SSH Private Key <span style="color:var(--text-muted)">(paste full key)</span></label>
<textarea name="ssh_key" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" class="mono" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg-elevated);color:var(--text-primary);font-size:12px;min-height:120px;resize:vertical"></textarea>
<label class="reset-field-label">SSH Host Key <span style="color:var(--text-muted)">(ssh-keyscan output, for pinning)</span></label>
<textarea name="ssh_host_key" placeholder="server.example.com ssh-rsa AAAAB3..." class="mono" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg-elevated);color:var(--text-primary);font-size:12px;min-height:60px;resize:vertical"></textarea>
<label class="reset-field-label">Notes</label>
<textarea name="notes" placeholder="Optional notes..." style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg-elevated);color:var(--text-primary);font-size:13px;font-family:inherit;min-height:60px;resize:vertical"></textarea>
<div style="display:flex;gap:10px;justify-content:flex-end">
<a href="/servers" class="btn">Cancel</a>
<button type="submit" class="btn btn-accent">Add Server</button>
</div>
</form>
</div>
</div>"""
    html += BASE_TEMPLATE_END
    return HTMLResponse(content=html)


@router.post("/add")
async def add_server_submit(
    request: Request,
    name: str = Form(...),
    base_url: str = Form(...),
    admin_username: str = Form(...),
    admin_password: str = Form(...),
    ssh_host: str = Form(""),
    ssh_port: int = Form(22),
    ssh_user: str = Form(""),
    ssh_key: str = Form(""),
    ssh_host_key: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "unknown")

    server = Server(
        name=name,
        base_url=base_url.rstrip("/"),
        ssh_host=ssh_host or None,
        ssh_port=ssh_port,
        ssh_user=ssh_user or None,
        ssh_key_encrypted=encrypt_value(ssh_key) if ssh_key.strip() else None,
        ssh_host_key=ssh_host_key.strip() or None,
        admin_username=admin_username,
        admin_password_encrypted=encrypt_value(admin_password),
        notes=notes or None,
    )
    db.add(server)
    await db.commit()

    await write_audit_log(db, actor=username, action="add_server", server_id=server.id, detail={"name": name, "base_url": base_url})
    await db.commit()

    return RedirectResponse(url="/servers", status_code=302)


@router.get("/{server_id}", response_class=HTMLResponse)
async def server_detail(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Server).options(selectinload(Server.instances)).where(Server.id == server_id)
    )
    server = result.scalar_one_or_none()
    if not server:
        return HTMLResponse(content=BASE_TEMPLATE_START + '<div class="card"><div class="empty-state">Server not found.</div></div>' + BASE_TEMPLATE_END, status_code=404)

    instances = list(server.instances or [])
    em = "\u2014"
    ssh_info = f"{server.ssh_user}@{server.ssh_host}:{server.ssh_port}" if server.ssh_host else em

    html = BASE_TEMPLATE_START
    html += f"""
<div class="card">
<div class="card-head">
<h2><a href="/">Fleet</a> / {_esc(server.name)}</h2>
<div style="display:flex;gap:8px">
<a href="/servers/{server.id}/edit" class="btn btn-sm btn-ghost">Edit</a>
<button class="btn btn-sm btn-ghost" onclick="location.reload()">Refresh</button>
</div>
</div>
<div class="server-meta">
<div class="server-meta-item"><span class="server-meta-label">URL</span><span class="server-meta-value">{_esc(server.base_url)}</span></div>
<div class="server-meta-item"><span class="server-meta-label">Admin</span><span>{_esc(server.admin_username)}</span></div>
<div class="server-meta-item"><span class="server-meta-label">SSH</span><span>{_esc(ssh_info)}</span></div>
<div class="server-meta-item"><span class="server-meta-label">Instances</span><span style="font-weight:600">{len(instances)}</span></div>
<div class="server-meta-item"><span class="server-meta-label">Last poll</span><span class="mono">{_format_dt(server.last_seen_at, '%Y-%m-%d %H:%M:%S')}</span></div>
</div>
</div>
"""
    if not instances:
        html += '<div class="card"><div class="empty-state">No instances found on this server. Poll may not have run yet, or the server has no OpenAlgo instances.</div></div>'
    else:
        html += '<div class="card"><div class="card-head"><h2>Instances</h2><a href="/provision" class="btn btn-accent btn-sm">Provision Instance</a></div><div class="table-wrap"><table><thead><tr><th>Instance</th><th>Domain</th><th>Broker</th><th>Status</th><th>Health</th><th>Version</th><th>Last Poll</th><th>Actions</th></tr></thead><tbody>'
        for inst in instances:
            health_badge = ""
            hs = inst.health_status or "unknown"
            if hs == "healthy":
                health_badge = '<span class="badge badge-healthy">healthy</span>'
            elif hs in ("warning",):
                health_badge = '<span class="badge badge-warning">warning</span>'
            elif hs in ("critical", "inactive", "failed"):
                health_badge = '<span class="badge badge-critical">critical</span>'
            elif hs == "unreachable":
                health_badge = '<span class="badge badge-unreachable">unreachable</span>'
            elif hs == "gone":
                health_badge = '<span class="badge badge-unreachable">gone</span>'
            else:
                health_badge = '<span class="badge badge-unknown">unknown</span>'

            status_badge = ""
            st = inst.status or "unknown"
            if st == "active":
                status_badge = '<span class="badge badge-healthy">active</span>'
            elif st == "wedged":
                status_badge = '<span class="badge badge-critical" title="systemd says active but the instance answers nothing">wedged</span>'
            elif st in ("inactive", "failed"):
                status_badge = '<span class="badge badge-critical">' + _esc(st) + '</span>'
            else:
                status_badge = '<span class="badge badge-unknown">' + _esc(st) + '</span>'

            em = "\u2014"
            poll_time = _format_dt(inst.last_polled_at, "%H:%M:%S")

            html += f"""<tr>
<td style="font-weight:600">{_esc(inst.instance_name)}</td>
<td class="mono">{_esc(inst.domain or em)}</td>
<td style="color:var(--text-secondary)">{_esc(inst.broker or em)}</td>
<td>{status_badge}</td>
<td>{health_badge}</td>
<td style="color:var(--text-secondary)">{_esc(inst.env_version or em)}</td>
<td style="font-size:12px;color:var(--text-muted)">{_esc(poll_time)}</td>
<td><div style="display:flex;gap:4px;flex-wrap:wrap">
<button class="btn btn-sm" onclick="actionRestart({_js_arg(inst.instance_name)})">Restart</button>
<button class="btn btn-sm btn-warning" onclick="actionStop({_js_arg(inst.instance_name)})">Stop</button>
<button class="btn btn-sm btn-success" onclick="actionStart({_js_arg(inst.instance_name)})">Start</button>
<button class="btn btn-sm btn-ghost" onclick="viewLogs({_js_arg(inst.instance_name)})">Logs</button>
<button class="btn btn-sm btn-ghost" onclick="actionHealthCheck({_js_arg(inst.instance_name)})">Health</button>
<button class="btn btn-sm" onclick="actionUpdate({_js_arg(inst.instance_name)})">Update</button>
</div></td>
</tr>"""
        html += '</tbody></table></div></div>'

    html += """
<div class="card">
<div class="card-head"><h2>Server Actions</h2></div>
<div class="action-bar">
<button class="btn btn-sm" onclick="actionRestartAll()">Restart All</button>
<button class="btn btn-sm btn-success" onclick="actionHealthCheckAll()">Health Check All</button>
<button class="btn btn-sm" onclick="actionUpdateAll()">Update All</button>
<button class="btn btn-sm btn-danger" onclick="actionReboot()">Reboot Server</button>
</div>
<div class="section-divider">
<button class="btn btn-sm" onclick="actionBackup()">Run Backup</button>
<button class="btn btn-sm" onclick="actionBackupList()">Backup List</button>
<button class="btn btn-sm" onclick="actionPatchSelfTest()">Patch Self-Test</button>
</div>
</div>
"""

    html += """
<div class="action-panel hidden" id="action-result">
<div class="action-panel-head"><h2 id="action-title">Action</h2></div>
<div id="action-log" class="job-log-viewer"></div>
<div class="action-panel-footer">
<button class="btn btn-sm" onclick="document.getElementById('action-result').classList.add('hidden')">Close</button>
</div>
</div>
"""

    html += f"""
<script>
const serverId={server_id};
async function apiCall(path,body){{
try{{
const r=await fetch('/api/servers/'+serverId+path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body||{{}})}});
const d=await r.json();
return d;
}}catch(e){{return{{error:e.message}};}}
}}
function showActionPanel(title,result){{
const panel=document.getElementById('action-result');
panel.classList.remove('hidden');
document.getElementById('action-title').textContent=title;
const logEl=document.getElementById('action-log');
if(result.job_id){{
logEl.textContent='Job started: '+result.job_id+'\\nPolling...';
pollJob(result.job_id,title,logEl);
}}else{{
logEl.textContent=JSON.stringify(result,null,2);
// stop/start are synchronous and report real systemctl failures - a 200 in the
// browser is not the same thing as the action having worked.
if(result.status&&result.status!=='queued')showToast(title+' - '+result.status,result.status==='success'?'success':'error');
else if(result.error)showToast(title+' - '+result.error,'error');
}}
}}
async function pollJob(jobId,title,logEl){{
try{{
const r=await fetch('/api/jobs/'+jobId+'?server_id='+serverId);
const d=await r.json();
logEl.textContent=d.output||d.error||JSON.stringify(d);
if(d.status==='running'||d.status==='queued'){{
setTimeout(()=>pollJob(jobId,title,logEl),2000);
}}else{{
logEl.textContent+='\\n\\n--- Job '+d.status+' ---';
}}
showToast(title+' - '+d.status,d.status==='error'?'error':'success');
}}catch(e){{
logEl.textContent='Poll error: '+e.message;
}}
}}
async function actionRestart(inst){{
if(!confirm('Restart instance '+inst+'?'))return;
const d=await apiCall('/restart-instance',{{instance:inst}});
showActionPanel('Restart '+inst,d);
}}
async function actionStop(inst){{
if(!confirm('STOP instance '+inst+'? This disables it too, so it stays down across reboots and Restart All until you press Start.'))return;
const d=await apiCall('/stop-instance',{{instance:inst}});
showActionPanel('Stop '+inst,d);
}}
async function actionStart(inst){{
const d=await apiCall('/start-instance',{{instance:inst}});
showActionPanel('Start '+inst,d);
}}
async function viewLogs(inst){{
const panel=document.getElementById('action-result');
panel.classList.remove('hidden');
document.getElementById('action-title').textContent='Logs: '+inst;
const logEl=document.getElementById('action-log');
logEl.textContent='Loading...';
try{{
const r=await fetch('/api/servers/'+serverId+'/logs/'+inst);
const d=await r.json();
if(d.logs){{logEl.textContent=d.logs.join('\\n');}}
else{{logEl.textContent=JSON.stringify(d);}}
}}catch(e){{logEl.textContent='Error: '+e.message;}}
}}
async function actionHealthCheck(inst){{
const d=await apiCall('/health-check',{{instance:inst,scope:'instance'}});
showActionPanel('Health Check '+inst,d);
}}
async function actionUpdate(inst){{
if(!confirm('Update instance '+inst+' to latest code? This will restart it.'))return;
const d=await apiCall('/update',{{instance:inst,scope:'instance'}});
showActionPanel('Update '+inst,d);
}}
async function actionRestartAll(){{
if(!confirm('Restart ALL instances on this server?'))return;
const d=await apiCall('/restart-all');
showActionPanel('Restart All',d);
}}
async function actionHealthCheckAll(){{
const d=await apiCall('/health-check',{{scope:'all'}});
showActionPanel('Health Check All',d);
}}
async function actionUpdateAll(){{
if(!confirm('Update ALL instances on this server to latest code? This will restart each one.'))return;
const d=await apiCall('/update',{{scope:'all'}});
showActionPanel('Update All',d);
}}
async function actionReboot(){{
if(!confirm('REBOOT the entire server? This will take all instances offline.'))return;
if(!confirm('Are you sure? A reboot will restart the entire operating system.'))return;
const d=await apiCall('/reboot-server');
showActionPanel('Reboot Server',d);
}}
async function actionBackup(){{
if(!confirm('Run backup on this server via SSH?'))return;
showActionPanel('Backup',{{job_id:'pending'}});
const r=await fetch('/provision/server/'+serverId+'/run-backup',{{method:'POST'}});
const d=await r.json();
if(d.job_id)pollProvJob(d.job_id,showActionPanel);
}}
async function actionBackupList(){{
showActionPanel('Backup List',{{job_id:'pending'}});
const r=await fetch('/provision/server/'+serverId+'/backup-list',{{method:'POST'}});
const d=await r.json();
if(d.job_id)pollProvJob(d.job_id,showActionPanel);
}}
async function actionPatchSelfTest(){{
if(!confirm('Run oa-patch-known-issues.sh --self-test on this server?'))return;
showActionPanel('Patch Self-Test',{{job_id:'pending'}});
const r=await fetch('/provision/server/'+serverId+'/run-patch-self-test',{{method:'POST'}});
const d=await r.json();
if(d.job_id)pollProvJob(d.job_id,showActionPanel);
}}
async function pollProvJob(jobId,showFn){{
try{{
const r=await fetch('/provision/jobs/'+jobId);
const d=await r.json();
showFn(d.job_type||'Job',d);
if(d.status==='running'||d.status==='queued')setTimeout(()=>pollProvJob(jobId,showFn),2000);
}}catch(e){{showFn('Error',{{error:e.message}});}}
}}
</script>
"""
    html += BASE_TEMPLATE_END
    return HTMLResponse(content=html)


@router.get("/{server_id}/edit", response_class=HTMLResponse)
async def edit_server_form(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return HTMLResponse(content="Server not found", status_code=404)

    html = BASE_TEMPLATE_START
    html += f"""
<div class="card">
<div class="card-head"><h2>Edit Server: {_esc(server.name)}</h2></div>
<div style="padding:20px">
<form method="POST" action="/servers/{server.id}/edit">
<label class="reset-field-label">Name</label>
<input class="reset-input" type="text" name="name" value="{_esc(server.name)}" required>
<label class="reset-field-label">Admin API URL</label>
<input class="reset-input" type="text" name="base_url" value="{_esc(server.base_url)}" required>
<label class="reset-field-label">Admin Username</label>
<input class="reset-input" type="text" name="admin_username" value="{_esc(server.admin_username)}" required>
<label class="reset-field-label">Admin Password <span style="color:var(--text-muted)">(leave blank to keep current)</span></label>
<input class="reset-input" type="password" name="admin_password" placeholder="Leave blank to keep current">
<hr style="border-color:var(--border);margin:16px 0">
<label class="reset-field-label">SSH Host</label>
<input class="reset-input" type="text" name="ssh_host" value="{_esc(server.ssh_host)}">
<label class="reset-field-label">SSH Port</label>
<input class="reset-input" type="number" name="ssh_port" value="{server.ssh_port}">
<label class="reset-field-label">SSH User</label>
<input class="reset-input" type="text" name="ssh_user" value="{_esc(server.ssh_user)}">
<label class="reset-field-label">SSH Private Key <span style="color:var(--text-muted)">(leave blank to keep current)</span></label>
<textarea name="ssh_key" placeholder="Leave blank to keep current" class="mono" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg-elevated);color:var(--text-primary);font-size:12px;min-height:60px;resize:vertical"></textarea>
<label class="reset-field-label">SSH Host Key <span style="color:var(--text-muted)">(leave blank to keep current)</span></label>
<textarea name="ssh_host_key" placeholder="Leave blank to keep current" class="mono" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg-elevated);color:var(--text-primary);font-size:12px;min-height:60px;resize:vertical"></textarea>
<label class="reset-field-label">Notes</label>
<textarea name="notes" class="reset-input">{_esc(server.notes)}</textarea>
<div style="display:flex;gap:10px;justify-content:flex-end">
<a href="/servers/{server.id}" class="btn">Cancel</a>
<button type="submit" class="btn btn-accent">Save Changes</button>
</div>
</form>
</div>
</div>"""
    html += BASE_TEMPLATE_END
    return HTMLResponse(content=html)


@router.post("/{server_id}/edit")
async def edit_server_submit(
    request: Request,
    server_id: int,
    name: str = Form(...),
    base_url: str = Form(...),
    admin_username: str = Form(...),
    admin_password: str = Form(""),
    ssh_host: str = Form(""),
    ssh_port: int = Form(22),
    ssh_user: str = Form(""),
    ssh_key: str = Form(""),
    ssh_host_key: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return RedirectResponse(url="/servers", status_code=302)

    username = request.session.get("username", "unknown")

    server.name = name
    server.base_url = base_url.rstrip("/")
    server.admin_username = admin_username
    if admin_password.strip():
        server.admin_password_encrypted = encrypt_value(admin_password)
    server.ssh_host = ssh_host or None
    server.ssh_port = ssh_port
    server.ssh_user = ssh_user or None
    if ssh_key.strip():
        server.ssh_key_encrypted = encrypt_value(ssh_key.strip())
    if ssh_host_key.strip():
        server.ssh_host_key = ssh_host_key.strip()
    server.notes = notes or None
    await db.commit()

    await write_audit_log(db, actor=username, action="edit_server", server_id=server.id, detail={"name": name})
    await db.commit()

    return RedirectResponse(url=f"/servers/{server_id}", status_code=302)
