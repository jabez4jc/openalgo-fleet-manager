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
.tele-charts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:16px 20px 4px}
@media(max-width:1100px){.tele-charts{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.tele-charts{grid-template-columns:minmax(0,1fr)}}
.tc{position:relative;border:1px solid var(--border);border-radius:var(--radius-md);padding:12px 14px 8px;--s1:#3987e5;--s2:#d95926}
.tc-title{font-size:13px;font-weight:600}
.tc-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.tc-now{font-size:12px;color:var(--text-secondary);font-variant-numeric:tabular-nums;white-space:nowrap}
.tc-legend{display:flex;gap:12px;font-size:11px;color:var(--text-secondary)}
.tc-legend i{display:inline-block;width:10px;height:2px;border-radius:1px;margin-right:5px;vertical-align:middle}
.tc svg{display:block;width:100%;height:120px;margin-top:6px;overflow:visible;touch-action:none}
.tc svg text{fill:var(--text-muted);font-size:10px;font-variant-numeric:tabular-nums}
.tc-tip{position:absolute;pointer-events:none;background:var(--bg-elevated);border:1px solid var(--border-hover);border-radius:var(--radius-sm);padding:6px 8px;font-size:11.5px;white-space:nowrap;box-shadow:var(--shadow-md);color:var(--text-secondary);z-index:2}
.tc-tip b{color:var(--text-primary);font-variant-numeric:tabular-nums}
.tc-tip i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
</style>
<div class="card">
<div class="card-head"><h2>System</h2><span class="tele-head-sub" id="tele-status">Connecting...</span></div>
<div class="tele-charts" id="tele-charts"></div>
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
teleRecord(t);
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
// --- Charts: the last 15 min of samples this tab has seen (kept across reloads per tab) ---
const TELE_WINDOW=15*60*1000,TELE_GAP=30000;
const teleKey='tele-hist-'+serverId;
let teleHist=[];
try{teleHist=JSON.parse(sessionStorage.getItem(teleKey)||'[]');}catch(e){}
const TELE_CHARTS=[
{title:'CPU utilization',unit:'Percent',fmt:telePct,series:[['CPU','cpu']]},
{title:'Memory used',unit:'Percent',fmt:telePct,series:[['RAM','mem']]},
{title:'Load average (1 min)',unit:'Runnable processes',fmt:v=>v==null?'N/A':v.toFixed(2),series:[['Load','load']]},
{title:'Network',unit:'Bytes per second',fmt:teleRate,bytes:1,series:[['In','rx'],['Out','tx']]},
{title:'Disk I/O',unit:'Bytes per second',fmt:teleRate,bytes:1,series:[['Read','rd'],['Write','wr']]},
{title:'TCP connections',unit:'Count',fmt:v=>v==null?'N/A':String(Math.round(v)),series:[['In use','tcp']]},
];
function teleRecord(t){
const c=t.cpu||{},n=t.network||{},io=(t.disk||{}).io||[],sum=(a,k)=>(a||[]).reduce((s,x)=>s+(x[k]||0),0);
const now=Date.now();
teleHist.push({t:now,cpu:c.percent,mem:(t.memory||{}).percent,load:(c.load||[])[0],
rx:sum(n.interfaces,'rx_bps'),tx:sum(n.interfaces,'tx_bps'),rd:sum(io,'read_bps'),wr:sum(io,'write_bps'),tcp:(n.tcp||{}).inuse});
teleHist=teleHist.filter(p=>p.t>=now-TELE_WINDOW);
try{sessionStorage.setItem(teleKey,JSON.stringify(teleHist));}catch(e){}
teleDrawCharts();
}
function teleNice(v){if(!(v>0))return 1;const e=Math.pow(10,Math.floor(Math.log10(v))),f=v/e;return (f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*e;}
function teleTime(ms){const d=new Date(ms);return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');}
let teleHover={};
function teleDrawCharts(){
const box=document.getElementById('tele-charts');
if(!box.children.length)box.innerHTML=TELE_CHARTS.map((c,i)=>'<div class="tc" id="tc'+i+'"><div class="tc-head"><div class="tc-title">'+c.title+'</div><div class="tc-now"></div></div><div class="tc-head"><div class="tele-sub">'+c.unit+'</div>'
+(c.series.length>1?'<div class="tc-legend">'+c.series.map((s,j)=>'<span><i style="background:var(--s'+(j+1)+')"></i>'+s[0]+'</span>').join('')+'</div>':'')
+'</div><svg role="img" aria-label="'+c.title+' over the last 15 minutes"></svg><div class="tc-tip" hidden></div></div>').join('');
TELE_CHARTS.forEach((c,i)=>teleDrawChart(c,document.getElementById('tc'+i)));
}
function teleDrawChart(c,el){
const svg=el.querySelector('svg'),W=Math.max(svg.clientWidth||300,120),H=120,L=c.bytes?64:44,R=6,T=6,B=18;
svg.setAttribute('viewBox','0 0 '+W+' '+H);
const pts=teleHist,last=pts[pts.length-1];
el.querySelector('.tc-now').textContent=last?c.series.map(s=>(c.series.length>1?s[0]+' ':'')+c.fmt(last[s[1]])).join(' · '):'';
if(pts.length<2){svg.innerHTML='<text x="'+(W/2)+'" y="'+(H/2)+'" text-anchor="middle">Collecting samples...</text>';return;}
const t0=pts[0].t,t1=Math.max(last.t,t0+60000);
let max=0;pts.forEach(p=>c.series.forEach(s=>{if(p[s[1]]>max)max=p[s[1]];}));
if(c.bytes){const e=Math.pow(1024,Math.max(0,Math.floor(Math.log(max*1.1||1)/Math.log(1024))));max=teleNice(max*1.1/e)*e;}else max=teleNice(max*1.1);
const x=t=>L+(t-t0)/(t1-t0)*(W-L-R),y=v=>T+(1-v/max)*(H-T-B);
let g='';
[0,.5,1].forEach(f=>{const v=max*f,yy=y(v).toFixed(1);g+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+'" stroke="var(--border)" stroke-width="1"/><text x="'+(L-6)+'" y="'+yy+'" dy="3" text-anchor="end">'+c.fmt(v).replace('.0%','%').replace(/\.0 /,' ').replace(/\.00$/,'')+'</text>';});
const ticks=4;for(let k=0;k<=ticks;k++){const tt=t0+(t1-t0)*k/ticks;g+='<text x="'+x(tt).toFixed(1)+'" y="'+(H-4)+'" text-anchor="'+(k===0?'start':k===ticks?'end':'middle')+'">'+teleTime(tt)+'</text>';}
c.series.forEach((s,j)=>{let d='',prev=null;pts.forEach(p=>{const v=p[s[1]];if(v==null){prev=null;return;}d+=(prev&&p.t-prev.t<=TELE_GAP?'L':'M')+x(p.t).toFixed(1)+' '+y(v).toFixed(1);prev=p;});
g+='<path d="'+d+'" fill="none" stroke="var(--s'+(j+1)+')" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';});
g+='<g class="tc-cross"></g>';
svg.innerHTML=g;
const tip=el.querySelector('.tc-tip'),cross=svg.querySelector('.tc-cross');
const show=px=>{
const tt=t0+(px-L)/(W-L-R)*(t1-t0);let p=pts[0];pts.forEach(q=>{if(Math.abs(q.t-tt)<Math.abs(p.t-tt))p=q;});
const xx=x(p.t).toFixed(1);
cross.innerHTML='<line x1="'+xx+'" x2="'+xx+'" y1="'+T+'" y2="'+(H-B)+'" stroke="var(--text-muted)" stroke-width="1"/>'
+c.series.map((s,j)=>p[s[1]]==null?'':'<circle cx="'+xx+'" cy="'+y(p[s[1]]).toFixed(1)+'" r="4" fill="var(--s'+(j+1)+')" stroke="var(--bg)" stroke-width="2"/>').join('');
tip.innerHTML='';const head=document.createElement('div');head.textContent=new Date(p.t).toLocaleTimeString();tip.appendChild(head);
c.series.forEach((s,j)=>{const r=document.createElement('div'),sw=document.createElement('i'),b=document.createElement('b');sw.style.background='var(--s'+(j+1)+')';b.textContent=c.fmt(p[s[1]]);r.append(sw,b,' '+s[0]);tip.appendChild(r);});
tip.hidden=false;
const sx=svg.getBoundingClientRect().width/W,left=xx*sx+14;
tip.style.left=Math.min(left,el.clientWidth-tip.offsetWidth-8)+'px';tip.style.top='54px';
};
svg.onpointermove=e=>{const r=svg.getBoundingClientRect();teleHover[c.title]=(e.clientX-r.left)*W/r.width;show(teleHover[c.title]);};
svg.onpointerleave=()=>{delete teleHover[c.title];tip.hidden=true;cross.innerHTML='';};
if(teleHover[c.title]!=null)show(teleHover[c.title]);
}
window.addEventListener('resize',()=>{if(teleHist.length)teleDrawCharts();});
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
if(teleHist.length)teleDrawCharts();
if(!document.hidden)startTelemetry();
"""
