import json
import html as _html
import logging
import secrets
from datetime import datetime, timezone
from threading import Thread

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Server, Instance, ProvisioningJob
from app.encryption import decrypt_value, encrypt_value
from app.config import SCRIPTS_REPO_PATH, SCRIPTS_REPO_URL, SCRIPTS_REF
from app.services.ssh_client import SSHClient
from app.services.audit import write_audit_log
from app.routers.dashboard_router import BASE_TEMPLATE_START, BASE_TEMPLATE_END

logger = logging.getLogger("fleetmgr.provisioning")

router = APIRouter(prefix="/provision", tags=["provisioning"])

VALID_BROKERS = [
    "fivepaisa", "fivepaisaxts", "aliceblue", "angel", "arrow", "compositedge",
    "dhan", "dhan_sandbox", "definedge", "deltaexchange", "firstock", "flattrade",
    "fyers", "groww", "ibulls", "iifl", "iiflcapital", "indmoney", "jainamxts",
    "kotak", "motilal", "mstock", "nubra", "paytm", "pocketful", "rmoney",
    "samco", "shoonya", "tradejini", "upstox", "wisdom", "zebu", "zerodha",
]
XTS_BROKERS = ["fivepaisaxts", "compositedge", "ibulls", "iifl", "jainamxts", "rmoney", "wisdom"]


def _esc(value: object) -> str:
    return _html.escape(str(value or ""))


