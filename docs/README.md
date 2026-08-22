# Documentation

This is the canonical documentation entry point for File Format Preservation Manager.

The documentation is organized around two questions:

1. **How does the system work?** — architecture, data model, governance.
2. **How do I use it?** — installation, operations, sources, use cases, AI and API.

## Start here

| Topic | Document | Audience |
| --- | --- | --- |
| System overview and responsibility boundaries | [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md) | Everyone |
| Data model, evidence layers and persisted collections | [`DATA_MODEL.md`](DATA_MODEL.md) | Operators, developers, auditors |
| Installation | [`INSTALLATION.md`](INSTALLATION.md) | New operators |
| End-to-end operation and source refresh | [`OPERATIONS.md`](OPERATIONS.md) | Operators/curators |
| Add a new dataset/source | [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md) | Developers/data stewards |
| Integrated data sources and exact upstream locations | [`sources/README.md`](sources/README.md) | Operators/data stewards |
| One-format and batch-report examples | [`USE_CASES.md`](USE_CASES.md) | Curators/operators |
| AI provider configuration | [`AI_PROVIDERS.md`](AI_PROVIDERS.md) | Operators/developers |
| Web UI, REST API and Swagger | [`API_AND_SWAGGER.md`](API_AND_SWAGGER.md) | Curators/integrators |

## Main concepts

### Registry Builder

[`../qnl_format_registry_builder/`](../qnl_format_registry_builder/) owns acquisition and registry maintenance:

```text
source -> snapshot -> source record -> canonical identity
       -> governed evidence/claims -> persistent current view + history
```

Use it when you need to add or refresh preservation-data sources.

### Preservation Risk Manager

[`../preservation_risk_manager/`](../preservation_risk_manager/) owns assessment and presentation:

```text
format identifier -> resolve canonical format
                  -> collect governed source evidence
                  -> configurable governed synthesis
                  -> optional AI-assisted synthesis
                  -> human / JSON / batch / web report
```

Use it when you want to assess formats, monitor a watchlist, or expose the results through the web/API layer.

## Governance documents

These are part of the active operational design rather than introductory navigation:

- Risk terminology and synthesis configuration: [`../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md`](../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md)
- Risk monitoring/reporting internals: [`../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md)
- Framework questions: [`../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md`](../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md)
- MongoDB schema: [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md)
- Identifier reconciliation: [`../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md`](../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md)
- Incremental update semantics: [`../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md`](../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md)

## Advanced/reference documentation

Detailed implementation references remain inside each module, but they are not intended to be competing entry points.

### Registry Builder reference

[`../qnl_format_registry_builder/docs/`](../qnl_format_registry_builder/docs/)

Useful deep references include adapter implementation, source retrieval/fallbacks, criterion mapping, reconciliation, MongoDB storage and source-specific transformation notes.

### Risk Manager reference

[`../preservation_risk_manager/docs/`](../preservation_risk_manager/docs/)

Useful deep references include framework authoring, CLI reference, module reference, evidence audits and detailed AI internals.

## Recommended reading paths

### New operator

```text
README.md
 -> INSTALLATION.md
 -> OPERATIONS.md
 -> USE_CASES.md
 -> sources/README.md
```

### Curator using the Risk Manager

```text
USE_CASES.md
 -> AI_PROVIDERS.md (only if AI is required)
 -> API_AND_SWAGGER.md (only if using the web app/API)
```

### New source developer

```text
REPOSITORY_ARCHITECTURE.md
 -> DATA_MODEL.md
 -> HOW_TO_ADD_A_SOURCE.md
 -> relevant source guide in sources/
 -> module adapter/mapping reference as needed
```

### Auditor/reviewer

```text
DATA_MODEL.md
 -> RISK_SYNTHESIS_AND_TERMINOLOGY.md
 -> source-specific guide
 -> MongoDB schema / mapping / reconciliation references
```

## Documentation rule

Root documents explain the supported workflow. Module-level documents provide implementation/reference detail. Historical plans and superseded documentation maps should not be used as operational instructions.
