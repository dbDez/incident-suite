"""Headless end-to-end smoke test — runs the full graph on a sample log.

Usage:  python scripts/smoke.py [data/sample_logs/web-outage.log]
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.incident_suite.graph import build_graph  # noqa: E402
from src.incident_suite import rag  # noqa: E402


def main() -> int:
    log = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data/sample_logs/web-outage.log")

    t0 = time.time()
    chunks = rag.warm_up()
    print(f"[smoke] RAG index ready: {chunks} chunks ({time.time()-t0:.1f}s)")

    graph = build_graph()
    final = {}
    for state in graph.stream({"log_path": log, "image_path": None}, stream_mode="values"):
        final = state

    print("\n=== TRACE ===")
    print("\n".join(final.get("trace", [])))

    classification = final.get("classification")
    plans = final.get("plans", [])
    cookbook = final.get("cookbook", "")

    print("\n=== RESULT ===")
    print(f"incidents: {len(classification.incidents) if classification else 0}")
    print(f"plans:     {len(plans)}")
    print(f"cookbook:  {len(cookbook)} chars")
    print(f"total:     {time.time()-t0:.1f}s")

    ok = (
        classification is not None
        and len(classification.incidents) >= 2
        and len(plans) == len(classification.incidents)
        and len(cookbook) > 200
    )
    print("SMOKE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
