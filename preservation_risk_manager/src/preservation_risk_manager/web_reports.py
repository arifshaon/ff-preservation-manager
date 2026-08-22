from __future__ import annotations

import csv
from datetime import datetime, timezone
from html import escape
from io import StringIO
import json
from pathlib import Path
import re
from typing import Any, Iterable
import zipfile

from preservation_risk_manager.format_identification import normalize_format_observation


_FORMAT_ID_HEADERS = {
    "format",
    "format_id",
    "formatid",
    "id",
    "pronom",
    "pronom_id",
    "pronom_puid",
    "puid",
}


def normalize_input_format_id(value: Any) -> str:
    text = str(value or "").strip().lstrip("\ufeff")
    if not text:
        return ""
    variants = normalize_format_observation(text)
    return variants[0] if variants else text


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = normalize_input_format_id(value)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _parse_csv(text: str) -> list[str]:
    rows = list(csv.reader(StringIO(text.lstrip("\ufeff"))))
    if not rows:
        return []

    header = [re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower()).strip("_") for value in rows[0]]
    format_column = next((index for index, value in enumerate(header) if value in _FORMAT_ID_HEADERS), None)
    start = 1 if format_column is not None else 0
    column = format_column if format_column is not None else 0

    values: list[str] = []
    for row in rows[start:]:
        if column >= len(row):
            continue
        value = str(row[column]).strip()
        if value:
            values.append(value)
    return _dedupe(values)


def parse_format_ids(text: str, *, filename: str | None = None) -> list[str]:
    """Parse pasted text or an uploaded TXT/CSV payload into distinct format IDs."""
    raw = str(text or "")
    if not raw.strip():
        return []
    name = str(filename or "").strip().lower()
    if name.endswith(".csv"):
        return _parse_csv(raw)

    values: list[str] = []
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        values.extend(part for part in re.split(r"[,;\t]+", stripped) if part.strip())
    return _dedupe(values)


def combine_format_id_inputs(
    *,
    entered_text: str | None,
    uploaded_text: str | None,
    uploaded_filename: str | None,
) -> list[str]:
    return _dedupe(
        parse_format_ids(entered_text or "")
        + parse_format_ids(uploaded_text or "", filename=uploaded_filename)
    )


def _percentage(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) * 100.0, 1)
    except (TypeError, ValueError):
        return None


def _source_name(item: dict[str, Any]) -> str:
    return str(
        item.get("source_label")
        or item.get("source_id")
        or item.get("source_type")
        or item.get("source_record_id")
        or "source"
    )


def _source_names(values: Any) -> str:
    names: list[str] = []
    for item in values or []:
        if not isinstance(item, dict):
            continue
        name = _source_name(item)
        if name not in names:
            names.append(name)
    return "; ".join(names)


