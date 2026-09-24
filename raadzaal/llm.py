"""Gemini on the free tier: JSON answers against a pydantic schema, cached by content hash, quota-safe."""
import hashlib
import json
import time
from pathlib import Path

from raadzaal import config


class QuotaExhausted(RuntimeError):
    """The free tier said no for today. The caller stops and leaves the rest pending."""


_client = None


def client():
    global _client
    if _client is None:
        from google import genai
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY missing in .env")
        _client = genai.Client(api_key=config.GEMINI_API_KEY, http_options={"timeout": 180_000})  # ms; a stuck request otherwise hangs the run
    return _client


def cache_key(model: str, prompt: str, schema_name: str) -> str:
    return hashlib.sha1(f"{model}\n{schema_name}\n{prompt}".encode("utf-8")).hexdigest()


def cache_path(key: str) -> Path:
    d = config.CACHE / "llm"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def _is_quota(exc: Exception) -> bool:
    s = str(exc)
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "quota" in s.lower()


def generate(prompt: str, schema, model: str | None = None, use_cache: bool = True, temperature: float = 0.2):
    """Return an instance of `schema` (a pydantic model) for the prompt. Raises QuotaExhausted when both models are out."""
    models = [model or config.LLM_MODEL] + ([config.LLM_FALLBACK] if not model else [])
    key = cache_key(models[0], prompt, schema.__name__)
    cp = cache_path(key)
    if use_cache and cp.exists():
        return schema.model_validate_json(cp.read_text(encoding="utf-8"))
    last = None
    for m in models:
        for attempt in range(2):
            try:
                r = client().models.generate_content(
                    model=m, contents=prompt,
                    config={"response_mime_type": "application/json", "response_schema": schema, "temperature": temperature})
                text = r.text or ""
                obj = schema.model_validate_json(text)
                cp.write_text(obj.model_dump_json(), encoding="utf-8")
                return obj
            except Exception as exc:  # noqa: BLE001
                last = exc
                if _is_quota(exc):
                    break  # try the fallback model
                time.sleep(3)
    if last is not None and _is_quota(last):
        raise QuotaExhausted(str(last)[:200])
    raise RuntimeError(f"Gemini failed: {str(last)[:300]}")


def fmt_time(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
