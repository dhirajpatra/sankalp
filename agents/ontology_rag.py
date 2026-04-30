"""
ontology_rag.py – Lightweight RAG layer for SANKALP doctrine rules.
Uses sentence-transformers (all-MiniLM-L6-v2) + FAISS for semantic search.
Falls back to keyword search if dependencies unavailable.
"""

import json
import os
import logging
import numpy as np
from pathlib import Path
from config_loader import cfg

logger = logging.getLogger("ontology_rag")

RULES_FILE = cfg("paths.rules_file")
INDEX_FILE = cfg("paths.rag_index")
META_FILE  = "data/processed/ontology_rag_meta.json"

_embedder = None
_index    = None
_meta     = []   # list of {"key": ..., "text": ...}


# ── Embedder ──────────────────────────────────────────────────────────────────

def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("SentenceTransformer loaded (all-MiniLM-L6-v2).")
    except Exception as e:
        logger.warning(f"sentence-transformers unavailable ({e}). Falling back to keyword search.")
        _embedder = None
    return _embedder


# ── Build / rebuild index from rules JSON ─────────────────────────────────────

def build_index(rules: dict | None = None) -> bool:
    """
    Embed each rule as a short text chunk and store in FAISS.
    Returns True on success, False if FAISS/embedder unavailable.
    """
    global _index, _meta

    if rules is None:
        if not os.path.exists(RULES_FILE):
            return False
        with open(RULES_FILE) as f:
            rules = json.load(f)

    embedder = _get_embedder()
    if embedder is None:
        return False

    try:
        import faiss
    except ImportError:
        logger.warning("faiss-cpu not installed. RAG disabled.")
        return False

    _meta = []
    texts = []
    for key, val in rules.items():
        if key == "__global_settings__":
            continue
        desc = val.get("description", "")
        chunk = (
            f"Rule: {key}. "
            f"Description: {desc}. "
            f"IAF min: {val.get('iaf_min_operational', 0)}, "
            f"Army min: {val.get('army_min_operational', 0)}, "
            f"Navy min: {val.get('navy_min_operational', 0)}. "
            f"Logic: {val.get('logic_mode', 'standard')}."
        )
        texts.append(chunk)
        _meta.append({"key": key, "text": chunk, "rule": val})

    if not texts:
        return False

    vecs = embedder.encode(texts, normalize_embeddings=True).astype("float32")
    dim  = vecs.shape[1]
    _index = faiss.IndexFlatIP(dim)   # inner-product = cosine on L2-normalised vecs
    _index.add(vecs)

    # Persist
    os.makedirs("data/processed", exist_ok=True)
    faiss.write_index(_index, INDEX_FILE)
    with open(META_FILE, "w") as f:
        json.dump(_meta, f)

    logger.info(f"RAG index built: {len(texts)} rules embedded.")
    return True


def _load_index():
    global _index, _meta
    if _index is not None:
        return True
    try:
        import faiss
        if os.path.exists(INDEX_FILE) and os.path.exists(META_FILE):
            _index = faiss.read_index(INDEX_FILE)
            with open(META_FILE) as f:
                _meta = json.load(f)
            logger.info(f"RAG index loaded from disk ({len(_meta)} rules).")
            return True
    except Exception as e:
        logger.warning(f"Could not load FAISS index: {e}")
    return False


# ── Semantic search ───────────────────────────────────────────────────────────

def semantic_search(query: str, top_k: int = 2) -> list[dict]:
    """
    Return top_k most relevant rules for the query.
    Each result: {"key": str, "text": str, "rule": dict, "score": float}
    Falls back to keyword matching if FAISS unavailable.
    """
    # Try FAISS path
    embedder = _get_embedder()
    if embedder and (_load_index() or build_index()):
        try:
            import faiss
            q_vec = embedder.encode([query], normalize_embeddings=True).astype("float32")
            scores, idxs = _index.search(q_vec, min(top_k, len(_meta)))
            results = []
            for score, idx in zip(scores[0], idxs[0]):
                if idx < 0:
                    continue
                m = _meta[idx].copy()
                m["score"] = float(score)
                results.append(m)
            return results
        except Exception as e:
            logger.warning(f"FAISS search failed: {e}")

    # Keyword fallback
    return _keyword_search(query, top_k)


def _keyword_search(query: str, top_k: int = 2) -> list[dict]:
    """Simple keyword overlap fallback when FAISS is unavailable."""
    if not os.path.exists(RULES_FILE):
        return []
    with open(RULES_FILE) as f:
        rules = json.load(f)

    q_words = set(query.lower().split())
    scored = []
    for key, val in rules.items():
        if key == "__global_settings__":
            continue
        doc = (key + " " + val.get("description", "")).lower()
        overlap = sum(1 for w in q_words if w in doc)
        scored.append((overlap, key, val))

    scored.sort(reverse=True)
    return [
        {"key": k, "text": k, "rule": v, "score": float(s)}
        for s, k, v in scored[:top_k]
    ]


# ── Helper: compact rule summary for prompt injection ─────────────────────────

def get_relevant_rules_for_prompt(query: str, top_k: int = 2) -> str:
    """
    Returns a compact string of the top_k relevant rules, ready to inject
    into a system prompt. Keeps token count minimal.
    """
    hits = semantic_search(query, top_k=top_k)
    if not hits:
        return "No relevant doctrine rules found."

    lines = []
    for h in hits:
        r = h["rule"]
        lines.append(
            f'- "{h["key"]}": IAF≥{r.get("iaf_min_operational",0)}, '
            f'Army≥{r.get("army_min_operational",0)}, '
            f'Navy≥{r.get("navy_min_operational",0)}, '
            f'Army_Threshold={r.get("army_enhancement_threshold",0)}, '
            f'mode={r.get("logic_mode","standard")}. '
            f'{r.get("description","")[:120]}'
        )
    return "\n".join(lines)


# ── Auto-rebuild when rules change ───────────────────────────────────────────

def invalidate_index():
    """Call this after save_rules() so the index stays fresh."""
    global _index, _meta
    _index = None
    _meta  = []
    # Delete cached files so next search triggers a rebuild
    for f in [INDEX_FILE, META_FILE]:
        if os.path.exists(f):
            os.remove(f)
    logger.info("RAG index invalidated.")
