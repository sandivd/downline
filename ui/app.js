'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const icons = (name, cls = '') => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ACTIVE = new Set(['queued','starting','downloading','processing','cancelling']);
const names = {new:'New download',queue:'Download queue',history:'History',settings:'Settings'};
let token = location.hash.slice(1);
if (token && !names[token]) { sessionStorage.setItem('downline-token', token); history.replaceState(null, '', '/'); }
else token = sessionStorage.getItem('downline-token') || '';
let state = {jobs:[], settings:{}, dependencies:{}}, page = 'new', filter = 'all', toastTimer, failures = 0;
let settingsLoaded = false, settingsDirty = false, preview = null, lastRender = '';

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('#theme-toggle').setAttribute('aria-checked', String(theme === 'dark'));
  $('#theme-caption').textContent = theme === 'dark' ? 'Dark mode' : 'Light mode';
  localStorage.setItem('downline-theme', theme);
}
setTheme(localStorage.getItem('downline-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
$('#theme-toggle').onclick = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

async function api(route, data) {
  const response = await fetch('/api/' + route, {method:data === undefined ? 'GET' : 'POST',
    headers:{'X-Downline-Token':token, ...(data === undefined ? {} : {'Content-Type':'application/json'})},
    ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Something went wrong. Try again.');
  return result;
}
function toast(message, error = false) {
  const el = $('#toast'); el.textContent = message; el.classList.toggle('error', error); el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.hidden = true, error ? 6500 : 3500);
}
function inputError(message = '') { $('#input-error').textContent = message; $('#input-error').hidden = !message; }
function navigate(next) {
  if (!names[next]) return;
  page = next;
  $$('.page').forEach(el => el.hidden = el.id !== 'page-' + page);
  $$('.nav-item').forEach(el => {el.classList.toggle('active', el.dataset.page === page); el.setAttribute('aria-current', el.dataset.page === page ? 'page' : 'false');});
  document.title = names[page] + ' — Downline';
  if (page === 'settings' && !settingsDirty) fillSettings();
  renderJobs(true); window.scrollTo(0, 0);
}
$$('[data-page]').forEach(b => b.onclick = () => navigate(b.dataset.page));
$$('[data-go]').forEach(b => b.onclick = () => navigate(b.dataset.go));
$('.brand').onclick = e => {e.preventDefault(); navigate('new');};
function duration(seconds) {
  if (!Number.isFinite(seconds)) return '';
  const n = Math.max(0, Math.floor(seconds));
  return n >= 3600 ? `${Math.floor(n/3600)}:${String(Math.floor(n/60)%60).padStart(2,'0')}:${String(n%60).padStart(2,'0')}` : `${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`;
}
function bytes(n) { if (!n) return ''; const i = Math.min(3, Math.floor(Math.log(n)/Math.log(1024))); return (n / 1024**i).toFixed(i ? 1 : 0) + ' ' + ['B','KB','MB','GB'][i]; }
function eta(n) { if (!Number.isFinite(n)) return ''; return n < 60 ? `${Math.ceil(n)}s left` : `${Math.ceil(n/60)}m left`; }
function links() { return $('#video-url').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean); }
$('#video-url').addEventListener('input', () => {inputError(); preview = null; $('#video-preview').hidden = true; const el=$('#video-url'); el.style.height='22px'; el.style.height=Math.min(155,el.scrollHeight)+'px';});
$('#paste').onclick = async () => {
  try { $('#video-url').value = (await navigator.clipboard.readText()).trim(); $('#video-url').dispatchEvent(new Event('input')); $('#video-url').focus(); }
  catch { $('#video-url').focus(); toast('Press Ctrl + V to paste your link.'); }
};
$('#analyze').onclick = async () => {
  const urls = links(); if (!urls.length) {inputError('Paste a video link first.'); return;}
  if (urls.length > 1) {inputError('Get details for one link at a time. You can add all links directly to the queue.'); return;}
  const button = $('#analyze'), original = button.innerHTML; button.disabled = true; button.textContent = 'Getting details…'; inputError();
  const entered = $('#video-url').value;
  try {
    const info = await api('analyze',{url:urls[0]});
    if ($('#video-url').value !== entered) return;
    preview = info;
    const meta = [info.site, info.uploader, duration(info.duration)].filter(Boolean);
    if (info.qualities?.length) meta.push('Available up to ' + info.qualities[0] + 'p');
    $('#video-preview').innerHTML = `<strong>${esc(info.title)}</strong><p>${meta.map(esc).join(' · ')}</p>`;
    $('#video-preview').hidden = false;
  } catch(e) {inputError(e.message);} finally {button.disabled=false; button.innerHTML=original;}
};
$('#format').onchange = () => {
  const audio = $('#format').value === 'mp3'; $('#quality').disabled = audio;
  $('#format-hint').textContent = audio ? 'Extracts audio at the best available MP3 quality. Video quality does not apply.' : $('#format').value === 'mkv' ? 'Keeps the best source codecs. High resolutions depend on what the video offers.' : 'MP4 favours widely supported codecs. Choose MKV for the best source quality.';
};
async function download() {
  const urls = links(); if (!urls.length) { inputError('Paste a video link from a supported platform first.'); $('#video-url').focus(); return; }
  const button=$('#download'); button.disabled=true; inputError();
  try {
    const result = await api('download',{urls,format:$('#format').value,quality:$('#quality').value});
    if (!result.added) {toast('Those videos are already in your queue.'); return;}
    $('#video-url').value=''; $('#video-url').dispatchEvent(new Event('input'));
    toast(`${result.added} ${result.added===1?'video':'videos'} added to your queue.`); await refresh(); navigate('queue');
  } catch(e) {inputError(e.message);} finally {button.disabled=false;}
}
$('#download').onclick = download;
document.addEventListener('keydown', e => {if ((e.ctrlKey||e.metaKey) && e.key==='Enter' && page==='new' && !$('#download').disabled) {e.preventDefault(); download();}});

function empty(title, description, icon, add = false) {
  return `<div class="empty-state">${icons(icon)}<h2>${esc(title)}</h2><p>${esc(description)}</p>${add?'<button class="secondary" data-go="new">'+icons('plus')+'Add your first video</button>':''}</div>`;
}
const statusNames = {queued:'Waiting',starting:'Connecting',downloading:'Downloading',processing:'Processing',cancelling:'Cancelling',completed:'Completed',failed:'Failed',cancelled:'Cancelled'};
function jobHTML(j) {
  const active=ACTIVE.has(j.status), downloading=['downloading','processing'].includes(j.status);
  const stateIcon=j.status==='completed'?'check':j.status==='failed'?'alert':j.status==='queued'?'clock':j.status==='cancelled'?'close':'arrow';
  const meta=[j.site,j.format.toUpperCase(),j.format==='mp3'?'Audio':j.quality==='best'?'Best available':'Up to '+j.quality+'p'];
  if (j.status==='completed' && j.bytes) meta.push(bytes(j.bytes));
  if (!active) meta.push(new Date((j.finished||j.created)*1000).toLocaleDateString(undefined,{day:'numeric',month:'short'}));
  const action=(name,label,icon)=>`<button class="icon-button" data-action="${name}" data-id="${j.id}" title="${label}" aria-label="${label}">${icons(icon)}</button>`;
  let actions=`<span class="job-state ${j.status}">${esc(statusNames[j.status]||j.status)}</span>`;
  if (active && j.status!=='cancelling') actions+=action('cancel','Cancel download','close');
  if (['failed','cancelled'].includes(j.status)) actions+=action('retry','Retry download','retry');
  if (j.status==='completed') actions+=action('open','Open video','play')+action('reveal','Show in folder','folder');
  if (!active) actions+=action('remove','Remove from history','trash');
  const pct=Number.isFinite(j.progress)?Math.min(100,Math.max(0,j.progress)):null;
  let progress='';
  if (downloading) progress=`<div class="progress-track ${pct===null||j.status==='processing'?'indeterminate':''}" role="progressbar" aria-label="Download progress" aria-valuemin="0" aria-valuemax="100" ${pct===null?'':`aria-valuenow="${Math.round(pct)}"`}><div class="progress-fill" data-progress="${pct||0}"></div></div><div class="progress-info"><span>${j.status==='processing'?'Merging / converting…':`${pct===null?'Downloading…':pct.toFixed(0)+'%'}${j.speed?' · '+esc(bytes(j.speed))+'/s':''}`}</span><span>${esc(j.status==='processing'?'Almost there':eta(j.eta))}</span></div>`;
  return `<article class="job-row" data-job="${j.id}"><div class="job-symbol ${j.status}">${icons(stateIcon)}</div><div class="job-info"><div class="job-title" title="${esc(j.url)}">${esc(j.title)}</div><div class="job-meta">${meta.map(esc).join('<span class="separator">/</span>')}</div>${progress}${j.error?'<p class="job-error">'+esc(j.error)+'</p>':''}</div><div class="job-actions">${actions}</div></article>`;
}
function renderJobs(force=false) {
  const signature=JSON.stringify([state.jobs,filter,state.paused,page]);
  if (!force && signature===lastRender) return; lastRender=signature;
  const focused=document.activeElement?.closest('[data-action]');
  const restoreFocus=focused?{id:focused.dataset.id,action:focused.dataset.action,container:focused.closest('.job-list').id}:null;
  const queue=state.jobs.filter(j=>ACTIVE.has(j.status));
  const historyJobs=state.jobs.filter(j=>!ACTIVE.has(j.status)).reverse();
  $('#queue-count').textContent=queue.length;
  $('#queue-description').textContent=queue.length?`${queue.length} ${queue.length===1?'video':'videos'} on the way to your computer.`:'Ready when you are.';
  $('#queue-summary').textContent=`${queue.length} ${queue.length===1?'download':'downloads'}`;
  $('#queue-notice').hidden=!state.paused;
  $('#pause-queue').innerHTML=icons(state.paused?'play':'pause')+`<span>${state.paused?'Resume queue':'Pause queue'}</span>`;
  $('#queue-jobs').innerHTML=queue.length?queue.map(jobHTML).join(''):empty('A little quiet in here.','Add a video and we’ll take care of the rest.','arrow',true);
  const shown=historyJobs.filter(j=>filter==='all'||(filter==='completed'?j.status==='completed':['failed','cancelled'].includes(j.status)));
  $('#history-jobs').innerHTML=shown.length?shown.map(jobHTML).join(''):empty(filter==='all'?'Nothing saved. Yet.':'No downloads in this view.',filter==='all'?'Finished downloads will appear here.':'Try a different filter.','clock',filter==='all');
  $('#clear-history').disabled=!historyJobs.length;
  $('#recent-section').hidden=!queue.length;
  $('#recent-jobs').innerHTML=queue.slice(0,2).map(jobHTML).join('');
  $$('.progress-fill').forEach(el=>el.style.width=Number(el.dataset.progress)+'%');
  if(restoreFocus) $(`#${restoreFocus.container} [data-id="${restoreFocus.id}"][data-action="${restoreFocus.action}"]`)?.focus({preventScroll:true});
}
async function refresh() {
  try {
    const previous=new Map(state.jobs.map(j=>[j.id,j.status]));
    state=await api('state'); failures=0; $('#connection-banner').hidden=true;
    for(const j of state.jobs){
      if(previous.has(j.id)&&previous.get(j.id)!==j.status){
        if(j.status==='completed')toast('Saved · '+j.title);
        if(j.status==='failed')toast('Download failed. Open History for the details.',true);
      }
    }
    const d=state.dependencies, ready=d.engine&&d.ffmpeg&&d.javascript;
    $('#engine-status').classList.toggle('missing',!ready);
    $('#engine-status').lastElementChild.textContent=state.updating?'Updating engine…':ready?'Ready':'Setup incomplete';
    $('#destination').textContent=state.settings.destination; $('#destination').title=state.settings.destination;
    $('#dependency-list').innerHTML=[['engine','yt-dlp'],['ffmpeg','FFmpeg'],['javascript','JavaScript']].map(([key,name])=>`<span class="${d[key]?'':'missing'}">${icons(d[key]?'check':'close')}${name}</span>`).join('');
    if (!settingsLoaded) fillSettings();
    renderJobs();
  } catch(e) {
    failures++; if (failures>=2) {$('#connection-banner').hidden=false; $('#engine-status').classList.add('missing'); $('#engine-status').lastElementChild.textContent='Disconnected';}
    if (failures===1 && /expired/.test(e.message)) toast(e.message,true);
  }
}
async function polling() { await refresh(); setTimeout(polling,900); }
polling();
$$('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;$$('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));renderJobs(true);});
$('#pause-queue').onclick=async()=>{try{await api('action',{action:'pause'});await refresh();}catch(e){toast(e.message,true);}};
document.addEventListener('click',async e=>{
  const go=e.target.closest('[data-go]'); if(go){navigate(go.dataset.go);return;}
  const button=e.target.closest('[data-action]'); if(!button)return;
  const {action,id}=button.dataset; button.disabled=true;
  try{
    if(['open','reveal'].includes(action)) await api('open',{id,reveal:action==='reveal'});
    else await api('action',{action,id});
    await refresh();
  }catch(err){toast(err.message,true);}finally{button.disabled=false;}
});
async function openFolder(){try{await api('open',{});}catch(e){toast(e.message,true);}}
$('#open-folder').onclick=openFolder;
$('#change-folder').onclick=()=>navigate('settings');
function fillSettings(){
  if(!state.settings.destination)return;
  $('#setting-destination').value=state.settings.destination;
  $('#setting-concurrency').value=state.settings.concurrency;
  $('#setting-history').checked=state.settings.remember_history;
  $('#setting-cookies').value=state.settings.cookies||'';
  settingsLoaded=true;settingsDirty=false;$('#settings-message').textContent='';
}
$('#settings-form').addEventListener('input',()=>{settingsDirty=true;$('#settings-message').textContent='';});
for(const [id,kind,target]of[['browse-destination','folder','setting-destination'],['browse-cookies','file','setting-cookies']]){
  $('#'+id).onclick=async()=>{const b=$('#'+id);b.disabled=true;try{const r=await api('pick',{kind});if(r.path){$('#'+target).value=r.path;settingsDirty=true;}}catch(e){toast(e.message,true);}finally{b.disabled=false;}};
}
$('#settings-form').onsubmit=async e=>{
  e.preventDefault();const b=$('button[type=submit]',$('#settings-form'));b.disabled=true;
  try{await api('settings',{destination:$('#setting-destination').value,concurrency:Number($('#setting-concurrency').value),remember_history:$('#setting-history').checked,cookies:$('#setting-cookies').value});settingsDirty=false;await refresh();$('#settings-message').textContent='Changes saved.';toast('Settings saved.');}catch(err){toast(err.message,true);}finally{b.disabled=false;}
};
$('#update-engine').onclick=async()=>{const b=$('#update-engine');b.disabled=true;b.lastElementChild.textContent='Updating…';try{const r=await api('update',{});toast(r.message);}catch(e){toast(e.message,true);}finally{b.disabled=false;b.lastElementChild.textContent='Check for updates';await refresh();}};
function confirmAction(title,text,label){return new Promise(resolve=>{const d=$('#confirm-dialog');$('#confirm-title').textContent=title;$('#confirm-text').textContent=text;$('#confirm-yes').textContent=label;$('#confirm-no').textContent='Cancel';let settled=false;const finish=result=>{if(settled)return;settled=true;d.close();resolve(result);};$('#confirm-yes').onclick=()=>finish(true);$('#confirm-no').onclick=()=>finish(false);d.oncancel=()=>finish(false);d.showModal();});}
$('#clear-history').onclick=async()=>{if(!await confirmAction('Clear your history?','This removes finished, failed, and cancelled entries. Your downloaded files stay on your PC.','Clear history'))return;try{await api('action',{action:'clear'});await refresh();toast('History cleared. Your files are untouched.');}catch(e){toast(e.message,true);}};
$('#quit').onclick=async()=>{if(!await confirmAction('Close Downline?',state.jobs.some(j=>ACTIVE.has(j.status))?'Active downloads will stop. You can retry them next time.':'The local download service will stop.','Quit Downline'))return;try{await api('quit',{});document.body.innerHTML='<main class="closed"><div class="content"><h1>All done.</h1><p>Downline is closed. You can close this window.</p></div></main>';}catch(e){toast(e.message,true);}};
