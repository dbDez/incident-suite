"""Incident Suite — Gradio operator console.

Upload a log (or pick a sample), optionally add a monitoring screenshot →
watch the agent trace stream live → read incidents, grounded plans,
Slack/JIRA outcomes and the synthesized cookbook.
"""

import tempfile
from pathlib import Path

import gradio as gr

from src.incident_suite import __version__, rag, telemetry
from src.incident_suite.graph import build_graph

SAMPLE_DIR = Path(__file__).parent / "data" / "sample_logs"


def kb_stats_md() -> str:
    s = rag.index_stats()
    return (
        f"**Knowledge base:** {s['runbooks']} runbooks → {s['chunks']} chunks "
        f"(heading-aware, embedded locally with `bge-small-en-v1.5`)"
    )


def add_runbook_ui(file_path: str | None):
    if not file_path:
        return "Upload a markdown runbook first.", kb_stats_md()
    chunks = rag.add_runbook(file_path)
    name = Path(file_path).name
    lines = [f"✅ **{name}** added and indexed — split into {len(chunks)} chunks:\n"]
    for c in chunks:
        lines.append(f"- `{name} → {c['section']}` ({c['words']} words) — _{c['preview']}…_")
    lines.append("\nRe-run an analysis: incidents matching this runbook will now cite it.")
    return "\n".join(lines), kb_stats_md()


def _tokens_md() -> str:
    s = telemetry.snapshot()
    return (
        f"🔢 **Tokens:** {s['total']:,} (prompt {s['prompt']:,} · completion "
        f"{s['completion']:,}) · {s['calls']} LLM calls · ≈ ${s['cost_usd']}"
    )


def run_suite(file_path: str | None, image_path: str | None, log_text: str = ""):
    if not file_path and (log_text or "").strip():
        pasted = Path(tempfile.gettempdir()) / "pasted.log"
        pasted.write_text(log_text, encoding="utf-8")
        file_path = str(pasted)
    if not file_path and not image_path:
        yield "—", "", "Provide a log file, pasted log text, a screenshot — or any combination.", "", ""
        return

    telemetry.reset()
    graph = build_graph()
    trace_lines: list[str] = []
    pending: list[str] = []  # live in-progress lines since the last completed step
    last_state: dict = {}
    now_running = "▶ starting…"
    inputs = {"log_path": file_path, "image_path": image_path}

    for mode, chunk in graph.stream(inputs, stream_mode=["custom", "values"]):
        if mode == "custom":
            pending.append(f"   ⏳ {chunk}")
            now_running = f"▶ **{chunk}**"
        else:
            last_state = chunk
            trace = chunk.get("trace", [])
            if len(trace) > len(trace_lines):
                trace_lines = trace
                pending = []  # superstep completed — its results replace the live lines
        yield (
            now_running,
            _tokens_md(),
            "\n".join(trace_lines + pending),
            _render_incidents(last_state),
            last_state.get("cookbook", ""),
        )

    yield (
        "✅ **Run complete**",
        _tokens_md(),
        "\n".join(trace_lines),
        _render_incidents(last_state),
        last_state.get("cookbook", ""),
    )


def _render_incidents(state: dict) -> str:
    classification = state.get("classification")
    if not classification:
        return ""
    plans = {p.incident_id: p for p in state.get("plans", [])}
    tickets = {t.incident_id: t for t in state.get("tickets", [])}
    out = [f"**Summary:** {classification.summary}\n"]
    for inc in classification.incidents:
        out.append(f"### [{inc.severity.value.upper()}] {inc.title}")
        out.append(
            f"`{inc.affected_component}` · ×{inc.occurrence_count} · first seen {inc.first_seen}"
        )
        plan = plans.get(inc.incident_id)
        if plan:
            out.append(f"\n**Plan** ({plan.runbook_source or 'first principles'}):")
            for s in plan.steps:
                out.append(f"{s.order}. {s.action}")
            if plan.citations:
                out.append(
                    "\n📚 _Grounded in: "
                    + "; ".join(f"{c.source}→{c.section} ({c.score})" for c in plan.citations)
                    + "_"
                )
            if plan.web_sources:
                out.append(
                    "🌐 _Research: "
                    + "; ".join(f"[{w.title}]({w.url})" for w in plan.web_sources)
                    + "_"
                )
            if plan.escalate:
                out.append("\n🚨 **Escalation required before action**")
        t = tickets.get(inc.incident_id)
        if t and t.ticket_url:
            out.append(f"\n🎫 [{t.ticket_key}]({t.ticket_url})")
        out.append("")
    return "\n".join(out)


def _graph_diagram() -> str | None:
    """Render the actual compiled LangGraph as a PNG (best-effort)."""
    try:
        png = build_graph().get_graph().draw_mermaid_png()
        path = Path(tempfile.gettempdir()) / "incident_suite_graph.png"
        path.write_bytes(png)
        return str(path)
    except Exception:
        return None


# Gradio's built-in icon buttons have aria-labels but no hover text — mirror
# every aria-label into a native title tooltip, including late-rendered nodes.
TOOLTIP_JS = """
() => {
  const apply = () => document
    .querySelectorAll('button[aria-label]:not([title]), [data-testid][aria-label]:not([title])')
    .forEach(el => el.title = el.getAttribute('aria-label'));
  apply();
  new MutationObserver(apply).observe(document.body, {subtree: true, childList: true});
}
"""

with gr.Blocks(title=f"Incident Suite v{__version__}", js=TOOLTIP_JS) as demo:
    gr.Markdown(
        f"# 🚨 Incident Suite `v{__version__}`\n"
        "Multi-agent DevOps incident analysis — LangGraph orchestration, runbook RAG, "
        "web research, vision intake."
    )
    with gr.Row():
        with gr.Column(scale=1):
            file_in = gr.File(label="Ops log", type="filepath", file_types=[".log", ".txt"])
            text_in = gr.Textbox(
                label="…or paste log text",
                lines=3,
                placeholder="Paste raw log lines here instead of uploading a file",
            )
            image_in = gr.Image(
                label="Monitoring screenshot (optional — works alone too)",
                type="filepath",
                sources=["upload", "clipboard"],
            )
            gr.Examples(
                examples=[[str(p)] for p in sorted(SAMPLE_DIR.glob("*.log"))],
                inputs=[file_in],
                label="Sample incidents",
            )
            run_btn = gr.Button("Analyze", variant="primary")
            running_out = gr.Markdown("—")
            tokens_out = gr.Markdown("")
            trace_out = gr.Textbox(label="Agent trace (live)", lines=18)
        with gr.Column(scale=2):
            incidents_out = gr.Markdown(label="Incidents & plans")
            cookbook_out = gr.Markdown(label="Cookbook")

    with gr.Accordion("📚 Knowledge base — add a runbook (live RAG re-index)", open=False):
        kb_stats = gr.Markdown(kb_stats_md())
        with gr.Row():
            runbook_in = gr.File(
                label="New runbook (.md)", type="filepath", file_types=[".md"]
            )
            add_btn = gr.Button("Add to knowledge base")
        chunks_out = gr.Markdown()
        add_btn.click(add_runbook_ui, inputs=[runbook_in], outputs=[chunks_out, kb_stats])

    diagram = _graph_diagram()
    if diagram:
        with gr.Accordion("Orchestration graph (rendered from the compiled LangGraph)", open=False):
            gr.Image(value=diagram, show_label=False, interactive=False)

    run_btn.click(
        run_suite,
        inputs=[file_in, image_in, text_in],
        outputs=[running_out, tokens_out, trace_out, incidents_out, cookbook_out],
    )

if __name__ == "__main__":
    demo.launch()