@router.get("", response_class=HTMLResponse)
async def provisioning_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).order_by(Server.name))
    servers = result.scalars().all()
    servers_with_ssh = [s for s in servers if s.ssh_host and s.ssh_key_encrypted]

    html = BASE_TEMPLATE_START
    html += """
<div class="page-intro">
<div><div class="eyebrow">Infrastructure</div><h1>Provision</h1><p>Deploy a new OpenAlgo instance or onboard a server with guided checks.</p></div>
</div>
<div class="card">
<div class="card-head"><div><h2>Provisioning wizard</h2><div class="card-subtitle">Remote installation and configuration</div></div></div>
    <div style="padding:20px">
<form id="provision-form" onsubmit="submitProvision(event)">
<div class="provision-grid">
<div>
<label class="reset-field-label">Provisioning Type</label>
<select name="job_type" id="prov-type" onchange="toggleFormFields()" required class="reset-input">
<option value="">Select type...</option>
<option value="new_instance">Add Instance to Existing Server</option>
<option value="new_server">Onboard New Server</option>
</select>
</div>
<div id="instance-fields">
"""
    if servers_with_ssh:
        html += '<label class="reset-field-label">Target Server</label>'
        html += '<select name="server_id" id="prov-server" class="reset-input">'
        html += '<option value="">Select server...</option>'
        for srv in servers_with_ssh:
            html += f'<option value="{srv.id}">{_esc(srv.name)} ({_esc(srv.ssh_host)})</option>'
        html += '</select>'
    else:
        html += '<div style="color:var(--text-muted);font-size:13px;margin-bottom:14px">No servers with SSH configured yet. Use "Onboard New Server" below.</div>'
        html += '<input type="hidden" name="server_id" value="0">'
    html += """
<label class="reset-field-label">Instance Domain</label>
<input class="reset-input" type="text" name="domain" id="prov-domain" placeholder="trade1.example.com">
<label class="reset-field-label">Broker</label>
<select name="broker" id="prov-broker" onchange="toggleXtsFields()" class="reset-input">
<option value="">Select broker...</option>
"""
    for b in VALID_BROKERS:
        html += f'<option value="{_esc(b)}">{_esc(b)}</option>'
    html += """
</select>
<label class="reset-field-label">API Key</label>
<input class="reset-input" type="text" name="api_key" id="prov-api-key">
<label class="reset-field-label">API Secret</label>
<input class="reset-input" type="password" name="api_secret" id="prov-api-secret">
<div id="xts-fields" style="display:none">
<label class="reset-field-label">Market Key <span style="color:var(--text-muted)">(XTS only)</span></label>
<input class="reset-input" type="text" name="market_key" id="prov-market-key">
<label class="reset-field-label">Market Secret <span style="color:var(--text-muted)">(XTS only)</span></label>
<input class="reset-input" type="password" name="market_secret" id="prov-market-secret">
</div>
</div>
<div id="server-fields" style="display:none">
<h3 style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--text-primary)">New Server SSH Access</h3>
<label class="reset-field-label">Server Name</label>
<input class="reset-input" type="text" name="server_name" id="prov-server-name" placeholder="prod-us-east-1">
<label class="reset-field-label">SSH Host</label>
<input class="reset-input" type="text" name="ssh_host" id="prov-ssh-host" placeholder="192.168.1.100">
<label class="reset-field-label">SSH Port</label>
<input class="reset-input" type="number" name="ssh_port" id="prov-ssh-port" value="22">
<label class="reset-field-label">SSH User</label>
<input class="reset-input" type="text" name="ssh_user" id="prov-ssh-user" value="ubuntu">
<label class="reset-field-label">SSH Private Key</label>
<textarea name="ssh_key" id="prov-ssh-key" rows="5" placeholder="-----BEGIN RSA PRIVATE KEY-----&#10;..." class="mono" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg-elevated);color:var(--text-primary);font-size:12px;resize:vertical"></textarea>
<label class="reset-field-label">Host Public Key <span style="color:var(--text-muted)">(optional, pin for security)</span></label>
<input type="text" name="host_key" id="prov-host-key" placeholder="ssh-ed25519 AAAAC3... or leave blank to auto-accept" class="reset-input mono">
</div>
</div>
<div style="margin-top:4px;padding:12px;background:var(--danger-soft);border:1px solid rgba(239,68,68,.3);border-radius:var(--radius-sm);font-size:13px;color:var(--danger)">
<strong>Warning:</strong> This runs root-level scripts on the remote server. Broker API secrets will be written to a temp file on the remote machine briefly. Confirm before proceeding.
</div>
<div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px">
<button type="submit" class="btn btn-accent">Provision</button>
</div>
</form>
<div id="prov-result" style="margin-top:16px;display:none">
<div class="action-panel-head"><h2 id="prov-result-title">Provisioning...</h2></div>
<div id="prov-log" class="job-log-viewer"></div>
</div>
</div>
</div>
<script>
function toggleFormFields(){
const type=document.getElementById('prov-type').value;
document.getElementById('instance-fields').style.display=type==='new_instance'||type==='new_server'?'block':'none';
document.getElementById('server-fields').style.display=type==='new_server'?'block':'none';
}
function toggleXtsFields(){
const broker=document.getElementById('prov-broker').value;
const xtsBrokers=""" + json.dumps(XTS_BROKERS) + """;
document.getElementById('xts-fields').style.display=xtsBrokers.includes(broker)?'block':'none';
}
async function submitProvision(e){
e.preventDefault();
const type=document.getElementById('prov-type').value;
let msg='';
if(type==='new_instance')msg='Provision a new instance on an existing server? This runs multi-install.sh remotely.';
else if(type==='new_server')msg='Onboard a new server? This will install dependencies, set up the first instance, and configure the admin API.';
else return alert('Select a provisioning type');
if(!confirm(msg))return;
const form=e.target;
const fd=new FormData(form);
const data=Object.fromEntries(fd.entries());
const resultEl=document.getElementById('prov-result');
const logEl=document.getElementById('prov-log');
const titleEl=document.getElementById('prov-result-title');
resultEl.style.display='block';
titleEl.textContent='Starting...';
logEl.textContent='Submitting...';
try{
const r=await fetch('/provision/submit',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify(data)
});
const d=await r.json();
if(d.error){logEl.textContent='Error: '+d.error;titleEl.textContent='Failed';return;}
titleEl.textContent='Job #'+d.job_id+' - '+d.status;
pollProvJob(d.job_id,logEl,titleEl);
}catch(e){logEl.textContent='Error: '+e.message;titleEl.textContent='Failed';}
}
async function pollProvJob(jobId,logEl,titleEl){
try{
const r=await fetch('/provision/jobs/'+jobId);
const d=await r.json();
logEl.textContent=d.log_text||d.status||'';
titleEl.textContent='Job #'+jobId+' - '+d.status;
if(d.status==='running'||d.status==='queued')setTimeout(()=>pollProvJob(jobId,logEl,titleEl),2000);
}catch(e){logEl.textContent='Poll error: '+e.message;}
}
</script>
"""
    html += BASE_TEMPLATE_END
    return HTMLResponse(content=html)


