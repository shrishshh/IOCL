"""
One-time (idempotent) ingestion script.

Run from repo root:
    py -3.11 -m backend.rag.ingest

Reads OISD-STD-225.pdf, chunks it, embeds with the same MiniLM encoder
already used by the classifier, and persists to a local Chroma collection.
"""
import re
import sys
from pathlib import Path

from pypdf import PdfReader

from ..classifier import encoder as _encoder

_RAG_DIR    = Path(__file__).resolve().parent
_PDF_PATH   = _RAG_DIR / "corpus" / "OISD-STD-225.pdf"
_VS_PATH    = _RAG_DIR / "vectorstore"
_COLLECTION = "oisd_std_225"

# ── PDF text extraction ────────────────────────────────────────────────────────

def _extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages  = [p.extract_text() or "" for p in reader.pages]
    return "\n".join(pages)


# ── Chunking ───────────────────────────────────────────────────────────────────

_CLAUSE_RE = re.compile(
    r'(?m)^(?=(?:Annexure\s+[IVX]+|(?:\d+\.)+(?:\d+|[ivxlcdm]+|[a-z])\s|\d+\s+[A-Z]))',
    re.IGNORECASE,
)


def _chunk_clauses(text: str) -> list[dict]:
    parts = _CLAUSE_RE.split(text)
    chunks: list[dict] = []
    for part in parts:
        part = part.strip()
        if len(part) < 30:
            continue
        first_line = part.split("\n")[0].strip()
        m = re.match(
            r'^(Annexure\s+[IVX]+|(?:\d+\.)+(?:\d+|[ivxlcdm]+|[a-z])|\d+)',
            first_line, re.IGNORECASE,
        )
        section    = m.group(1) if m else "General"
        chunk_type = "annexure_row" if re.match(r"Annexure", section, re.I) else "clause"
        chunks.append({
            "text":         part[:1200],   # hard cap per chunk
            "section":      section,
            "section_name": first_line[:80],
            "type":         chunk_type,
        })
    return chunks


def _sliding_chunks(text: str, size: int = 400, overlap: int = 50) -> list[dict]:
    """Fallback: section-aware sliding window over word tokens."""
    words   = text.split()
    step    = size - overlap
    cur_sec = "General"
    chunks: list[dict] = []
    for i in range(0, len(words), step):
        chunk_text = " ".join(words[i: i + size])
        if not chunk_text:
            continue
        m = re.search(r'(?:^|\n)((?:\d+\.)+(?:\d+|[ivxlcdm]+|[a-z])|\d+\s+[A-Z]\w+)',
                      chunk_text)
        if m:
            cur_sec = m.group(1)[:20].strip()
        chunks.append({
            "text":         chunk_text,
            "section":      cur_sec,
            "section_name": cur_sec,
            "type":         "clause",
        })
    return chunks


def _make_chunks(text: str) -> list[dict]:
    chunks = _chunk_clauses(text)
    if len(chunks) < 20:
        print(f"  Clause parsing yielded only {len(chunks)} chunks — falling back to sliding window.")
        chunks = _sliding_chunks(text)
    return chunks


# ── Main ingestion ─────────────────────────────────────────────────────────────

def ingest() -> None:
    if not _PDF_PATH.exists():
        print(f"[ingest] PDF not found: {_PDF_PATH}")
        print("         Place OISD-STD-225.pdf at backend/rag/corpus/OISD-STD-225.pdf and re-run.")
        sys.exit(1)

    print(f"[ingest] Reading {_PDF_PATH.name} …")
    text = _extract_text(_PDF_PATH)
    print(f"         {len(text):,} chars extracted")

    chunks = _make_chunks(text)
    print(f"         {len(chunks)} chunks created")

    import chromadb  # imported here so startup doesn't fail if chromadb isn't installed
    _VS_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(_VS_PATH))

    # Idempotent: drop and recreate
    try:
        client.delete_collection(_COLLECTION)
        print("         Deleted existing collection.")
    except Exception:
        pass

    collection = client.create_collection(
        name=_COLLECTION,
        metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )

    texts = [c["text"] for c in chunks]
    BATCH = 64
    all_embeddings: list = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i: i + BATCH]
        embs  = _encoder.encode(batch, show_progress_bar=False)
        all_embeddings.extend(embs.tolist())
        print(f"         Embedded {min(i + BATCH, len(texts)):>{len(str(len(texts)))}}/{len(texts)}", end="\r")
    print()

    collection.add(
        ids       = [str(i) for i in range(len(chunks))],
        embeddings= all_embeddings,
        documents = texts,
        metadatas = [
            {
                "source":       "OISD-STD-225",
                "section":      c["section"],
                "section_name": c["section_name"],
                "type":         c["type"],
            }
            for c in chunks
        ],
    )

    print(f"[ingest] Done. {len(chunks)} chunks in Chroma at {_VS_PATH}")


if __name__ == "__main__":
    ingest()
