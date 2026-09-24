"""Split a recording into agenda items: a Gemini reading gives the anchors, a monotone alignment on embeddings and cues fills the gaps."""
import json
import os
import re
from pathlib import Path

import numpy as np
from pydantic import BaseModel
from rapidfuzz import fuzz

from raadzaal import agenda as agenda_mod
from raadzaal import config, db, llm

WIN, STRIDE = 45.0, 15.0
MIN_GAP_WINDOWS = 2          # an item lasts at least two strides (30 s)
FLOOR = 0.22                 # start score under which an item counts as not found
ORDER_NUMBER_WEIGHT = float(os.environ.get('ORDER_NUMBER_WEIGHT', '0.1'))  # spoken number vs agenda order
CHUNK, OVERLAP = 5 * 3600, 5 * 60   # one Gemini call per session; the free tier counts requests, not tokens
_embedder = None
_NUMBER_WORDS = {1: "een", 2: "twee", 3: "drie", 4: "vier", 5: "vijf", 6: "zes", 7: "zeven", 8: "acht", 9: "negen", 10: "tien",
                 11: "elf", 12: "twaalf", 13: "dertien", 14: "veertien", 15: "vijftien", 16: "zestien", 17: "zeventien",
                 18: "achttien", 19: "negentien", 20: "twintig"}
_STOP = set("de het een en van voor over met op in tot bij aan door naar uit als om te dat die dit deze er ook nog wordt worden is zijn was waren goedkeuring kennisname kennisgeving vaststelling besluit betreffende inzake".split())


def windows(segments: list[dict], win: float = WIN, stride: float = STRIDE) -> list[dict]:
    if not segments:
        return []
    end = max(s["end"] for s in segments)
    out, t = [], 0.0
    i = 0
    while t < end:
        texts = []
        j = i
        while j < len(segments) and segments[j]["start"] < t + win:
            if segments[j]["end"] > t:
                texts.append(segments[j]["text"])
            j += 1
        while i < len(segments) and segments[i]["end"] <= t + stride:
            i += 1
        out.append({"start": t, "end": min(t + win, end), "text": " ".join(texts)})
        t += stride
    return out


def embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(config.EMBED_MODEL, cache_folder=str(config.MODELS / "st"), device="cpu")
    return _embedder


def embed(texts: list[str]) -> np.ndarray:
    v = embedder().encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
    return np.asarray(v, dtype=np.float32)


def content_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zà-ÿ0-9]{4,}", text.lower()) if t not in _STOP}


def cue_bonus(window_text: str, item: dict) -> float:
    t = window_text.lower()
    bonus = 0.0
    # only a number printed in the official title is trusted: the order in the open data can be off by one
    # from what the chair says (Beernem counts the opening announcements, Lokaal Beslist does not)
    printed = agenda_mod.position_from_title(item.get("title") or "")
    for pos, weight in ((printed, 0.25), (None if printed else item.get("position"), ORDER_NUMBER_WEIGHT)):
        if pos and (re.search(rf"\b(agenda)?punt(je)?\s+{pos}\b", t) or
                    (pos in _NUMBER_WORDS and re.search(rf"\b(agenda)?punt(je)?\s+{_NUMBER_WORDS[pos]}\b", t))):
            bonus += weight
    if re.search(r"volgend(e)? (agenda)?punt|gaan we over naar|komen we bij|dan komen we aan|volgende? (agenda)?punt", t):
        bonus += 0.05
    toks = content_tokens(item.get("title") or "")
    if toks:
        hit = len(toks & content_tokens(t)) / len(toks)
        bonus += 0.25 * hit
    return bonus


def score_matrix(wins: list[dict], items: list[dict]) -> np.ndarray:
    if not wins or not items:
        return np.zeros((len(items), len(wins)), dtype=np.float32)
    W = embed([w["text"] or " " for w in wins])
    T = embed([it["title"] for it in items])
    S = T @ W.T
    for i, it in enumerate(items):
        for j, w in enumerate(wins):
            S[i, j] += cue_bonus(w["text"], it)
    return S


