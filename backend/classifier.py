"""
Loads the risk classifier bundle once at import time.
Bundle must live at <repo_root>/SymanticAnalysis/risk_classifier_bundle.pkl
"""

import pickle
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BUNDLE_PATH = _REPO_ROOT / "SymanticAnalysis" / "risk_classifier_bundle.pkl"

with open(_BUNDLE_PATH, "rb") as _f:
    _bundle = pickle.load(_f)

from sentence_transformers import SentenceTransformer  # noqa: E402 (after pickle load)

_encoder = SentenceTransformer(_bundle["encoder_name"])
encoder  = _encoder   # public alias reused by the RAG retriever


def predict_labels(remarks: list[str]) -> list[str]:
    """Encode remarks and return predicted risk labels."""
    vecs = _encoder.encode(remarks)
    indices = _bundle["classifier"].predict(vecs)
    return [_bundle["labels"][i] for i in indices]
