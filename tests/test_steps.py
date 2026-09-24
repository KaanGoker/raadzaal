import argparse

from raadzaal import db, steps


def args(**kw):
    base = dict(municipality=None, session=None, limit=0, force=False)
    base.update(kw)
    return argparse.Namespace(**base)


def seed(con):
    for i, st in enumerate(["transcribed", "downloaded", "diarised", "downloaded"]):
        db.upsert_session(con, {"id": f"s{i}", "municipality": "haacht", "date": f"2026-0{i + 1}-01", "title": "t", "duration_s": 1, "url": "u"})
        if st != "found":
            db.advance(con, f"s{i}", st)


def test_select_skips_sessions_the_step_already_did(tmp_db):
    seed(tmp_db)
    got = [r["id"] for r in steps._select(tmp_db, args(limit=1), "downloaded", "transcribe")]
    assert got == ["s1"]  # s0 is already transcribed, so --limit 1 must not pick it again
    assert [r["id"] for r in steps._select(tmp_db, args(), "downloaded", "transcribe")] == ["s1", "s3"]
    assert [r["id"] for r in steps._select(tmp_db, args(), "transcribed", "diarise")] == ["s0"]


def test_select_force_and_explicit_session(tmp_db):
    seed(tmp_db)
    assert len(steps._select(tmp_db, args(force=True), "downloaded", "transcribe")) == 4
    assert [r["id"] for r in steps._select(tmp_db, args(session=["s0"]), "downloaded", "transcribe")] == ["s0"]


def test_steps_without_a_done_status_run_on_all_eligible(tmp_db):
    seed(tmp_db)
    assert len(steps._select(tmp_db, args(), "diarised", "speakers")) == 1
