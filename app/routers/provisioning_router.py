import json
import logging
from datetime import datetime, timezone
from threading import Thread

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Server, ProvisioningJob
from app.encryption import decrypt_value
from app.config import SCRIPTS_REPO_PATH
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


def _run_provision_job(db_url: str, job_id: int, ssh_config: dict, command: str, cleanup_cmd: str | None = None):
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import select, update

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _run():
        async with factory() as db:
            result = await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))
            job = result.scalar_one_or_none()
            if not job:
                return
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            await db.commit()

            ssh = None
            try:
                ssh = SSHClient(
                    host=ssh_config["host"],
                    port=ssh_config["port"],
                    username=ssh_config["user"],
                    private_key_pem=ssh_config["key"],
                    host_key=ssh_config.get("host_key"),
                )
                ssh.connect()
                exit_code, output = ssh.git_sync_then_invoke(command, timeout=1800)

                if cleanup_cmd:
                    try:
                        ssh._run(cleanup_cmd, timeout=10)
                    except Exception:
                        pass

                job.status = "success" if exit_code == 0 else "failed"
                job.log_text = output
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()

            except Exception as e:
                job.status = "failed"
                job.log_text = f"SSH error: {e}"
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()
            finally:
                if ssh:
                    try:
                        ssh.close()
                    except Exception:
                        pass

    asyncio.run(_run())


@router.get("", response_class=HTMLResponse)
async def provisioning_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).order_by(Server.name))
    servers = result.scalars().all()
    servers_with_ssh = [s for s in servers if s.ssh_host and s.ssh_key_encrypted]

    html = BASE_TEMPLATE_START
    html += """
<div class="card">
<div class="card-head"><h2>Provisioning Wizard</h2></div>
"""
    if not servers_with_ssh:
        html += '<div class="empty-state">No servers with SSH configured.<br>Add a server with SSH credentials first from the <a href="/servers/add" style="color:var(--accent)">Servers page</a>.</div>'
    else:
        html += """
<div style="padding:20px">
<form id="provision-form" onsubmit="submitProvision(event)">
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
<div>
<label>Target Server</label>
<select name="server_id" id="prov-server" required style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--text);font-size:13px;font-family:inherit">
<option value="">Select server...</option>
"""
        for srv in servers_with_ssh:
            html += f'<option value="{srv.id}">{srv.name} ({srv.ssh_host})</option>'
        html += """
</select>
<label>Provisioning Type</label>
<select name="job_type" id="prov-type" onchange="toggleFormFields()" required style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--text);font-size:13px;font-family:inherit">
<option value="">Select type...</option>
<option value="new_instance">Add Instance to Existing Server</option>
</select>
</div>
<div id="instance-fields">
<label>Instance Domain</label>
<input type="text" name="domain" id="prov-domain" placeholder="trade1.example.com" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--text);font-size:13px;font-family:inherit">
<label>Broker</label>
<select name="broker" id="prov-broker" onchange="toggleXtsFields()" required style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--text);font-size:13px;font-family:inherit">
<option value="">Select broker...</option>
"""
        for b in VALID_BROKERS:
            html += f'<option value="{b}">{b}</option>'
        html += """
</select>
<label>API Key</label>
<input type="text" name="api_key" id="prov-api-key" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--text);font-size:13px;font-family:inherit">
<label>API Secret</label>
<input type="password" name="api_secret" id="prov-api-secret" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--text);font-size:13px;font-family:inherit">
<div id="xts-fields" style="display:none">
<label>Market Key <span style="color:var(--text-faint)">(XTS only)</span></label>
<input type="text" name="market_key" id="prov-market-key" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--text);font-size:13px;font-family:inherit">
<label>Market Secret <span style="color:var(--text-faint)">(XTS only)</span></label>
<input type="password" name="market_secret" id="prov-market-secret" style="width:100%;padding:8px 10px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--text);font-size:13px;font-family:inherit">
</div>
</div>
</div>
<div style="margin-top:4px;padding:12px;background:var(--danger-soft);border:1px solid rgba(244,88,110,.35);border-radius:var(--radius-sm);font-size:13px;color:var(--danger)">
<strong>Warning:</strong> This runs root-level scripts on the remote server. Broker API secrets will be written to a temp file on the remote machine briefly. Confirm before proceeding.
</div>
<div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px">
<button type="submit" class="btn btn-accent" onclick="return confirm('Provision this instance on the target server? This runs root-level scripts and will write broker secrets to a temp file on the remote server.')">Provision</button>
</div>
</form>
<div id="prov-result" style="margin-top:16px;display:none">
<div class="card-head"><h2 id="prov-result-title">Provisioning...</h2></div>
<div id="prov-log" class="job-log-viewer"></div>
</div>
</div>
"""
    html += """
<script>
function toggleFormFields(){
const type=document.getElementById('prov-type').value;
document.getElementById('instance-fields').style.display=type==='new_instance'?'block':'none';
}
function toggleXtsFields(){
const broker=document.getElementById('prov-broker').value;
const xtsBrokers=""" + json.dumps(XTS_BROKERS) + """;
document.getElementById('xts-fields').style.display=xtsBrokers.includes(broker)?'block':'none';
}
async function submitProvision(e){
e.preventDefault();
if(!confirm('Provision this instance on the target server? This runs root-level scripts and will write broker secrets to a temp file on the remote server.'))return;

const form=e.target;
const fd=new FormData(form);
const data=Object.fromEntries(fd.entries());

const resultEl=document.getElementById('prov-result');
const logEl=document.getElementById('prov-log');
const titleEl=document.getElementById('prov-result-title');
resultEl.style.display='block';
titleEl.textContent='Starting provisioning...';
logEl.textContent='Submitting...';

try{
const r=await fetch('/provision/submit',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify(data)
});
const d=await r.json();
if(d.error){
logEl.textContent='Error: '+d.error;
titleEl.textContent='Failed';
return;
}
titleEl.textContent='Job #'+d.job_id+' - '+d.status;
pollProvJob(d.job_id,logEl,titleEl);
}catch(e){
logEl.textContent='Error: '+e.message;
titleEl.textContent='Failed';
}
}
async function pollProvJob(jobId,logEl,titleEl){
try{
const r=await fetch('/provision/jobs/'+jobId);
const d=await r.json();
logEl.textContent=d.log_text||d.status||'';
titleEl.textContent='Job #'+jobId+' - '+d.status;
if(d.status==='running'||d.status==='queued'){
setTimeout(()=>pollProvJob(jobId,logEl,titleEl),2000);
}
}catch(e){
logEl.textContent='Poll error: '+e.message;
}
}
</script>
"""
    html += '</div>' + BASE_TEMPLATE_END
    return HTMLResponse(content=html)


