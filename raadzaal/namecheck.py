"""Second pass over the written summaries: nobody but a council member may be named.

The summary prompt already says so, but the model still names residents, staff and speakers from outside the
council now and then. One Gemini call per session lists every person in every summary text and rewrites the
texts that name someone outside the list; the code then decides with the council list, not the model."""
import re

from pydantic import BaseModel

from raadzaal import config, db, llm, speakers

BATCH = 25  # the model overlooks names in long lists; small batches on a stronger model catch them
MODELS = ("gemini-3-flash-preview", "gemini-flash-latest", "gemini-3.1-flash-lite")  # free tier: about 20 calls a day each


def generate(prompt: str, schema):
    """The first model in MODELS that still has free quota today."""
    last = None
    for m in MODELS:
        try:
            return llm.generate(prompt, schema, model=m)
        except (llm.QuotaExhausted, RuntimeError) as exc:
            last = exc
    raise llm.QuotaExhausted(str(last)[:200])
_PART = r"(?:[A-Z][\w'’\-]+|[Vv]an|[Dd]er|[Dd]en|[Dd]e|[Tt]er)\b"
HONORIFIC_RE = re.compile(r"\b(?i:de heer|meneer|mijnheer|mevrouw|mr\.?|mrs\.?|ms\.?)\s+(" + _PART + r"(?:\s+" + _PART + r"){0,3})")


def titled_names(text: str) -> list[str]:
    """Names after "de heer", "mevrouw" and the like: always a person, whatever the model says."""
    out = []
    for m in HONORIFIC_RE.finditer(text or ""):
        words = m.group(1).split()
        while words and not words[-1][0].isupper():
            words.pop()
        if words:
            out.append(" ".join(words))
    return out

PROMPT = """Je controleert teksten van een website over een gemeenteraad van {municipality} ({date}).
Enkel deze personen mogen met naam genoemd worden: {allowed}.

Geef voor elke tekst hieronder:
- persons: elke persoon die in de tekst bij naam genoemd wordt (voornaam, achternaam of beide, ook "meneer X", "mevrouw X"). Geen plaatsen, partijen, verenigingen of bedrijven.
- text: dezelfde tekst, waarin elke persoon die NIET op de lijst staat vervangen is door een neutrale omschrijving (een inwoner, een medewerker, de algemeen directeur, een raadslid, een vertegenwoordiger). Verander verder niets. Staat er niemand buiten de lijst in, geef de tekst dan letterlijk terug.

Teksten:
{texts}
"""


class Checked(BaseModel):
    key: str
    persons: list[str]
    text: str


class NameCheck(BaseModel):
    texts: list[Checked]


REWRITE = """Herschrijf elke tekst hieronder zo dat de genoemde personen niet meer bij naam vermeld worden.
Vervang elke naam (met "de heer", "mevrouw", "meneer" ervoor) door een omschrijving die uit de tekst zelf volgt,
zoals "een vertegenwoordiger", "de vraagsteller" of "de spreker". Verzin geen rol die niet in de tekst staat: is de rol
niet duidelijk, schrijf dan "iemand" (in het Engels "someone"). Verander verder niets aan de tekst.

{texts}
"""


class Rewritten(BaseModel):
    key: str
    text: str


class Rewrites(BaseModel):
    texts: list[Rewritten]


def rewrite(todo: dict[str, tuple[str, list[str]]]) -> dict[str, str]:
    """key -> (text, names to remove) in, key -> rewritten text out."""
    if not todo:
        return {}
    block = "\n".join(f"[{k}] Te verwijderen: {', '.join(names)}\nTekst: {text}" for k, (text, names) in todo.items())
    r = generate(REWRITE.format(texts=block), Rewrites)
    return {x.key.strip("[] "): x.text for x in r.texts}


def is_allowed(person: str, allowed: list[str]) -> bool:
    """One allowed name at a time: the list holds full names and bare surnames from agenda titles, and matching
    against all of them at once calls "Peters" ambiguous when both "Bram Peters" and "Peters" are on it."""
    return any(speakers.match_member(person, {"members": [{"name": a}]}) is not None for a in allowed)


