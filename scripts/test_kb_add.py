"""Verify add_runbook chunks + indexes, then revert (keeps the demo runbook staged)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.incident_suite import rag  # noqa: E402

print("stats before:", rag.index_stats())
chunks = rag.add_runbook(ROOT / "data/sample_runbooks/batch-job-sla-breach.md")
print("chunks created:", len(chunks))
for c in chunks:
    print(f"  - {c['section']} ({c['words']} words)")
print("stats after:", rag.index_stats())

(ROOT / "runbooks/batch-job-sla-breach.md").unlink()
rag._store.cache_clear()
print("reverted — demo runbook stays staged at data/sample_runbooks/ for the camera")
