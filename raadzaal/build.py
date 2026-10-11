"""Write the JSON the static dashboard reads: index, one file per session, a search corpus and the stats."""
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from raadzaal import config, db, diarise, speakers
from raadzaal.summarise import RAISED_RE

CHUNK_S = 30.0
MINOR_S = 30.0  # unnamed clusters with less speaking time are shown together as 'overige sprekers'
DISAGREE_S = 120.0


DASH_RE = re.compile("[\u2013\u2014\u2212]")
NOT_FOUND_RE = re.compile(r"niet (?:terug)?gevonden|niet besproken|komt niet aan bod", re.I)
# The chair closing the council and opening the OCMW council (raad voor maatschappelijk welzijn), which follows on the
# same recording. The last agenda item runs to the end of the recording unless this cue cuts it.
OCMW_RE = re.compile(r"(?:gaan|komen|kunnen) we\s+(?:\w+\s+){0,3}?(?:naar|aan|tot)\s+(?:de|het)\s+(?:ocmw|raad voor maatschappelijk welzijn)"
                     r"|overgaan naar (?:de|het) (?:ocmw|raad voor maatschappelijk welzijn)"
                     r"|sluiten we (?:bij deze )?de gemeenteraad|gemeenteraad (?:is )?ten einde", re.I)
OCMW_MIN_S = 30.0  # the cue must come this long after the item started, or it is the item itself being announced


def speller(slug: str):
    """Fix the recurring speech-recognition errors listed under `spelling` in municipalities.yaml (whole words only)."""
    fixes = (config.municipality(slug).get("spelling") or {})
    rx = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(fixes, key=len, reverse=True)) + r")\b") if fixes else None

    def fix(t):
        if not isinstance(t, str):
            return t
        t = DASH_RE.sub("-", t)  # official titles use en dashes; the site keeps to plain hyphens
        return rx.sub(lambda m: fixes[m.group(1)], t) if rx else t
    return fix


def outcome_from_votes(votes: dict | None, model_outcome: str | None) -> str | None:
    """The official vote decides the badge; the model's reading only counts when there was no vote."""
    if votes:
        if votes["gevolg"]:
            g = votes["gevolg"].lower()
            if "goedgekeurd" in g or "aangenomen" in g:
                return "aangenomen"
            if "afgekeurd" in g or "verworpen" in g:
                return "verworpen"
        return "aangenomen" if votes["voor"] > votes["tegen"] else "verworpen"
    return model_outcome