def dp_align(S: np.ndarray, min_gap: int = MIN_GAP_WINDOWS) -> list[int]:
    """Start window per item, strictly increasing by at least `min_gap`, maximising the summed start scores."""
    n, m = S.shape
    if n == 0 or m == 0:
        return []
    NEG = -1e9
    best = np.full((n, m), NEG, dtype=np.float64)
    back = np.full((n, m), -1, dtype=np.int64)
    best[0] = S[0]
    for i in range(1, n):
        # prefix max of best[i-1] up to j - min_gap
        pm_val, pm_idx = NEG, -1
        for j in range(m):
            k = j - min_gap
            if k >= 0 and best[i - 1, k] > pm_val:
                pm_val, pm_idx = best[i - 1, k], k
            if pm_idx >= 0:
                best[i, j] = S[i, j] + pm_val
                back[i, j] = pm_idx
    j = int(np.argmax(best[n - 1]))
    starts = [0] * n
    for i in range(n - 1, -1, -1):
        starts[i] = j
        j = int(back[i, j]) if i > 0 else j
    return starts


def spans(starts: list[int], wins: list[dict], S: np.ndarray, session_end: float) -> list[dict]:
    out = []
    for i, j in enumerate(starts):
        start = wins[j]["start"]
        end = wins[starts[i + 1]]["start"] if i + 1 < len(starts) else session_end
        score = float(S[i, j])
        out.append({"start": start, "end": end, "score": round(score, 3), "found": score >= FLOOR})
    return out


def agenda_dp(segments: list[dict], items: list[dict]) -> list[dict]:
    wins = windows(segments)
    S = score_matrix(wins, items)
    starts = dp_align(S)
    end = max((s["end"] for s in segments), default=0.0)
    res = spans(starts, wins, S, end) if starts else []
    return [{"item_id": it["id"], **sp} for it, sp in zip(items, res)]


# Gemini second opinion

class AlignedItem(BaseModel):
    start_s: float
    title: str
    number: int | None = None


class AlignedItems(BaseModel):
    items: list[AlignedItem]


def render(segments: list[dict], t0: float, t1: float) -> str:
    lines = []
    for s in segments:
        if s["end"] < t0 or s["start"] > t1:
            continue
        lines.append(f"[{int(s['start'])}] {s['text']}")
    return "\n".join(lines)


def llm_align(segments: list[dict], agenda_titles: list[str] | None) -> list[dict]:
    prompt_tpl = (config.PROMPTS / "align.md").read_text(encoding="utf-8")
    hint = ""
    if agenda_titles:
        hint = "The official agenda, in order, was:\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(agenda_titles))
    end = max((s["end"] for s in segments), default=0.0)
    found = []
    t = 0.0
    while t < end:
        t1 = min(t + CHUNK, end)
        text = render(segments, t, t1)
        if text.strip():
            prompt = prompt_tpl.format(agenda_hint=hint, part_label=f"{llm.fmt_time(t)} to {llm.fmt_time(t1)}", transcript=text)
            res = llm.generate(prompt, AlignedItems)
            for it in res.items:
                if t <= it.start_s <= t1:
                    found.append({"start": float(it.start_s), "title": it.title.strip(), "number": it.number})
        t += CHUNK - OVERLAP
    return stitch(found)


def stitch(found: list[dict], window: float = 60.0) -> list[dict]:
    """Merge the same announcement seen in two overlapping chunks."""
    out: list[dict] = []
    for f in sorted(found, key=lambda x: x["start"]):
        if out and f["start"] - out[-1]["start"] <= window and (
                fuzz.token_set_ratio(f["title"], out[-1]["title"]) >= 70 or (f["number"] and f["number"] == out[-1]["number"])):
            continue
        out.append(dict(f))
    return out


