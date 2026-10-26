"""Server-detail panels for the newer admin API endpoints: read-only terminal,
Telegram notices, admin password, and the factory-reset form.

Kept out of servers_router.py so that file stays readable. The script relies on
serverId, apiCall, showActionPanel and showToast defined by the page's main
script, so it must be placed after that script (serverId is a const).
"""
import html as _html

from app.routers.telemetry_ui import TELEMETRY_CARD, TELEMETRY_JS  # noqa: F401 - TELEMETRY_CARD is placed by servers_router

_TOOLS_JS = r"""
function openDialog(id){document.getElementById(id).classList.remove('hidden');}
function closeDialog(id){document.getElementById(id).classList.add('hidden');}
async function getJson(path){
try{const r=await fetch('/api/servers/'+serverId+path);return await r.json();}
catch(e){return{error:e.message};}
}
function formData(form){return Object.fromEntries(new FormData(form).entries());}

async function actionInvalidateSession(inst){
if(!confirm('Revoke the broker session of '+inst+'? The client must log in to the broker again before trading.'))return;
showActionPanel('Invalidate session '+inst,await apiCall('/invalidate-session',{instance:inst}));
}
function actionFactoryReset(inst){
const f=document.getElementById('reset-form');
f.reset();f.instance.value=inst;
document.getElementById('reset-inst').textContent=inst;
openDialog('reset-dialog');
}
async function submitFactoryReset(e){
e.preventDefault();
const data=formData(e.target);
if(prompt('This deletes every user and broker login of '+data.instance+'. Type the instance name to confirm.')!==data.instance)return;
closeDialog('reset-dialog');
showActionPanel('Factory reset '+data.instance,{message:'Resetting - this restarts the instance...'});
showActionPanel('Factory reset '+data.instance,await apiCall('/reset-admin-user',data));
}

async function actionDeleteInstance(inst){
const typed=prompt('DELETE '+inst+'? The server takes a full backup first (no backup, no delete), then removes the service, files, nginx site and certificate.\n\nType the instance name to confirm.');
if(typed===null)return;
if(typed!==inst){showToast('Name did not match - nothing deleted','error');return;}
const d=await apiCall('/delete-instance',{instance:inst,confirm:typed});
showActionPanel('Delete '+inst,d);
if(d.removed)setTimeout(()=>location.reload(),1500);
}
async function actionUpdateScripts(){
if(!confirm('Update the scripts and admin dashboard on this server? Instances are not restarted.'))return;
showActionPanel('Update Scripts',await apiCall('/update',{scope:'scripts'}));
}
async function actionHealthCheckSystem(){
showActionPanel('System Health Check',await apiCall('/health-check',{scope:'system'}));
}

function terminalActionChanged(){
const a=document.getElementById('term-action').value;
const needsInst=['systemctl_status','journalctl_tail','sqlite_select'].includes(a);
document.getElementById('term-inst-wrap').classList.toggle('hidden',!needsInst);
document.getElementById('term-lines-wrap').classList.toggle('hidden',a!=='journalctl_tail');
document.getElementById('term-sql-wrap').classList.toggle('hidden',a!=='sqlite_select');
if(a==='sqlite_select')loadTerminalDbs();
}
async function loadTerminalDbs(){
const sel=document.getElementById('term-db');
sel.innerHTML='<option value="">Loading...</option>';
const d=await getJson('/terminal/dbs?instance='+encodeURIComponent(document.getElementById('term-inst').value));
sel.innerHTML='';
(d.dbs||[]).forEach(db=>{const o=document.createElement('option');o.value=o.textContent=db;sel.appendChild(o);});
if(!sel.options.length){const o=document.createElement('option');o.value='';o.textContent=d.error||'No databases';sel.appendChild(o);}
}
async function submitTerminal(e){
e.preventDefault();
const data=formData(e.target);
const out=document.getElementById('term-output');
out.textContent='Running...';
const d=await apiCall('/terminal/run',data);
out.textContent=d.output!==undefined?(d.output||'(no output)')+(d.exit_code?'\n\n[exit '+d.exit_code+']':''):(d.error||JSON.stringify(d,null,2));
}

async function loadTelegram(){
const el=document.getElementById('tg-status');
const d=await getJson('/telegram');
el.textContent=d.error?('Unknown: '+d.error):(d.configured?'On - chat '+d.chat_id:'Off');
el.className='badge '+(d.error?'badge-unknown':(d.configured?'badge-healthy':'badge-warning'));
}
async function submitTelegram(e){
e.preventDefault();
const data=formData(e.target);
const btn=e.target.querySelector('button[type=submit]');
btn.disabled=true;btn.textContent='Checking token...';
const d=await apiCall('/telegram',data);
btn.disabled=false;btn.textContent='Save & send test';
if(d.status==='success'){closeDialog('tg-dialog');e.target.reset();showToast(d.message||'Telegram saved','success');loadTelegram();}
else showToast('Telegram - '+(d.error||d.message||'failed'),'error');
}
async function submitPassword(e){
e.preventDefault();
const data=formData(e.target);
if(data.new_password!==data.confirm_password){showToast('Passwords do not match','error');return;}
const d=await apiCall('/change-password',{new_password:data.new_password});
if(d.status==='success'){closeDialog('pw-dialog');e.target.reset();showToast('Admin password changed and saved in the fleet manager','success');}
else showToast('Change password - '+(d.error||d.message||'failed'),'error');
}

terminalActionChanged();
loadTelegram();
"""


