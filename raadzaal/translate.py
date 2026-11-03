"""English for the English version of the site: every agenda title, summary, quote and decision line in the published
data, translated once and kept in docs/data/en.json as Dutch text -> English text. Keyed by the text itself, so a
rebuild keeps every translation whose Dutch did not change and only new lines go to the model."""
import json

from pydantic import BaseModel

from raadzaal import config, llm

BATCH = 50
MODELS = ("gemini-2.5-flash", "gemini-3-flash-preview", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite")

PROMPT = """Translate these texts from a website about Flemish municipal council meetings from Dutch into plain American English.

- Keep every person name, street name, place name, party name and organization name as it is.
- Use these terms: gemeenteraad = municipal council, burgemeester = mayor, schepen = alderman, college van burgemeester en schepenen = board of mayor and aldermen, raadslid = councillor, OCMW = OCMW (public social welfare center) the first time in a text, intercommunale = intermunicipal company, RUP = spatial implementation plan (RUP), retributie = fee, belasting = tax.
- A quote is spoken Flemish: translate the meaning in natural spoken English, do not smooth it into a formal sentence.
- Translate only. Add nothing, explain nothing, leave nothing out.

Return one entry per text with its number.

{texts}
"""


class Line(BaseModel):
    i: int
    en: str


class Lines(BaseModel):
    texts: list[Line]


def generate(prompt: str):
    last = None
    for m in MODELS:
        try:
            return llm.generate(prompt, Lines, model=m)
        except (llm.QuotaExhausted, RuntimeError) as exc:
            last = exc
    raise llm.QuotaExhausted(str(last)[:200])


def match_end(nl: str, en: str) -> str:
    """The model closes agenda titles with a period; a title without one keeps none."""
    return en if nl.rstrip().endswith((".", "!", "?")) else en.rstrip(".")


def texts(payloads: list[dict]) -> list[str]:
    """Every Dutch line the site shows that is not a transcript line, in a stable order."""
    out = []
    for p in payloads:
        out += p["notes"].get("decided") or []
        for a in p["agenda"]:
            out.append(a["title"])
            sm = a.get("summary")
            if sm:
                out += [sm.get("nl"), sm.get("quote")]
    seen, keep = set(), []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            keep.append(t)
    return keep


def run(con, args) -> int:
    path = config.DOCS_DATA / "en.json"
    have = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    payloads = [json.loads(f.read_text(encoding="utf-8")) for f in sorted((config.DOCS_DATA / "sessions").glob("*.json"))]
    wanted = texts(payloads)
    todo = [t for t in wanted if t not in have]
    print(f"{len(wanted)} texts, {len(todo)} to translate")
    try:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            r = generate(PROMPT.format(texts="\n".join(f"[{n}] {t}" for n, t in enumerate(chunk))))
            for line in r.texts:
                if 0 <= line.i < len(chunk) and line.en.strip():
                    have[chunk[line.i]] = match_end(chunk[line.i], line.en.strip())
            print(f"  {min(i + BATCH, len(todo))}/{len(todo)}")
    finally:
        out = {t: have[t] for t in wanted if t in have}  # lines that left the site are dropped
        path.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    missing = [t for t in wanted if t not in out]
    print(f"en.json: {len(out)} lines, {len(missing)} missing")
    return 1 if missing else 0
