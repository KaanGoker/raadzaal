"""Per-item and per-session summaries with Gemini, verified against the transcript and the council list."""
import hashlib
import re
from typing import Literal

from pydantic import BaseModel

from raadzaal import config, db, llm, speakers

TOPICS = ("mobiliteit", "ruimtelijke ordening", "financiën", "wonen", "milieu en klimaat", "onderwijs en jeugd",
          "cultuur en sport", "welzijn en zorg", "veiligheid", "personeel en organisatie", "economie en handel",
          "participatie en bestuur", "nutsvoorzieningen en afval", "andere")
OUTCOMES = ("aangenomen", "verworpen", "kennisname", "uitgesteld", "onbekend")
MAX_SPAN_CHARS = 9000
MAX_PROMPT_CHARS = 300_000  # about 75k tokens; a longer session is summarised in two calls


class ItemSummary(BaseModel):
    number: int | None = None
    discussed: bool = True
    nl: str
    topic: Literal[TOPICS]  # type: ignore[valid-type]
    outcome: Literal[OUTCOMES]  # type: ignore[valid-type]
    raised_by: str | None = None
    quote: str | None = None
    quote_start: float | None = None


class ItemSummaries(BaseModel):
    items: list[ItemSummary]


class SessionNotes(BaseModel):
    decided: list[str]


class SessionSummary(BaseModel):
    items: list[ItemSummary]
    decided: list[str]


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9à-ÿ]+", " ", t.lower()).strip()


def quote_in_text(quote: str | None, text: str) -> bool:
    if not quote:
        return False
    q, t = _norm(quote), _norm(text)
    if len(q) < 12:
        return False
    if q in t:
        return True
    # tolerate one recognition slip: 85 % of the quote's 4-grams must be present
    words = q.split()
    grams = [" ".join(words[i:i + 4]) for i in range(max(len(words) - 3, 1))]
    return sum(1 for g in grams if g in t) >= 0.85 * len(grams)


def allowed_names(council: dict, items: list[dict]) -> list[str]:
    names = [m["name"] for m in council.get("members", [])]
    for it in items:
        n = speakers.name_from_title(it.get("title") or "")
        if n and n not in names:
            names.append(n)
    return names


def check_raised_by(raised: str | None, allowed: list[str], title: str) -> str | None:
    if not raised:
        return None
    m = speakers.match_member(raised, {"members": [{"name": a} for a in allowed]})
    if m:
        return m["name"]
    if speakers.fold(raised) in speakers.fold(title):
        return raised
    return None


def span_text(segments: list[dict], names: dict[int, str], start: float, end: float) -> str:
    lines = []
    for s in segments:
        if s["end"] < start or s["start"] > end:
            continue
        who = names.get(s.get("speaker"), f"Spreker {s['speaker']}" if s.get("speaker") is not None else "?")
        lines.append(f"[{int(s['start'])}] {who}: {s['text']}")
    text = "\n".join(lines)
    if len(text) <= MAX_SPAN_CHARS:
        return text
    # keep whole lines: the first two thirds of the budget from the start, the last third from the end
    head, tail, size = [], [], 0
    for ln in lines:
        if size + len(ln) + 1 > MAX_SPAN_CHARS * 2 // 3:
            break
        head.append(ln); size += len(ln) + 1
    size = 0
    for ln in reversed(lines[len(head):]):
        if size + len(ln) + 1 > MAX_SPAN_CHARS // 3:
            break
        tail.append(ln); size += len(ln) + 1
    return "\n".join(head + ["[...]"] + tail[::-1])


def content_hash(*parts: str) -> str:
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def render_items(batch: list[dict]) -> str:
    out = []
    for it in batch:
        votes = ""
        if it.get("votes_for") is not None:
            votes = f" Stemming: {it['votes_for']} voor, {it['votes_against']} tegen, {it['abstentions']} onthoudingen."
        out.append(f"### Item {it['position']}: {it['title']}{votes}\n{it['text']}\n")
    return "\n".join(out)