def _governed_risk(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    context = result.get("external_risk_context") if isinstance(result.get("external_risk_context"), dict) else {}
    governed = context.get("policy_synthesized_risk")
    if isinstance(governed, dict):
        return governed
    registry = context.get("registry_synthesized_risk")
    return registry if isinstance(registry, dict) else {}


def _ai_synthesis(response: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    synthesis = response.get("ai_synthesis") if isinstance(response.get("ai_synthesis"), dict) else {}
    overall = synthesis.get("overall_synthesized_risk") if isinstance(synthesis.get("overall_synthesized_risk"), dict) else {}
    return synthesis, overall


def _synthesis_policy_from_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    for item in items:
        if not isinstance(item, dict):
            continue
        response = item.get("response") if isinstance(item.get("response"), dict) else {}
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        context = result.get("external_risk_context") if isinstance(result.get("external_risk_context"), dict) else {}
        policy = context.get("synthesis_policy")
        if isinstance(policy, dict) and isinstance(policy.get("semantic_levels"), list):
            return dict(policy)
        synthesis = response.get("ai_synthesis") if isinstance(response.get("ai_synthesis"), dict) else {}
        overall = synthesis.get("overall_synthesized_risk") if isinstance(synthesis.get("overall_synthesized_risk"), dict) else {}
        if overall.get("policy_id"):
            return {
                "policy_id": overall.get("policy_id"),
                "version": overall.get("policy_version"),
                "semantic_levels": [],
            }
    return {}


def _semantic_levels(policy: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configured = []
    for item in policy.get("semantic_levels") or []:
        if not isinstance(item, dict):
            continue
        level_id = str(item.get("id") or "").strip()
        if not level_id:
            continue
        configured.append({
            "id": level_id,
            "label": str(item.get("label") or level_id),
            "rank": int(item.get("rank", len(configured))),
        })
    if configured:
        return sorted(configured, key=lambda item: item["rank"])

    observed: list[str] = []
    for row in rows:
        for key in ("governed_risk_level", "ai_risk_level"):
            value = str(row.get(key) or "").strip()
            if value and value not in observed:
                observed.append(value)
    return [
        {"id": value, "label": value.replace("_", " ").title(), "rank": index}
        for index, value in enumerate(observed)
    ]


def summary_row(item: dict[str, Any]) -> dict[str, Any]:
    response = item.get("response") if isinstance(item.get("response"), dict) else {}
    deterministic = response.get("result") if isinstance(response.get("result"), dict) else {}
    identity = deterministic.get("format") if isinstance(deterministic.get("format"), dict) else {}
    puids = identity.get("puids") if isinstance(identity.get("puids"), list) else []
    governed = _governed_risk(response)
    ai_synthesis, ai_overall = _ai_synthesis(response)
    external = ai_synthesis.get("external_capability") if isinstance(ai_synthesis.get("external_capability"), dict) else {}

    # Older fill-gaps diagnostics remain available but are deliberately secondary
    # to the governed overall-risk result and optional AI overall synthesis.
    ai_questions = response.get("ai_risk_assessment") if isinstance(response.get("ai_risk_assessment"), dict) else {}
    ai_analysis = ai_questions.get("analysis") if isinstance(ai_questions.get("analysis"), dict) else {}

    error = response.get("error")
    if not error and response.get("status") not in {None, "ok"}:
        resolution = response.get("resolution") if isinstance(response.get("resolution"), dict) else {}
        error = resolution.get("status") or response.get("status")

    selected_scopes = governed.get("selected_scope_types") or []
    quality_warnings = ai_overall.get("quality_warnings") or []
    ai_status = ai_synthesis.get("status") or ai_questions.get("status")

    return {
        "input_format_id": item.get("input_format_id"),
        "status": response.get("status"),
        "resolved_format_id": identity.get("format_id"),
        "puid": puids[0] if puids else item.get("resolved_puid"),
        "label": identity.get("label"),
        "version": identity.get("version"),
        "governed_risk_level": governed.get("semantic_level"),
        "governed_risk_label": governed.get("semantic_label"),
        "governed_selected_scope": "; ".join(str(value) for value in selected_scopes),
        "governed_headline_sources": _source_names(governed.get("contributors")),
        "governed_context_sources": _source_names(governed.get("contextual_contributors")),
        "governed_unmapped_assessment_count": len(governed.get("unmapped_assessments") or []),
        "ai_status": ai_status,
        "ai_risk_level": ai_overall.get("semantic_level"),
        "ai_risk_label": ai_overall.get("semantic_label"),
        "ai_confidence": ai_overall.get("confidence"),
        "ai_relation_to_governed": ai_overall.get("governed_baseline_relation"),
        "ai_web_search_used": bool(external.get("web_search_used")) if ai_synthesis else None,
        "ai_external_source_count": len(external.get("sources") or []) if ai_synthesis else None,
        "ai_quality_warning_count": len(quality_warnings) if ai_synthesis else None,
        "framework_analysis_status": deterministic.get("analysis_status"),
        "framework_risk_band": deterministic.get("risk_band"),
        "framework_evidence_completeness_pct": _percentage(deterministic.get("evidence_completeness")),
        "framework_missing_count": deterministic.get("missing_count"),
        "criterion_claims_used": deterministic.get("criterion_claims_used"),
        "fill_gaps_ai_band": ai_analysis.get("analysed_band"),
        "error": error,
    }


def _level_counts(rows: list[dict[str, Any]], key: str, levels: list[dict[str, Any]]) -> dict[str, int]:
    level_ids = [str(item.get("id")) for item in levels if str(item.get("id") or "").strip()]
    counts = {level_id: 0 for level_id in level_ids}
    counts["unassessed"] = 0
    for row in rows:
        value = str(row.get(key) or "").strip()
        if value and value in counts and value != "unassessed":
            counts[value] += 1
        else:
            counts["unassessed"] += 1
    return counts


def report_document(
    *,
    framework: dict[str, Any],
    scope: str,
    institution_id: str | None,
    ai_mode: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = [summary_row(item) for item in items]
    policy = _synthesis_policy_from_items(items)
    levels = _semantic_levels(policy, rows)
    success_count = sum(1 for row in rows if row.get("status") == "ok")
    ai_success = sum(1 for row in rows if row.get("ai_status") == "ok")
    return {
        "report_type": "format_risk_batch",
        "report_schema_version": "2.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "framework": framework,
        "synthesis_policy": policy,
        "semantic_levels": levels,
        "scope": scope,
        "institution_id": institution_id,
        "ai_mode": ai_mode,
        "input_count": len(items),
        "successful_assessments": success_count,
        "failed_or_unresolved": len(items) - success_count,
        "governed_risk_counts": _level_counts(rows, "governed_risk_level", levels),
        "ai_successful_syntheses": ai_success,
        "ai_risk_counts": _level_counts(rows, "ai_risk_level", levels) if ai_mode == "synthesize" else None,
        "summary": rows,
        "items": items,
    }


def _json_for_html(value: Any) -> str:
    return escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _curator_html(report: dict[str, Any]) -> str:
    rows = report.get("summary") if isinstance(report.get("summary"), list) else []
    items = report.get("items") if isinstance(report.get("items"), list) else []
    levels = [item for item in report.get("semantic_levels") or [] if isinstance(item, dict) and item.get("id")]
    levels_desc = sorted(levels, key=lambda item: int(item.get("rank", 0)), reverse=True)
    labels = {str(item["id"]): str(item.get("label") or item["id"]) for item in levels}
    item_by_input = {str(item.get("input_format_id")): item for item in items if isinstance(item, dict)}

    table_rows: list[str] = []
    detail_sections: list[str] = []
    for index, row in enumerate(rows, start=1):
        input_id = str(row.get("input_format_id") or "")
        governed = str(row.get("governed_risk_label") or row.get("governed_risk_level") or "Not assessed")
        ai = str(row.get("ai_risk_label") or row.get("ai_risk_level") or "—")
        confidence = row.get("ai_confidence")
        confidence_text = f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "—"
        detail_id = f"detail-{index}"
        search_text = " ".join(str(row.get(key) or "") for key in (
            "input_format_id", "puid", "label", "governed_risk_level", "ai_risk_level",
            "governed_headline_sources", "governed_context_sources",
        )).lower()
        table_rows.append(
            f'<tr data-search="{escape(search_text, quote=True)}" '
            f'data-governed="{escape(str(row.get("governed_risk_level") or "unassessed"), quote=True)}">'
            f'<td><a href="#{detail_id}">{escape(input_id)}</a></td>'
            f'<td>{escape(str(row.get("puid") or ""))}</td>'
            f'<td>{escape(str(row.get("label") or ""))}</td>'
            f'<td><strong>{escape(governed)}</strong></td>'
            f'<td>{escape(str(row.get("governed_selected_scope") or ""))}</td>'
            f'<td>{escape(ai)}</td>'
            f'<td>{escape(confidence_text)}</td>'
            f'<td>{escape(str(row.get("ai_relation_to_governed") or "—").replace("_", " "))}</td>'
            f'<td>{escape(str(row.get("status") or ""))}</td>'
            '</tr>'
        )
        source_item = item_by_input.get(input_id) or {}
        response = source_item.get("response") if isinstance(source_item.get("response"), dict) else {}
        deterministic = response.get("result") if isinstance(response.get("result"), dict) else {}
        context = deterministic.get("external_risk_context") if isinstance(deterministic.get("external_risk_context"), dict) else {}
        synthesis, ai_overall = _ai_synthesis(response)
        assessments = context.get("assessments") or []
        considerations = ai_overall.get("considerations") or []
        external = synthesis.get("external_capability") if isinstance(synthesis.get("external_capability"), dict) else {}
        sources = external.get("sources") or []

        assessment_html = ''.join(
            '<li><strong>' + escape(_source_name(a)) + '</strong>: '
            + escape(str(a.get("native_label") or a.get("native_score") or ""))
            + ' → ' + escape(str(a.get("semantic_label") or a.get("semantic_level") or "unmapped"))
            + ' <span class="muted">(' + escape(str(a.get("scope_type") or "unspecified")) + ')</span></li>'
            for a in assessments if isinstance(a, dict)
        ) or '<li>No governed source-level risk assessment available.</li>'
        consideration_html = ''.join(
            '<li>' + escape(str(c.get("finding") or ""))
            + ' <span class="muted">[' + escape(str(c.get("basis") or ""))
            + '; ' + escape(str(c.get("risk_effect") or "")) + ']</span></li>'
            for c in considerations if isinstance(c, dict)
        ) or '<li>No AI considerations returned.</li>'
        source_links = ''.join(
            '<li><a href="' + escape(str(s.get("url") or ""), quote=True) + '">'
            + escape(str(s.get("title") or s.get("url") or "source")) + '</a></li>'
            for s in sources if isinstance(s, dict) and s.get("url")
        ) or '<li>No external web sources returned.</li>'
        detail_sections.append(f'''
<section id="{detail_id}" class="detail">
  <h2>{escape(str(row.get("label") or input_id))} <span class="muted">{escape(str(row.get("puid") or ""))}</span></h2>
  <div class="riskline"><strong>Governed risk:</strong> {escape(governed)} &nbsp; <strong>AI-assisted risk:</strong> {escape(ai)} &nbsp; <strong>AI confidence:</strong> {escape(confidence_text)}</div>
  <details open><summary>Governed source assessments</summary><ul>{assessment_html}</ul></details>
  <details><summary>AI rationale and considerations</summary>
    <p>{escape(str(ai_overall.get("rationale") or "No AI rationale returned."))}</p>
    <ul>{consideration_html}</ul>
    <p><strong>Uncertainty:</strong> {escape(str(ai_overall.get("uncertainty") or "—"))}</p>
  </details>
  <details><summary>External sources consulted by AI</summary><ul>{source_links}</ul></details>
  <details><summary>Full machine record</summary><pre>{_json_for_html(response)}</pre></details>
</section>''')

    governed_counts = report.get("governed_risk_counts") or {}
    count_parts = [f"{labels.get(str(item['id']), str(item['id']))}: {governed_counts.get(str(item['id']), 0)}" for item in levels_desc]
    count_parts.append(f"Unassessed: {governed_counts.get('unassessed', 0)}")
    count_text = " · ".join(count_parts)
    risk_options = ''.join(
        f'<option value="{escape(str(item["id"]), quote=True)}">{escape(str(item.get("label") or item["id"]))}</option>'
        for item in levels_desc
    ) + '<option value="unassessed">Unassessed</option>'
    policy = report.get("synthesis_policy") if isinstance(report.get("synthesis_policy"), dict) else {}
    policy_text = ""
    if policy.get("policy_id"):
        policy_text = f" · Policy: {policy.get('policy_id')} v{policy.get('version') or ''}".rstrip()

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Preservation Risk Batch Report</title>
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:#f5f7fa;color:#172033}}main{{max-width:1400px;margin:auto;padding:28px}}h1{{margin-bottom:6px}}.muted{{color:#667085;font-weight:400}}.summary,.detail{{background:#fff;border:1px solid #e2e7ef;border-radius:12px;padding:18px;margin:16px 0}}.controls{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}}input,select{{padding:9px 10px;border:1px solid #cbd3df;border-radius:8px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:9px;border-bottom:1px solid #edf0f4;text-align:left;vertical-align:top}}th{{background:#f8fafc;position:sticky;top:0}}.tablewrap{{overflow:auto;max-height:65vh}}a{{color:#175cd3}}details{{margin:12px 0;border-top:1px solid #edf0f4;padding-top:10px}}summary{{font-weight:700;cursor:pointer}}pre{{white-space:pre-wrap;overflow:auto;background:#f7f8fa;padding:12px;border-radius:8px;font-size:12px}}.riskline{{padding:10px;background:#f8fafc;border-radius:8px}}
</style></head><body><main>
<h1>Preservation Risk Batch Report</h1>
<p class="muted">Generated {escape(str(report.get("generated_at") or ""))} · AI mode: {escape(str(report.get("ai_mode") or "off"))}{escape(policy_text)}</p>
<section class="summary"><strong>{escape(count_text)}</strong><div class="controls"><input id="search" placeholder="Filter by format, PUID or source"><select id="risk"><option value="">All governed risks</option>{risk_options}</select></div>
<div class="tablewrap"><table><thead><tr><th>Input</th><th>PUID</th><th>Format</th><th>Governed risk</th><th>Scope</th><th>AI risk</th><th>AI confidence</th><th>AI relation</th><th>Status</th></tr></thead><tbody id="rows">{''.join(table_rows)}</tbody></table></div></section>
{''.join(detail_sections)}
<script>const q=document.getElementById('search'),r=document.getElementById('risk');function f(){{const s=q.value.toLowerCase(),v=r.value;document.querySelectorAll('#rows tr').forEach(x=>{{x.style.display=((!s||x.dataset.search.includes(s))&&(!v||x.dataset.governed===v))?'':'none'}})}}q.addEventListener('input',f);r.addEventListener('change',f);</script>
</main></body></html>'''


def write_report_artifacts(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "risk-report.json"
    csv_path = directory / "risk-report.csv"
    html_path = directory / "risk-report.html"
    zip_path = directory / "risk-report.zip"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")

    rows = report.get("summary") if isinstance(report.get("summary"), list) else []
    fieldnames = list(rows[0].keys()) if rows else ["input_format_id", "status", "error"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    html_path.write_text(_curator_html(report), encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.write(json_path, arcname=json_path.name)
        archive.write(html_path, arcname=html_path.name)

    return {
        "html": html_path.name,
        "csv": csv_path.name,
        "json": json_path.name,
        "zip": zip_path.name,
    }