def map_to_agenda(llm_items: list[dict], items: list[dict]) -> dict[int, float]:
    """item_id -> LLM start. Titles decide; a spoken number only adds a small bonus, because chairs often count
    differently from the official order (Beernem and Tervuren run one off). Best matches are taken first."""
    pairs = []
    for li_idx, li in enumerate(llm_items):
        for it in items:
            score = fuzz.token_set_ratio(li["title"], it["title"])
            if li.get("number") and li["number"] == it.get("position"):
                score += 10
            pairs.append((score, li_idx, it["id"]))
    pairs.sort(key=lambda x: -x[0])
    used_li, used_it, res = set(), set(), {}
    for score, li_idx, item_id in pairs:
        if score < 60:
            break
        if li_idx in used_li or item_id in used_it:
            continue
        used_li.add(li_idx); used_it.add(item_id)
        res[item_id] = llm_items[li_idx]["start"]
    return res


def _increasing(pairs: list[tuple[int, float]]) -> set[int]:
    """Indices (into pairs, ordered by agenda position) of the longest run of strictly increasing start times."""
    n = len(pairs)
    if n == 0:
        return set()
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if pairs[j][1] < pairs[i][1] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(n), key=lambda k: best[k])
    keep = set()
    while i != -1:
        keep.add(i)
        i = prev[i]
    return keep


def final_spans(items: list[dict], dp: list[dict], llm_starts: dict[int, float], session_end: float) -> list[dict]:
    """The published spans. Gemini's reading anchors the items it recognised (kept only where they are in agenda
    order); the embedding placement fills the items in between when it falls between the neighbouring anchors.
    The score is the disagreement between the two methods in seconds, or None when only one method placed the item."""
    n = len(items)
    anchored = [(i, llm_starts[it["id"]]) for i, it in enumerate(items) if it["id"] in llm_starts]
    keep = _increasing(anchored)
    start: list[float | None] = [None] * n
    for k, (i, t) in enumerate(anchored):
        if k in keep:
            start[i] = t
    for i in range(n):
        if start[i] is not None or not dp[i]["found"]:
            continue
        lo = max((start[j] for j in range(i) if start[j] is not None), default=-1.0)
        hi = min((start[j] for j in range(i + 1, n) if start[j] is not None), default=float("inf"))
        if lo < dp[i]["start"] < hi:
            start[i] = dp[i]["start"]
    placed = sorted((start[i], i) for i in range(n) if start[i] is not None)
    end = [None] * n
    for k, (t, i) in enumerate(placed):
        end[i] = placed[k + 1][0] if k + 1 < len(placed) else session_end
    out = []
    for i, it in enumerate(items):
        dis = None
        if it["id"] in llm_starts and dp[i]["found"]:
            dis = round(abs(llm_starts[it["id"]] - dp[i]["start"]), 1)
        out.append({"item_id": it["id"], "start": start[i], "end": end[i], "method": "final", "score": dis})
    return out


