"""Topics inside long items that cover many subjects: a questions round, or an item the summary could only call 'andere'.
The item's transcript is cut into windows of about two minutes and each window gets its own topic, one call per item.
The windows go to the topic_windows table; build.stats counts their minutes instead of the single item topic."""
import json
import re
from typing import Literal

from pydantic import BaseModel

from raadzaal import config, db, llm
from raadzaal.summarise import TOPICS

WINDOW_S = 120.0
MIN_S = 180.0  # shorter items keep their single topic
MODELS = ("gemini-2.5-flash", "gemini-3-flash-preview", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite")
QUESTIONS_RE = re.compile(r"^\s*(?:eventuele vragen|vragenronde|mondelinge vragen|varia(?:-punten)?(?: gemeenteraad)?\s*$)", re.I)

PROMPT = """Below is one agenda item of a Flemish municipal council meeting, "{title}", cut into numbered parts of about two minutes of transcript.
Give each part the one topic it is about, from this list: {topics}.

- A part about a question, an answer or a debate gets the topic of its subject, even when the item as a whole is a questions round.
- Use "andere" only when a part fits none of the other topics, for example pure procedure, greetings or the order of the meeting.
- A part that continues the subject of the part before it keeps that topic.

Return one entry per part with its number.

{parts}
"""


class Window(BaseModel):
    i: int
    topic: Literal[TOPICS]  # type: ignore[valid-type]


class Windows(BaseModel):
    windows: list[Window]


def generate(prompt: str):
    last = None
    for m in MODELS:
        try:
            return llm.generate(prompt, Windows, model=m)
        except (llm.QuotaExhausted, RuntimeError) as exc:
            last = exc
    raise llm.QuotaExhausted(str(last)[:200])


def needs_windows(item: dict) -> bool:
    """A placed, summarised item of at least MIN_S that is a questions round or has no real topic."""
    if item["start"] is None or not item["summary"]:
        return False
    if (item["end"] or item["start"]) - item["start"] < MIN_S:
        return False
    return item["summary"]["topic"] == "andere" or bool(QUESTIONS_RE.search(item["title"] or ""))


def windows(transcript: list[list], start: float, end: float, size: float = WINDOW_S) -> list[dict]:
    """The item's transcript lines in windows of about `size` seconds. The windows cover the item from start to end
    without gaps: each one ends where the next begins, the last at the item's end."""
    out = []
    for st, en, text, spk in transcript:
        if st < start or st >= end:
            continue
        if not out or st - out[-1]["start"] >= size:
            out.append({"start": start if not out else st, "end": end, "lines": []})
        out[-1]["lines"].append(text)
    for a, b in zip(out, out[1:]):
        a["end"] = b["start"]
    return [{"start": w["start"], "end": w["end"], "text": " ".join(w["lines"])} for w in out]


def label(title: str, wins: list[dict], fallback: str) -> list[dict]:
    """One call for all windows of an item; a window the model skipped keeps the item's own topic."""
    parts = "\n\n".join(f"[{n}] {w['text']}" for n, w in enumerate(wins))
    r = generate(PROMPT.format(title=title, topics=", ".join(f'"{t}"' for t in TOPICS), parts=parts))
    got = {w.i: w.topic for w in r.windows}
    return [{"start": w["start"], "end": w["end"], "topic": got.get(n, fallback)} for n, w in enumerate(wins)]


def minutes(item_start: float, item_end: float, rows: list[dict], fallback: str) -> dict[str, float]:
    """Minutes per topic for one item from its windows, clipped to the item's span as built now. Time no window
    covers (the span grew since the windows were made) counts for the item's own topic."""
    out: dict[str, float] = {}
    covered = 0.0
    for w in rows:
        s, e = max(w["start"], item_start), min(w["end"], item_end)
        if e > s:
            out[w["topic"]] = out.get(w["topic"], 0.0) + (e - s) / 60
            covered += e - s
    rest = (item_end - item_start) - covered
    if rest > 0:
        out[fallback] = out.get(fallback, 0.0) + rest / 60
    return out


def load(con) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in con.execute("SELECT item_id, start, end, topic FROM topic_windows ORDER BY item_id, start"):
        out.setdefault(r["item_id"], []).append({"start": r["start"], "end": r["end"], "topic": r["topic"]})
    return out


def run(con, args) -> int:
    payloads = [json.loads(f.read_text(encoding="utf-8")) for f in sorted((config.DOCS_DATA / "sessions").glob("*.json"))]
    if args.municipality:
        payloads = [p for p in payloads if p["municipality"] == args.municipality]
    if args.session:
        payloads = [p for p in payloads if p["id"] in args.session]
    for p in payloads:
        for a in p["agenda"]:
            if not needs_windows(a):
                continue
            wins = windows(p["transcript"], a["start"], a["end"] or a["start"])
            if not wins:
                continue
            try:
                rows = label(a["title"], wins, a["summary"]["topic"])
            except llm.QuotaExhausted as exc:
                print(f"  quota: {exc}")
                return 1
            con.execute("DELETE FROM topic_windows WHERE item_id=?", (a["id"],))
            con.executemany("INSERT INTO topic_windows(session_id,item_id,start,end,topic) VALUES(?,?,?,?,?)",
                            [(p["id"], a["id"], w["start"], w["end"], w["topic"]) for w in rows])
            con.commit()
            counts = {}
            for w in rows:
                counts[w["topic"]] = counts.get(w["topic"], 0) + 1
            print(f"{p['id']} item {a['id']} {a['title'][:50]}: {len(rows)} windows {counts}")
    return 0
