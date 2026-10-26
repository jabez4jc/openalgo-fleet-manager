"""System card on the server page: live telemetry relayed from the server's
/api/telemetry/stream, laid out like the System card of the admin dashboard.

TELEMETRY_CARD goes near the top of the page; TELEMETRY_JS needs serverId and
getJson, so it runs inside the tools script at the end of the page.
"""

TELEMETRY_CARD = """<style>
.tele-head-sub{font-size:12px;color:var(--text-muted)}
.tele-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;padding:16px 20px}
.tele-label{color:var(--text-muted);font-size:11px;text-transform:uppercase;letter-spacing:.03em;margin-bottom:5px}
.tele-value{font-weight:650;font-size:14px;font-variant-numeric:tabular-nums;margin-bottom:6px}
.tele-sub{font-size:12px;color:var(--text-muted)}
.tele-meter{height:4px;border-radius:2px;background:var(--border);overflow:hidden;margin-bottom:4px}
.tele-meter>div{height:100%;border-radius:2px;background:var(--success);transition:width .4s ease}
.tele-meter>div.warn{background:var(--warning)}
.tele-meter>div.crit{background:var(--danger)}
.tele-cores{display:grid;grid-template-columns:repeat(auto-fill,minmax(36px,1fr));gap:6px;padding:0 20px 14px}
.tele-wrap{overflow-x:auto;padding:0 20px 16px}
.tele-table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}
.tele-table th{text-align:left;color:var(--text-muted);font-weight:500;font-size:11px;text-transform:uppercase;padding:6px 8px;border-bottom:1px solid var(--border)}
.tele-table td{padding:5px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.tele-table .num{text-align:right}
.tele-table td.warn{color:var(--warning)}
.tele-table td.crit{color:var(--danger)}
</style>
<div class="card">
<div class="card-head"><h2>System</h2><span class="tele-head-sub" id="tele-status">Connecting...</span></div>
<div id="tele-body"><div class="empty-state">Loading telemetry...</div></div>
</div>
"""

