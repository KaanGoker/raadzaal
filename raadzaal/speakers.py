"""Names for diarised speakers, from what the chair says and from the agenda titles. Conservative by design."""
import re
import unicodedata

import yaml
from rapidfuzz import fuzz

from raadzaal import config, db

NAME = r"([A-Z][\w'’\-]+(?:\s+(?:van|der|den|de|d'|het|op|'t|ten|te|[A-Z][\w'’\-]+)\b){0,3})"
TITLE = r"(?:mevrouw|meneer|mijnheer|de heer|schepen|raadslid|burgemeester|voorzitter|collega|dokter|dr\.?)\s+"
HANDOVER_RE = re.compile(r"(?i:het woord is aan|ik geef het woord aan|geef ik het woord aan|geef ik graag het woord aan|"
                         r"ik geef graag het woord aan|het woord aan|aan het woord is|dan is het woord aan)\s+(?i:" + TITLE + r")?" + NAME)
THANKS_RE = re.compile(r"(?i:dank u wel|dankuwel|dank u|bedankt|dank je wel|merci)\s*,?\s+(?i:" + TITLE + r")" + NAME)
SELF_RE = re.compile(r"(?i:\bik ben)\s+(?i:" + TITLE + r")?" + NAME)
LEAD = r"(?P<lead>(?:(?:ja|jawel|oké|ok|okay|goed|dan|en|allee|voilà|dank u wel|dank u|dankuwel|bedankt|merci)[,.]?\s+)*)"
VOCATIVE_RE = re.compile(r"^" + LEAD + r"(?i:(?:meneer|mevrouw|mijnheer|de heer|schepen|raadslid|burgemeester|collega)\s+)?"
                         r"(?P<name>[A-Z][\w'’\-]+(?:\s+(?:van|der|den|de|[A-Z][\w'’\-]+)){0,2})\s*[.?!,]?$", re.I)
TRAILING_RE = re.compile(r",\s*(?i:(?:meneer|mevrouw|mijnheer|de heer|schepen|raadslid|burgemeester)\s+)?"
                         r"(?P<name>[A-Z][\w'’\-]+(?:\s+(?:van|der|den|de|[A-Z][\w'’\-]+)){0,2})\s*[.?]$")
TITLE_NAME_RE = re.compile(r"\((?:raadslid|raadsleden|schepen|burgemeester)\s+" + NAME + r"\)|(?:vraag|voorstel|interpellatie)\s+van\s+(?:raadslid\s+)?" + NAME, re.I)
STOP = {"ja", "nee", "dank", "ik", "en", "dat", "dit", "wij", "we", "goed", "oké", "ok", "dus", "maar", "voorzitter",
        "schepen", "burgemeester", "raadslid", "mevrouw", "meneer", "mijnheer", "heer", "collega", "allemaal", "iedereen",
        "punt", "agendapunt", "dokter", "dr"}
MIN_VOTES = 2
DIRECT_CUES = {"handover", "thanks", "self"}
FUZZ = 85


def load_council(slug: str, on: str | None = None) -> dict:
    """The council file; with `on`, members who left before that date are dropped and former members who sat on
    that date are added (with role raadslid)."""
    p = config.COUNCILS / f"{slug}.yaml"
    if not p.exists():
        return {"members": [], "parties": []}
    c = yaml.safe_load(p.read_text(encoding="utf-8")) or {"members": [], "parties": []}
    if on:
        extra = [{"name": f["name"], "party": f.get("party"), "role": "raadslid"} for f in c.get("former", [])
                 if f.get("from", "0000") <= on <= (f.get("until") or "9999")]
        c = {**c, "members": list(c.get("members", [])) + extra}
    return c


def _clean(name: str) -> str:
    name = re.sub(r"[.,;:!?]+$", "", name.strip())
    toks = name.split()
    while toks and toks[-1].lower().rstrip(".") in STOP:
        toks.pop()
    while toks and toks[0].lower().rstrip(".") in STOP:
        toks.pop(0)
    return " ".join(toks)


