# Agent brief: restructure the documentation

**Audience: an AI coding agent (ChatGPT/Codex, Claude Code, or equivalent) with repository write access.**

You are restructuring the documentation of the `ff-preservation-manager` repository. This brief is
self-contained: every fact you need has been verified against the code and is recorded below. Do not
assume prior context.

Work through the phases in order. Each task has explicit acceptance criteria. Do not skip a phase
because a later one looks more interesting — Phase 1 unblocks users immediately and later phases
depend on the files it creates.

This brief is a work order, not permanent documentation. Delete it in your final commit once every
acceptance criterion in §8 passes.

**Baseline note:** as of writing, all relative links in the repository resolve and the test suite is
green (275 passed). You are starting from a clean state — any breakage after this point is yours.

---

## 1. Why this work exists

The repository has two active modules:

```text
qnl_format_registry_builder   builds the file-format evidence registry (writes MongoDB)
preservation_risk_manager     reads that registry and assesses preservation risk
```

The documentation is currently 58 markdown files / ~18,500 lines, organised **by topic**. It needs to
be organised **by audience and sequence**, because it has exactly two readers:

| Reader | Wants to know |
| --- | --- |
| **Operator** (runs it) | What do I install, which datasets do I load, in what order, where do the data files come from, how do I confirm MongoDB is populated, how do I then run the risk manager? |
| **Developer/admin** (extends it) | How do I add a dataset that isn't already supported, or change how the system works? |

Today both readers start at the same README and hit undifferentiated content. The single most
important structural fact:

> **Adding a dataset is not a separate destination. It is a prefix to the operator path.**
> A developer who adds a source must then run it like any other source. The developer track must
> therefore *terminate by handing off into the operator track*, not run parallel to it.

---

## 2. Ground rules

These are non-negotiable. Violating any of them makes the work unusable.

### 2.1 Do not change meaning

This is a documentation restructure. You are moving, merging, splitting and de-duplicating prose.

- **Never** change preservation semantics, authority rules, source roles, risk vocabulary, or
  governance/approval language. When merging two documents that describe the same rule differently,
  keep the more specific wording and flag the discrepancy in your summary — do not silently pick one.
- **Never** invent a URL, a pinned release, a commit hash, a SHA-256, or an expected record/claim
  count. Every such value must be copied verbatim from an existing document or config file. If a
  count does not already exist in the docs, write "no reviewed baseline count is documented" rather
  than computing or guessing one.
- **Never** edit files under `qnl_format_registry_builder/config/` or any `.py` file in this work.
  Configuration and code changes are out of scope (see §9 for items that need maintainer approval).

### 2.2 Preserve content when merging

When this brief says "merge A and B into C", the default is that **no substantive sentence is lost**.
Remove only genuine duplication — the same fact stated twice. If you are unsure whether two passages
are duplicates, keep both and note the overlap.

### 2.3 Every document declares its audience

Every documentation file you create or substantially edit begins with one of these two lines,
immediately after the H1 title:

```markdown
**Audience: operator.**
```

```markdown
**Audience: developer.**
```

A file contains content for its declared audience only. When a section would serve the other reader,
replace it with a link. This single convention is what stops the structure from re-tangling.

(A small number of shared references — `DATA_MODEL.md`, `REPOSITORY_ARCHITECTURE.md` — may use
`**Audience: operator and developer.**`. Use this sparingly; it is not an escape hatch.)

### 2.4 Shell examples

Existing docs are almost entirely PowerShell (~110 fenced `powershell` blocks vs 4 `bash` in the
builder docs). Backtick line continuations, `Test-Path`, `Copy-Item` and `@'…'@ | python -` heredocs
all fail on Linux and macOS.

For every command on the **operator critical path** (install, `registry_builder run`,
`storage_status`, the four backfills, the Wikidata verifier), provide both:

````markdown
```powershell
python -m registry_builder run `
  --config config/sources.qnl.pronom-only.json `
  --workdir work `
  --out out/pronom
```

```bash
python -m registry_builder run \
  --config config/sources.qnl.pronom-only.json \
  --workdir work \
  --out out/pronom
```
````

Elsewhere, one shell is sufficient. Use forward slashes in paths everywhere — they work on Windows
too, and several docs currently use `config\...` which works nowhere else.

### 2.5 Links

Use relative links. After every phase, run the link check in §8 and fix what you broke. A restructure
that leaves dangling links is a net loss.

---

## 3. Phase 0 — establish the baseline

Run these before changing anything. They confirm the environment works and give you the numbers you
will verify against at the end.

```bash
cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
python -m pytest -q          # expect: 275 passed
```

Record the current documentation inventory:

```bash
cd /path/to/ff-preservation-manager
find . -name "*.md" -not -path "./.git/*" -not -path "*/.pytest_cache/*" \
  -not -path "*/config/prompts/*" | wc -l          # expect: 58
