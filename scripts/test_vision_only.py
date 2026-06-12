"""Verify: screenshot-only analysis + thread-safe RAG build + token telemetry."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from src.incident_suite import telemetry  # noqa: E402
from src.incident_suite.graph import build_graph  # noqa: E402

telemetry.reset()
graph = build_graph()
final = {}
statuses = []
for mode, chunk in graph.stream(
    {"log_path": None, "image_path": str(ROOT / "data/sample_screenshots/monitoring-dashboard.png")},
    stream_mode=["custom", "values"],
):
    if mode == "custom":
        statuses.append(chunk)
    else:
        final = chunk

print("=== TRACE ===")
print("\n".join(final.get("trace", [])))
c = final.get("classification")
t = telemetry.snapshot()
print("=== RESULT ===")
print(f"incidents: {len(c.incidents) if c else 0} | plans: {len(final.get('plans', []))} "
      f"| cookbook: {len(final.get('cookbook', ''))} chars")
print(f"tokens: {t['total']:,} over {t['calls']} calls (~${t['cost_usd']})")
print(f"live statuses seen: {len(statuses)}")
ok = c and len(c.incidents) >= 2 and len(final.get("plans", [])) == len(c.incidents) and t["total"] > 0
print("VISION-ONLY SMOKE:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
