"""Runtime configuration: load per-engine config blobs and validate them.

The engine (fast|llm|batch) is chosen by the input subfolder, not a global mode.
Each engine has its own config blob (config/<engine>.json). A missing or invalid
config falls back to sensible code defaults so the pipeline works out of the box.
"""
import copy
import json
import logging
import os
import re
import time
from typing import Any, Dict

from shared import storage

ENGINES = {"fast", "llm", "batch"}
VALID_PROFANITY = {"None", "Masked", "Removed", "Tags"}

# Per-instance config cache: avoids re-reading the config blob on every message.
_CONFIG_TTL_SECONDS = int(os.environ.get("CONFIG_CACHE_TTL_SECONDS", "60") or 60)
_config_cache: Dict[str, Any] = {}

# Matches a JSON string (kept) OR a // line / /* block */ comment (removed), so we can
# strip comments from config files without corrupting values like URLs inside strings.
_JSONC_RE = re.compile(r'("(?:\\.|[^"\\])*")|(//[^\n]*|/\*.*?\*/)', re.DOTALL)


def _strip_jsonc(text: str) -> str:
    return _JSONC_RE.sub(lambda m: m.group(1) or "", text)


def _defaults(engine: str) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "locales": ["en-US"],
        "diarization": {"enabled": False, "maxSpeakers": 4},
        "profanityFilterMode": "Masked",
        "channels": [],
    }
    if engine == "llm":
        base["locales"] = []  # LLM Speech is multilingual by default
        base["llm"] = {"task": "transcribe", "targetLanguage": "", "prompt": []}
    elif engine == "batch":
        base["batch"] = {
            "timeToLiveHours": 12,
            "wordLevelTimestamps": True,
            "displayFormWordLevelTimestamps": False,
            "punctuationMode": "DictatedAndAutomatic",
            "model": "",
        }
    else:  # fast
        base["phraseList"] = []
    return base


def load_config(engine: str) -> Dict[str, Any]:
    cached = _config_cache.get(engine)
    if cached and cached[0] > time.monotonic():
        return copy.deepcopy(cached[1])

    container = os.environ["CONFIG_CONTAINER"]
    blob = f"{engine}.json"
    merged = _defaults(engine)
    try:
        raw = storage.download(container, blob, account="input")
        merged.update(json.loads(_strip_jsonc(raw.decode("utf-8"))))
    except Exception:  # noqa: BLE001 - missing/invalid config falls back to defaults
        logging.warning("Config %s/%s not readable; using defaults for engine '%s'", container, blob, engine)
    merged.pop("$schema", None)  # editor metadata, not a transcription setting
    _config_cache[engine] = (time.monotonic() + _CONFIG_TTL_SECONDS, copy.deepcopy(merged))
    return merged


def validate_config(cfg: Dict[str, Any], engine: str) -> Dict[str, Any]:
    if cfg.get("profanityFilterMode") not in VALID_PROFANITY:
        cfg["profanityFilterMode"] = "Masked"

    diar = cfg.setdefault("diarization", {})
    speakers = int(diar.get("maxSpeakers", 4) or 4)
    diar["maxSpeakers"] = min(max(speakers, 2), 35)

    # LLM Speech uses prompting instead of phrase lists.
    if engine == "llm" and cfg.get("phraseList"):
        logging.info("phraseList is not supported for llm; use llm.prompt instead. Ignoring.")
        cfg["phraseList"] = []

    return cfg
