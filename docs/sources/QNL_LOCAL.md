# QNL / institutional evidence

## What it is

The project supports institution-specific evidence and policy overlays in addition to global external sources.

This material is local to the institution. There is no public upstream URL unless the institution deliberately publishes one.

## Current configured QNL policy source

`sources.qnl.json` contains a disabled institutional policy adapter:

```json
{
  "id": "qnl_policy_current",
  "type": "institution_policy_xlsx",
  "enabled": false,
  "required": true,
  "institution_id": "qnl",
  "institution_name": "Qatar National Library",
  "institution_format_id_prefix": "QNL",
  "uris": [
    "input/QNL File Format Policy and Action Plan_27_November_2025.xlsx"
  ]
}
```

It remains disabled until the institutional policy overlay is deliberately integrated into the active registry workflow.

## Role

Institution evidence can describe facts such as:

```text
local software/tool availability
local preservation capability
local migration pathway
institution-specific policy/category/action
local readiness/exposure
```

These statements must not automatically become universal facts about the file format.

Example:

```text
"QNL does not currently have tool X"
```

is an institution-scoped observation, not:

```text
"No preservation tool exists for this format"
```

## Scope model

Institutional evidence should retain:

```text
institution_id = qnl
source_independence = institution_scoped
```

or the equivalent explicit institutional scope in the relevant persisted object.

Global Risk Manager requests exclude institution-scoped evidence. Institution-scoped requests may use global evidence plus matching institutional evidence.

## Privacy / AI boundary

When institution-scoped/private assessment evidence is present, the current capability-driven AI workflow suppresses public web-search tooling for that call.

The configured AI provider still receives the assessment prompt unless the deployment/operator chooses not to run AI at all. Apply institutional information-governance rules when selecting the provider.

## Adding/updating a local QNL dataset

1. place the reviewed source file in an approved local path;
2. configure its adapter/field map without committing sensitive data;
3. set `institution_id` explicitly;
4. run extraction/reconciliation/mapping in isolation;
5. verify that local claims are not promoted to global evidence;
6. review any local policy or readiness mappings;
7. integrate through the normal Registry Builder storage path;
8. test both global and `--institution qnl` Risk Manager behavior.

Do not paste local evidence directly into MongoDB if that bypasses source/run provenance.

## Relevant module references

- [`../../qnl_format_registry_builder/docs/INSTITUTIONAL_OVERLAYS.md`](../../qnl_format_registry_builder/docs/INSTITUTIONAL_OVERLAYS.md)
- [`../../qnl_format_registry_builder/docs/QNL_INSTITUTION_FORMAT_EVIDENCE.md`](../../qnl_format_registry_builder/docs/QNL_INSTITUTION_FORMAT_EVIDENCE.md)
- [`../../qnl_format_registry_builder/docs/PRESERVATION_METHOD_PROFILES.md`](../../qnl_format_registry_builder/docs/PRESERVATION_METHOD_PROFILES.md)

## No external URL

Unlike PRONOM, LOC, NARA, DPC and Wikidata, this source is institution-supplied. The authoritative location is the reviewed local document/configuration managed by QNL, not a public URL hard-coded in this repository.
