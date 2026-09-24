"""Find council recordings on a municipality's YouTube channel."""
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime

from raadzaal import config, db

MONTHS = {"januari": 1, "jan": 1, "februari": 2, "febr": 2, "feb": 2, "maart": 3, "mrt": 3, "april": 4, "apr": 4,
          "mei": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "augustus": 8, "aug": 8, "september": 9, "sept": 9,
          "sep": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11, "december": 12, "dec": 12}
_DMY = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
_YMD = re.compile(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b")
_TEXT = re.compile(r"\b(\d{1,2})\s+([a-z]+)\.?\s+(\d{4})\b", re.I)
CACHE_TTL = 12 * 3600


def parse_date(title: str) -> str | None:
    """ISO date from a title, or None. Day-first numeric forms win, then year-first, then Dutch month names."""
    for rx, order in ((_DMY, "dmy"), (_YMD, "ymd")):
        for m in rx.finditer(title):
            a, b, c = (int(x) for x in m.groups())
            d, mo, y = (a, b, c) if order == "dmy" else (c, b, a)
            try:
                return datetime(y, mo, d).date().isoformat()
            except ValueError:
                continue
    for m in _TEXT.finditer(title):
        d, name, y = int(m.group(1)), m.group(2).lower().rstrip("."), int(m.group(3))
        if name in MONTHS:
            try:
                return datetime(y, MONTHS[name], d).date().isoformat()
            except ValueError:
                continue
    return None


def is_council(title: str, title_regex: str) -> bool:
    t = title.strip().lower()
    if not re.search(title_regex, t, re.I):
        return False
    return not re.search(config.EXCLUDE_TITLE_RE, t, re.I)


def parse_title(title: str, title_regex: str) -> tuple[bool, str | None]:
    return is_council(title, title_regex), parse_date(title)


def _env() -> dict:
    env = dict(os.environ)
    env["PATH"] = os.path.expanduser("~/.deno/bin") + os.pathsep + env.get("PATH", "")
    return env


def _list_tab(url: str) -> list[dict]:
    out = subprocess.run(["yt-dlp", "--remote-components", "ejs:github", "--flat-playlist", "-J", url],
                         capture_output=True, text=True, timeout=300, env=_env())
    if out.returncode != 0 or not out.stdout.strip():
        if "does not have a" in out.stderr or "404" in out.stderr:
            return []  # the channel has no such tab
        raise RuntimeError(f"yt-dlp failed for {url}: {out.stderr[-400:]}")
    data = json.loads(out.stdout)
    return [{"id": e.get("id"), "title": e.get("title") or "", "duration": e.get("duration"),
             "url": f"https://www.youtube.com/watch?v={e.get('id')}"}
            for e in data.get("entries", []) if e.get("id")]


def list_channel(url: str, use_cache: bool = True) -> list[dict]:
    """Flat listing of a channel's uploads and its finished livestreams, cached for 12 hours.

    Council sessions are usually streamed live, and YouTube lists those under the Live tab, not Videos."""
    config.ensure_dirs()
    base = re.sub(r"/(videos|streams|live)/?$", "", url.rstrip("/"))
    key = hashlib.sha1(base.encode()).hexdigest()[:12]
    cache = config.CACHE / f"channel_{key}.json"
    if use_cache and cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL:
        return json.loads(cache.read_text(encoding="utf-8"))
    seen, entries = set(), []
    for tab in ("videos", "streams"):
        for e in _list_tab(f"{base}/{tab}"):
            if e["id"] not in seen:
                seen.add(e["id"]); entries.append(e)
    cache.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return entries


def discover(con, m: dict, min_duration: int = 900, min_date: str | None = None) -> list[dict]:
    """Insert the council sessions of one municipality that are not in the database yet."""
    if not m.get("youtube"):
        return []
    min_date = min_date or config.MIN_DATE
    excluded = set((m.get("exclude") or {}).keys())
    new = []
    for e in list_channel(m["youtube"]):
        if e["id"] in excluded:
            continue
        council, date = parse_title(e["title"], m.get("title_regex", "gemeenteraad"))
        if not council or not date or (e.get("duration") or 0) < min_duration or date < min_date:
            continue
        row = {"id": e["id"], "municipality": m["slug"], "date": date, "title": e["title"].strip(),
               "duration_s": e.get("duration"), "url": f"https://www.youtube.com/watch?v={e['id']}"}
        if db.upsert_session(con, row):
            new.append(row)
    con.commit()
    return new


def drop_excluded(con) -> int:
    """Remove sessions whose video id is on a municipality's exclude list, with everything derived from them."""
    n = 0
    for m in config.municipalities(all_entries=True):
        for vid in (m.get("exclude") or {}):
            if con.execute("SELECT 1 FROM sessions WHERE id=?", (vid,)).fetchone():
                for t in ("transcript_segments", "speaker_turns", "speaker_names", "item_spans", "session_notes"):
                    con.execute(f"DELETE FROM {t} WHERE session_id=?", (vid,))
                con.execute("DELETE FROM summaries WHERE item_id IN (SELECT id FROM agenda_items WHERE session_id=?)", (vid,))
                con.execute("DELETE FROM agenda_items WHERE session_id=?", (vid,))
                con.execute("DELETE FROM sessions WHERE id=?", (vid,))
                n += 1
    con.commit()
    return n


def run(con, args) -> int:
    dropped = drop_excluded(con)
    if dropped:
        print(f"{dropped} excluded session(s) removed")
    munis = [config.municipality(args.municipality)] if args.municipality else config.municipalities()
    total = 0
    for m in munis:
        rid = db.run_start(con, "discover")
        try:
            new = discover(con, m)
            db.run_end(con, rid, True, f"{len(new)} new")
        except Exception as exc:  # one channel failing never stops the others
            db.run_end(con, rid, False, str(exc))
            print(f"{m['slug']}: {exc}")
            continue
        total += len(new)
        for s in new:
            print(f"{m['slug']:<10} {s['date']} {int((s['duration_s'] or 0) // 60):>4} min  {s['id']}  {s['title'][:70]}")
    print(f"{total} new session(s)")
    return 0
