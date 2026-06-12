# Incident Suite — Multi-Agent DevOps Incident Analysis

> Upload ops logs (and optionally a monitoring screenshot) → specialized agents classify incidents, ground remediation plans in a runbook corpus via RAG, enrich them with live web research, notify Slack, raise JIRA tickets, and synthesize an actionable cookbook — orchestrated with LangGraph, with full agent-trace transparency and an Inspect AI eval suite.

**Eng Accelerator Hackathon — Topic 1.** Built by Pieter Sadie.

![Incident Suite operator console — live agent trace, grounded plans, citations](docs/02-analysis.png)

## Architecture

```
        ┌────────────────────────────────────────────────────┐
        │               Gradio Operator Console               │
        │  upload log + optional screenshot · live trace · UI │
        └───────────────────────┬────────────────────────────┘
                                │
                 ┌──────────────▼──────────────┐
                 │ Ingest (side-channel parser) │←─ 👁 Vision intake
                 │ raw log NEVER enters the LLM │   (screenshot → observations)
                 └──────────────┬──────────────┘
                                │
                 ┌──────────────▼──────────────┐
                 │  🔎 Classifier (structured    │
                 │     JSON output, Pydantic)   │
                 └──────────────┬──────────────┘
                                │  LangGraph Send API — one parallel
                                │  branch PER incident (map-reduce)
              ┌─────────────────┼─────────────────┐
        ┌─────▼─────┐     ┌─────▼─────┐     ┌─────▼─────┐
        │ 🛠 Remediate│     │ 🛠 Remediate│ ... │ 🛠 Remediate│
        │ 📚 RAG over │     │ 📚 + 🌐 web │     │  (per      │
        │  runbooks/  │     │   research  │     │  incident) │
        └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
              └─────────────────┼─────────────────┘
              ┌─────────────────┼─────────────────┐
         ┌────▼────┐      ┌─────▼────┐      ┌─────▼─────┐
         │ 💬 Slack │      │ 🎫 JIRA  │      │ 📕 Cookbook │
         │ notifier │      │ tickets  │      │ checklist  │
         └─────────┘      └──────────┘      └───────────┘
```

## Tech stack

| Layer | Tech |
|---|---|
| Orchestration | **LangGraph** — `StateGraph`, conditional edges, **Send API map-reduce** (parallel branch per incident), implicit joins |
| Agents & contracts | **LangChain** structured outputs over **Pydantic** schemas at every boundary |
| RAG | **Chroma** vector store + **FastEmbed** local embeddings (`BAAI/bge-small-en-v1.5`, ONNX — no API key) + `MarkdownHeaderTextSplitter` heading-aware chunking with scored citations |
| Models | **OpenRouter** (one key, any model) — text + vision |
| Web research | **Tavily** search per incident (optional, graceful skip) |
| UI | **Gradio** — streaming agent trace, graph diagram rendered from the compiled LangGraph |
| Evals | **Inspect AI** — LLM judge vs deterministic known-incidents checklist |

## Design principles

1. **Side-channel doctrine** — raw log files never ride the LLM context. The ingest
   layer parses, deduplicates and windows the log in Python; agents receive compact
   structured extracts only.
2. **Guarded actions** — the Remediation agent *proposes* steps with rationale and
   per-step risk; it never executes anything. Slack/JIRA are the only outbound
   writes, both explicit and severity-gated.
3. **Structured outputs everywhere** — every agent boundary is a strict Pydantic
   schema; no free-text handoffs.
4. **Grounding over generation** — remediation plans cite their runbook chunks
   (with similarity scores) and web sources; ungrounded plans escalate to a human.
5. **Transparency** — the UI streams the LangGraph node trace live: ingest stats,
   incidents found, RAG hits with scores, research results, delivery outcomes.
6. **Evaluated, not vibed** — `evals/` scores the Classifier against incidents
   deliberately seeded in the sample logs.

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows (use Python 3.12)
pip install -r requirements.txt
cp .env.example .env                              # add your OpenRouter key
python app.py                                     # opens the Gradio console
```

Only `OPENROUTER_API_KEY` is required. Slack, JIRA and Tavily are optional —
agents report "skipped" gracefully. First run downloads the local embedding
model (~130 MB) once.

Try it immediately: pick a sample from `data/sample_logs/` in the UI.

## Evals

The classifier is scored with Inspect AI against incidents deliberately seeded
in the sample logs (LLM judge, deterministic known-incidents checklist —
identified? severity right? evidence grounded?). **Current result:
`accuracy 1.000` (2/2 samples CORRECT, gpt-4o-mini classifier, Sonnet judge).**

```bash
cd evals
inspect eval task_classifier.py --model openai/openai/gpt-4o-mini
inspect view
```

See `evals/README.md` for the OpenRouter env setup.

## Repo layout

| Path | What |
|---|---|
| `app.py` | Gradio operator console |
| `src/incident_suite/ingest.py` | Side-channel log parser |
| `src/incident_suite/vision.py` | Screenshot → observations (vision intake) |
| `src/incident_suite/rag.py` | Chroma + FastEmbed runbook RAG |
| `src/incident_suite/graph.py` | LangGraph orchestrator (Send API map-reduce) |
| `src/incident_suite/agents/` | Classifier · Remediation · Research · Cookbook |
| `src/incident_suite/integrations/` | Slack webhook + JIRA REST clients |
| `runbooks/` | Remediation knowledge corpus (12 runbooks, RAG source) |
| `data/sample_logs/` | Reproducible demo incidents |
| `data/sample_screenshots/` | Synthetic monitoring dashboard for the vision-intake demo (upload alongside a log) |
| `evals/` | Inspect AI eval of the Classifier agent |