def split_by_size(items: list[dict], limit: int = MAX_PROMPT_CHARS) -> list[list[dict]]:
    parts, cur, size = [], [], 0
    for it in items:
        n = len(it["text"]) + len(it["title"]) + 200
        if cur and size + n > limit:
            parts.append(cur); cur, size = [], 0
        cur.append(it); size += n
    if cur:
        parts.append(cur)
    return parts


def match_by_number(items: list[dict], got: list[ItemSummary]) -> list[ItemSummary | None]:
    """Pair answers with items by the item number the model echoes; fall back to order when numbers are missing."""
    by_num = {g.number: g for g in got if g.number is not None}
    if len(by_num) >= max(1, len(got) - 1):
        return [by_num.get(it["position"]) for it in items]
    return (list(got) + [None] * len(items))[: len(items)]


def summarise_session(session: dict, items: list[dict], allowed: list[str], with_notes: bool = True) -> tuple[list[ItemSummary | None], SessionNotes | None]:
    tpl = (config.PROMPTS / "item.md").read_text(encoding="utf-8")
    m = config.municipality(session["municipality"])
    results: list[ItemSummary | None] = []
    notes = None
    parts = split_by_size(items)
    for k, part in enumerate(parts):
        last = k == len(parts) - 1
        prompt = tpl.format(municipality=m["name"], date=session["date"], allowed_names=", ".join(allowed) or "(none)",
                            n=len(part), items=render_items(part))
        if with_notes and last and len(parts) == 1:
            prompt += "\n\n" + (config.PROMPTS / "session_inline.md").read_text(encoding="utf-8").format(allowed_names=", ".join(allowed) or "(none)")
            res = llm.generate(prompt, SessionSummary)
            notes = SessionNotes(decided=res.decided)
        else:
            res = llm.generate(prompt, ItemSummaries)
        results.extend(match_by_number(part, list(res.items)))
    return results, notes


RAISED_RE = re.compile(r"\b(vraag|vragen|voorstel|interpellatie|amendement|agendapunt van|toegevoegd)\b", re.I)


def locate_quote(quote: str, segments: list[dict]) -> float | None:
    """Start time of the segment where the quote begins (the model's own time stamp is not trusted)."""
    words = _norm(quote).split()
    if len(words) < 3:
        return None
    head = " ".join(words[:4])
    best, best_score = None, 0.0
    for s in segments:
        t = _norm(s["text"])
        if head and head in t:
            return s["start"]
        score = sum(1 for w in words[:8] if w in t.split()) / min(len(words), 8)
        if score > best_score:
            best, best_score = s["start"], score
    return best if best_score >= 0.75 else None


def verify(summary: ItemSummary, item: dict, allowed: list[str]) -> ItemSummary:
    s = summary.model_copy()
    if not quote_in_text(s.quote, item["text"]):
        s.quote, s.quote_start = None, None
    elif item.get("segments"):
        s.quote_start = locate_quote(s.quote, item["segments"])
    # "raised by" only exists for questions, proposals and amendments; the official title wins when it names someone
    from_title = speakers.name_from_title(item["title"])
    if from_title:
        m = speakers.match_member(from_title, {"members": [{"name": a} for a in allowed]})
        s.raised_by = m["name"] if m else from_title
    elif RAISED_RE.search(item["title"]):
        s.raised_by = check_raised_by(s.raised_by, allowed, item["title"])
    else:
        s.raised_by = None
    if s.topic not in TOPICS:
        s.topic = "andere"
    if s.outcome not in OUTCOMES:
        s.outcome = "onbekend"
    return s


def session_notes(session: dict, items: list[dict], summaries: list[dict], allowed: list[str]) -> SessionNotes:
    tpl = (config.PROMPTS / "session.md").read_text(encoding="utf-8")
    m = config.municipality(session["municipality"])
    lines = []
    for it, sm in zip(items, summaries):
        if not sm:
            continue
        votes = f" ({it['votes_for']} voor, {it['votes_against']} tegen, {it['abstentions']} onth.)" if it.get("votes_for") is not None else ""
        qs = f" quote_start={sm['quote_start']}" if sm.get("quote_start") else ""
        lines.append(f"- Item {it['position']} (start {int(it['start'] or 0)} s{qs}): {it['title']}{votes}. {sm['nl']} Uitkomst: {sm['outcome']}.")
    prompt = tpl.format(municipality=m["name"], date=session["date"], allowed_names=", ".join(allowed) or "(none)", items="\n".join(lines))
    return llm.generate(prompt, SessionNotes)