@router.post("/submit")
async def submit_provision(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    job_type = body.get("job_type", "")
    domain = body.get("domain", "")
    broker = body.get("broker", "")
    api_key = body.get("api_key", "")
    api_secret = body.get("api_secret", "")
    market_key = body.get("market_key", "")
    market_secret = body.get("market_secret", "")

    if job_type not in ("new_instance", "new_server"):
        return JSONResponse({"error": "Invalid job_type"}, status_code=400)

    if not domain or not broker:
        return JSONResponse({"error": "Domain and broker are required"}, status_code=400)
    if broker not in VALID_BROKERS:
        return JSONResponse({"error": f"Invalid broker: {broker}"}, status_code=400)

    username = request.session.get("username", "unknown")
    admin_pw = secrets.token_urlsafe(16)

    if job_type == "new_server":
        server_name = body.get("server_name", "").strip()
        ssh_host = body.get("ssh_host", "").strip()
        try:
            ssh_port = int(body.get("ssh_port", 22))
        except (TypeError, ValueError):
            return JSONResponse({"error": "SSH port must be a number"}, status_code=400)
        ssh_user = body.get("ssh_user", "").strip()
        ssh_key_pem = body.get("ssh_key", "").strip()
        host_key = body.get("host_key", "").strip() or None

        if not server_name or not ssh_host or not ssh_user or not ssh_key_pem:
            return JSONResponse({"error": "Server name, SSH host, user, and private key are required"}, status_code=400)

        base_url = f"https://{domain}:8888"

        server = Server(
            name=server_name,
            base_url=base_url,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            ssh_key_encrypted=encrypt_value(ssh_key_pem),
            ssh_host_key=host_key,
        )
        db.add(server)
        await db.flush()
        await db.refresh(server)

        job = ProvisioningJob(
            server_id=server.id,
            job_type=job_type,
            params_json=json.dumps({"domain": domain, "broker": broker, "server_name": server_name}),
            status="queued",
            triggered_by=username,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        instance_name = domain.split(".")[0] if "." in domain else domain

        await write_audit_log(db, actor=username, action="provision_new_server", server_id=server.id, instance_name=domain,
                              detail={"server_name": server_name, "broker": broker})
        await db.commit()

        _run_new_server(server, job.id, admin_pw, domain, broker, api_key, api_secret, market_key, market_secret, instance_name)
        return JSONResponse({"job_id": str(job.id), "status": "queued", "server_id": server.id})

    try:
        server_id = int(body.get("server_id", 0))
    except (TypeError, ValueError):
        return JSONResponse({"error": "A valid target server is required"}, status_code=400)
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)
    if not server.ssh_host or not server.ssh_key_encrypted:
        return JSONResponse({"error": "Server has no SSH credentials"}, status_code=400)

    job = ProvisioningJob(
        server_id=server_id,
        job_type=job_type,
        params_json=json.dumps({"domain": domain, "broker": broker}),
        status="queued",
        triggered_by=username,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await write_audit_log(db, actor=username, action="provision_new_instance", server_id=server_id, instance_name=domain,
                          detail={"broker": broker})
    await db.commit()

    _run_new_instance(server, job.id, admin_pw, domain, broker, api_key, api_secret, market_key, market_secret)
    return JSONResponse({"job_id": str(job.id), "status": "queued"})


def _make_config_content(domain: str, broker: str, api_key: str, api_secret: str, market_key: str, market_secret: str) -> str:
    lines = [
        "CHANGE_TZ=y",
        "BRANCH=main",
        "INSTANCES=1",
        f"INSTANCE_1_DOMAIN={domain}",
        f"INSTANCE_1_BROKER={broker}",
        f"INSTANCE_1_API_KEY={api_key}",
        f"INSTANCE_1_API_SECRET={api_secret}",
    ]
    if broker in XTS_BROKERS:
        lines.append(f"INSTANCE_1_MARKET_KEY={market_key}")
        lines.append(f"INSTANCE_1_MARKET_SECRET={market_secret}")
    return "\n".join(lines) + "\n"


def _run_new_instance(server: Server, job_id: int, admin_pw: str, domain: str, broker: str,
                      api_key: str, api_secret: str, market_key: str, market_secret: str):
    from app.config import DATABASE_URL

    instance_name = domain.split(".")[0] if "." in domain else domain
    config_content = _make_config_content(domain, broker, api_key, api_secret, market_key, market_secret)
    remote_config_path = f"/tmp/instance-{job_id}.env"
    multi_install_cmd = f"sudo bash {SCRIPTS_REPO_PATH}/multi-install.sh --config {remote_config_path}"

    def _run():
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        engine = create_async_engine(DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _inner():
            async with factory() as db:
                j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
                if j:
                    j.status = "running"; j.started_at = datetime.now(timezone.utc)
                    j.log_text = "Connecting via SSH..."; await db.commit()

            ssh = None
            try:
                ssh = SSHClient(
                    host=server.ssh_host, port=server.ssh_port, username=server.ssh_user,
                    private_key_pem=decrypt_value(server.ssh_key_encrypted), host_key=server.ssh_host_key,
                )
                ssh.connect()
                await _update_job(job_id, factory, "Writing config file on remote server...")

                ssh.write_temp_file(config_content, remote_config_path)
                await _update_job(job_id, factory, "Syncing scripts repo and running multi-install.sh...")

                exit_code, output = ssh.git_sync_then_invoke(multi_install_cmd, timeout=1800)
                ssh.delete_temp_file(remote_config_path)

                async with factory() as db:
                    j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
                    if j:
                        if exit_code == 0:
                            j.status = "success"; j.log_text = output; j.finished_at = datetime.now(timezone.utc)
                            inst = Instance(server_id=server.id, instance_name=instance_name, domain=domain,
                                           broker=broker, status="provisioned", health_status="pending")
                            db.add(inst)
                        else:
                            j.status = "failed"; j.log_text = output; j.finished_at = datetime.now(timezone.utc)
                        await db.commit()

            except Exception as e:
                async with factory() as db:
                    j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
                    if j:
                        j.status = "failed"; j.log_text = f"SSH error: {e}"; j.finished_at = datetime.now(timezone.utc)
                        await db.commit()
            finally:
                if ssh:
                    try:
                        ssh.close()
                    except Exception:
                        pass

        asyncio.run(_inner())

    Thread(target=_run, daemon=True).start()


def _run_new_server(server: Server, job_id: int, admin_pw: str, domain: str, broker: str,
                    api_key: str, api_secret: str, market_key: str, market_secret: str, instance_name: str):
    from app.config import DATABASE_URL

    config_content = _make_config_content(domain, broker, api_key, api_secret, market_key, market_secret)
    remote_config_path = f"/tmp/bootstrap-{job_id}.env"
    multi_install_cmd = f"sudo bash {SCRIPTS_REPO_PATH}/multi-install.sh --config {remote_config_path}"

    def _run():
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        engine = create_async_engine(DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _inner():
            async with factory() as db:
                j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
                if j:
                    j.status = "running"; j.started_at = datetime.now(timezone.utc)
                    j.log_text = "Connecting via SSH to new server..."; await db.commit()

            ssh = None
            try:
                ssh = SSHClient(
                    host=server.ssh_host, port=server.ssh_port, username=server.ssh_user,
                    private_key_pem=decrypt_value(server.ssh_key_encrypted), host_key=server.ssh_host_key,
                )
                ssh.connect()
                await _update_job(job_id, factory, "Writing broker config file...")
                ssh.write_temp_file(config_content, remote_config_path)

                await _update_job(job_id, factory, "Syncing scripts repo...")
                sync_cmd = (
                    f"if [ -d {SCRIPTS_REPO_PATH}/.git ]; then "
                    f"sudo git -C {SCRIPTS_REPO_PATH} fetch --quiet origin && "
                    f"sudo git -C {SCRIPTS_REPO_PATH} reset --hard 'origin/{SCRIPTS_REF}'; "
                    f"else sudo git clone --quiet -b '{SCRIPTS_REF}' {SCRIPTS_REPO_URL} {SCRIPTS_REPO_PATH}; "
                    f"fi"
                )
                exit_code, output = ssh._run(sync_cmd, timeout=30)
                if exit_code != 0:
                    raise RuntimeError(f"git-sync failed: {output[:500]}")

                await _update_job(job_id, factory, "Running multi-install.sh (install deps + first instance)...")
                exit_code, output = ssh._run(f"sudo bash {SCRIPTS_REPO_PATH}/multi-install.sh --config {remote_config_path}", timeout=1800)
                ssh.delete_temp_file(remote_config_path)

                if exit_code != 0:
                    raise RuntimeError(f"multi-install.sh failed (exit {exit_code}):\n{output[:2000]}")

                await _update_job(job_id, factory, "Setting admin password via --set-admin-password...")
                admin_username = "fleetmgr"
                pw_exit, pw_output = ssh.set_admin_password(admin_username, admin_pw)
                if pw_exit != 0:
                    logger.warning("set_admin_password on %s: exit %d, %s", server.ssh_host, pw_exit, pw_output[:200])
                    pw_output = f"(admin password may not have been set)\n{pw_output}"

                async with factory() as db:
                    srv = (await db.execute(select(Server).where(Server.id == server.id))).scalar_one_or_none()
                    j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
                    if srv:
                        srv.admin_username = admin_username
                        srv.admin_password_encrypted = encrypt_value(admin_pw)
                    if j:
                        j.status = "success"; j.log_text = output + "\n\n" + pw_output; j.finished_at = datetime.now(timezone.utc)
                    inst = Instance(server_id=server.id, instance_name=instance_name, domain=domain,
                                   broker=broker, status="provisioned", health_status="pending")
                    db.add(inst)
                    await db.commit()

            except Exception as e:
                async with factory() as db:
                    j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
                    if j:
                        j.status = "failed"; j.log_text = f"Bootstrap failed: {e}"; j.finished_at = datetime.now(timezone.utc)
                        await db.commit()
            finally:
                if ssh:
                    try:
                        ssh.close()
                    except Exception:
                        pass

        asyncio.run(_inner())

    Thread(target=_run, daemon=True).start()


async def _update_job(job_id: int, factory, text: str):
    async with factory() as db:
        j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
        if j:
            j.log_text = text
            await db.commit()


@router.get("/jobs/{job_id}")
async def get_provision_job(request: Request, job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return JSONResponse({
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "log_text": job.log_text,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "triggered_by": job.triggered_by,
    })


@router.post("/server/{server_id}/run-backup")
async def run_backup(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)
    if not server.ssh_host or not server.ssh_key_encrypted:
        return JSONResponse({"error": "Server has no SSH credentials"}, status_code=400)

    username = request.session.get("username", "unknown")
    job = ProvisioningJob(server_id=server_id, job_type="backup", status="queued", triggered_by=username)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await write_audit_log(db, actor=username, action="run_backup", server_id=server_id)
    await db.commit()

    _run_ssh_script(server, job.id, "oa-backup.sh", timeout=600)
    return JSONResponse({"job_id": str(job.id), "status": "queued"})


@router.post("/server/{server_id}/run-patch-self-test")
async def run_patch_self_test(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)
    if not server.ssh_host or not server.ssh_key_encrypted:
        return JSONResponse({"error": "Server has no SSH credentials"}, status_code=400)

    username = request.session.get("username", "unknown")
    job = ProvisioningJob(server_id=server_id, job_type="patch_self_test", status="queued", triggered_by=username)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await write_audit_log(db, actor=username, action="run_patch_self_test", server_id=server_id)
    await db.commit()

    _run_ssh_script(server, job.id, "oa-patch-known-issues.sh", args="--self-test", timeout=300)
    return JSONResponse({"job_id": str(job.id), "status": "queued"})


@router.post("/server/{server_id}/backup-list")
async def get_backup_list(request: Request, server_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)
    if not server.ssh_host or not server.ssh_key_encrypted:
        return JSONResponse({"error": "Server has no SSH credentials"}, status_code=400)

    username = request.session.get("username", "unknown")
    job = ProvisioningJob(server_id=server_id, job_type="backup_list", status="queued", triggered_by=username)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await write_audit_log(db, actor=username, action="backup_list", server_id=server_id)
    await db.commit()

    _run_ssh_script(server, job.id, "oa-backup.sh", args="list", timeout=30)
    return JSONResponse({"job_id": str(job.id), "status": "queued"})


def _run_ssh_script(server: Server, job_id: int, script: str, args: str = "", timeout: int = 300):
    from app.config import DATABASE_URL
    from app.services.ssh_client import SSHClient

    def _run():
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        engine = create_async_engine(DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _inner():
            async with factory() as db:
                j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
                if j:
                    j.status = "running"; j.started_at = datetime.now(timezone.utc)
                    j.log_text = f"Connecting via SSH to run {script}..." if not args else f"Connecting via SSH to run {script} {args}..."
                    await db.commit()

            ssh = None
            try:
                ssh = SSHClient(
                    host=server.ssh_host, port=server.ssh_port, username=server.ssh_user,
                    private_key_pem=decrypt_value(server.ssh_key_encrypted), host_key=server.ssh_host_key,
                )
                ssh.connect()
                exit_code, output = ssh.run_script(script, args=args, timeout=timeout)

                async with factory() as db:
                    j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
                    if j:
                        j.status = "success" if exit_code == 0 else "failed"
                        j.log_text = output; j.finished_at = datetime.now(timezone.utc)
                        await db.commit()

            except Exception as e:
                async with factory() as db:
                    j = (await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))).scalar_one_or_none()
                    if j:
                        j.status = "failed"; j.log_text = f"SSH error: {e}"; j.finished_at = datetime.now(timezone.utc)
                        await db.commit()
            finally:
                if ssh:
                    try:
                        ssh.close()
                    except Exception:
                        pass

        asyncio.run(_inner())

    Thread(target=_run, daemon=True).start()
