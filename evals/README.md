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

```bash
pip install inspect-ai
inspect eval task_classifier.py --model openai/openai/gpt-4o-mini
inspect eval task_classifier.py --model openai/anthropic/claude-sonnet-4-6   # compare models
inspect view
```

Uses the same OpenRouter key as the app (`OPENAI_API_KEY`/`OPENAI_BASE_URL`
per Inspect AI's openai provider convention — see `.env.example`).
