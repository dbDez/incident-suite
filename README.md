# Incident Suite — Multi-Agent DevOps Incident Analysis

> Upload ops logs → specialized agents classify incidents, map remediations from a runbook corpus (RAG), notify Slack, raise JIRA tickets, and synthesize an actionable cookbook checklist — orchestrated with LangGraph, with full agent-trace transparency.

**Eng Accelerator Hackathon — Topic 1.** Built by Pieter Sadie.

## Architecture

```
            ┌──────────────────────────────────────────────┐
            │              Gradio Operator Console          │
            │   (upload logs · live agent trace · outputs)  │
            └──────────────────┬───────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Log Ingest (side-   │   raw logs are parsed OUTSIDE
                    │  channel parser)     │   the LLM — agents only ever
                    └──────────┬──────────┘   see structured extracts
                               │
                ┌──────────────▼──────────────┐
                │   LangGraph Orchestrator     │
                └┬─────────┬─────────┬────────┘
                 │         │         │
     ┌───────────▼──┐ ┌────▼─────┐ ┌─▼──────────────┐
     │ Classifier   │ │Remediation│ │ Cookbook       │
     │ (structured  │ │ (RAG over │ │ Synthesizer    │
     │  JSON output)│ │ runbooks/)│ │ (checklist .md)│
     └───────────┬──┘ └────┬─────┘ └─┬──────────────┘
                 │         │         │
            ┌────▼───┐ ┌───▼────┐    │
            │ Slack  │ │ JIRA   │    │
            │notifier│ │ ticket │    │
            └────────┘ └────────┘    │
                                     ▼
                          incident-cookbook.md
```

### Design principles (ported from a production operator-console design)

1. **Side-channel doctrine** — raw log files never ride the LLM context. The ingest
   layer parses, deduplicates and windows the log outside the model; agents receive
   compact structured extracts only.
2. **Guarded actions** — the Remediation agent *proposes* fixes with rationale; it
   never executes anything. Slack/JIRA are the only outbound writes, both explicit.
3. **Structured outputs everywhere** — the Classifier emits a strict Pydantic JSON
   schema, so every downstream agent consumes deterministic input.
4. **Transparency** — the UI streams the LangGraph node trace live, so you can watch
   each agent claim, work, and hand off.
5. **Evaluated, not vibed** — `evals/` contains an Inspect AI task that scores the
   Classifier against known incidents seeded in the sample logs (LLM judge + rubric).

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env                              # add your OpenRouter key (Slack/JIRA optional)
python app.py                                     # opens the Gradio console
```

Try it immediately: load a file from `data/sample_logs/` in the UI.

## Evals

```bash
cd evals
inspect eval task_classifier.py --model openai/openai/gpt-4o-mini
inspect view
```

## Repo layout

| Path | What |
|---|---|
| `app.py` | Gradio operator console |
| `src/incident_suite/ingest.py` | Side-channel log parser |
| `src/incident_suite/graph.py` | LangGraph orchestrator |
| `src/incident_suite/agents/` | Classifier · Remediation · Notifier · JIRA · Cookbook |
| `src/incident_suite/integrations/` | Slack webhook + JIRA REST clients |
| `runbooks/` | Remediation knowledge corpus (RAG source) |
| `data/sample_logs/` | Reproducible demo incidents |
| `evals/` | Inspect AI eval of the Classifier agent |
