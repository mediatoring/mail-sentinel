'use strict';


document.querySelectorAll('[data-t]').forEach(e=>{if(!Object.hasOwn(en,e.dataset.t))en[e.dataset.t]=e.textContent});
let lang=localStorage.getItem('sentinel-lang')||'en',state=null,selected=null,previewed=false,running=false,currentJob=null,lastJob=null;
const $=id=>document.getElementById(id), t=k=>(lang==='cs'?cs[k]:en[k])||en[k]||k;
const params=new URLSearchParams(location.hash.slice(1));
if(params.get('token')) {sessionStorage.setItem('sentinel-token',params.get('token'));history.replaceState(null,'',location.pathname);}
const token=sessionStorage.getItem('sentinel-token')||'';
// Reopening the terminal URL after a restart may only change the fragment.
// Reload to consume the new token and discard the previous session's job state.
window.addEventListener('hashchange',()=>{
 const next=new URLSearchParams(location.hash.slice(1)).get('token');
 if(next&&next!==token){sessionStorage.removeItem('sentinel-job');location.reload();}
});
function notice(text){$('notice').textContent=text;$('notice').hidden=!text;}
function translate(){$('supportLink').href=lang==='cs'?'https://mediatoring.cz/kyberbezpecnost/':'https://mediatoring.cz/en/cybersecurity/';document.documentElement.lang=lang;$('lang').value=lang;document.querySelectorAll('[data-t]').forEach(e=>e.textContent=t(e.dataset.t));if(state){$('privacy').textContent=t(state.privacy_mode);renderMessages();}if(lastJob)renderJob(lastJob);}
async function api(path,data){let r;try{r=await fetch('/api/'+path,{method:data?'POST':'GET',headers:{'X-Sentinel-Token':token,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});}catch{throw Error(t('networkFailed'));}const j=await r.json();if(!r.ok){const e=Error(j.error||'Request failed');e.status=r.status;throw e;}return j;}
async function safe(fn){try{await fn();}catch(e){notice(e.message)}}
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
async function refresh(){state=await api('state');if(!localStorage.getItem('sentinel-lang')){lang=state.language;translate();}$('provider').textContent=state.provider+' / '+(state.model||'—');$('privacy').textContent=t(state.privacy_mode);$('count').textContent=state.messages.length;$('analyze').disabled=!state.configured||running||!selected;if(!state.configured){notice(t('noModel'));$('setup').open=true;}renderMessages();await historyLoad();}
let renderMessages;
function select(m){if(running)return;selected=m.id;previewed=false;lastJob=null;$('consent').checked=false;$('empty').hidden=true;$('detail').hidden=false;$('source').textContent=m.source.toUpperCase();$('subject').textContent=m.subject;$('sender').textContent=m.sender;$('outgoing').hidden=true;$('report').hidden=true;$('approve').hidden=true;$('events').replaceChildren(node('p',t('traceHint'),'muted'));$('jobStatus').textContent='';$('consentWrap').hidden=!state.external;$('analyze').disabled=!state.configured;renderMessages();}
function renderJob(j){lastJob=j;$('events').replaceChildren();$('cancelJob').hidden=j.status!=='running';$('jobStatus').textContent=t(j.status==='running'?'working':j.status);for(const ev of j.events||[]){if(ev.type==='tool'){const el=node('div',undefined,'event '+ev.status);el.append(node('strong',ev.id+' · '+ev.tool+(ev.status==='denied'?' · DENIED':'')));const d=node('details');d.append(node('summary',t('observations')),node('pre',JSON.stringify(ev.observation,null,2)));el.append(d);$('events').append(el)}else if(ev.type==='error'){$('events').append(node('p',t(['context_limit','provider_unavailable','output_limit','tool_call_invalid','provider_error'].includes(ev.error_code)?ev.error_code:'failed'),'notice'));}}if(j.report){const r=j.report,box=$('report');box.replaceChildren();box.hidden=false;box.className='report-card'+(r.verdict==='HIGH_RISK'?' high':'');box.append(node('h3',t(r.verdict)),node('p',r.summary),node('small',t('references')+': '+r.evidence_ids.join(', ')));for(const k of ['uncertainties','recommendations']){box.append(node('h3',t(k)));const ul=node('ul');r[k].forEach(x=>ul.append(node('li',x)));box.append(ul)}}$('approve').hidden=!j.approval_token;$('approve').onclick=()=>safe(async()=>{if(!confirm(t('approveConfirm')))return;await api('approve',{token:j.approval_token,report_id:j.report_id});j.approval_token=null;$('approve').hidden=true;notice(t('moved'));});}
async function poll(){try{const j=await api('jobs/'+currentJob);renderJob(j);if(j.status==='running'){setTimeout(poll,900)}else{sessionStorage.removeItem('sentinel-job');running=false;$('file').disabled=false;$('imap').disabled=false;$('analyze').disabled=!state.configured;await historyLoad()}}catch(e){if([401,403,404].includes(e.status)){sessionStorage.removeItem('sentinel-job');running=false;$('file').disabled=e.status!==404;$('imap').disabled=e.status!==404;$('analyze').disabled=e.status!==404||!state.configured;notice(t(e.status===404?'jobMissing':'sessionExpired'));return;}notice(t('reconnecting'));setTimeout(poll,3000)}}
let historyLoad;
$('lang').onchange=()=>{lang=$('lang').value;localStorage.setItem('sentinel-lang',lang);translate();safe(historyLoad)};
$('refresh').onclick=()=>safe(refresh);$('historyRefresh').onclick=()=>safe(historyLoad);
$('analyze').onclick=()=>safe(async()=>{if(running)return;if(state.external&&(!previewed||!$('consent').checked))throw Error(t('consentRequired'));running=true;$('analyze').disabled=true;let j;try{j=await api('analyze',{message_id:selected,consent:$('consent').checked});}catch(e){running=false;$('analyze').disabled=!state.configured;throw e;}$('file').disabled=true;$('imap').disabled=true;currentJob=j.job_id;sessionStorage.setItem('sentinel-job',currentJob);$('analyze').disabled=true;$('report').hidden=true;$('approve').hidden=true;$('jobStatus').textContent=t('working');poll();});
$('imap').onclick=()=>safe(async()=>{$('imap').disabled=true;try{const r=await api('imap',{});$('sourceFilter').value='own';await refresh();notice(t('loaded')+' '+r.count);}finally{$('imap').disabled=false}});
$('file').onchange=()=>safe(async()=>{const f=$('file').files[0];if(!f||running)return;if(f.size>1000000)throw Error('Maximum upload size: 1 MB');const bytes=new Uint8Array(await f.arrayBuffer());let binary='';for(const b of bytes)binary+=String.fromCharCode(b);const r=await api('import',{eml_base64:btoa(binary)});$('sourceFilter').value='own';showView('review');await refresh();select(state.messages.find(m=>m.id===r.message_id));$('file').value='';});


async function loadSettings(){const v=await api('settings');settingsProvider=null;for(const [k,x]of Object.entries(v)){if(k==='check_modes'){for(const [n,mode]of Object.entries(x)){const field=$('settings').elements.namedItem('check_'+n);if(field)field.value=mode;}continue;}const e=$('settings').elements.namedItem(k);if(e){if(e.type==='checkbox')e.checked=x;else e.value=Array.isArray(x)?x.join(', '):x;}}updateProviderFields();updateQuarantineField();if(typeof updateOAuthFields==='function')updateOAuthFields();}
const endpointDrafts={};
let settingsProvider=null;
function fieldVisible(name,visible){const e=$('settings').elements.namedItem(name);e.closest('label').hidden=!visible;e.disabled=!visible;}
function updateProviderFields(){
 const f=$('settings').elements,p=f.provider.value;
 if(settingsProvider!==null&&settingsProvider!==p){
  endpointDrafts[settingsProvider]=f.base_url.value;
  f.base_url.value=endpointDrafts[p]||'';
  f.api_key.value='';
  f.model.value='';
  $('modelOptions').replaceChildren();
  f.allow_external.checked=false;
 }
 settingsProvider=p;
 fieldVisible('base_url',p==='local'||p==='compatible');
 fieldVisible('api_key',p!=='local');
 fieldVisible('allow_external',p!=='local');
 f.base_url.required=p==='compatible';
 f.base_url.placeholder=p==='compatible'?'https://api.example.com/v1':'http://127.0.0.1:1234/v1';
}
function updateQuarantineField(){fieldVisible('quarantine_folder',$('settings').elements.allow_quarantine.checked);}
$('settings').elements.allow_quarantine.onchange=updateQuarantineField;
updateProviderFields();updateQuarantineField();