TELEMETRY_JS = r"""
function teleEsc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}
function teleSize(n){if(n==null)return 'N/A';const u=['B','KB','MB','GB','TB'];let i=0;while(n>=1024&&i<4){n/=1024;i++;}return n.toFixed(i?1:0)+' '+u[i];}
function teleRate(n){return n==null?'N/A':teleSize(n)+'/s';}
function telePct(p){return p==null?'N/A':p.toFixed(1)+'%';}
function teleUptime(s){if(s==null)return 'N/A';const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return (d?d+'d ':'')+h+'h '+m+'m';}
function teleClass(p){return p==null?'':p>=90?'crit':p>=75?'warn':'';}
function teleMeter(p){return '<div class="tele-meter"><div class="'+teleClass(p)+'" style="width:'+Math.min(p||0,100)+'%"></div></div>';}
function teleStat(label,value,pct,sub){return '<div><div class="tele-label">'+label+'</div><div class="tele-value">'+value+'</div>'+(pct===undefined?'':teleMeter(pct))+(sub?'<div class="tele-sub">'+sub+'</div>':'')+'</div>';}
function renderTelemetry(t,mode){
const c=t.cpu||{},m=t.memory||{},n=t.network||{},p=t.processes||{},dk=t.disk||{};
const sum=(a,k)=>(a||[]).reduce((s,x)=>s+(x[k]||0),0);
const tcp=n.tcp||{};
const mounts=(dk.mounts||[]).map(d=>teleStat('Disk '+teleEsc(d.mount),teleSize(d.used)+' / '+teleSize(d.total)+' ('+telePct(d.percent)+')',d.percent,'inodes '+telePct(d.inodes_percent))).join('');
const cores=(c.per_core||[]).map((v,i)=>'<div title="CPU '+i+': '+telePct(v)+'">'+teleMeter(v)+'</div>').join('');
const rows=(p.top||[]).map(r=>'<tr title="'+teleEsc(r.cmdline)+'"><td>'+r.pid+'</td><td>'+teleEsc(r.name)+'</td><td>'+teleEsc(r.unit||'')+'</td><td>'+teleEsc(r.user)+'</td><td class="num '+teleClass(r.cpu_percent)+'">'+(r.cpu_percent==null?'...':r.cpu_percent.toFixed(1))+'</td><td class="num">'+teleSize(r.rss)+'</td><td class="num">'+telePct(r.mem_percent)+'</td><td class="num">'+r.threads+'</td></tr>').join('');
document.getElementById('tele-body').innerHTML='<div class="tele-grid">'
+teleStat('CPU ('+c.cores+' cores)',telePct(c.percent),c.percent,'iowait '+telePct(c.iowait)+' · steal '+telePct(c.steal))
+teleStat('Load Avg',(c.load||[]).join(' / ')||'N/A')
+teleStat('RAM Used',teleSize(m.used)+' / '+teleSize(m.total)+' ('+telePct(m.percent)+')',m.percent,'cache '+teleSize(m.cached))
+teleStat('Swap Used',teleSize(m.swap_used)+' / '+teleSize(m.swap_total),m.swap_percent)
+teleStat('Network','↓ '+teleRate(sum(n.interfaces,'rx_bps'))+' · ↑ '+teleRate(sum(n.interfaces,'tx_bps')),undefined,'TCP in use '+(tcp.inuse??'N/A')+' · time-wait '+(tcp.tw??'N/A'))
+teleStat('Disk I/O','R '+teleRate(sum(dk.io,'read_bps'))+' · W '+teleRate(sum(dk.io,'write_bps')))
+teleStat('Processes',p.total??'N/A',undefined,(p.running??0)+' running · '+(p.zombie??0)+' zombie · '+(p.threads??0)+' threads')
+mounts+'</div>'+(cores?'<div class="tele-cores">'+cores+'</div>':'')
+'<div class="tele-wrap"><table class="tele-table"><thead><tr><th>PID</th><th>Process</th><th>Service</th><th>User</th><th class="num">CPU%</th><th class="num">RSS</th><th class="num">Mem%</th><th class="num">Thr</th></tr></thead><tbody>'+rows+'</tbody></table></div>';
document.getElementById('tele-status').textContent='● '+mode+' · up '+teleUptime(t.uptime_seconds);
}
function teleError(msg){
document.getElementById('tele-status').textContent='Unavailable';
document.getElementById('tele-body').innerHTML='<div class="empty-state">Telemetry unavailable: '+teleEsc(msg)+'</div>';
}
// Live stream first; if it never delivers, fall back to a snapshot every 15 s.
// Nothing runs while the tab is hidden: the server samples only for an open stream.
let teleSrc=null,teleLive=false,telePolling=null;
async function pollTelemetry(){
const t=await getJson('/telemetry');
if(t.error)teleError(t.detail||t.error);else renderTelemetry(t,'Updated '+new Date().toLocaleTimeString()+' · every 15s');
}
function startPolling(){if(!telePolling){pollTelemetry();telePolling=setInterval(pollTelemetry,15000);}}
function stopTelemetry(){
if(teleSrc){teleSrc.close();teleSrc=null;}
clearInterval(telePolling);telePolling=null;teleLive=false;
document.getElementById('tele-status').textContent='Paused while the tab is hidden';
}
function startTelemetry(){
if(typeof EventSource==='undefined'){startPolling();return;}
const src=teleSrc=new EventSource('/api/servers/'+serverId+'/telemetry/stream');
src.onmessage=e=>{teleLive=true;const t=JSON.parse(e.data);renderTelemetry(t,'Live · every '+(t.interval||'?')+'s');};
src.addEventListener('error',e=>{if(!teleLive||e.data){src.close();teleSrc=null;startPolling();}});
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopTelemetry();else if(!teleSrc&&!telePolling)startTelemetry();});
if(!document.hidden)startTelemetry();
"""