def run(con, session: dict, args) -> int:
    segs = [dict(r) for r in con.execute("SELECT start,end,text,speaker FROM transcript_segments WHERE session_id=? ORDER BY start", (session["id"],))]
    items = [dict(r) for r in con.execute(
        "SELECT a.id, a.position, a.title, a.votes_for, a.votes_against, a.abstentions, s.start, s.end FROM agenda_items a "
        "JOIN item_spans s ON s.item_id=a.id AND s.session_id=a.session_id AND s.method='final' "
        "WHERE a.session_id=? AND a.public=1 AND s.start IS NOT NULL ORDER BY s.start", (session["id"],))]
    names = {r["speaker"]: r["name"] for r in con.execute("SELECT speaker,name FROM speaker_names WHERE session_id=?", (session["id"],))}
    council = speakers.load_council(session["municipality"], session["date"])
    allowed = allowed_names(council, items)
    for it in items:
        it["text"] = span_text(segs, names, it["start"], it["end"])
        it["segments"] = [x for x in segs if x["end"] >= it["start"] and x["start"] <= it["end"]]
        it["hash"] = content_hash(config.LLM_MODEL, it["title"], it["text"])
    todo = [it for it in items if args.force or con.execute("SELECT 1 FROM summaries WHERE item_id=? AND content_hash=?", (it["id"], it["hash"])).fetchone() is None]
    budget = config.LLM_MAX_ITEMS
    todo = todo[:budget]
    rid = db.run_start(con, "summarise", session["id"])
    done = 0
    try:
        inline_notes = None
        if todo:
            got, inline_notes = summarise_session(session, todo, allowed, with_notes=(len(todo) == len(items)))
            for it, sm in zip(todo, got):
                if sm is None:
                    continue
                v = verify(sm, it, allowed)
                con.execute("INSERT OR REPLACE INTO summaries(item_id,model,content_hash,nl,topic,outcome,raised_by,quote,quote_start,created_at,discussed) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (it["id"], config.LLM_MODEL, it["hash"], v.nl, v.topic, v.outcome, v.raised_by, v.quote, v.quote_start, db.now(),
                             int(v.discussed)))
                done += 1
            con.commit()
        sums = []
        for it in items:
            r = con.execute("SELECT nl,outcome,quote_start FROM summaries WHERE item_id=?", (it["id"],)).fetchone()
            sums.append(dict(r) if r else None)
        if any(sums):
            h = content_hash(config.LLM_MODEL, *[(s or {}).get("nl", "") for s in sums])
            if args.force or con.execute("SELECT 1 FROM session_notes WHERE session_id=? AND content_hash=?", (session["id"], h)).fetchone() is None:
                notes = inline_notes or session_notes(session, items, sums, allowed)
                con.execute("INSERT OR REPLACE INTO session_notes(session_id,model,content_hash,decided,created_at) VALUES(?,?,?,?,?)",
                            (session["id"], config.LLM_MODEL, h, db.dumps(notes.decided), db.now()))
                con.commit()
        pending = sum(1 for it in items if con.execute("SELECT 1 FROM summaries WHERE item_id=?", (it["id"],)).fetchone() is None)
        if pending == 0:
            db.advance(con, session["id"], "summarised")
        db.run_end(con, rid, True, f"{done} new, {pending} pending")
        print(f"{session['municipality']:<10} {session['date']}  {done} summaries written, {pending} pending")
    except llm.QuotaExhausted as exc:
        con.commit()
        db.run_end(con, rid, False, f"quota: {exc}")
        print(f"{session['municipality']:<10} {session['date']}  gemini quota reached after {done}; the rest stays pending")
        return 1
    except Exception as exc:
        db.run_end(con, rid, False, str(exc))
        print(f"{session['municipality']:<10} {session['date']}  summarise failed: {exc}")
        return 1
    return 0
