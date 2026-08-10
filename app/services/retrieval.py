"""Help-centre retrieval.

Loads the article corpus from disk, embeds it, embeds the query, and returns the
closest articles by cosine similarity.

Note what this does on every single request: it re-embeds the entire corpus.
The corpus does not change between requests. This is the most expensive thing
the service does and it is left in on purpose — it is the target of the
embedding and retrieval caching work in Sprint 2.
"""

import json
from typing import Dict, List

from ..config import DATA_DIR, settings
from . import model_client
from .errors import RetrievalUnavailable

CORPUS_PATH = DATA_DIR / "help_center.jsonl"


def load_corpus() -> List[Dict]:
    with CORPUS_PATH.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def search(query: str, top_k: int | None = None) -> List[Dict]:
    """Return the top_k most similar help-centre articles for a query."""
    if settings.fault_retrieval_down:
        raise RetrievalUnavailable("help-centre index unreachable")

    top_k = top_k or settings.retrieval_top_k
    corpus = load_corpus()

    doc_texts = [f"{doc['title']} {doc['body']}" for doc in corpus]
    doc_vectors = model_client.embed(doc_texts)
    query_vector = model_client.embed([query])[0]

    scored = [
        {**doc, "score": round(_cosine(query_vector, vector), 4)}
        for doc, vector in zip(corpus, doc_vectors)
    ]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def _cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