def _texts(con, session_id: str) -> dict[str, str]:
    out = {}
    for r in con.execute("SELECT m.item_id, m.nl, m.quote FROM summaries m JOIN agenda_items a ON a.id=m.item_id "
                         "WHERE a.session_id=?", (session_id,)):
        for field in ("nl", "quote"):
            if r[field]:
                out[f"{r['item_id']}.{field}"] = r[field]
    notes = con.execute("SELECT decided FROM session_notes WHERE session_id=?", (session_id,)).fetchone()
    if notes:
        for i, d in enumerate(db.loads(notes["decided"])):
            out[f"decided.{i}"] = d
    return out


def outsiders(checked: Checked | None, allowed: list[str]) -> list[str]:
    return [p for p in (checked.persons if checked else []) if p.strip() and not is_allowed(p, allowed)]


def resolve(original: str, new: str | None, outside: list[str], verbatim: bool) -> str | None:
    """The text to publish. A verbatim text (a quote) naming an outsider is dropped, never rewritten; a rewrite that
    still carries a name, or lost half the text, is dropped too."""
    if not outside:
        return original
    if verbatim or not new:
        return None
    low = new.lower()
    if any(part.lower() in low for p in outside for part in p.split() if len(part) > 3) or len(new) < 0.5 * len(original):
        return None
    return new


def run(con, session: dict, args) -> int:
    from raadzaal import summarise
    texts = _texts(con, session["id"])
    if not texts:
        return 0
    council = speakers.load_council(session["municipality"], session["date"])
    titles = [dict(r) for r in con.execute("SELECT title FROM agenda_items WHERE session_id=?", (session["id"],))]
    allowed = summarise.allowed_names(council, titles)
    m = config.municipality(session["municipality"])
    items = list(texts.items())
    by_key: dict[str, Checked] = {}
    for i in range(0, len(items), BATCH):
        chunk = items[i:i + BATCH]
        prompt = PROMPT.format(municipality=m["name"], date=session["date"], allowed=", ".join(allowed) or "(niemand)",
                               texts="\n".join(f"[{k}] {v}" for k, v in chunk))
        for c in generate(prompt, NameCheck).texts:
            by_key[c.key.strip("[] ")] = c
    for k, v in texts.items():
        extra = titled_names(v)
        c = by_key.setdefault(k, Checked(key=k, persons=[], text=v))
        c.persons += [n for n in extra if n not in c.persons]
    out = {k: outsiders(by_key.get(k), allowed) for k in texts}
    rewritten = rewrite({k: (texts[k], o) for k, o in out.items() if o and not k.endswith(".quote")})
    fixed, removed = {}, []
    for k, v in texts.items():
        if out[k]:
            fixed[k] = resolve(v, rewritten.get(k), out[k], verbatim=k.endswith(".quote"))
            removed += out[k]
    for k, v in fixed.items():
        head, field = k.split(".")
        if head.isdigit():
            if field == "quote":
                con.execute("UPDATE summaries SET quote=NULL, quote_start=NULL WHERE item_id=?", (int(head),))
            elif v is None:
                con.execute("UPDATE summaries SET nl=NULL WHERE item_id=?", (int(head),))
            else:
                con.execute(f"UPDATE summaries SET {field}=? WHERE item_id=?", (v, int(head)))
    notes = con.execute("SELECT decided FROM session_notes WHERE session_id=?", (session["id"],)).fetchone()
    if notes and any(not k[0].isdigit() for k in fixed):
        decided = [fixed.get(f"decided.{i}", d) for i, d in enumerate(db.loads(notes["decided"]))]
        con.execute("UPDATE session_notes SET decided=? WHERE session_id=?", (db.dumps([d for d in decided if d]), session["id"]))
    con.commit()
    print(f"{session['municipality']:<10} {session['date']}  {len(texts)} texts, {len(fixed)} changed, removed: {', '.join(sorted(set(removed))) or 'none'}")
    return 0