def fold(s: str) -> str:
    """Lowercase, no accents, Flemish spelling variants merged (ij and y, doubled letters), so that Whisper's
    'Goddijn' meets 'Godyns' and 'Van Besien' meets 'Vanbesien'."""
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    s = s.replace("ij", "y")
    s = re.sub(r"[^a-z ]+", " ", s)
    s = re.sub(r"(.)\1+", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _forms(member: dict) -> dict:
    parts = member["name"].split()
    first, last = parts[0], " ".join(parts[1:]) or parts[0]
    return {"full": fold(member["name"]), "last": fold(last), "last_joined": fold(last).replace(" ", ""),
            "first": fold(first)}


def match_member(name: str, council: dict) -> dict | None:
    """The council member a spoken name refers to, or None when there is no clear match or two members fit equally.
    A first name alone counts only when no other member shares it."""
    raw = fold(_clean(name))
    if len(raw) < 3:
        return None
    joined = raw.replace(" ", "")
    members = council.get("members", [])
    firsts = [_forms(m)["first"] for m in members]
    scored = []
    for m in members:
        f = _forms(m)
        cands = [fuzz.ratio(raw, f["full"]), fuzz.ratio(raw, f["last"])]
        # a long surname survives one recognition slip more ('Van Edelbos' for 'Vannetelbosch')
        lj = fuzz.ratio(joined, f["last_joined"])
        cands.append(lj + (5 if len(f["last_joined"]) >= 8 else 0))
        if len(raw.split()) >= 2:
            cands.append(fuzz.partial_ratio(raw, f["full"]) if len(raw) >= 6 else 0)
        if firsts.count(f["first"]) == 1 and raw == f["first"]:
            cands.append(100)  # a first name alone must be exact and unique in the council
        scored.append((min(max(cands), 100), m))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < FUZZ:
        return None
    if len(scored) > 1 and scored[1][0] >= scored[0][0] - 3 and scored[1][1]["name"] != scored[0][1]["name"]:
        return None
    return scored[0][1]


def cues_from_text(text: str) -> list[tuple[str, str]]:
    """(kind, raw name) cues found in one segment's text."""
    out = []
    for m in HANDOVER_RE.finditer(text):
        out.append(("handover", m.group(1)))
    for m in THANKS_RE.finditer(text):
        out.append(("thanks", m.group(1)))
    for m in SELF_RE.finditer(text):
        out.append(("self", m.group(1)))
    if not out:
        v = VOCATIVE_RE.match(text.strip())
        if v:
            kind = "thanks" if v.group("lead") and re.search(r"dank|bedankt|merci", v.group("lead"), re.I) else "handover"
            out.append((kind, v.group("name")))
        else:
            t = TRAILING_RE.search(text.strip())
            if t:
                out.append(("handover", t.group("name")))
    return [(k, _clean(n)) for k, n in out if _clean(n)]


def name_from_title(title: str) -> str | None:
    m = TITLE_NAME_RE.search(title)
    if not m:
        return None
    return _clean(m.group(1) or m.group(2) or "")


def members_mentioned(text: str, council: dict) -> int:
    """How many different council members a segment names (a roll-call vote names many and says nothing about turns)."""
    found = set()
    for tok in re.findall(r"[A-Z][\w'’\-]+(?:\s+(?:[Vv]an|[Dd]e|[Dd]er|[Dd]en)\s+[A-Z][\w'’\-]+)?", text):
        m = match_member(tok, council)
        if m:
            found.add(m["name"])
    return len(found)


def _next_speaker_after(segments: list[dict], idx: int, current: int | None, horizon: float = 20.0) -> int | None:
    t0 = segments[idx]["end"]
    for s in segments[idx + 1:]:
        if s["start"] - t0 > horizon:
            break
        if s.get("speaker") is not None and s["speaker"] != current:
            return s["speaker"]
    return None


def _prev_speaker_before(segments: list[dict], idx: int, current: int | None, horizon: float = 20.0) -> int | None:
    t0 = segments[idx]["start"]
    for s in reversed(segments[:idx]):
        if t0 - s["end"] > horizon:
            break
        if s.get("speaker") is not None and s["speaker"] != current:
            return s["speaker"]
    return None


def collect_votes(segments: list[dict], items: list[dict], turn_time: dict[int, float], council: dict | None = None) -> dict[int, dict[str, list]]:
    """votes[speaker][name] = list of cue kinds. With a council, a vocative cue only counts when it names a member,
    and segments that name three or more members (roll-call votes) are skipped."""
    votes: dict[int, dict[str, list]] = {}
    given: dict[int, int] = {}

    def vote(spk, name, kind):
        if spk is None or not name:
            return
        votes.setdefault(spk, {}).setdefault(name, []).append(kind)

    for i, s in enumerate(segments):
        if council and council.get("members") and members_mentioned(s["text"], council) >= 3:
            continue
        for kind, name in cues_from_text(s["text"]):
            if council and council.get("members") and match_member(name, council) is None:
                continue
            if kind == "handover":
                vote(_next_speaker_after(segments, i, s.get("speaker")), name, kind)
                if s.get("speaker") is not None:
                    given[s["speaker"]] = given.get(s["speaker"], 0) + 1
            elif kind == "thanks":
                vote(_prev_speaker_before(segments, i, s.get("speaker")), name, kind)
            elif kind == "self":
                vote(s.get("speaker"), name, kind)
    # the chair is the one who keeps giving the floor
    total_given = sum(given.values())
    if council and council.get("chair") and total_given >= 5:
        spk, n = max(given.items(), key=lambda kv: kv[1])
        if n >= 5 and n >= 0.5 * total_given:
            votes.setdefault(spk, {}).setdefault(council["chair"], []).extend(["chair", "chair"])
    # agenda titles that carry a name: the non-chair speaker with the most time inside the item's span
    chair = max(turn_time, key=turn_time.get) if turn_time else None
    for it in items:
        name = name_from_title(it.get("title") or "")
        if not name or it.get("start") is None or it.get("end") is None:
            continue
        inside: dict[int, float] = {}
        for s in segments:
            if s.get("speaker") is None or s["end"] < it["start"] or s["start"] > it["end"]:
                continue
            if s["speaker"] == chair:
                continue
            inside[s["speaker"]] = inside.get(s["speaker"], 0.0) + (s["end"] - s["start"])
        if inside:
            vote(max(inside, key=inside.get), name, "agenda")
    return votes


def decide(votes: dict[int, dict[str, list]], council: dict) -> dict[int, dict]:
    """A speaker gets a name when one council member wins at least two cues, beats the runner-up two to one, and at
    least one cue is direct (given the floor, thanked, or introducing themselves). Being the chair or the name in an
    agenda title only supports a name: on their own they named the wrong cluster too often (a schepen answering a
    question, councillors merged into the chair's cluster). People who are not on the council list are never named."""
    out = {}
    for spk, names in votes.items():
        scored = []
        for raw, kinds in names.items():
            member = match_member(raw, council)
            canonical = member["name"] if member else raw
            scored.append((canonical, member, kinds))
        merged: dict[str, dict] = {}
        for canonical, member, kinds in scored:
            m = merged.setdefault(canonical, {"member": member, "kinds": []})
            m["kinds"].extend(kinds)
        ranked = sorted(merged.items(), key=lambda kv: len(kv[1]["kinds"]), reverse=True)
        top_name, top = ranked[0]
        second = len(ranked[1][1]["kinds"]) if len(ranked) > 1 else 0
        n = len(top["kinds"])
        direct = sum(1 for k in top["kinds"] if k in DIRECT_CUES)
        if n >= MIN_VOTES and n >= 2 * second and direct >= 1 and top["member"]:
            member = top["member"] or {}
            out[spk] = {"name": top_name, "party": member.get("party"), "role": member.get("role"),
                        "confidence": round(min(1.0, n / (n + second + 1)), 2), "cues": top["kinds"]}
    return out


def attributed_share(turn_time: dict[int, float], names: dict[int, dict]) -> float:
    total = sum(turn_time.values())
    if not total:
        return 0.0
    return round(sum(t for spk, t in turn_time.items() if spk in names) / total, 3)


def run(con, session: dict, args) -> int:
    from raadzaal import diarise
    segs = [dict(r) for r in con.execute("SELECT start,end,text,speaker FROM transcript_segments WHERE session_id=? ORDER BY start", (session["id"],))]
    turns = [dict(r) for r in con.execute("SELECT speaker,start,end FROM speaker_turns WHERE session_id=?", (session["id"],))]
    items = [dict(r) for r in con.execute(
        "SELECT a.id, a.title, s.start, s.end FROM agenda_items a LEFT JOIN item_spans s ON s.item_id=a.id AND s.session_id=a.session_id AND s.method='final' "
        "WHERE a.session_id=?", (session["id"],))]
    council = load_council(session["municipality"], session["date"])
    tt = diarise.speaking_time(turns)
    names = decide(collect_votes(segs, items, tt, council), council)
    rows = [{"session_id": session["id"], "speaker": spk, "name": v["name"], "party": v["party"], "role": v["role"],
             "confidence": v["confidence"], "cues": db.dumps(v["cues"])} for spk, v in names.items()]
    db.replace_rows(con, "speaker_names", session["id"], rows)
    share = attributed_share(tt, names)
    print(f"{session['municipality']:<10} {session['date']}  {len(names)} of {len(tt)} speakers named, {share:.0%} of speaking time")
    return 0
