from __future__ import annotations


INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QNL Preservation Risk Manager</title>
<style>
:root{--bg:#f5f7fb;--card:#fff;--ink:#172033;--muted:#667085;--line:#dfe4ee;--accent:#175cd3;--accent2:#0b4bb3;--good:#067647;--warn:#b54708;--bad:#b42318;--shadow:0 8px 30px rgba(16,24,40,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}.shell{max-width:1180px;margin:0 auto;padding:28px 22px 60px}.hero{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:24px}.hero h1{margin:0 0 8px;font-size:30px;letter-spacing:-.02em}.hero p{margin:0;color:var(--muted);max-width:760px;line-height:1.5}.badge{background:#eaf2ff;color:#174ea6;padding:7px 11px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}.tabs{display:flex;gap:8px;margin-bottom:16px}.tab{border:1px solid var(--line);background:#fff;color:#344054;padding:10px 16px;border-radius:10px;font-weight:650;cursor:pointer}.tab.active{background:var(--accent);border-color:var(--accent);color:#fff}.panel{display:none}.panel.active{display:block}.grid{display:grid;grid-template-columns:1.05fr .95fr;gap:18px}@media(max-width:900px){.grid{grid-template-columns:1fr}.hero{flex-direction:column}}.card{background:var(--card);border:1px solid #e7eaf0;border-radius:16px;box-shadow:var(--shadow);padding:20px}.card h2,.card h3{margin-top:0}.hint{color:var(--muted);font-size:13px;line-height:1.45}.field{margin:16px 0}.field label{display:block;font-size:13px;font-weight:700;margin-bottom:7px;color:#344054}.field input[type=text],.field textarea,.field select{width:100%;border:1px solid #cfd6e2;background:#fff;border-radius:10px;padding:11px 12px;font:inherit;color:var(--ink);outline:none}.field textarea{min-height:130px;resize:vertical}.field input:focus,.field textarea:focus,.field select:focus{border-color:#84adff;box-shadow:0 0 0 3px #e7efff}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.check{display:flex;gap:9px;align-items:center;margin:12px 0;font-size:14px}.button{border:0;background:var(--accent);color:#fff;border-radius:10px;padding:11px 16px;font-weight:700;cursor:pointer}.button:hover{background:var(--accent2)}.button.secondary{background:#eef4ff;color:#1849a9}.button:disabled{opacity:.55;cursor:not-allowed}.drop{border:1px dashed #98a2b3;border-radius:12px;padding:16px;background:#fafbfc}.drop input{width:100%}.job{margin-top:16px;border:1px solid var(--line);border-radius:14px;padding:16px;background:#fbfcfe}.job.hidden{display:none}.jobtop{display:flex;justify-content:space-between;gap:10px;align-items:center}.status{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.04em}.status.completed{color:var(--good)}.status.failed{color:var(--bad)}.status.running{color:var(--accent)}.bar{height:10px;background:#e9edf3;border-radius:999px;overflow:hidden;margin:11px 0}.bar>div{height:100%;background:var(--accent);width:0;transition:width .25s ease}.downloads{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.downloads a{text-decoration:none;background:#eef4ff;color:#1849a9;padding:8px 10px;border-radius:8px;font-size:13px;font-weight:700}.result{margin-top:14px;max-height:560px;overflow:auto;border:1px solid var(--line);border-radius:10px;background:#fff}.result pre{white-space:pre-wrap;margin:0;padding:15px;font:13px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace}.tablewrap{overflow:auto}.previewtable{width:100%;border-collapse:collapse;font-size:12px}.previewtable th,.previewtable td{text-align:left;border-bottom:1px solid #edf0f5;padding:9px 10px;white-space:nowrap}.previewtable th{position:sticky;top:0;background:#f8fafc;color:#475467}.notice{padding:11px 12px;border-radius:10px;background:#fff7ed;color:#9a3412;font-size:13px;margin:12px 0}.recent{margin-top:18px}.recent-row{display:grid;grid-template-columns:110px 1fr 100px;gap:10px;padding:9px 0;border-bottom:1px solid #edf0f5;font-size:13px}.small{font-size:12px;color:var(--muted)}.config{font-size:12px;color:var(--muted);margin-top:8px}.error{color:var(--bad);font-weight:600}.ok{color:var(--good);font-weight:600}
</style>
</head>
<body>
<div class="shell">
  <div class="hero">
    <div><h1>QNL Preservation Risk Manager</h1><p>Ask preservation-risk questions in natural language or generate downloadable risk reports for a supplied set of format identifiers. Assessments use the same registry, framework, evidence, and AI controls as the command-line interface.</p><div id="configSummary" class="config"></div></div>
    <div class="badge">Local web interface</div>
  </div>

  <div class="tabs">
    <button class="tab active" data-tab="human">Ask a risk question</button>
    <button class="tab" data-tab="batch">Batch risk report</button>
  </div>

  <section id="human" class="panel active">
    <div class="grid">
      <div class="card">
        <h2>Human question</h2>
        <p class="hint">Use normal language. Examples: “What is the risk of PDF?” or “What are the software dependency risks of fmt/18?”</p>
        <form id="humanForm">
          <div class="field"><label for="question">Question</label><textarea id="question" required placeholder="What is the preservation risk of PDF?"></textarea></div>
          <div class="row">
            <div class="field"><label for="humanAiMode">AI risk mode</label><select id="humanAiMode"><option value="fill-gaps" selected>Fill evidence gaps</option><option value="off">Off</option><option value="review-all">Independent review</option></select></div>
            <div class="field"><label for="humanScope">Scope</label><select id="humanScope"><option value="global">Global</option><option value="institution">Institution</option></select></div>
          </div>
          <div id="humanInstitutionField" class="field" style="display:none"><label for="humanInstitution">Institution ID</label><input id="humanInstitution" type="text" placeholder="qnl"></div>
          <label class="check"><input id="humanAiIdentification" type="checkbox" checked> Allow bounded AI fallback for human format identification</label>
          <button class="button" type="submit">Run assessment</button>
        </form>
        <div id="humanJob" class="job hidden"></div>
      </div>
      <div class="card">
        <h3>How this behaves</h3>
        <p class="hint">Simple PUIDs resolve deterministically. Broad names such as PDF may match several PRONOM PUIDs; the configured human format assessment limit is applied before assessment begins.</p>
        <div class="notice">AI never replaces deterministically resolved answers. AI-assisted results are shown separately and retain evidence/audit metadata.</div>
        <div id="humanRecent" class="recent"></div>
      </div>
    </div>
  </section>

  <section id="batch" class="panel">
    <div class="grid">
      <div class="card">
        <h2>Batch risk report</h2>
        <p class="hint">Paste PRONOM PUIDs/canonical IDs or upload a TXT/CSV file. CSV may contain a <b>puid</b>, <b>pronom_puid</b>, <b>format_id</b>, <b>format</b>, or <b>id</b> column.</p>
        <form id="batchForm">
          <div class="field"><label for="formatIds">Format IDs</label><textarea id="formatIds" placeholder="fmt/18&#10;fmt/19&#10;fmt/276"></textarea></div>
          <div class="field drop"><label for="formatFile">Upload TXT or CSV</label><input id="formatFile" type="file" accept=".txt,.csv,text/plain,text/csv"><div id="fileNote" class="small"></div></div>
          <div class="row">
            <div class="field"><label for="batchAiMode">AI risk mode</label><select id="batchAiMode"><option value="off" selected>Deterministic only</option><option value="fill-gaps">Fill evidence gaps</option></select></div>
            <div class="field"><label for="batchScope">Scope</label><select id="batchScope"><option value="global">Global</option><option value="institution">Institution</option></select></div>
          </div>
          <div id="batchInstitutionField" class="field" style="display:none"><label for="batchInstitution">Institution ID</label><input id="batchInstitution" type="text" placeholder="qnl"></div>
          <button class="button" type="submit">Generate report</button>
        </form>
        <div id="batchJob" class="job hidden"></div>
      </div>
      <div class="card">
        <h3>Report output</h3>
        <p class="hint">The job runs in the background and shows progress. When complete you can download:</p>
        <p class="hint"><b>CSV</b> — compact summary for analysis<br><b>JSON</b> — full assessment and audit detail<br><b>ZIP</b> — both files together</p>
        <div class="notice">Batch mode expects identifiers rather than descriptive names. AI identification is not used for the uploaded list.</div>
        <div id="batchRecent" class="recent"></div>
      </div>
    </div>
  </section>
</div>
<script>
const polls = new Map();
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function tab(name){document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id===name));}
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
function scopeToggle(selectId,fieldId){document.getElementById(selectId).addEventListener('change',e=>document.getElementById(fieldId).style.display=e.target.value==='institution'?'block':'none');}
scopeToggle('humanScope','humanInstitutionField');scopeToggle('batchScope','batchInstitutionField');
document.getElementById('formatFile').addEventListener('change',e=>{const f=e.target.files[0];document.getElementById('fileNote').textContent=f?`${f.name} — ${(f.size/1024).toFixed(1)} KB`:'';});
async function api(url,options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});let data;try{data=await r.json();}catch{data={detail:await r.text()};}if(!r.ok)throw new Error(data.detail||data.error||`HTTP ${r.status}`);return data;}
function jobShell(job){return `<div class="jobtop"><strong>${esc(job.message||'Working')}</strong><span class="status ${esc(job.status)}">${esc(job.status)}</span></div><div class="bar"><div style="width:${Number(job.progress||0)}%"></div></div><div class="small">${Number(job.progress||0)}% · Job ${esc(job.job_id)}</div><div class="downloads"></div><div class="result"></div>`;}
function renderDownloads(container,job){const d=container.querySelector('.downloads');d.innerHTML='';Object.keys(job.downloads||{}).forEach(name=>{const a=document.createElement('a');a.href=`/api/jobs/${job.job_id}/download/${encodeURIComponent(name)}`;a.textContent=`Download ${name.toUpperCase()}`;d.appendChild(a);});}
function renderPreview(container,job){const r=container.querySelector('.result');r.innerHTML='';const p=job.preview||{};if(p.kind==='human'&&p.text){const pre=document.createElement('pre');pre.textContent=p.text;r.appendChild(pre);}else if(p.kind==='batch'&&Array.isArray(p.rows)){const wrap=document.createElement('div');wrap.className='tablewrap';let h='<table class="previewtable"><thead><tr><th>Input</th><th>PUID</th><th>Label</th><th>Deterministic</th><th>AI-assisted</th><th>Status</th></tr></thead><tbody>';for(const row of p.rows){h+=`<tr><td>${esc(row.input_format_id)}</td><td>${esc(row.puid||'')}</td><td>${esc(row.label||'')}</td><td>${esc(row.deterministic_risk_band||row.deterministic_analysis_status||'Unbanded')}</td><td>${esc(row.ai_risk_band||row.ai_status||'—')}</td><td>${esc(row.status||'')}</td></tr>`;}h+='</tbody></table>';wrap.innerHTML=h;r.appendChild(wrap);if(p.preview_truncated){const n=document.createElement('div');n.className='small';n.style.padding='10px';n.textContent='Preview limited to first 50 rows. Download the report for the complete result.';r.appendChild(n);}}
}
function showJob(targetId,job){const el=document.getElementById(targetId);el.classList.remove('hidden');el.innerHTML=jobShell(job);if(job.error){const x=document.createElement('div');x.className='error';x.style.marginTop='10px';x.textContent=job.error;el.appendChild(x);}renderDownloads(el,job);renderPreview(el,job);}
async function watch(jobId,targetId){if(polls.has(targetId))clearInterval(polls.get(targetId));const tick=async()=>{try{const job=await api(`/api/jobs/${jobId}`);showJob(targetId,job);if(['completed','failed'].includes(job.status)){clearInterval(polls.get(targetId));polls.delete(targetId);loadRecent();}}catch(e){console.error(e);}};await tick();const handle=setInterval(tick,900);polls.set(targetId,handle);}
document.getElementById('humanForm').addEventListener('submit',async e=>{e.preventDefault();const btn=e.submitter;btn.disabled=true;try{const body={question:document.getElementById('question').value,ai_mode:document.getElementById('humanAiMode').value,enable_ai_identification:document.getElementById('humanAiIdentification').checked,scope:document.getElementById('humanScope').value,institution_id:document.getElementById('humanInstitution').value||null};const job=await api('/api/jobs/human',{method:'POST',body:JSON.stringify(body)});showJob('humanJob',job);watch(job.job_id,'humanJob');}catch(err){alert(err.message);}finally{btn.disabled=false;}});
document.getElementById('batchForm').addEventListener('submit',async e=>{e.preventDefault();const btn=e.submitter;btn.disabled=true;try{const file=document.getElementById('formatFile').files[0];const uploaded_text=file?await file.text():'';const body={ids_text:document.getElementById('formatIds').value,uploaded_text,uploaded_filename:file?file.name:null,ai_mode:document.getElementById('batchAiMode').value,scope:document.getElementById('batchScope').value,institution_id:document.getElementById('batchInstitution').value||null};const job=await api('/api/jobs/batch',{method:'POST',body:JSON.stringify(body)});showJob('batchJob',job);watch(job.job_id,'batchJob');}catch(err){alert(err.message);}finally{btn.disabled=false;}});
async function loadRecent(){try{const jobs=await api('/api/jobs');for(const [kind,target] of [['human','humanRecent'],['batch','batchRecent']]){const rows=jobs.filter(j=>j.kind===kind).slice(0,5);const el=document.getElementById(target);el.innerHTML=rows.length?'<h3>Recent jobs</h3>':'';for(const j of rows){const div=document.createElement('div');div.className='recent-row';div.innerHTML=`<span>${esc(j.kind)}</span><span>${esc(j.message)}</span><span class="status ${esc(j.status)}">${esc(j.status)}</span>`;el.appendChild(div);}}}catch(e){console.error(e);}}
async function loadConfig(){try{const c=await api('/api/config');document.getElementById('configSummary').textContent=`Framework: ${c.framework_id||c.framework} · Human assessment limit: ${c.human_format_assessment_limit} · Batch maximum: ${c.batch_max_formats}`;}catch(e){console.error(e);}}
loadConfig();loadRecent();
</script>
</body>
</html>'''
