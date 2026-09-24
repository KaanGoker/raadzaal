from raadzaal import db, config


def test_schema_and_version(tmp_db):
    assert tmp_db.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    tables = {r[0] for r in tmp_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sessions", "agenda_items", "transcript_segments", "summaries", "runs"} <= tables


def test_connect_is_idempotent(tmp_path):
    p = tmp_path / "x.db"
    db.connect(p).close()
    con = db.connect(p)
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_session_upsert_and_advance(tmp_db):
    s = {"id": "abc", "municipality": "haacht", "date": "2026-01-26", "title": "t", "duration_s": 10, "url": "u"}
    assert db.upsert_session(tmp_db, s) is True
    assert db.upsert_session(tmp_db, s) is False
    db.advance(tmp_db, "abc", "transcribed")
    db.advance(tmp_db, "abc", "found")  # never backwards
    assert db.sessions(tmp_db)[0]["status"] == "transcribed"


def test_municipalities_registry():
    enabled = config.municipalities()
    assert {m["slug"] for m in enabled} == {"haacht", "tervuren", "beernem"}
    assert len(config.municipalities(all_entries=True)) >= 5
    assert config.municipality("leuven")["enabled"] is False
