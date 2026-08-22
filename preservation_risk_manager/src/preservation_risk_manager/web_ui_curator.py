from __future__ import annotations


INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QNL Preservation Risk Manager</title>
<style>
:root{--bg:#f5f7fb;--card:#fff;--ink:#172033;--muted:#667085;--line:#dfe4ee;--accent:#175cd3;--accent2:#0b4bb3;--good:#067647;--warn:#b54708;--bad:#b42318;--shadow:0 8px 30px rgba(16,24,40,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}.shell{max-width:1220px;margin:0 auto;padding:28px 22px 60px}.hero{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:24px}.hero h1{margin:0 0 8px;font-size:30px;letter-spacing:-.02em}.hero p{margin:0;color:var(--muted);max-width:820px;line-height:1.5}.badge{background:#eaf2ff;color:#174ea6;padding:7px 11px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}.tab{border:1px solid var(--line);background:#fff;color:#344054;padding:10px 16px;border-radius:10px;font-weight:650;cursor:pointer}.tab.active{background:var(--accent);border-color:var(--accent);color:#fff}.panel{display:none}.panel.active{display:block}.grid{display:grid;grid-template-columns:1.05fr .95fr;gap:18px}@media(max-width:900px){.grid{grid-template-columns:1fr}.hero{flex-direction:column}}.card{background:var(--card);border:1px solid #e7eaf0;border-radius:16px;box-shadow:var(--shadow);padding:20px}.card h2,.card h3{margin-top:0}.hint{color:var(--muted);font-size:13px;line-height:1.5}.field{margin:16px 0}.field label{display:block;font-size:13px;font-weight:700;margin-bottom:7px;color:#344054}.field input[type=text],.field textarea,.field select{width:100%;border:1px solid #cfd6e2;background:#fff;border-radius:10px;padding:11px 12px;font:inherit;color:var(--ink);outline:none}.field textarea{min-height:130px;resize:vertical}.field input:focus,.field textarea:focus,.field select:focus{border-color:#84adff;box-shadow:0 0 0 3px #e7efff}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.check{display:flex;gap:9px;align-items:center;margin:12px 0;font-size:14px}.button{border:0;background:var(--accent);color:#fff;border-radius:10px;padding:11px 16px;font-weight:700;cursor:pointer}.button:hover{background:var(--accent2)}.button.secondary{background:#eef4ff;color:#1849a9}.button.smallbtn{padding:7px 10px;font-size:12px}.button:disabled{opacity:.55;cursor:not-allowed}.actions{display:flex;gap:7px;flex-wrap:wrap}.drop{border:1px dashed #98a2b3;border-radius:12px;padding:16px;background:#fafbfc}.drop input{width:100%}.job{margin-top:16px;border:1px solid var(--line);border-radius:14px;padding:16px;background:#fbfcfe}.job.hidden{display:none}.jobtop{display:flex;justify-content:space-between;gap:10px;align-items:center}.status{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.04em}.status.completed{color:var(--good)}.status.failed{color:var(--bad)}.status.running{color:var(--accent)}.bar{height:10px;background:#e9edf3;border-radius:999px;overflow:hidden;margin:11px 0}.bar>div{height:100%;background:var(--accent);width:0;transition:width .25s ease}.downloads{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.downloads a{text-decoration:none;background:#eef4ff;color:#1849a9;padding:8px 10px;border-radius:8px;font-size:13px;font-weight:700}.result{margin-top:14px;max-height:600px;overflow:auto;border:1px solid var(--line);border-radius:10px;background:#fff}.result pre{white-space:pre-wrap;margin:0;padding:15px;font:13px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace}.tablewrap{overflow:auto}.previewtable{width:100%;border-collapse:collapse;font-size:12px}.previewtable th,.previewtable td{text-align:left;border-bottom:1px solid #edf0f5;padding:9px 10px;vertical-align:top}.previewtable th{position:sticky;top:0;background:#f8fafc;color:#475467;white-space:nowrap}.notice{padding:11px 12px;border-radius:10px;background:#fff7ed;color:#9a3412;font-size:13px;margin:12px 0}.info{padding:11px 12px;border-radius:10px;background:#eff6ff;color:#1e40af;font-size:13px;margin:12px 0}.recent{margin-top:18px}.recent-row{display:grid;grid-template-columns:110px 1fr 100px;gap:10px;padding:9px 0;border-bottom:1px solid #edf0f5;font-size:13px}.small{font-size:12px;color:var(--muted)}.config{font-size:12px;color:var(--muted);margin-top:8px}.error{color:var(--bad);font-weight:600}.ok{color:var(--good);font-weight:600}.lookup-meta{margin:10px 0;color:var(--muted);font-size:13px}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;white-space:nowrap}
</style>
</head>
<body>
<div class="shell">
  <div class="hero">
    <div>
      <h1>QNL Preservation Risk Manager</h1>
      <p>Curator interface for asking preservation-risk questions, discovering PRONOM PUIDs, and generating downloadable risk reports from a controlled list of formats.</p>
      <div id="configSummary" class="config"></div>
    </div>
    <div class="badge">Curator interface</div>
  </div>

  <div class="tabs">
    <button class="tab active" data-tab="human">Ask Risk</button>
    <button class="tab" data-tab="lookup">PUID Lookup</button>
    <button class="tab" data-tab="batch">Run Report</button>
  </div>

  <section id="human" class="panel active">
    <div class="grid">
      <div class="card">
        <h2>Ask a preservation-risk question</h2>
        <p class="hint">Ask in normal language. A full PRONOM PUID such as <b>fmt/276</b> resolves directly. A broader term such as <b>PDF</b> can match several PUIDs; only the configured first matches are assessed.</p>
        <form id="humanForm">
          <div class="field"><label for="question">Question</label><textarea id="question" required placeholder="What is the preservation risk of fmt/276?"></textarea></div>
          <div class="row">
            <div class="field"><label for="humanAiMode">AI analysis</label><select id="humanAiMode"><option value="synthesize" selected>AI-assisted overall synthesis</option><option value="off">Governed evidence only</option><option value="fill-gaps">Fill question evidence gaps</option><option value="review-all">Review question evidence</option></select></div>
            <div class="field"><label for="humanScope">Scope</label><select id="humanScope"><option value="global">Global</option><option value="institution">Institution</option></select></div>
          </div>
          <div id="humanInstitutionField" class="field" style="display:none"><label for="humanInstitution">Institution ID</label><input id="humanInstitution" type="text" placeholder="qnl"></div>
          <label class="check"><input id="humanAiIdentification" type="checkbox" checked> Allow bounded AI fallback when local format identification is unresolved</label>
          <button class="button" type="submit">Assess risk</button>
        </form>
        <div id="humanJob" class="job hidden"></div>
      </div>
      <div class="card">
        <h3>Resolution behavior</h3>
        <p class="hint"><b>Exact PUID:</b> “What is the risk of fmt/276?” assesses that exact format.</p>
        <p class="hint"><b>Name/family term:</b> “What is the risk of PDF?” discovers matching PUID-backed formats and assesses only the configured first N matches.</p>
        <div class="notice">The governed source-risk result remains the audit baseline. AI-assisted synthesis is displayed separately and never rewrites source-native evidence or the governed result.</div>
        <div id="humanRecent" class="recent"></div>
      </div>
    </div>
  </section>

  <section id="lookup" class="panel">
    <div class="card">
      <h2>Find a PRONOM PUID</h2>
      <p class="hint">Use this when you know the format name but not its PUID. Search by format name, PUID, MIME type, extension, or another registry identifier. Example searches: <b>PDF</b>, <b>TIFF</b>, <b>application/pdf</b>, <b>.docx</b>, or <b>fmt/276</b>.</p>
      <form id="lookupForm">
        <div class="row">
          <div class="field"><label for="lookupQuery">Format or identifier</label><input id="lookupQuery" type="text" required placeholder="PDF"></div>
          <div class="field" style="display:flex;align-items:flex-end"><button class="button" type="submit">Search registry</button></div>
        </div>
      </form>
      <div id="lookupMeta" class="lookup-meta"></div>
      <div id="lookupResults" class="result" style="display:none"></div>
      <div class="info">From a result, choose <b>Assess</b> to open the Ask Risk tab for that exact PUID, or <b>Add to report</b> to place it in the Run Report list.</div>
    </div>
  </section>

  <section id="batch" class="panel">
    <div class="grid">
      <div class="card">
        <h2>Run a risk report</h2>
        <p class="hint">Paste PRONOM PUIDs/canonical IDs or upload a TXT/CSV file. CSV may contain a <b>puid</b>, <b>pronom_puid</b>, <b>format_id</b>, <b>format</b>, or <b>id</b> column.</p>
        <form id="batchForm">
          <div class="field"><label for="formatIds">PUIDs / format IDs</label><textarea id="formatIds" placeholder="fmt/18&#10;fmt/19&#10;fmt/276"></textarea></div>
          <div class="field drop"><label for="formatFile">Upload TXT or CSV</label><input id="formatFile" type="file" accept=".txt,.csv,text/plain,text/csv"><div id="fileNote" class="small"></div></div>
          <div class="row">
            <div class="field"><label for="batchAiMode">AI analysis</label><select id="batchAiMode"><option value="off" selected>Governed database evidence only</option><option value="synthesize">AI-assisted overall synthesis</option><option value="fill-gaps">Legacy question-level fill gaps</option></select></div>
            <div class="field"><label for="batchScope">Scope</label><select id="batchScope"><option value="global">Global</option><option value="institution">Institution</option></select></div>
          </div>
          <div id="batchInstitutionField" class="field" style="display:none"><label for="batchInstitution">Institution ID</label><input id="batchInstitution" type="text" placeholder="qnl"></div>
          <button class="button" type="submit">Generate report</button>
        </form>
        <div id="batchJob" class="job hidden"></div>
      </div>
      <div class="card">
        <h3>Report output</h3>
        <p class="hint">The report runs as a background job. When complete you can download:</p>
        <p class="hint"><b>HTML</b> — curator report with evidence drill-down<br><b>CSV</b> — compact governed/AI summary<br><b>JSON</b> — full assessment and audit detail<br><b>ZIP</b> — all report files together</p>
        <div class="notice">Batch mode expects explicit identifiers rather than descriptive names. Use PUID Lookup first when the required PUID is not known.</div>
        <div id="batchRecent" class="recent"></div>
      </div>
    </div>
  </section>
</div>
<script>
const polls=new Map();
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function tab(name){document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id===name));}
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
function scopeToggle(selectId,fieldId){document.getElementById(selectId).addEventListener('change',e=>document.getElementById(fieldId).style.display=e.target.value==='institution'?'block':'none');}
scopeToggle('humanScope','humanInstitutionField');scopeToggle('batchScope','batchInstitutionField');
document.getElementById('formatFile').addEventListener('change',e=>{const f=e.target.files[0];document.getElementById('fileNote').textContent=f?`${f.name} — ${(f.size/1024).toFixed(1)} KB`:'';});
async function api(url,options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});let data;try{data=await r.json();}catch{data={detail:await r.text()};}if(!r.ok)throw new Error(data.detail||data.error||`HTTP ${r.status}`);return data;}
function jobShell(job){return `<div class="jobtop"><strong>${esc(job.message||'Working')}</strong><span class="status ${esc(job.status)}">${esc(job.status)}</span></div><div class="bar"><div style="width:${Number(job.progress||0)}%"></div></div><div class="small">${Number(job.progress||0)}% · Job ${esc(job.job_id)}</div><div class="downloads"></div><div class="result"></div>`;}
function renderDownloads(container,job){const d=container.querySelector('.downloads');d.innerHTML='';Object.keys(job.downloads||{}).forEach(name=>{const a=document.createElement('a');a.href=`/api/jobs/${job.job_id}/download/${encodeURIComponent(name)}`;a.textContent=`Download ${name.toUpperCase()}`;d.appendChild(a);});}
function renderPreview(container,job){const r=container.querySelector('.result');r.innerHTML='';const p=job.preview||{};if(p.kind==='human'&&p.text){const pre=document.createElement('pre');pre.textContent=p.text;r.appendChild(pre);}else if(p.kind==='batch'&&Array.isArray(p.rows)){const wrap=document.createElement('div');wrap.className='tablewrap';let h='<table class="previewtable"><thead><tr><th>Input</th><th>PUID</th><th>Label</th><th>Governed risk</th><th>AI risk</th><th>Confidence</th><th>Relation</th><th>Status</th></tr></thead><tbody>';for(const row of p.rows){h+=`<tr><td>${esc(row.input_format_id)}</td><td class="mono">${esc(row.puid||'')}</td><td>${esc(row.label||'')}</td><td>${esc(row.governed_risk_label||row.governed_risk_level||'Not assessed')}</td><td>${esc(row.ai_risk_label||row.ai_risk_level||'—')}</td><td>${esc(row.ai_confidence??'—')}</td><td>${esc((row.ai_relation_to_governed||'—').replaceAll('_',' '))}</td><td>${esc(row.status||'')}</td></tr>`;}h+='</tbody></table>';wrap.innerHTML=h;r.appendChild(wrap);if(p.preview_truncated){const n=document.createElement('div');n.className='small';n.style.padding='10px';n.textContent='Preview limited to first 50 rows. Download the report for the complete result.';r.appendChild(n);}}}
function showJob(targetId,job){const el=document.getElementById(targetId);el.classList.remove('hidden');el.innerHTML=jobShell(job);if(job.error){const x=document.createElement('div');x.className='error';x.style.marginTop='10px';x.textContent=job.error;el.appendChild(x);}renderDownloads(el,job);renderPreview(el,job);}
async function watch(jobId,targetId){if(polls.has(targetId))clearInterval(polls.get(targetId));const tick=async()=>{try{const job=await api(`/api/jobs/${jobId}`);showJob(targetId,job);if(['completed','failed'].includes(job.status)){clearInterval(polls.get(targetId));polls.delete(targetId);loadRecent();}}catch(e){console.error(e);}};await tick();const handle=setInterval(tick,900);polls.set(targetId,handle);}