def run(con, session: dict, args) -> int:
    segs = [dict(r) for r in con.execute("SELECT id,start,end,text,speaker FROM transcript_segments WHERE session_id=? ORDER BY start", (session["id"],))]
    if not segs:
        print(f"{session['id']}: no transcript")
        return 1
    items = [dict(r) for r in con.execute("SELECT id,position,title,origin FROM agenda_items WHERE session_id=? ORDER BY position", (session["id"],))]
    end = max(s["end"] for s in segs)
    rid = db.run_start(con, "align", session["id"])
    try:
        rows = []
        if items and items[0]["origin"] == "lblod":
            dp = agenda_dp(segs, items)
            rows += [{"session_id": session["id"], "item_id": d["item_id"], "start": d["start"], "end": d["end"], "method": "agenda_dp", "score": d["score"]} for d in dp]
            llm_starts = {}
            try:
                li = llm_align(segs, [it["title"] for it in items])
                llm_starts = map_to_agenda(li, items)
                rows += [{"session_id": session["id"], "item_id": k, "start": v, "end": None, "method": "llm", "score": None} for k, v in llm_starts.items()]
            except llm.QuotaExhausted as exc:
                print(f"  gemini quota: {exc}; second opinion skipped")
            rows += [{"session_id": session["id"], **f} for f in final_spans(items, dp, llm_starts, end)]
        else:
            li = llm_align(segs, None)
            existing = [(r["position"], r["title"]) for r in con.execute(
                "SELECT position, title FROM agenda_items WHERE session_id=? AND origin='llm' ORDER BY position", (session["id"],))]
            if existing != [(i, l["title"]) for i, l in enumerate(li, 1)]:
                # a different reading: replace the items (their summaries go with them)
                con.execute("DELETE FROM summaries WHERE item_id IN (SELECT id FROM agenda_items WHERE session_id=? AND origin='llm')", (session["id"],))
                con.execute("DELETE FROM agenda_items WHERE session_id=? AND origin='llm'", (session["id"],))
                for i, l in enumerate(li, 1):
                    con.execute("INSERT INTO agenda_items(session_id,position,title,public,origin) VALUES(?,?,?,1,'llm')",
                                (session["id"], i, l["title"]))
                con.commit()
            new_items = [dict(r) for r in con.execute("SELECT id,position,title FROM agenda_items WHERE session_id=? AND origin='llm' ORDER BY id", (session["id"],))]
            for i, (it, l) in enumerate(zip(new_items, li)):
                e = li[i + 1]["start"] if i + 1 < len(li) else end
                rows.append({"session_id": session["id"], "item_id": it["id"], "start": l["start"], "end": e, "method": "llm", "score": None})
                rows.append({"session_id": session["id"], "item_id": it["id"], "start": l["start"], "end": e, "method": "final", "score": None})
        db.replace_rows(con, "item_spans", session["id"], rows)
        db.advance(con, session["id"], "aligned")
        n_final = sum(1 for r in rows if r["method"] == "final" and r["start"] is not None)
        db.run_end(con, rid, True, f"{n_final} items placed")
        print(f"{session['municipality']:<10} {session['date']}  {n_final} items placed")
    except Exception as exc:
        db.run_end(con, rid, False, str(exc))
        print(f"{session['municipality']:<10} {session['date']}  align failed: {exc}")
        return 1
    return 0


def boundary_scores(pred: list[float], gold: list[float], tol: float = 60.0) -> dict:
    """Recall: gold starts with a prediction within `tol`. Precision: predictions within `tol` of a gold start. Median error over matched gold."""
    if not gold:
        return {"n_gold": 0}
    errs = [min((abs(p - g) for p in pred), default=float("inf")) for g in gold]
    matched = [e for e in errs if e <= tol]
    prec_hits = sum(1 for p in pred if any(abs(p - g) <= tol for g in gold))
    return {"n_gold": len(gold), "n_pred": len(pred), "recall": round(len(matched) / len(gold), 3),
            "precision": round(prec_hits / len(pred), 3) if pred else 0.0,
            "median_error_s": round(float(np.median(matched)), 1) if matched else None}


def eval_lines(con) -> list[str]:
    """Compare the placed item starts with the hand-labelled starts in tests/fixtures/gold_spans.json.

    The gold file maps a session id to a list of start seconds (one per agenda item announced on the recording),
    so the score does not depend on how the items are numbered."""
    gold_path = Path(config.ROOT / "tests" / "fixtures" / "gold_spans.json")
    if not gold_path.exists():
        return []
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    lines = []
    for method in ("agenda_dp", "llm", "final"):
        for sid, entry in gold.items():
            starts = entry["starts"] if isinstance(entry, dict) else entry
            pred = [r["start"] for r in con.execute("SELECT start FROM item_spans WHERE session_id=? AND method=? AND start IS NOT NULL", (sid, method))]
            if not pred:
                continue
            sc = boundary_scores(pred, starts)
            muni = con.execute("SELECT municipality, date FROM sessions WHERE id=?", (sid,)).fetchone()
            lines.append(f"{method:<9} {muni['municipality']:<9} {muni['date']}  gold {sc['n_gold']:>2}  placed {sc['n_pred']:>2}  "
                         f"recall {sc['recall']:.0%}  precision {sc['precision']:.0%}  median error {sc['median_error_s']} s")
    return lines


def evaluate(con, args) -> int:
    lines = eval_lines(con)
    print("\n".join(lines) if lines else "no gold file, or nothing placed yet for the gold sessions")
    return 0
