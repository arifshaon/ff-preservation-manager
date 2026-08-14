# Storage and export configuration example

This file shows the intended shape of the next-generation pipeline config.

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "qnl_format_registry"
  },
  "exports": [
    {
      "type": "json",
      "enabled": true,
      "path": "output/latest/registry.json"
    },
    {
      "type": "jsonl",
      "enabled": true,
      "path": "output/latest/registry.jsonl"
    },
    {
      "type": "csv",
      "enabled": true,
      "path": "output/latest/registry.csv"
    },
    {
      "type": "sqlite",
      "enabled": false,
      "path": "output/latest/registry.sqlite"
    },
    {
      "type": "markdown_report",
      "enabled": true,
      "path": "output/latest/coverage_report.md"
    }
  ]
}
```

The current pipeline still writes exports directly. The next refactor should route these through exporter adapters.
