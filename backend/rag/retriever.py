"""
Retriever: reuses the MiniLM encoder already loaded by backend.classifier.
Lazily initialises Chroma on first call so startup never fails if the
vectorstore hasn't been built yet.
"""
from pathlib import Path
from typing import Any

from ..classifier import encoder as _encoder

_RAG_DIR    = Path(__file__).resolve().parent
_VS_PATH    = _RAG_DIR / "vectorstore"
_COLLECTION = "oisd_std_225"

_client: Any     = None
_collection: Any = None


def _get_collection() -> Any:
    global _client, _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb
        _client     = chromadb.PersistentClient(path=str(_VS_PATH))
        _collection = _client.get_or_create_collection(
            name=_COLLECTION,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )
    except Exception:
        pass
    return _collection


def retrieve(query: str, k: int = 4) -> list[dict]:
    """
    Embed *query* with MiniLM and return the top-k matching OISD-STD-225 chunks.
    Returns [] if the vectorstore is empty or unavailable (never raises).
    """
    try:
        col = _get_collection()
        if col is None or col.count() == 0:
            return []
        qvec    = _encoder.encode([query])[0].tolist()
        results = col.query(
            query_embeddings=[qvec],
            n_results=min(k, col.count()),
            include=["documents", "metadatas", "distances"],
        )
        out: list[dict] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            out.append({
                "text":         doc,
                "section":      meta.get("section", ""),
                "section_name": meta.get("section_name", ""),
                "score":        round(1.0 - float(dist), 4),
            })
        return out
    except Exception:
        return []
