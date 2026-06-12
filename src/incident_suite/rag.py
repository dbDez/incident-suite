"""Runbook RAG — Chroma vector store + FastEmbed local embeddings.

Heading-aware chunking via LangChain's MarkdownHeaderTextSplitter so each
chunk carries its runbook + section breadcrumb. Embeddings run locally
(BAAI/bge-small-en-v1.5, ONNX) — no API key, fully reproducible by judges.

The index is built in-memory at startup; the corpus is small enough that a
fresh build costs seconds and can never go stale against runbooks/.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from .schemas import Citation, Incident

RUNBOOK_DIR = Path(__file__).resolve().parents[2] / "runbooks"

# Chroma returns cosine DISTANCE (lower = closer). Above this, a chunk is
# considered unrelated and the Remediation agent falls back to first principles.
MAX_DISTANCE = 0.75
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


@lru_cache(maxsize=1)
def _store() -> Chroma:
    return Chroma.from_documents(
        documents=_load_chunks(),
        embedding=FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5"),
        collection_metadata={"hnsw:space": "cosine"},
    )


def warm_up() -> int:
    """Build the index eagerly (first FastEmbed call downloads the model)."""
    return len(_store().get()["ids"])


def retrieve(incident: Incident) -> list[Citation]:
    query = (
        f"{incident.title}. Category: {incident.category}. "
        f"Component: {incident.affected_component}. "
        f"Evidence: {' '.join(incident.evidence[:3])}"
    )
    results = _store().similarity_search_with_score(query, k=TOP_K)
    citations = [
        Citation(
            source=doc.metadata.get("source", "unknown"),
            section=doc.metadata.get("section", doc.metadata.get("runbook", "")),
            score=round(1.0 - distance, 3),
            excerpt=doc.page_content,
        )
        for doc, distance in results
        if distance <= MAX_DISTANCE
    ]
    return citations
