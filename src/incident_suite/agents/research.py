"""Web Research agent — Tavily search for live external context per incident:
known bugs, vendor advisories, similar outage reports. Degrades gracefully
when TAVILY_API_KEY is unset (the suite runs fully without it)."""

from __future__ import annotations

import os

from ..schemas import Incident, WebFinding


def investigate(incident: Incident) -> list[WebFinding]:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return []

    from tavily import TavilyClient  # imported lazily — optional dependency path

    client = TavilyClient(api_key=key)
    query = (
        f"{incident.title} {incident.affected_component} "
        f"{incident.category} root cause fix"
    )
    try:
        response = client.search(query=query, max_results=3, search_depth="basic")
    except Exception:
        return []  # research is enrichment, never a blocker

    return [
        WebFinding(
            title=r.get("title", "untitled"),
            url=r.get("url", ""),
            snippet=(r.get("content") or "")[:400],
        )
        for r in response.get("results", [])
    ]
