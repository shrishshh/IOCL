"""
Provider-agnostic LLM adapter backed by Groq (OpenAI-compatible API).

Env vars (read from .env at repo root or shell environment):
  GROQ_API_KEY   — required; no key → generate() returns None silently
  GROQ_MODEL     — default "llama-3.1-8b-instant"
  GROQ_BASE_URL  — default "https://api.groq.com/openai/v1"

To switch to a local model: set GROQ_BASE_URL + GROQ_MODEL + GROQ_API_KEY
accordingly — nothing else needs to change.

Env vars are re-read on every generate() call so the server never needs a
restart when .env is created or updated after startup.
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"

_client     = None
_client_key = ""   # which key the cached client was built with


def _get_client(api_key: str, base_url: str):
    global _client, _client_key
    if _client is None or api_key != _client_key:
        from openai import OpenAI
        _client     = OpenAI(api_key=api_key, base_url=base_url)
        _client_key = api_key
    return _client


def generate(system: str, user: str, timeout: float = 25.0) -> Optional[str]:
    """
    Call the LLM and return the response text.
    Re-reads .env on every call — server restart not required after key changes.
    Returns None on any error; must never raise so it can't break submission.
    """
    # override=True so .env always wins over a stale os.environ entry
    load_dotenv(_DOTENV_PATH, override=True)
    api_key  = os.getenv("GROQ_API_KEY",  "")
    base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    model    = os.getenv("GROQ_MODEL",    "llama-3.1-8b-instant")

    if not api_key:
        return None
    try:
        resp = _get_client(api_key, base_url).chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens=350,
            timeout=timeout,
        )
        text = resp.choices[0].message.content
        return text.strip() if text else None
    except Exception:
        return None
