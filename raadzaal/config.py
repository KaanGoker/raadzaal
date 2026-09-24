"""Paths, environment and the municipality registry."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(os.environ.get("RAADZAAL_ROOT") or Path(__file__).resolve().parents[1])
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
AUDIO = DATA / "audio"
TRANSCRIPTS = DATA / "transcripts"
DB_PATH = DATA / "db" / "raadzaal.db"
MODELS = ROOT / "models"
DOCS = ROOT / "docs"
DOCS_DATA = DOCS / "data"
COUNCILS = ROOT / "councils"
PROMPTS = ROOT / "prompts"
CACHE = DATA / "cache"

TZ = "Europe/Brussels"
HARVESTER_URL = "https://lokaalbeslist-harvester-{n}.s.redhost.be/sparql"
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8_float16")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-2.5-flash-lite")
LLM_FALLBACK = os.environ.get("LLM_FALLBACK", "gemini-2.5-flash")
LLM_MAX_ITEMS = int(os.environ.get("LLM_MAX_ITEMS", "240"))
MIN_DATE = os.environ.get("MIN_DATE", "2026-01-01")  # sessions before this date are not processed
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Titles that look like a council session but are something else.
EXCLUDE_TITLE_RE = r"commissie|infovergadering|infomoment|toelichting|installatievergadering|^raad voor maatschappelijk welzijn|^ocmw-raad\b(?!.*gemeenteraad)"


def ensure_dirs() -> None:
    for p in (AUDIO, TRANSCRIPTS, DB_PATH.parent, MODELS, DOCS_DATA, CACHE):
        p.mkdir(parents=True, exist_ok=True)


def municipalities(all_entries: bool = False) -> list[dict]:
    """The registry, enabled entries only unless asked for all."""
    with (ROOT / "municipalities.yaml").open(encoding="utf-8") as fh:
        entries = yaml.safe_load(fh) or []
    out = []
    for e in entries:
        if all_entries or e.get("enabled", True):
            out.append(e)
    return out


def municipality(slug: str) -> dict:
    for e in municipalities(all_entries=True):
        if e["slug"] == slug:
            return e
    raise KeyError(f"unknown municipality {slug}")
