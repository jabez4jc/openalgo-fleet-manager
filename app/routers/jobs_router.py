from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import Server, ProvisioningJob
from app.encryption import decrypt_value
from app.services.admin_api import AdminAPISession
from app.routers.dashboard_router import BASE_TEMPLATE_START, BASE_TEMPLATE_END

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs/{job_id}")
async def get_job_status(request: Request, job_id: str, server_id: int = Query(None), db: AsyncSession = Depends(get_db)):
    local_job = None
    if server_id and job_id.isdigit():
        result = await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == int(job_id)))
        local_job = result.scalar_one_or_none()

    if local_job:
        return JSONResponse({
            "id": str(local_job.id),
            "job_type": local_job.job_type,
            "status": local_job.status,
            "output": local_job.log_text or "",
            "exit_code": None,
            "error": None,
            "started_at": local_job.started_at.isoformat() if local_job.started_at else None,
            "finished_at": local_job.finished_at.isoformat() if local_job.finished_at else None,
        })

    if not server_id:
        return JSONResponse({"error": "server_id query param required for remote jobs"}, status_code=400)

    result = await db.execute(select(Server).where(Server.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        return JSONResponse({"error": "Server not found"}, status_code=404)

    api = AdminAPISession(
        base_url=server.base_url,
        username=server.admin_username or "",
        password=decrypt_value(server.admin_password_encrypted or ""),
    )
    result = await api.get_job_status(job_id)
    return JSONResponse(result)


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProvisioningJob).order_by(desc(ProvisioningJob.id)).limit(100)
    )
    jobs = result.scalars().all()

    html = BASE_TEMPLATE_START
    html += """
<div class="card">
<div class="card-head"><h2>Jobs History</h2></div>
"""
    if not jobs:
        html += '<div class="empty-state">No provisioning jobs yet.</div>'
    else:
        html += '<div class="table-wrap"><table><thead><tr><th>ID</th><th>Type</th><th>Server</th><th>Status</th><th>Started</th><th>Finished</th><th>Triggered By</th></tr></thead><tbody>'
        for job in jobs:
            server_name = job.server.name if job.server else "\u2014"
            status_badge = ""
            if job.status == "success":
                status_badge = '<span class="badge badge-healthy">success</span>'
            elif job.status == "failed":
                status_badge = '<span class="badge badge-critical">failed</span>'
            elif job.status == "running":
                status_badge = '<span class="badge badge-warning">running</span>'
            else:
                status_badge = f'<span class="badge badge-unknown">{job.status}</span>'

            em = "\u2014"
            str_started = job.started_at.strftime('%Y-%m-%d %H:%M') if job.started_at else em
            str_finished = job.finished_at.strftime('%Y-%m-%d %H:%M') if job.finished_at else em
            triggered = job.triggered_by or em
            html += f"""<tr>
<td><a href="/jobs/{job.id}" style="color:var(--accent);text-decoration:none;font-weight:600">{job.id}</a></td>
<td style="font-weight:500">{job.job_type}</td>
<td style="color:var(--text-secondary)">{server_name}</td>
<td>{status_badge}</td>
<td style="font-size:12px;color:var(--text-secondary)">{str_started}</td>
<td style="font-size:12px;color:var(--text-secondary)">{str_finished}</td>
<td style="color:var(--text-secondary)">{triggered}</td>
</tr>"""
        html += '</tbody></table></div>'
    html += '</div>' + BASE_TEMPLATE_END
    return HTMLResponse(content=html)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProvisioningJob).where(ProvisioningJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        return HTMLResponse(content=BASE_TEMPLATE_START + '<div class="card"><div class="empty-state">Job not found.</div></div>' + BASE_TEMPLATE_END)

    em_job = "\u2014"
    started_str = job.started_at.strftime('%Y-%m-%d %H:%M:%S') if job.started_at else em_job
    finished_str = job.finished_at.strftime('%Y-%m-%d %H:%M:%S') if job.finished_at else em_job
    triggered_by = job.triggered_by or em_job
    server_name = job.server.name if job.server else em_job

    html = BASE_TEMPLATE_START
    html += f"""
<div class="card">
<div class="card-head"><h2>Job #{job.id}: {job.job_type}</h2></div>
<div class="kpi-row">
<div class="kpi"><div class="kpi-label">Status</div><div class="kpi-value">{job.status}</div></div>
<div class="kpi"><div class="kpi-label">Server</div><div class="kpi-value" style="font-size:16px;font-weight:600">{server_name}</div></div>
<div class="kpi"><div class="kpi-label">Triggered By</div><div class="kpi-value" style="font-size:16px;font-weight:600">{triggered_by}</div></div>
</div>
<div class="card-head"><h2>Log Output</h2></div>
<div class="job-log-viewer">{job.log_text or '(no output)'}</div>
<div style="padding:12px 20px 16px;font-size:12px;color:var(--text-muted)">
Started: {started_str} &middot;
Finished: {finished_str}
</div>
</div>
"""
    html += BASE_TEMPLATE_END
    return HTMLResponse(content=html)
