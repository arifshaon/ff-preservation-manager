# LOC FDD–PRONOM–Wikidata crosswalk

The Library of Congress publishes a monthly CSV mapping Format Description Document (FDD) identifiers to PRONOM PUIDs and Wikidata QIDs. LOC also documents that these links are not always exact identity equivalences: FDDs, PRONOM, and Wikidata may describe different hierarchy or granularity levels.

For that reason, `loc_fdd_mapping_csv` is intentionally an **evidence-only** source. It snapshots and parses the official CSV, preserves source rows and match/status/note fields, and records copied PUID/QID assertions as unverified namespace claims. It does not create canonical records and it does not automatically merge FDDs to PRONOM/Wikidata identities.

The LOC FDD XML source remains the authority for the FDD identifier itself. PRONOM remains the authority for PUIDs. Wikidata remains the authority for QIDs.

Current pinned review source:

- mapping date: `20260713`
- CSV: `https://www.loc.gov/preservation/digital/formats/mappings/fdd-puid-qid-20260713.csv`
- mapping page: `https://www.loc.gov/preservation/digital/formats/fdd/fdd_puid_qid.shtml`

Review acquisition:

```powershell
python -m registry_builder.loc_fdd_mapping_download `
  --out loc-fdd-puid-qid-20260713.json `
  --workdir work
```

After the real CSV schema and mapping-status vocabulary are reviewed, an explicit mapping policy can promote only approved exact-equivalence relationships into reconciliation. Broad family, version-mismatched, combo-pack, or otherwise non-exact relationships must remain contextual cross-references.

LOC sustainability factors are handled separately by the FDD XML adapter and the approved LOC criterion mapping. The official top-level sustainability framework has seven factors: Disclosure, Adoption, Transparency, Self-documentation, External dependencies, Impact of patents, and Technical protection mechanisms. Documentation text may be retained as supporting disclosure evidence but is not an eighth top-level factor.
