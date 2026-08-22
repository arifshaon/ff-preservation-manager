from __future__ import annotations

from preservation_risk_manager.web_ui import INDEX_HTML as _BASE_INDEX_HTML


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not apply curator UI adaptation: {label}")
    return text.replace(old, new, 1)


INDEX_HTML = _BASE_INDEX_HTML

INDEX_HTML = _replace_once(
    INDEX_HTML,
    '<div class="field"><label for="humanAiMode">AI risk mode</label><select id="humanAiMode"><option value="fill-gaps" selected>Fill evidence gaps</option><option value="off">Off</option><option value="review-all">Independent review</option></select></div>',
    '<div class="field"><label for="humanAiMode">AI risk mode</label><select id="humanAiMode"><option value="synthesize" selected>AI-assisted overall synthesis</option><option value="off">Governed evidence only</option><option value="fill-gaps">Fill question evidence gaps</option><option value="review-all">Review question evidence</option></select></div>',
    label="human AI mode",
)
INDEX_HTML = _replace_once(
    INDEX_HTML,
    '<div class="field"><label for="batchAiMode">AI risk mode</label><select id="batchAiMode"><option value="off" selected>Deterministic only</option><option value="fill-gaps">Fill evidence gaps</option></select></div>',
    '<div class="field"><label for="batchAiMode">AI risk mode</label><select id="batchAiMode"><option value="off" selected>Governed database evidence only</option><option value="synthesize">AI-assisted overall synthesis</option><option value="fill-gaps">Legacy question-level fill gaps</option></select></div>',
    label="batch AI mode",
)
INDEX_HTML = _replace_once(
    INDEX_HTML,
    '<p class="hint"><b>CSV</b> — compact summary for analysis<br><b>JSON</b> — full assessment and audit detail<br><b>ZIP</b> — both files together</p>',
    '<p class="hint"><b>HTML</b> — curator report with filtering and evidence drill-down<br><b>CSV</b> — compact governed/AI summary for analysis<br><b>JSON</b> — full assessment and audit detail<br><b>ZIP</b> — all report files together</p>',
    label="batch artifact help",
)
INDEX_HTML = _replace_once(
    INDEX_HTML,
    '<div class="notice">AI never replaces deterministically resolved answers. AI-assisted results are shown separately and retain evidence/audit metadata.</div>',
    '<div class="notice">The governed source-risk synthesis remains visible as the auditable baseline. AI-assisted synthesis is shown separately and never rewrites source-native evidence or the governed result.</div>',
    label="human governance notice",
)
INDEX_HTML = _replace_once(
    INDEX_HTML,
    '<div class="notice">Batch mode expects identifiers rather than descriptive names. AI identification is not used for the uploaded list.</div>',
    '<div class="notice">Batch mode expects identifiers rather than descriptive names. The report leads with governed overall risk and, when selected, shows AI-assisted overall risk separately with confidence, relation, evidence and external-source audit.</div>',
    label="batch governance notice",
)

_old_preview = "let h='<table class=\"previewtable\"><thead><tr><th>Input</th><th>PUID</th><th>Label</th><th>Deterministic</th><th>AI-assisted</th><th>Status</th></tr></thead><tbody>';for(const row of p.rows){h+=`<tr><td>${esc(row.input_format_id)}</td><td>${esc(row.puid||'')}</td><td>${esc(row.label||'')}</td><td>${esc(row.deterministic_risk_band||row.deterministic_analysis_status||'Unbanded')}</td><td>${esc(row.ai_risk_band||row.ai_status||'—')}</td><td>${esc(row.status||'')}</td></tr>`;}"
_new_preview = "let h='<table class=\"previewtable\"><thead><tr><th>Input</th><th>PUID</th><th>Label</th><th>Governed risk</th><th>AI risk</th><th>Confidence</th><th>Relation</th><th>Status</th></tr></thead><tbody>';for(const row of p.rows){h+=`<tr><td>${esc(row.input_format_id)}</td><td>${esc(row.puid||'')}</td><td>${esc(row.label||'')}</td><td>${esc(row.governed_risk_label||row.governed_risk_level||'Not assessed')}</td><td>${esc(row.ai_risk_label||row.ai_risk_level||'—')}</td><td>${esc(row.ai_confidence??'—')}</td><td>${esc((row.ai_relation_to_governed||'—').replaceAll('_',' '))}</td><td>${esc(row.status||'')}</td></tr>`;}"
INDEX_HTML = _replace_once(INDEX_HTML, _old_preview, _new_preview, label="batch preview table")