find . -name "*.md" -not -path "./.git/*" -not -path "*/.pytest_cache/*" \
  -not -path "*/config/prompts/*" -exec cat {} + | wc -l   # expect: ~18486
```

**Do not commit** the `qnl_format_registry_builder.egg-info/` directory created by the install; it is
not currently gitignored (see Task 4.4).

---

## 4. Phase 1 — the two-track spine (highest priority)

This phase alone resolves the worst problem: a new user cannot find the MongoDB build path at all.

### Task 1.1 — Root README becomes a router

Edit `README.md` (repo root). Near the top, immediately after the one-paragraph description, add a
section that presents the two tracks and the ordered operator path. Suggested shape:

```markdown
## Which path are you on?

| You want to… | Start here |
| --- | --- |
| **Run the system** — build the registry and assess format risk | [Operator path](#operator-path) below |
| **Extend the system** — add a new dataset or change how it works | [Developer path](#developer-path) below |

### Operator path

1. Install — `qnl_format_registry_builder/docs/INSTALLATION.md`
2. Build the registry in MongoDB, one source at a time —
   `qnl_format_registry_builder/docs/BUILDING_THE_REGISTRY.md`
3. Confirm what was loaded — `qnl_format_registry_builder/docs/READING_THE_REGISTRY.md`
4. Assess risk — `preservation_risk_manager/README.md`

Want a 15-minute preview with no database? `docs/GETTING_STARTED.md`.

### Developer path

1. Architecture — `docs/REPOSITORY_ARCHITECTURE.md`
2. Data model — `docs/DATA_MODEL.md`
3. Add a new source — `docs/HOW_TO_ADD_A_SOURCE.md`
4. Contribute — `qnl_format_registry_builder/CONTRIBUTING.md`
```

Keep the existing AI-governance section and module table; move them below the router.

**Acceptance:** the root README links to `BUILDING_THE_REGISTRY.md` (the renamed runbook) within the
first screen of text, and states the build-then-assess order explicitly.

### Task 1.2 — Rename and split the runbook

`qnl_format_registry_builder/docs/PERSISTENT_INTEGRATION.md` (1,053 lines) is the best document in
the repository and is currently unreachable from any README. It is also two documents in one:

- lines 1–855 (`## 1.` through `## 12.`) — operator content
- lines 856–1053 (`## 13. TODO — make source operation more generic`, `## 14. Adding a new
  dataset/source`) — developer content

Do this:

1. `git mv qnl_format_registry_builder/docs/PERSISTENT_INTEGRATION.md \
      qnl_format_registry_builder/docs/BUILDING_THE_REGISTRY.md`
2. Add `**Audience: operator.**` under the title.
3. Move `## 13` into `qnl_format_registry_builder/docs/NEXT_STEPS.md` as a section titled
   "Making source operation more generic". Preserve its numbered TODO list verbatim.
4. Move `## 14` into `docs/HOW_TO_ADD_A_SOURCE.md` as an "Operational and authority checklist"
   section. Its eight steps overlap that document's seven steps — merge them rather than appending,
   keeping every distinct requirement.
5. Update every inbound link. Find them with:
   `grep -rn "PERSISTENT_INTEGRATION" --include="*.md" .`
   (13 references at time of writing, in `INSTALLATION_SETUP_AND_RUN.md`, `DOCUMENTATION_MAP.md`
   and `NEXT_STEPS.md`.)

**Acceptance:** `BUILDING_THE_REGISTRY.md` contains only operator content and ends at the current
§12 ("Failure rules for operators"), plus the new handoff section from Task 1.4. No file references
`PERSISTENT_INTEGRATION.md`.

### Task 1.3 — Link the runbook from every entry point

Add a link to `BUILDING_THE_REGISTRY.md` in:

- `README.md` (repo root) — done in Task 1.1
- `qnl_format_registry_builder/README.md` — add a row to its "Start here" table
- `docs/GETTING_STARTED.md` — add a closing section: the quickstart used in-memory storage; the
  production path is the source-by-source MongoDB build, link to it
- `docs/DOCUMENTATION_MAP.md` — add a row

**Acceptance:** `grep -rln "BUILDING_THE_REGISTRY" --include="*.md" .` returns at least these four
files.

### Task 1.4 — Close the loop to the risk manager

`BUILDING_THE_REGISTRY.md` currently contains **zero** mentions of `preservation_risk_manager`. After
§10 (final verification) the operator has a populated database and no documented next step.

Add a short section "§10.1 — Confirm the risk manager can read it" containing the persistent-store
handoff command. Copy it from `qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md` §20
("Relationship to the risk manager"), adapting the `--storage-config` argument to a production
`sources.qnl.*.json` config rather than the example config (see Defect D5 in §7).

**Acceptance:** an operator finishing the runbook has one command to run that proves the handoff.

### Task 1.5 — Add the missing clone step

There is **no `git clone` instruction anywhere in the repository** (verified: zero matches for
`git clone` across all markdown). Every install section begins at `cd qnl_format_registry_builder`.

Add clone + `cd` to the top of `docs/GETTING_STARTED.md` and to the install section of the new
`INSTALLATION.md` (Task 3.1).

### Task 1.6 — State the working-directory invariant

All `registry_builder` commands must run from the `qnl_format_registry_builder/` directory. This is
verified behaviour, not a convention: source `uris` and local file paths resolve against the current
working directory, so running the quickstart from the repository root fails with
`FileNotFoundError: 'examples/qnl_institution_format_evidence.seed.json'`.

Note that config paths resolve inconsistently, and document both rules:

| Config key | Resolved relative to |
| --- | --- |
| source `uris`, `local_file`, `local_files`, `archive_url`, `zip_uri`, `directory` | the current working directory |
| `criteria`, `mappings`, `storage_config`, `input_csv`, `out` in backfill configs | the config file's own directory |

Put the invariant in `INSTALLATION.md` §1 and the resolution table in
`qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md`.

---

## 5. Phase 2 — the source catalogue and per-source pages

This is the phase that delivers "which dataset, how to add it, where the files are, how it lands in
MongoDB". It is the highest-value new content.

### Task 2.1 — Create the per-source template

Create `qnl_format_registry_builder/docs/sources/_TEMPLATE.md` with exactly these headings:

```markdown
# <Source name>

**Audience: operator.**

## Role and authority boundary
<!-- What this source contributes. What it may NOT create (identity? risk? relationships?). -->

## Where the data comes from
<!-- Authoritative URL(s), pinned release/commit, licence or terms if known. -->

## Adapter and configuration
<!-- Adapter type name, production config file path. -->

## Run
<!-- The ingest command, PowerShell and bash. -->

## Verify
<!-- storage_status command with any documented expected counts. -->

## Governed follow-on stage
<!-- Criterion/risk/relationship backfill command, or "none". -->

## What appears in MongoDB
<!-- Collections written and, where documented, expected counts. -->

## Manual / local fallback
<!-- Where to place a manually downloaded file and which config key points at it. -->

## Stop conditions
<!-- When the operator must halt rather than improvise. -->
```

`qnl_format_registry_builder/docs/DPC_BIT_LIST_SOURCE.md` is the closest existing document to this
shape — read it first as a model.

### Task 2.2 — Create the source catalogue

Create `qnl_format_registry_builder/docs/SOURCE_CATALOGUE.md`, audience: operator. It contains one
table — the single source of truth for what gets loaded and from where. Populate it **only** with
the verified values in Appendix B of this brief. Do not add a column you cannot fill from existing
documents.

The catalogue must state the load order and why it is that order (authoritative format identities
before evidence-only and relationship-only sources).

**Acceptance:** every URL, pin and count in the catalogue can be traced to an existing doc or config
file. Every row links to its `sources/*.md` page.

### Task 2.3 — Write the per-source pages

Create one page per production source, from the template, folding in the existing documents listed:

| New file | Folds in |
| --- | --- |
| `sources/PRONOM.md` | `BUILDING_THE_REGISTRY.md` §2 |
| `sources/LOC_FDD.md` | §3, §5, `LOC_FDD_SUSTAINABILITY.md` |
| `sources/LOC_CROSSWALK.md` | §4, `LOC_FDD_CROSSWALK_SOURCE.md` |
| `sources/NARA.md` | §6, `NARA_ADAPTER_REQUIREMENTS.md`, `NARA_LOCAL_FILES.md` |
| `sources/DPC.md` | §7, `DPC_BIT_LIST_SOURCE.md`, `DPC_RISK_PERSISTENCE.md` |
| `sources/WIKIDATA.md` | §8, §9, `WIKIDATA_SOURCE.md`, `WIKIDATA_PRODUCTION_INTEGRATION.md` |
| `sources/QNL_INSTITUTION.md` | `QNL_INSTITUTION_FORMAT_EVIDENCE.md` |

The Wikidata merge is the largest win: `WIKIDATA_SOURCE.md` (400 lines) and
`WIKIDATA_PRODUCTION_INTEGRATION.md` (361 lines) both contain sections titled "Frozen production
contract", "Adapters", "Controlled refresh workflow", "Production drift gates", "Verified
changed-source simulation" and independent verification — and `BUILDING_THE_REGISTRY.md` §8–9 covers
the same operational steps a third time. Merge to one page; keep every distinct governance rule.

After each merge, `git rm` the folded-in source documents and fix inbound links.

**Acceptance:** `BUILDING_THE_REGISTRY.md` §2–§9 are replaced by a short ordered list linking to the
`sources/` pages. The runbook drops from ~1,053 to roughly 450 lines.

### Task 2.4 — Replace the five-document update rule

`qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md` ends with a section "Where to
document a new source" instructing developers to update **five** separate documents per source. That
burden is the root cause of the reference gaps in §7 — it is not being carried.

Delete that section. Replace it, in `docs/HOW_TO_ADD_A_SOURCE.md`, with:

> When your source works, document it in exactly two places: copy
> `qnl_format_registry_builder/docs/sources/_TEMPLATE.md` to `sources/<YOUR_SOURCE>.md` and fill it
> in, then add one row to `SOURCE_CATALOGUE.md`. That page is both the operator instruction and the
> reference — there is no third place to update.

This is the convergence point between the two tracks. Make it explicit that the developer's final
step hands off into the operator path.

---

## 6. Phase 3 — split the mixed-audience documents

### Task 3.1 — Split the install/run guide

`qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md` (510 lines) is operator content
except §18 ("Add a new source or criterion mapping") and §19 ("Add a storage backend"), lines
418–468.

- Operator part → `qnl_format_registry_builder/docs/INSTALLATION.md` (install, requirements, MongoDB
  setup, working-directory invariant) and `qnl_format_registry_builder/docs/CLI_REFERENCE.md`
  (§13–17: validate, collision report, evidence audit, mapping validate, claims backfill).
- §18 → merge into `docs/HOW_TO_ADD_A_SOURCE.md`.
- §19 → merge into `qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`.
- §20 → used by Task 1.4; then remove.

### Task 3.2 — Break up "Adding and running data sources"

`ADDING_AND_RUNNING_DATA_SOURCES.md` is 1,070 lines — the largest builder doc — and its title fuses
both audiences. It triplicates content:

- its "Seven-step source onboarding path" duplicates `docs/HOW_TO_ADD_A_SOURCE.md`'s seven steps
- its "Running NARA/PRONOM/LOC only with MongoDB" sections duplicate the runbook's §2/§3/§6
- its config blocks duplicate `ADAPTER_REFERENCE.md`

Split it:

| Content | Destination |
| --- | --- |
| Acquisition patterns 1–5, adapter class guidance | `ADAPTER_IMPLEMENTATION_GUIDE.md` |
| "Running X only with MongoDB" examples | the relevant `sources/*.md` — **but see below** |
| Seven-step path | delete — `docs/HOW_TO_ADD_A_SOURCE.md` is the single surviving copy |
| "Common mistakes to avoid" | new `qnl_format_registry_builder/docs/PITFALLS.md`, audience: developer |
| "Where to document a new source" | delete (Task 2.4) |

Then `git rm` the file.

**Do not carry the "Running X only with MongoDB" sections across verbatim.** Each one prints a JSON
config blob and then runs `--config config/nara.mongodb.local.json` (or `pronom.`/`loc.`) — a file
the reader is never told to create, and which does not exist. Worse, committed example configs
already do exactly this job:

```text
config/sources.nara.mongodb.example.json
config/sources.pronom.mongodb.example.json
config/sources.loc.mongodb.example.json
```

Replace each hand-written blob with a reference to the committed example config. (Note those examples
also use database `format_registry` — see §9.3.)

**Note:** the seven-step onboarding path currently exists in three places —
`docs/HOW_TO_ADD_A_SOURCE.md`, `ADDING_AND_RUNNING_DATA_SOURCES.md`, and as a nine-step variant in
`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md` Part A. Keep `docs/HOW_TO_ADD_A_SOURCE.md` as the
survivor; make the other two link to it.

### Task 3.3 — Rewrite the builder README as a router

`qnl_format_registry_builder/README.md` (426 lines) switches audience eight times. Reduce it to
roughly 120 lines: what the module is, the pipeline diagram, the two-track router, and links. Move
developer-facing sections ("AI-assisted source onboarding", "Storage and common interface", "Adding
sources/backends", "Tests") into the Track B documents.

### Task 3.4 — Merge the remaining overlapping pairs

| Merge | Into | Rationale |
| --- | --- | --- |
| `criterion_mapping_workflow.md` + `ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md` | `CRITERION_MAPPING.md` (developer) | 922 lines combined, overlapping step lists |
| `INCREMENTAL_SOURCE_UPDATES.md` + `REBUILD_FROM_STORED_SOURCE_RECORDS.md` | `UPDATING_AND_REBUILDING.md` (operator) | both cover re-running without re-acquiring; the second is currently unreachable |
| `METHOD_COVERAGE_NOTES.md` | appendix of `PRESERVATION_METHOD_PROFILES.md` | lessons-learned note, not a reference |

### Task 3.5 — Delete redundant navigation and history

`git rm` these:

| File | Reason |
| --- | --- |
| `qnl_format_registry_builder/docs/history/ADAPTER_REFACTOR_PLAN.md` | its own header says it records a completed refactor and must not be treated as current guidance |
| `qnl_format_registry_builder/docs/DOCUMENTATION_MAP.md` | three documentation maps (630 lines total) for 58 docs; keep the root one only |
| `preservation_risk_manager/docs/DOCUMENTATION_MAP.md` | same |

Before deleting the two module maps, fold any unique routing information into
`docs/DOCUMENTATION_MAP.md`, and restructure that file around the two tracks rather than its current
18-row by-role table.

---

## 7. Phase 4 — fill the verified reference gaps

These are factual omissions confirmed against the code. Fixing them is mechanical.

### Task 4.1 — Document the seven missing adapters

`qnl_format_registry_builder/docs/ADAPTER_REFERENCE.md` documents 8 of the 15 adapters registered in
`registry_builder/adapters/__init__.py`. Verify the current list yourself with:

```bash
cd qnl_format_registry_builder
python -c "from registry_builder.adapters import ADAPTERS; print(sorted(ADAPTERS))"
```

Missing at time of writing:

| Adapter type | Note |
| --- | --- |
| `loc_fdd_xml_reviewed` | **used by the production LOC config** `sources.qnl.loc-sustainability.json` |
| `dpc_bit_list` | full production source |
| `loc_fdd_mapping_csv` | LOC crosswalk, evidence-only |
| `loc_fdd_pronom_bridge` | approved bridge |
| `qnl_institution_format_evidence` | **used by the quickstart config** |
| `wikidata_sparql` | |
| `wikidata_sparql_evidence` | production Wikidata adapter |

Also mark `nara_preservation_csv` and `qnl_policy_xlsx` as deprecated compatibility aliases — the
code comments in `adapters/__init__.py` say so, but the reference does not.

**Acceptance:** every name printed by the command above has a `## \`<name>\`` section, and the two
deprecated aliases are labelled.

### Task 4.2 — Document the three missing MongoDB collections

`qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md` documents 11 collections. The code
reads/writes 14. These three have **zero mentions** in the file:

| Collection | Written by |
| --- | --- |
| `risk_assessment_claims` | NARA and DPC governed risk backfills (runbook steps 6 and 8) |
| `source_relationship_claims` | Wikidata relationship backfill (step 9) |
| `format_evidence_claims` | |

These are precisely the collections produced by the governed post-ingest stages — the second half of
the source-by-source build. Add them to the "Collection overview" table and give each a `##` section
matching the style of the existing ones. Derive field lists from the code that writes them
(`registry_builder/nara_risk_assessment_backfill.py`,
`registry_builder/dpc_risk_assessment_backfill.py`,
`registry_builder/wikidata_relationship_backfill.py`), not from guesswork.

Verify your work:

```bash
cd qnl_format_registry_builder
grep -rhoE '(query|upsert)\(\s*"[a-z_]+"' registry_builder/*.py registry_builder/**/*.py \
  | grep -oE '"[a-z_]+"' | tr -d '"' | sort -u
```

Every collection printed must appear in the schema doc.

### Task 4.3 — Recover the LOC–PRONOM bridge instructions

`BUILDING_THE_REGISTRY.md` §4 states that `config/external_identity_mappings/loc_fdd_pronom_20260713.policy-v2.json`
is absent from `main` (true) and that a fresh clone therefore "cannot reproduce the exact approved
LOC-PRONOM bridge". That is overstated — the repository ships the tools that generate it:

```text
registry_builder.loc_fdd_mapping_download    → loc-fdd-puid-qid-20260713.json
registry_builder.loc_fdd_mapping_review      → …review.json
registry_builder.loc_fdd_pronom_verify       → verification detail JSON
registry_builder.loc_fdd_pronom_bridge_approve --verification … --review … --out <policy JSON>
```

Document this regeneration chain in `sources/LOC_CROSSWALK.md`, with the existing caveat retained
prominently: the generated artifact is a **candidate**, and it is not "approved" until a named human
reviews it. Do not remove the warning that broad, family, version-mismatched and many-to-one
crosswalk rows were deliberately excluded during the original review.

### Task 4.4 — Fix the `.gitignore` / documented-paths mismatch

Five paths the runbook tells operators to create are not gitignored. Verified with `git check-ignore`:

| Path from the docs | Currently |
| --- | --- |
| `qnl_format_registry_builder/inputs/…` | **not ignored** — `.gitignore` has `input/` (singular), the runbook says `inputs/` (plural) |
| `qnl_format_registry_builder/out/…` | **not ignored** — `.gitignore` has `output/`; the CLI default and the runbook both use `out/` |
| `qnl_format_registry_builder/config/sources.local.*.json` | **not ignored** — runbook §1.4 tells operators to create these |
| `qnl_format_registry_builder/wikidata-file-formats-policy-v3.csv` | **not ignored** — runbook §8 requires this exact path |
| `qnl_format_registry_builder/*.egg-info/` | **not ignored** — created by the documented install command |

Note the split runs along document lines: `ADAPTER_REFERENCE.md`, `ADDING_AND_RUNNING_DATA_SOURCES.md`
and `INSTITUTIONAL_OVERLAYS.md` use `input/` (ignored); `BUILDING_THE_REGISTRY.md` and
`INSTALLATION_SETUP_AND_RUN.md` use `inputs/` (not ignored) across 19 references.

Pick **one** directory name, make every document use it, and extend `.gitignore` to cover all five
paths. `.gitignore` is the one non-documentation file you may edit in this work.

### Task 4.5 — Link the orphaned documents

Six builder documents are referenced by no other markdown file:

```text
DPC_BIT_LIST_SOURCE.md
DPC_RISK_PERSISTENCE.md
LOC_FDD_CROSSWALK_SOURCE.md
LOC_FDD_SUSTAINABILITY.md
REBUILD_FROM_STORED_SOURCE_RECORDS.md
RISK_ASSESSMENTS.md
```

The first four are absorbed by Task 2.3 and the fifth by Task 3.4. `RISK_ASSESSMENTS.md` survives —
link it from `READING_THE_REGISTRY.md` and the documentation map.

Re-run the orphan check after Phase 4 (script in §8); the only acceptable orphans are the root
`README.md` and `docs/DOCUMENTATION_MAP.md`.

---

## 8. Verification

Run all of these before declaring the work complete.

### 8.1 Tests still pass

```bash
cd qnl_format_registry_builder && python -m pytest -q     # expect: 275 passed
```

### 8.2 No dangling relative links

```bash
cd /path/to/ff-preservation-manager
python - <<'PY'
import pathlib, re
root = pathlib.Path(".")
bad = []
for md in root.rglob("*.md"):
    if ".git" in md.parts or ".pytest_cache" in md.parts:
        continue
    for link in re.findall(r"\]\(([^)#][^)]*)\)", md.read_text(encoding="utf-8")):
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        target = (md.parent / link.split("#")[0]).resolve()
        if not target.exists():
            bad.append(f"{md}: {link}")
print("\n".join(bad) or "all relative links resolve")
PY
```

**Must print** `all relative links resolve`.

### 8.3 No orphaned documents

```bash
for f in $(find . -name "*.md" -not -path "./.git/*" -not -path "*/.pytest_cache/*" \
           -not -path "*/config/prompts/*"); do
  b=$(basename "$f")
  n=$(grep -rl "$b" --include="*.md" . | grep -v "/$b$" | wc -l)
  [ "$n" -eq 0 ] && echo "ORPHAN: $f"
done
```

Only the root `README.md`, `docs/DOCUMENTATION_MAP.md` and this brief may appear.

### 8.4 Adapter and collection coverage

Re-run the two commands in Tasks 4.1 and 4.2. Every adapter type and every collection name must
appear in the corresponding reference document.

### 8.5 Audience declarations

```bash
for f in $(find . -name "*.md" -not -path "./.git/*" -not -path "*/.pytest_cache/*" \
           -not -path "*/config/prompts/*"); do
  head -5 "$f" | grep -q "^\*\*Audience:" || echo "MISSING AUDIENCE: $f"
done
```

Only the root `README.md` may lack a declaration. Note that all 58 files currently lack one — the
convention is introduced by this work, so expect this check to fail loudly until Phase 3 is done.

### 8.6 The operator path is walkable

Read the root README as if you knew nothing, and follow only the links it gives you. Confirm you
reach, in order: install → MongoDB setup → the source catalogue → a per-source page with a run
command → a verification command → the risk manager. If any step requires a link that is not on the
page you are on, the spine is broken.

### 8.7 Documentation volume

Re-run the Phase 0 inventory. Expect roughly **18 files / ~5,800 lines** in the builder (from 34 /
10,336). If the line count has *grown*, you have added rather than consolidated — review Phase 3.

---

## 9. Out of scope — needs maintainer approval

Do **not** perform these. They are recorded so you do not "fix" them accidentally, and so the
maintainer can decide separately. Mention them in your final summary.

### 9.1 Duplicate approved LOC criterion mappings

`config/criterion_mappings/` contains both `loc_fdd_xml.v1.approved.json` and
`loc_fdd_xml.v2.approved.json`. Both are `review_status: approved`, both cover the same seven
`sustainability.*` criteria, and they use distinct rule IDs (`…v1` / `…v2`), so neither supersedes
the other.

Any command that points `--mappings` at the whole `config/criterion_mappings` directory — the
quickstart config, `INSTALLATION_SETUP_AND_RUN.md` §15/§16/§17, and
`config/criterion-claims-backfill.mongodb.example.json` — applies **both generations**. A verified
quickstart run produced 2,504 LOC claims covering only 1,278 distinct (canonical, criterion) pairs:
1,226 duplicated. The production LOC backfill is unaffected because it targets the single v2 file.

Resolving this means retiring or relocating a config file. **You may document the hazard** — add a
warning wherever a doc tells the reader to pass a mapping *directory* — but do not move or edit the
config.

### 9.2 Misleading `mapping_versions` in the run report

`registry_builder/pipeline.py:173` builds `mapping_versions` as a dict keyed by `source_type`, so
when several mapping files share a source type, later files overwrite earlier ones. A verified run
reported `loc_fdd_xml: 2026-08-21-v2-draft2` — a `needs_review` draft that contributed zero claims.
`INSTALLATION_SETUP_AND_RUN.md` §8 tells operators to inspect this report. Code fix, not a docs fix.

### 9.3 The documentation points at the wrong database — 62 references

This is the most pervasive defect in the repository and the highest-value single fix. Treat it as the
maintainer's first decision, not a footnote.

Every production config (`config/sources.qnl.*.json`, and every `*.production.json` backfill config)
writes to database **`qnl_format_registry`**. But `config/storage.mongodb.example.json` and
`config/criterion-claims-backfill.mongodb.example.json` declare database **`format_registry`**, and
the documentation points readers at those example configs **62 times across 18 documents** — versus
only 3 documents that mention `qnl_format_registry` at all.

Verify for yourself:

```bash
grep -rho "storage.mongodb.example.json" --include='*.md' . | wc -l   # 62
grep -rl  "storage.mongodb.example.json" --include='*.md' . | wc -l   # 18
grep -rl  "qnl_format_registry\b"        --include='*.md' . | wc -l   #  3
```

Affected: `qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md` §15/§17,
`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`, `criterion_mapping_workflow.md`,
`STORAGE_AND_EXPORT_CONFIG.md`, `REBUILD_FROM_STORED_SOURCE_RECORDS.md`, `docs/GETTING_STARTED.md`,
the root `README.md`, and essentially every command example in the risk manager docs
(`INSTALLATION_SETUP_AND_RUN.md`, `CLI_REFERENCE.md`, `FORMAT_IDENTIFICATION.md`,
`AI_ASSISTED_ANALYSIS.md`, `AI_PROVIDER_INTERFACE.md`, `HUMAN_AND_SYSTEM_QUERIES.md`, `WEB_UI.md`,
`RISK_MONITORING_AND_REPORTING.md`, `RISK_ANALYSIS_WORKFLOW.md`, `REGISTRY_RISK_EVIDENCE_AUDIT.md`,
`README.md`).

**Why it matters:** an operator completes the source-by-source build into `qnl_format_registry`,
then follows any documented audit or risk-query example and silently queries an empty
`format_registry`. The result is unknowns and "Not Assessed" — which is precisely the failure the
docs elsewhere warn must never be read as format safety
(`INSTALLATION_SETUP_AND_RUN.md` §8). The system looks like it has no evidence when it is fully
populated.

Two possible fixes, both requiring maintainer approval because both touch `config/`:

- **Option A (one line):** change `database` to `qnl_format_registry` in
  `config/storage.mongodb.example.json` and `config/criterion-claims-backfill.mongodb.example.json`.
  All 62 references become correct at once. Risk: anyone with an existing local `format_registry`
  database silently starts pointing elsewhere.
- **Option B:** add a new `config/storage.qnl.mongodb.json` pointing at `qnl_format_registry`, leave
  the examples untouched, and repoint the 62 doc references. More edits, no behavioural surprise.

**What you may do without approval:** wherever a document tells the reader to pass
`storage.mongodb.example.json`, add a one-line warning that this example targets `format_registry`
and that a production build populates `qnl_format_registry`. Do not edit the config files.

---

## 10. How to work and what to hand back

### Commits

One commit per phase, on the branch you were given. Suggested messages:

```text
docs: add two-track spine and promote the MongoDB build runbook
docs: add source catalogue and per-source pages
docs: split mixed-audience documents by reader
docs: document missing adapters, collections and ignored paths
```

Use `git mv` for renames so history is preserved. Never force-push.

### Final summary

Report:

1. every file created, renamed and deleted;
2. the before/after file and line counts;
3. the output of all six checks in §8;
4. any place where two merged documents disagreed and you kept both (§2.2);
5. the three out-of-scope items from §9, restated for the maintainer.

If any acceptance criterion cannot be met, say so explicitly and explain why. Do not report the work
as complete with a check failing.

---

## Appendix A — the reading orders you are building toward

**Operator:**

```text
README.md
  -> INSTALLATION.md                 install, MongoDB up
  -> BUILDING_THE_REGISTRY.md        order, prerequisites, stop rules
  -> SOURCE_CATALOGUE.md             which datasets, from where
  -> sources/PRONOM.md … WIKIDATA.md load one at a time, verify each
  -> READING_THE_REGISTRY.md         what you now have
  -> preservation_risk_manager/README.md
```

**Developer:**

```text
README.md
  -> REPOSITORY_ARCHITECTURE.md
  -> DATA_MODEL.md
  -> ADAPTER_IMPLEMENTATION_GUIDE.md write the adapter
  -> HOW_TO_ADD_A_SOURCE.md          the one seven-step path
  -> CRITERION_MAPPING.md            map evidence to criteria
  -> sources/_TEMPLATE.md            ← hands off into the operator path
  -> CONTRIBUTING.md
```

---

## Appendix B — verified source data for the catalogue

Every value below was read from an existing document or config file. Use these; do not re-derive
them. Where a cell says "not documented", leave it empty rather than inventing a value.

**Load order and rationale:** authoritative format identities first (PRONOM, LOC, NARA), then
evidence-only sources (DPC), then relationship-only sources (Wikidata).

| # | Source | Adapter type | Production config | Data location | Pin |
| --- | --- | --- | --- | --- | --- |
| 1 | PRONOM | `pronom_registry` | `config/sources.qnl.pronom-only.json` | `https://github.com/nationalarchives/pronom/archive/refs/heads/develop.zip` | branch `develop` |
| 2 | LOC FDD XML | `loc_fdd_xml_reviewed` (source id `loc_fdd_xml`) | `config/sources.qnl.loc-sustainability.json` | `https://www.loc.gov/preservation/digital/formats/fddXML.zip` | current release |
| 3 | LOC crosswalk | `loc_fdd_mapping_csv` | `config/sources.qnl.loc-crosswalk-only.json` | `https://www.loc.gov/preservation/digital/formats/mappings/fdd-puid-qid-20260713.csv` | mapping date `20260713` |
| 3b | LOC–PRONOM bridge | `loc_fdd_pronom_bridge` | `config/sources.qnl.loc-crosswalk-bridge.json` | `config/external_identity_mappings/loc_fdd_pronom_20260713.policy-v2.json` — **absent from `main`**, regenerable per Task 4.3 | policy v2 |
| 4 | NARA | `nara_digital_preservation_framework` | `config/sources.qnl.nara-only.json` | two CSVs under `raw.githubusercontent.com/usnationalarchives/digital-preservation/master/` — `NARA_PreservationActionPlan_FileFormats_20260320.csv` and `NARA_File_Format_Risk_Matrix_20260320_Numbered.csv` | release `20260320` |
| 5 | DPC Global Bit List | `dpc_bit_list` | `config/sources.qnl.dpc-only.json` | `https://github.com/Digital-Preservation-Coalition/bit-list/archive/3ad3fef626ea7c128ef8c323d92227e5cae2efc8.zip` | edition 2025, commit `3ad3fef626ea7c128ef8c323d92227e5cae2efc8` |
| 6 | Wikidata | `wikidata_sparql_evidence` | `config/wikidata_relationship_backfill.production.json` | WDQS `https://query.wikidata.org/sparql` (no static file URL) | population policy `2026-08-20-v3` |

**Governed follow-on stages:**

| Source | Command | Production config |
| --- | --- | --- |
| LOC sustainability claims | `registry_builder criterion-claims backfill` | `config/loc_fdd_sustainability_backfill.production.json` |
| NARA risk claims | `python -m registry_builder.nara_risk_assessment_backfill` | `config/nara_risk_assessment_backfill.production.json` |
| DPC risk claims | `python -m registry_builder.dpc_risk_assessment_backfill` | `config/dpc_risk_assessment_backfill.production.json` |
| Wikidata relationships (first load) | `python -m registry_builder.wikidata_relationship_backfill` | `config/wikidata_relationship_backfill.production.json` |
| Wikidata refresh (later) | `python -m registry_builder.wikidata_refresh` | `config/wikidata_refresh.production.json` |

**Documented reviewed-baseline counts.** These are historical review baselines, not invariants — the
docs are explicit that a future source release may legitimately change them, and that an operator
must never edit an expected count to force a changed result through a gate. Carry that caveat over.

| Measure | Value |
| --- | --- |
| DPC source records | 84 (all `evidence_only`) |
| LOC criterion claims | 1,565 |
| NARA risk claims | 758, targeting 743 canonical formats (4 same-canonical conflicts deliberately preserved) |
| DPC risk claims | 51 |
| Wikidata evidence-only source records | 15,479 (snapshot SHA-256 `a6c1e598b567dd89557a67f186e99bf8486cddf40615384bbe998e450a1810df`) |
| Wikidata current relationship claims | 2,856 |
| Wikidata QIDs with relationships | 2,519 |
| Canonical formats with Wikidata relationships | 2,793 |
| Promoted Wikidata strong identifiers | 0 (invariant — Wikidata must never promote identity) |
| Wikidata risk assessments | 0 (invariant — Wikidata contributes no risk) |
| Final canonical formats | 3,372 |

No reviewed baseline count is documented for PRONOM or LOC FDD record counts. Leave those cells
empty.

**Known reproducibility gaps to carry forward, not paper over:**

- the approved LOC–PRONOM bridge artifact is not in `main` (Task 4.3 gives the regeneration chain,
  with human review still required);
- the approved 15,479-row Wikidata policy-v3 CSV is not distributed as a repository file; a live WDQS
  acquisition may legitimately differ from the approved baseline.
