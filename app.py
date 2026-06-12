"""Incident Suite — Gradio operator console.

Upload a log (or pick a sample), optionally add a monitoring screenshot →
watch the agent trace stream live → read incidents, grounded plans,
Slack/JIRA outcomes and the synthesized cookbook.
"""

import tempfile
from pathlib import Path

import gradio as gr

from src.incident_suite import __version__
from src.incident_suite.graph import build_graph

SAMPLE_DIR = Path(__file__).parent / "data" / "sample_logs"


def run_suite(file_path: str | None, image_path: str | None):
    if not file_path:
        yield "Pick a log file first.", "", ""
        return

    graph = build_graph()
    trace_lines: list[str] = []
    pending: list[str] = []  # live in-progress lines since the last completed step
    last_state: dict = {}
    inputs = {"log_path": file_path, "image_path": image_path}

    for mode, chunk in graph.stream(inputs, stream_mode=["custom", "values"]):
        if mode == "custom":
            pending.append(f"   ⏳ {chunk}")
        else:
            last_state = chunk
            trace = chunk.get("trace", [])
            if len(trace) > len(trace_lines):
                trace_lines = trace
                pending = []  # superstep completed — its results replace the live lines
        yield (
            "\n".join(trace_lines + pending),
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


with gr.Blocks(title=f"Incident Suite v{__version__}") as demo:
    gr.Markdown(
        f"# 🚨 Incident Suite `v{__version__}`\n"
        "Multi-agent DevOps incident analysis — LangGraph orchestration, runbook RAG, "
        "web research, vision intake."
    )
    with gr.Row():
        with gr.Column(scale=1):
            file_in = gr.File(label="Ops log", type="filepath", file_types=[".log", ".txt"])
            image_in = gr.Image(
                label="Monitoring screenshot (optional)", type="filepath"
            )
            gr.Examples(
                examples=[[str(p)] for p in sorted(SAMPLE_DIR.glob("*.log"))],
                inputs=[file_in],
                label="Sample incidents",
            )
            run_btn = gr.Button("Analyze", variant="primary")
            trace_out = gr.Textbox(label="Agent trace (live)", lines=18)
        with gr.Column(scale=2):
            incidents_out = gr.Markdown(label="Incidents & plans")
            cookbook_out = gr.Markdown(label="Cookbook")

    diagram = _graph_diagram()
    if diagram:
        with gr.Accordion("Orchestration graph (rendered from the compiled LangGraph)", open=False):
            gr.Image(value=diagram, show_label=False, interactive=False)

    run_btn.click(
        run_suite, inputs=[file_in, image_in], outputs=[trace_out, incidents_out, cookbook_out]
    )

if __name__ == "__main__":
    demo.launch()
