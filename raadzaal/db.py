"""SQLite store. One file, versioned schema, small helpers."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from raadzaal import config

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS municipalities (
  slug TEXT PRIMARY KEY, name TEXT NOT NULL, province TEXT, youtube TEXT,
  lblod_harvester INTEGER, lblod_label TEXT, added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, municipality TEXT NOT NULL, date TEXT NOT NULL, title TEXT NOT NULL,
  duration_s REAL, url TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'found',
  lblod_zitting TEXT, found_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agenda_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, position INTEGER,
  title TEXT NOT NULL, public INTEGER NOT NULL DEFAULT 1, lblod_uri TEXT, source_url TEXT,
  votes_for INTEGER, votes_against INTEGER, abstentions INTEGER, outcome TEXT,
  origin TEXT NOT NULL DEFAULT 'lblod',
  UNIQUE(session_id, lblod_uri));
CREATE TABLE IF NOT EXISTS transcript_segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, start REAL NOT NULL, end REAL NOT NULL,
  text TEXT NOT NULL, speaker INTEGER, avg_logprob REAL, no_speech_prob REAL);
CREATE INDEX IF NOT EXISTS idx_segments_session ON transcript_segments(session_id, start);
CREATE TABLE IF NOT EXISTS speaker_turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, speaker INTEGER NOT NULL,
  start REAL NOT NULL, end REAL NOT NULL);
CREATE TABLE IF NOT EXISTS speaker_names (
  session_id TEXT NOT NULL, speaker INTEGER NOT NULL, name TEXT, party TEXT, role TEXT,
  direct INTEGER NOT NULL DEFAULT 0, cue_start REAL, cue_text TEXT, cues TEXT, PRIMARY KEY(session_id, speaker));
CREATE TABLE IF NOT EXISTS item_spans (
  session_id TEXT NOT NULL, item_id INTEGER NOT NULL, start REAL, end REAL,
  method TEXT NOT NULL, score REAL, PRIMARY KEY(session_id, item_id, method));
CREATE TABLE IF NOT EXISTS summaries (
  item_id INTEGER PRIMARY KEY, model TEXT, content_hash TEXT NOT NULL, nl TEXT, topic TEXT,
  outcome TEXT, raised_by TEXT, quote TEXT, quote_start REAL, created_at TEXT NOT NULL,
  discussed INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS session_notes (
  session_id TEXT PRIMARY KEY, model TEXT, content_hash TEXT NOT NULL, decided TEXT,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, step TEXT NOT NULL, session_id TEXT, started_at TEXT NOT NULL,
  finished_at TEXT, ok INTEGER, message TEXT);
"""

STATUSES = ["found", "downloaded", "transcribed", "diarised", "aligned", "summarised", "built"]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=120)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version < SCHEMA_VERSION:
        con.executescript(SCHEMA)
        _migrate(con)
        con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        con.commit()
    return con


def _migrate(con) -> None:
    """Bring a database from an earlier schema version up to date; each step is a no-op on a fresh file."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(summaries)")}
    if "discussed" not in cols:  # version 2
        con.execute("ALTER TABLE summaries ADD COLUMN discussed INTEGER NOT NULL DEFAULT 1")
    if "en" in cols:  # version 3: the English line and the notable moments were generated but never published
        con.execute("ALTER TABLE summaries DROP COLUMN en")
    if "notable" in {r[1] for r in con.execute("PRAGMA table_info(session_notes)")}:
        con.execute("ALTER TABLE session_notes DROP COLUMN notable")
    cols = {r[1] for r in con.execute("PRAGMA table_info(speaker_names)")}
    if "direct" not in cols:  # version 4: a name is published only with a direct cue, and the cue is kept
        con.execute("ALTER TABLE speaker_names ADD COLUMN direct INTEGER NOT NULL DEFAULT 0")
        con.execute("ALTER TABLE speaker_names ADD COLUMN cue_start REAL")
        con.execute("ALTER TABLE speaker_names ADD COLUMN cue_text TEXT")
    if "confidence" in cols:
        con.execute("ALTER TABLE speaker_names DROP COLUMN confidence")


def upsert_municipality(con, m: dict) -> None:
    con.execute(
        "INSERT INTO municipalities(slug,name,province,youtube,lblod_harvester,lblod_label,added_at) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET name=excluded.name, province=excluded.province, "
        "youtube=excluded.youtube, lblod_harvester=excluded.lblod_harvester, lblod_label=excluded.lblod_label",
        (m["slug"], m["name"], m.get("province"), m.get("youtube"), m.get("lblod_harvester"), m.get("lblod_label"), now()))


def upsert_session(con, s: dict) -> bool:
    """Insert a session if new. Returns True when inserted."""
    cur = con.execute(
        "INSERT OR IGNORE INTO sessions(id,municipality,date,title,duration_s,url,status,found_at,updated_at) "
        "VALUES(?,?,?,?,?,?,'found',?,?)",
        (s["id"], s["municipality"], s["date"], s["title"], s.get("duration_s"), s["url"], now(), now()))
    return cur.rowcount == 1


def sessions(con, municipality: str | None = None, status: str | None = None, ids: list | None = None) -> list:
    q, args = "SELECT * FROM sessions WHERE 1=1", []
    if municipality:
        q += " AND municipality=?"; args.append(municipality)
    if status:
        q += " AND status=?"; args.append(status)
    if ids:
        q += f" AND id IN ({','.join('?' * len(ids))})"; args.extend(ids)
    q += " ORDER BY municipality, date"
    return [dict(r) for r in con.execute(q, args)]


def status_index(status: str) -> int:
    return STATUSES.index(status)


def advance(con, session_id: str, status: str) -> None:
    """Move a session forward to `status`; never backwards."""
    row = con.execute("SELECT status FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        raise KeyError(session_id)
    if status_index(status) > status_index(row["status"]):
        con.execute("UPDATE sessions SET status=?, updated_at=? WHERE id=?", (status, now(), session_id))
        con.commit()


def run_start(con, step: str, session_id: str | None = None) -> int:
    cur = con.execute("INSERT INTO runs(step,session_id,started_at) VALUES(?,?,?)", (step, session_id, now()))
    con.commit()
    return cur.lastrowid


def run_end(con, run_id: int, ok: bool, message: str = "") -> None:
    con.execute("UPDATE runs SET finished_at=?, ok=?, message=? WHERE id=?", (now(), int(ok), message[:500], run_id))
    con.commit()


def replace_rows(con, table: str, session_id: str, rows: list[dict]) -> None:
    """Delete a session's rows in `table` and insert the new ones."""
    con.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
    if rows:
        cols = list(rows[0].keys())
        con.executemany(
            f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
            [tuple(r[c] for c in cols) for r in rows])
    con.commit()


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(s: str | None):
    return json.loads(s) if s else None
