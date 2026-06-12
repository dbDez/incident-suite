# Evals — Incident Classifier

Inspect AI eval that scores the Log Classifier agent against **known incidents
deliberately seeded** into `data/sample_logs/`. Pattern follows the Eng Acc
evals session (LLM judge + deterministic criteria checklist).

For each sample log the judge checks, per known incident:

- **D1** — was the incident identified at all?
- **D2** — is the assigned severity within one level of expected?
- **D3** — is the evidence grounded in real log lines (no hallucinated quotes)?

Grade: CORRECT ≥ 0.8 weighted, PARTIAL ≥ 0.5.

## Run

Inspect AI reaches OpenRouter through its `openai/` provider — point it at
OpenRouter with two env vars (same key the app uses):

```bash
# Windows (PowerShell)
$env:OPENAI_API_KEY  = "<your OpenRouter key>"
$env:OPENAI_BASE_URL = "https://openrouter.ai/api/v1"

# macOS/Linux
export OPENAI_API_KEY=<your OpenRouter key>
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
```

Then, from the repo root:

```bash
cd evals
inspect eval task_classifier.py --model openai/openai/gpt-4o-mini
inspect eval task_classifier.py --model openai/anthropic/claude-sonnet-4-6   # compare models
inspect view
```

(Model ids are `openai/<openrouter-model-id>` — the first `openai/` selects
Inspect's provider, the rest is the OpenRouter model path.)
