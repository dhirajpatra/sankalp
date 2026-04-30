"""
config_loader.py – SANKALP Central Configuration Loader
========================================================
Usage anywhere in the project:

    from config_loader import cfg

    neo4j_uri = cfg("neo4j.uri")
    port      = cfg("streamlit.port")
    threshold = cfg("readiness.operational_threshold")

Environment variables always override config.yml values.
The mapping of env-var → config key is defined in ENV_OVERRIDES below.
"""

import os
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("config_loader")

# ── Locate config.yml (search up to 4 dirs from this file) ───────────────────
def _find_config() -> Path:
    candidate = Path(__file__).resolve().parent
    for _ in range(4):
        cfg_file = candidate / "config.yml"
        if cfg_file.exists():
            return cfg_file
        candidate = candidate.parent
    raise FileNotFoundError(
        "config.yml not found. Place it in the project root alongside this loader."
    )


# ── Env-var overrides: env_var_name → dotted config key ──────────────────────
ENV_OVERRIDES: dict[str, str] = {
    "NEO4J_URI":                     "neo4j.uri",
    "NEO4J_USER":                    "neo4j.user",
    "NEO4J_PASSWORD":                "neo4j.password",
    "MODEL":                         "llm.model",
    "GROQ_API_KEY":                  "llm.api_key",
    "GROQ_LLM_API_KEY":              "llm.api_key",
    "LLM_API_KEY":                   "llm.api_key",
    "GLOBAL_OPERATIONAL_THRESHOLD":  "readiness.operational_threshold",
}


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    """Parse config.yml once and cache the result."""
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required: pip install pyyaml --break-system-packages"
        )
    cfg_path = _find_config()
    with open(cfg_path, "r") as f:
        data = yaml.safe_load(f) or {}
    logger.debug(f"Loaded config from {cfg_path}")
    return data


def _deep_get(data: dict, dotted_key: str):
    """Traverse nested dict using a dotted key, e.g. 'neo4j.uri'."""
    keys = dotted_key.split(".")
    node = data
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return node


def _apply_env_overrides(data: dict) -> None:
    """
    Mutate the loaded config dict in-place with any env-var overrides.
    Only applies when the env var is set to a non-empty, non-placeholder value.
    """
    PLACEHOLDERS = {"", "your_api_key_here", "changeme", "xxxx", "gsk_..."}
    for env_var, dotted_key in ENV_OVERRIDES.items():
        val = os.getenv(env_var, "").strip().strip("\"'")
        if val and val.lower() not in PLACEHOLDERS:
            # Navigate to parent dict and set leaf
            keys = dotted_key.split(".")
            node = data
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            # Cast to int if the existing value is an int
            existing = node.get(keys[-1])
            try:
                node[keys[-1]] = int(val) if isinstance(existing, int) else val
            except (ValueError, TypeError):
                node[keys[-1]] = val


# ── Public API ─────────────────────────────────────────────────────────────────

def cfg(dotted_key: str, default=None):
    """
    Retrieve a configuration value by dotted key.

    Priority (highest → lowest):
      1. Environment variable (see ENV_OVERRIDES mapping)
      2. config.yml value
      3. `default` argument

    Examples:
        cfg("neo4j.uri")                       → "bolt://localhost:7687"
        cfg("streamlit.port")                  → 8501
        cfg("readiness.operational_threshold") → 5
        cfg("paths.iaf_gold_db")               → "data/processed/sankalp_gold.db"
    """
    data = _load_raw()
    _apply_env_overrides(data)
    val = _deep_get(data, dotted_key)
    if val is None:
        if default is not None:
            return default
        logger.warning(f"Config key '{dotted_key}' not found and no default provided.")
    return val


def cfg_section(dotted_prefix: str) -> dict:
    """
    Return a whole config sub-section as a dict.

    Example:
        cfg_section("neo4j.connection") → {"retries": 5, "retry_delay_seconds": 2}
    """
    data = _load_raw()
    _apply_env_overrides(data)
    result = _deep_get(data, dotted_prefix)
    return result if isinstance(result, dict) else {}


def reload():
    """Force reload config from disk (clears lru_cache)."""
    _load_raw.cache_clear()
    logger.info("config.yml reloaded.")


# ── Quick self-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("neo4j.uri              →", cfg("neo4j.uri"))
    print("streamlit.port         →", cfg("streamlit.port"))
    print("readiness.iaf.weight_base →", cfg("readiness.iaf.weight_base"))
    print("paths.iaf_gold_db      →", cfg("paths.iaf_gold_db"))
    print("llm.model              →", cfg("llm.model"))
    print("neo4j section          →", cfg_section("neo4j.connection"))
