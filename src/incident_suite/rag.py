"""Runbook RAG — Chroma vector store + FastEmbed local embeddings.

Heading-aware chunking via LangChain's MarkdownHeaderTextSplitter so each
chunk carries its runbook + section breadcrumb. Embeddings run locally
(BAAI/bge-small-en-v1.5, ONNX) — no API key, fully reproducible by judges.

The index is built in-memory at startup; the corpus is small enough that a
fresh build costs seconds and can never go stale against runbooks/.
"""

from __future__ import annotations

import threading
from pathlib import Path

from itertools import count

from langchain_chroma import Chroma
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from .schemas import Citation, Incident

RUNBOOK_DIR = Path(__file__).resolve().parents[2] / "runbooks"

# Chroma returns cosine DISTANCE (lower = closer); we report similarity = 1-distance.
# bge-small similarities cluster high, so a flat floor lets unrelated runbooks
# leak in. Instead: if the BEST chunk isn't a confident match, retrieve nothing
# (the Remediation agent then reasons from first principles and escalates);
# otherwise keep only chunks from the winning runbook plus other confident hits.
MIN_TOP_SIMILARITY = 0.72
TOP_K = 4

_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "runbook"), ("##", "section")]
)


def _load_chunks() -> list[Document]:
    docs: list[Document] = []
    for path in sorted(RUNBOOK_DIR.glob("*.md")):
        for chunk in _splitter.split_text(path.read_text(encoding="utf-8")):
            chunk.metadata["source"] = path.name
            docs.append(chunk)
    return docs


_build_no = count(1)
_store_lock = threading.Lock()
_store_instance: Chroma | None = None


def _store() -> Chroma:
    # Double-checked locking: parallel LangGraph Send branches must never race
    # the build — chromadb's shared-client setup/teardown is not thread-safe.
    # Unique collection per build: chromadb caches clients in-process, so a
    # rebuild (e.g. after add_runbook) into the same collection name would
    # APPEND duplicates instead of starting fresh.
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = Chroma.from_documents(
                    documents=_load_chunks(),
                    embedding=FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5"),
                    collection_name=f"runbooks_v{next(_build_no)}",
                    collection_metadata={"hnsw:space": "cosine"},
                )
    return _store_instance


def reset() -> None:
    """Drop the index so the next access rebuilds from runbooks/."""
    global _store_instance
    with _store_lock:
        _store_instance = None


def warm_up() -> int:
    """Build the index eagerly (first FastEmbed call downloads the model)."""
    return len(_store().get()["ids"])


def index_stats() -> dict:
    return {
        "runbooks": len(list(RUNBOOK_DIR.glob("*.md"))),
        "chunks": len(_store().get()["ids"]),
    }


def add_runbook(file_path: str | Path) -> list[dict]:
    """Add a runbook to the knowledge base: copy into runbooks/, re-chunk,
    re-embed, rebuild the index. Returns the new file's chunks so the UI can
    SHOW the heading-aware chunking. Corpus is small — full rebuild is seconds."""
    src = Path(file_path)
    dest = RUNBOOK_DIR / src.name
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    reset()
    warm_up()

    return [
        {
            "section": chunk.metadata.get("section", chunk.metadata.get("runbook", "(intro)")),
            "words": len(chunk.page_content.split()),
            "preview": chunk.page_content[:120].replace("\n", " "),
        }
        for chunk in _splitter.split_text(dest.read_text(encoding="utf-8"))
    ]


def retrieve(incident: Incident) -> list[Citation]:
    query = (
        f"{incident.title}. Category: {incident.category}. "
        f"Component: {incident.affected_component}. "
        f"Evidence: {' '.join(incident.evidence[:3])}"
    )
    results = _store().similarity_search_with_score(query, k=TOP_K)
    if not results:
        return []

    scored = [
        Citation(
            source=doc.metadata.get("source", "unknown"),
            section=doc.metadata.get("section", doc.metadata.get("runbook", "")),
            score=round(1.0 - distance, 3),
            excerpt=doc.page_content,
        )
        for doc, distance in results
    ]
    top = max(scored, key=lambda c: c.score)
    if top.score < MIN_TOP_SIMILARITY:
        return []  # no confident runbook — first principles + escalation
    return [c for c in scored if c.source == top.source or c.score >= MIN_TOP_SIMILARITY]