document.getElementById('humanForm').addEventListener('submit',async e=>{e.preventDefault();const btn=e.submitter;btn.disabled=true;try{const body={question:document.getElementById('question').value,ai_mode:document.getElementById('humanAiMode').value,enable_ai_identification:document.getElementById('humanAiIdentification').checked,scope:document.getElementById('humanScope').value,institution_id:document.getElementById('humanInstitution').value||null};const job=await api('/api/jobs/human',{method:'POST',body:JSON.stringify(body)});showJob('humanJob',job);watch(job.job_id,'humanJob');}catch(err){alert(err.message);}finally{btn.disabled=false;}});

document.getElementById('lookupForm').addEventListener('submit',async e=>{e.preventDefault();const btn=e.submitter;btn.disabled=true;const meta=document.getElementById('lookupMeta');const out=document.getElementById('lookupResults');try{meta.textContent='Searching registry…';out.style.display='none';out.innerHTML='';const q=document.getElementById('lookupQuery').value.trim();const data=await api(`/api/formats/lookup?q=${encodeURIComponent(q)}`);meta.textContent=data.match_count?`${data.match_count} PUID-backed match${data.match_count===1?'':'es'} found. Showing ${data.returned_count}${data.limit_applied?` of ${data.match_count} (configured limit ${data.limit})`:''}.`:`No PUID-backed formats matched “${q}”.`;if(data.matches.length){let h='<div class="tablewrap"><table class="previewtable"><thead><tr><th>PUID</th><th>Format</th><th>Version</th><th>Extension</th><th>MIME</th><th>Actions</th></tr></thead><tbody>';data.matches.forEach((row,i)=>{h+=`<tr><td class="mono">${esc(row.puid)}</td><td>${esc(row.label||'')}</td><td>${esc(row.version||'')}</td><td>${esc((row.extensions||[]).join(', '))}</td><td>${esc((row.mime_types||[]).join(', '))}</td><td><div class="actions"><button class="button secondary smallbtn" type="button" data-assess="${i}">Assess</button><button class="button secondary smallbtn" type="button" data-report="${i}">Add to report</button></div></td></tr>`;});h+='</tbody></table></div>';out.innerHTML=h;out.style.display='block';out.querySelectorAll('[data-assess]').forEach(b=>b.addEventListener('click',()=>{const row=data.matches[Number(b.dataset.assess)];document.getElementById('question').value=`What is the preservation risk of ${row.puid}?`;tab('human');document.getElementById('question').focus();}));out.querySelectorAll('[data-report]').forEach(b=>b.addEventListener('click',()=>{const row=data.matches[Number(b.dataset.report)];const area=document.getElementById('formatIds');const ids=area.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);if(!ids.includes(row.puid))ids.push(row.puid);area.value=ids.join('\n');tab('batch');area.focus();}));}}catch(err){meta.innerHTML=`<span class="error">${esc(err.message)}</span>`;}finally{btn.disabled=false;}});