def _agenda(con, session_id: str, fix=lambda t: t) -> list[dict]:
    rows = con.execute(
        "SELECT a.id, a.position, a.title, a.public, a.votes_for, a.votes_against, a.abstentions, a.outcome AS vote_outcome, a.origin, a.source_url, "
        "s.start, s.end, s.score AS disagreement, m.nl, m.en, m.topic, m.outcome, m.raised_by, m.quote, m.quote_start, m.discussed "
        "FROM agenda_items a LEFT JOIN item_spans s ON s.item_id=a.id AND s.session_id=a.session_id AND s.method='final' "
        "LEFT JOIN summaries m ON m.item_id=a.id WHERE a.session_id=? ORDER BY a.position, a.id", (session_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        summary = None
        doubtful = d["discussed"] == 0 or bool(d["nl"] and NOT_FOUND_RE.search(d["nl"]))
        votes = None
        if d["votes_for"] is not None and (d["votes_for"] or 0) + (d["votes_against"] or 0) + (d["abstentions"] or 0) > 0:
            votes = {"voor": d["votes_for"], "tegen": d["votes_against"] or 0, "onthouding": d["abstentions"] or 0, "gevolg": d["vote_outcome"]}
        # a summary is only shown for an item that is placed on the recording now; older summaries of items that lost
        # their place describe whatever the old span held
        if d["nl"] and not doubtful and d["start"] is not None:
            summary = {k: fix(d[k]) for k in ("nl", "topic", "quote", "quote_start")}
            summary["outcome"] = outcome_from_votes(votes, d["outcome"])
            name = speakers.name_from_title(d["title"] or "")
            summary["raised_by"] = d["raised_by"] if (name or RAISED_RE.search(d["title"] or "")) else None
        out.append({"id": d["id"], "position": d["position"], "title": fix(d["title"]), "public": bool(d["public"]), "origin": d["origin"],
                    "source_url": d["source_url"], "start": None if doubtful else d["start"], "end": None if doubtful else d["end"],
                    "placed_at": d["start"], "doubtful": doubtful and d["start"] is not None, "disagreement": d["disagreement"],
                    "votes": votes, "summary": summary})
    return out


def cut_ocmw_tail(agenda: list[dict], transcript: list[list]) -> float | None:
    """End the last placed item where the chair opens the OCMW council. Returns the cut time, or None."""
    placed = [a for a in agenda if a["start"] is not None]
    if not placed:
        return None
    last = max(placed, key=lambda a: a["start"])
    for st, en, text, spk in transcript:
        if st > last["start"] + OCMW_MIN_S and (last["end"] is None or st < last["end"]) and OCMW_RE.search(text):
            last["end"] = st
            return st
    return None


def _speakers(con, session_id: str) -> tuple[list[dict], float]:
    turns = [dict(r) for r in con.execute("SELECT speaker,start,end FROM speaker_turns WHERE session_id=?", (session_id,))]
    tt = diarise.speaking_time(turns)
    names = {r["speaker"]: dict(r) for r in con.execute("SELECT speaker,name,party,role FROM speaker_names WHERE session_id=?", (session_id,))}
    total = sum(tt.values()) or 1.0
    out = []
    rank = 0
    for spk, sec in sorted(tt.items(), key=lambda kv: -kv[1]):
        n = names.get(spk, {})
        if not n.get("name"):
            rank += 1
        label = n.get("name") or (f"Spreker {rank}" if sec >= MINOR_S else None)
        out.append({"speaker": spk, "label": label, "name": n.get("name"), "party": n.get("party"), "role": n.get("role"),
                    "seconds": round(sec), "share": round(sec / total, 3)})
    attributed = round(sum(s["seconds"] for s in out if s["name"]) / total, 3) if out else 0.0
    return out, attributed


def _transcript(con, session_id: str, fix=lambda t: t) -> list[list]:
    return [[round(r["start"], 1), round(r["end"], 1), fix(r["text"]), r["speaker"]] for r in
            con.execute("SELECT start,end,text,speaker FROM transcript_segments WHERE session_id=? ORDER BY start", (session_id,))]


def session_payload(con, s: dict) -> dict:
    m = config.municipality(s["municipality"])
    fix = speller(s["municipality"])
    agenda = _agenda(con, s["id"], fix)
    transcript = _transcript(con, s["id"], fix)
    cut_ocmw_tail(agenda, transcript)
    spk, attributed = _speakers(con, s["id"])
    notes = con.execute("SELECT decided, notable FROM session_notes WHERE session_id=?", (s["id"],)).fetchone()
    method = "agenda_dp" if any(a["origin"] == "lblod" for a in agenda) else ("llm" if agenda else "none")
    disagreements = sum(1 for a in agenda if (a["disagreement"] or 0) > DISAGREE_S)
    return {"id": s["id"], "municipality": s["municipality"], "municipality_name": m["name"], "date": s["date"], "title": s["title"],
            "duration_s": s["duration_s"], "url": s["url"], "status": s["status"], "lblod_zitting": s["lblod_zitting"],
            "agenda": agenda, "speakers": spk, "attributed_share": attributed,
            "notes": {"decided": [fix(d) for d in db.loads(notes["decided"])] if notes else []},  # "notable" picks partisan lines: not published
            "method": {"alignment": method, "disagreements_over_120s": disagreements},
            "transcript": transcript}


def search_docs(payloads: list[dict]) -> list[dict]:
    docs = []
    for p in payloads:
        for a in p["agenda"]:
            if a["start"] is None:
                continue
            text = a["title"] + (" " + a["summary"]["nl"] if a["summary"] else "")
            docs.append({"id": f"i{a['id']}", "type": "item", "session": p["id"], "municipality": p["municipality_name"], "date": p["date"],
                         "title": a["title"], "text": text, "start": a["start"]})
        chunk, t0, n = [], 0.0, 0
        for st, en, text, spk in p["transcript"]:
            if not chunk:
                t0 = st
            chunk.append(text)
            if en - t0 >= CHUNK_S:
                docs.append({"id": f"c{p['id']}-{n}", "type": "chunk", "session": p["id"], "municipality": p["municipality_name"],
                             "date": p["date"], "title": "", "text": " ".join(chunk), "start": t0})
                chunk, n = [], n + 1
        if chunk:
            docs.append({"id": f"c{p['id']}-{n}", "type": "chunk", "session": p["id"], "municipality": p["municipality_name"],
                         "date": p["date"], "title": "", "text": " ".join(chunk), "start": t0})
    return docs


def stats(payloads: list[dict]) -> dict:
    topic_min = defaultdict(float)
    muni = defaultdict(lambda: {"sessions": 0, "hours": 0.0, "items": 0, "summarised": 0, "named_seconds": 0.0, "total_seconds": 0.0})
    contested, questions_s, total_span_s = [], 0.0, 0.0
    for p in payloads:
        mm = muni[p["municipality"]]
        mm["sessions"] += 1
        mm["hours"] += (p["duration_s"] or 0) / 3600
        for a in p["agenda"]:
            if a["votes"] and (a["votes"]["tegen"] or 0) > 0:  # official vote counts hold whatever the placement
                contested.append({"session": p["id"], "municipality": p["municipality_name"], "date": p["date"], "title": a["title"],
                                  "votes": a["votes"], "start": a["start"]})
            if a["start"] is None:
                continue
            mm["items"] += 1
            dur = (a["end"] or a["start"]) - a["start"]
            total_span_s += dur
            if a["summary"]:
                mm["summarised"] += 1
                topic_min[a["summary"]["topic"]] += dur / 60
            if any(w in a["title"].lower() for w in ("vraag", "interpellatie", "voorstel", "vragen")):
                questions_s += dur
        for s in p["speakers"]:
            mm["total_seconds"] += s["seconds"]
            if s["name"]:
                mm["named_seconds"] += s["seconds"]
    out_m = {}
    for slug, mm in muni.items():
        out_m[slug] = {"sessions": mm["sessions"], "hours": round(mm["hours"], 1), "items": mm["items"], "summarised": mm["summarised"],
                       "attributed_share": round(mm["named_seconds"] / mm["total_seconds"], 3) if mm["total_seconds"] else 0.0}
    return {"topic_minutes": {k: round(v) for k, v in sorted(topic_min.items(), key=lambda kv: -kv[1])},
            "municipalities": out_m, "contested": sorted(contested, key=lambda c: -c["votes"]["tegen"])[:30],
            "questions_share": round(questions_s / total_span_s, 3) if total_span_s else 0.0,
            "hours_total": round(sum(mm["hours"] for mm in out_m.values()), 1),
            "items_total": sum(mm["items"] for mm in out_m.values())}


def write(con) -> dict:
    config.DOCS_DATA.mkdir(parents=True, exist_ok=True)
    (config.DOCS_DATA / "sessions").mkdir(exist_ok=True)
    sessions = [s for s in db.sessions(con) if db.status_index(s["status"]) >= db.status_index("transcribed")]
    keep = {f"{s['id']}.json" for s in sessions}
    for old in (config.DOCS_DATA / "sessions").glob("*.json"):
        if old.name not in keep:
            old.unlink()  # excluded or removed sessions must not stay online
    payloads = []
    for s in sessions:
        p = session_payload(con, s)
        payloads.append(p)
        (config.DOCS_DATA / "sessions" / f"{s['id']}.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    munis = []
    for m in config.municipalities():
        ps = [p for p in payloads if p["municipality"] == m["slug"]]
        munis.append({"slug": m["slug"], "name": m["name"], "province": m["province"], "sessions": len(ps),
                      "hours": round(sum((p["duration_s"] or 0) for p in ps) / 3600, 1),
                      "last_date": max((p["date"] for p in ps), default=None), "has_agenda": m.get("lblod_harvester") is not None})
    index = {"built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "municipalities": munis,
             "sessions": [{"id": p["id"], "municipality": p["municipality"], "municipality_name": p["municipality_name"], "date": p["date"],
                           "title": p["title"], "duration_s": p["duration_s"], "items": sum(1 for a in p["agenda"] if a["start"] is not None),
                           "summarised": sum(1 for a in p["agenda"] if a["summary"]), "url": p["url"],
                           "decided": p["notes"]["decided"][:2]} for p in sorted(payloads, key=lambda p: p["date"], reverse=True)]}
    (config.DOCS_DATA / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    (config.DOCS_DATA / "search.json").write_text(json.dumps(search_docs(payloads), ensure_ascii=False), encoding="utf-8")
    st = stats(payloads)
    (config.DOCS_DATA / "stats.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    for s in sessions:
        if db.status_index(s["status"]) >= db.status_index("summarised"):
            db.advance(con, s["id"], "built")
    return {"sessions": len(payloads), **{k: st[k] for k in ("hours_total", "items_total")}}


def run(con, args) -> int:
    r = write(con)
    print(f"built {r['sessions']} sessions, {r['hours_total']} h, {r['items_total']} items -> {config.DOCS_DATA}")
    return 0
