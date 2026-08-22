# AI Input Logging

AI request logging is disabled by default.

To record the exact application input handed to the configured AI provider, add `input_log_file` to the AI configuration:

```json
{
  "ai": {
    "provider": "azure_openai",
    "input_log_file": "logs/ai-inputs.jsonl"
  }
}
```

The path is resolved from the process working directory unless an absolute path is supplied. Parent directories are created automatically.

The log is append-only JSON Lines (`.jsonl`). Each AI call is one JSON object containing:

- execution sequence and UTC timestamp;
- provider and model/deployment identifier;
- call type (`generate`, `generate_with_capabilities`, or compatibility `research_web`);
- exact system/user/assistant/tool messages in the `AIRequest`;
- application-defined tools, required tool name, structured response schema, temperature, and output-token limit;
- effective external-research domain filters and automatic web tool choice for capability-driven calls.

For capability-driven synthesis, logging occurs after evidence compaction and TPM budgeting. The recorded system/user messages are therefore the actual bounded context handed to the provider, not the larger pre-compaction source material.

API keys and credentials are not written to the log.

## Security

The prompt itself may contain registry evidence, institution-scoped assessment evidence, internal notes, or other information supplied to the AI provider. Treat the log file as assessment data and protect it accordingly. Do not commit it to source control.

Remove `input_log_file` or set it to `null` to disable logging.