document.getElementById('batchForm').addEventListener('submit',async e=>{e.preventDefault();const btn=e.submitter;btn.disabled=true;try{const file=document.getElementById('formatFile').files[0];const uploaded_text=file?await file.text():'';const body={ids_text:document.getElementById('formatIds').value,uploaded_text,uploaded_filename:file?file.name:null,ai_mode:document.getElementById('batchAiMode').value,scope:document.getElementById('batchScope').value,institution_id:document.getElementById('batchInstitution').value||null};const job=await api('/api/jobs/batch',{method:'POST',body:JSON.stringify(body)});showJob('batchJob',job);watch(job.job_id,'batchJob');}catch(err){alert(err.message);}finally{btn.disabled=false;}});

async function loadRecent(){try{const jobs=await api('/api/jobs');for(const [kind,target] of [['human','humanRecent'],['batch','batchRecent']]){const rows=jobs.filter(j=>j.kind===kind).slice(0,5);const el=document.getElementById(target);el.innerHTML=rows.length?'<h3>Recent jobs</h3>':'';for(const j of rows){const div=document.createElement('div');div.className='recent-row';div.innerHTML=`<span>${esc(j.kind)}</span><span>${esc(j.message)}</span><span class="status ${esc(j.status)}">${esc(j.status)}</span>`;el.appendChild(div);}}}catch(e){console.error(e);}}
async function loadConfig(){try{const c=await api('/api/config');document.getElementById('configSummary').textContent=`Framework: ${c.framework_id||c.framework} · PUID match limit: ${c.puid_lookup_limit} · Batch maximum: ${c.batch_max_formats} · AI: ${c.ai_configured?'configured':'not configured'}`;}catch(e){console.error(e);}}
loadConfig();loadRecent();
</script>
</body>
</html>'''