@router.post("/submit")
async def submit_provision(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    server_id = int(body.get("server_id", 0))
    job_type = body.get("job_type", "")
    domain = body.get("domain", "")
    broker = body.get("broker", "")
    api_key = body.get("api_key", "")
    api_secret = body.get("api_secret", "")
    market_key = body.get("market_key", "")
    market_secret = body.get("market_secret", "")

    if job_type not in ("new_instance",):
        return JSONResponse({"error": "Invalid job_type"}, status_code=400)

    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    if not server.ssh_host or not server.ssh_key_encrypted:
        return JSONResponse({"error": "Server has no SSH credentials"}, status_code=400)

    if not domain or not broker:
        return JSONResponse({"error": "Domain and broker are required"}, status_code=400)

    if broker not in VALID_BROKERS:
        return JSONResponse({"error": f"Invalid broker: {broker}"}, status_code=400)

    username = request.session.get("username", "unknown")

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

    await write_audit_log(db, actor=username, action=f"provision_{job_type}", server_id=server_id, instance_name=domain, detail={"broker": broker})

    config_lines = [
        "CHANGE_TZ=y",
        f"BRANCH=main",
        "INSTANCES=1",
        f"INSTANCE_1_DOMAIN={domain}",
        f"INSTANCE_1_BROKER={broker}",
        f"INSTANCE_1_API_KEY={api_key}",
        f"INSTANCE_1_API_SECRET={api_secret}",
    ]
    if broker in XTS_BROKERS:
        config_lines.append(f"INSTANCE_1_MARKET_KEY={market_key}")
        config_lines.append(f"INSTANCE_1_MARKET_SECRET={market_secret}")
    config_content = "\n".join(config_lines) + "\n"

    remote_config_path = f"/tmp/instance-{job.id}.env"
    multi_install_cmd = f"sudo bash {SCRIPTS_REPO_PATH}/multi-install.sh --config {remote_config_path}"
    cleanup_cmd = f"shred -u {remote_config_path} 2>/dev/null || rm -f {remote_config_path}"

    ssh_config = {
        "host": server.ssh_host,
        "port": server.ssh_port,
        "user": server.ssh_user,
        "key": decrypt_value(server.ssh_key_encrypted),
        "host_key": server.ssh_host_key,
    }

    from app.config import DATABASE_URL

    def _run_prep_and_start():
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        engine = create_async_engine(DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with factory() as db2:
                result2 = await db2.execute(select(ProvisioningJob).where(ProvisioningJob.id == job.id))
                j = result2.scalar_one_or_none()
                if not j:
                    return
                j.status = "running"
                j.started_at = datetime.now(timezone.utc)
                j.log_text = "Connecting via SSH..."
                await db2.commit()

            ssh = None
            try:
                ssh = SSHClient(**ssh_config)
                ssh.connect()

                async with factory() as db3:
                    result3 = await db3.execute(select(ProvisioningJob).where(ProvisioningJob.id == job.id))
                    j3 = result3.scalar_one_or_none()
                    if j3:
                        j3.log_text = "Writing config file..."
                        await db3.commit()

                ssh.write_temp_file(config_content, remote_config_path)

                async with factory() as db4:
                    result4 = await db4.execute(select(ProvisioningJob).where(ProvisioningJob.id == job.id))
                    j4 = result4.scalar_one_or_none()
                    if j4:
                        j4.log_text = "Syncing scripts repo and running multi-install.sh..."
                        await db4.commit()

                exit_code, output = ssh.git_sync_then_invoke(multi_install_cmd, timeout=1800)

                try:
                    ssh._run(cleanup_cmd, timeout=10)
                except Exception:
                    pass

                async with factory() as db5:
                    result5 = await db5.execute(select(ProvisioningJob).where(ProvisioningJob.id == job.id))
                    j5 = result5.scalar_one_or_none()
                    if j5:
                        j5.status = "success" if exit_code == 0 else "failed"
                        j5.log_text = output
                        j5.finished_at = datetime.now(timezone.utc)
                        await db5.commit()

            except Exception as e:
                async with factory() as db6:
                    result6 = await db6.execute(select(ProvisioningJob).where(ProvisioningJob.id == job.id))
                    j6 = result6.scalar_one_or_none()
                    if j6:
                        j6.status = "failed"
                        j6.log_text = f"SSH error: {e}"
                        j6.finished_at = datetime.now(timezone.utc)
                        await db6.commit()
            finally:
                if ssh:
                    try:
                        ssh.close()
                    except Exception:
                        pass

        asyncio.run(_run())

    Thread(target=_run_prep_and_start, daemon=True).start()

    return JSONResponse({"job_id": str(job.id), "status": "queued"})


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