def server_tools_html(instance_names: list[str]) -> str:
    options = "".join(f'<option value="{_html.escape(n)}">{_html.escape(n)}</option>' for n in instance_names)
    return f"""
<div class="card">
<div class="card-head"><div><h2>Server Settings</h2><div class="card-subtitle">Admin dashboard settings on this server</div></div></div>
<div class="action-bar">
<span>Telegram notices <span id="tg-status" class="badge badge-unknown">...</span></span>
<button class="btn btn-sm" onclick="openDialog('tg-dialog')">Set Telegram bot</button>
<button class="btn btn-sm" onclick="openDialog('pw-dialog')">Change admin password</button>
</div>
</div>

<div class="card">
<div class="card-head"><div><h2>Terminal</h2><div class="card-subtitle">Whitelisted read-only commands. Safe during market hours.</div></div></div>
<form class="form-card" onsubmit="submitTerminal(event)">
<div class="form-grid">
<div><label class="reset-field-label">Command</label>
<select class="reset-input" name="action" id="term-action" onchange="terminalActionChanged()">
<option value="systemctl_status">systemctl status</option>
<option value="journalctl_tail">journalctl tail</option>
<option value="df">df (disk)</option>
<option value="free">free (memory)</option>
<option value="uptime">uptime</option>
<option value="sqlite_select">sqlite3 SELECT</option>
</select></div>
<div id="term-inst-wrap"><label class="reset-field-label">Instance</label>
<select class="reset-input" name="instance" id="term-inst" onchange="if(document.getElementById('term-action').value==='sqlite_select')loadTerminalDbs()">{options}</select></div>
<div id="term-lines-wrap"><label class="reset-field-label">Lines</label>
<input class="reset-input" type="number" name="lines" value="100" min="1" max="1000"></div>
<div id="term-sql-wrap" class="field-full"><label class="reset-field-label">Database</label>
<select class="reset-input" name="db" id="term-db"></select>
<label class="reset-field-label">Query (one SELECT)</label>
<textarea class="reset-input mono" name="query" placeholder="SELECT * FROM users LIMIT 10"></textarea></div>
</div>
<div class="form-actions"><button type="submit" class="btn btn-accent btn-sm">Run</button></div>
</form>
<div id="term-output" class="job-log-viewer">(no output yet)</div>
</div>

<div class="dialog-overlay hidden" id="reset-dialog">
<form class="dialog" id="reset-form" onsubmit="submitFactoryReset(event)">
<h2>Factory reset <span id="reset-inst" class="mono"></span></h2>
<p class="help-text">Deletes the instance's users and broker logins, so it returns to first-time setup. Restarts the instance. Leave the fields blank to keep the current broker and keys.</p>
<input type="hidden" name="instance">
<label>New broker (short name, optional)</label><input name="broker" autocomplete="off" placeholder="e.g. zerodha">
<label>Broker API key</label><input name="broker_api_key" autocomplete="off">
<label>Broker API secret</label><input name="broker_api_secret" type="password" autocomplete="new-password">
<label>Market data API key (XTS brokers)</label><input name="broker_api_key_market" autocomplete="off">
<label>Market data API secret (XTS brokers)</label><input name="broker_api_secret_market" type="password" autocomplete="new-password">
<div class="dialog-actions"><button type="button" class="btn btn-sm" onclick="closeDialog('reset-dialog')">Cancel</button><button type="submit" class="btn btn-sm btn-danger">Factory reset</button></div>
</form>
</div>

<div class="dialog-overlay hidden" id="tg-dialog">
<form class="dialog" onsubmit="submitTelegram(event)">
<h2>Telegram bot</h2>
<p class="help-text">The server checks the token and sends a test message before saving. The token is never shown again.</p>
<label>Bot token from @BotFather</label><input name="token" type="password" autocomplete="off" required>
<label>Chat ID (blank = detect from the latest message to the bot)</label><input name="chat_id" autocomplete="off">
<div class="dialog-actions"><button type="button" class="btn btn-sm" onclick="closeDialog('tg-dialog')">Cancel</button><button type="submit" class="btn btn-sm btn-accent">Save &amp; send test</button></div>
</form>
</div>

<div class="dialog-overlay hidden" id="pw-dialog">
<form class="dialog" onsubmit="submitPassword(event)">
<h2>Change admin password</h2>
<p class="help-text">Changes this server's admin dashboard password. The fleet manager saves the new password, so polling keeps working.</p>
<label>New password</label><input name="new_password" type="password" minlength="8" autocomplete="new-password" required>
<label>Confirm new password</label><input name="confirm_password" type="password" minlength="8" autocomplete="new-password" required>
<div class="dialog-actions"><button type="button" class="btn btn-sm" onclick="closeDialog('pw-dialog')">Cancel</button><button type="submit" class="btn btn-sm btn-accent">Change password</button></div>
</form>
</div>

<script>{_TOOLS_JS}{TELEMETRY_JS}</script>
"""
