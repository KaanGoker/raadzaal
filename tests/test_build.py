import json

from raadzaal import build, db, report


def _seed(con):
    db.upsert_session(con, {"id": "v1", "municipality": "beernem", "date": "2026-03-19", "title": "Gemeenteraad", "duration_s": 3600, "url": "u"})
    con.execute("INSERT INTO agenda_items(session_id,position,title,public,origin,votes_for,votes_against,abstentions) VALUES('v1',1,'Notulen',1,'lblod',24,0,0)")
    con.execute("INSERT INTO agenda_items(session_id,position,title,public,origin,votes_for,votes_against,abstentions) VALUES('v1',2,'Belasting',1,'lblod',15,9,1)")
    con.execute("INSERT INTO agenda_items(session_id,position,title,public,origin) VALUES('v1',3,'Vraag over fietspad',1,'lblod')")
    con.execute("INSERT INTO item_spans VALUES('v1',1,0,600,'final',10)")
    con.execute("INSERT INTO item_spans VALUES('v1',2,600,2400,'final',200)")
    con.execute("INSERT INTO item_spans VALUES('v1',3,NULL,NULL,'final',NULL)")
    con.execute("INSERT INTO summaries(item_id,model,content_hash,nl,en,topic,outcome,raised_by,quote,quote_start,created_at,discussed) "
                "VALUES(1,'m','h','Notulen goedgekeurd.','Minutes approved.','participatie en bestuur','aangenomen',NULL,NULL,NULL,'t',1)")
    con.execute("INSERT INTO summaries(item_id,model,content_hash,nl,en,topic,outcome,created_at,discussed) "
                "VALUES(2,'m','h','Dit punt werd niet teruggevonden in de opname.','Not found.','financiën','onbekend','t',0)")
    for i in range(0, 3600, 10):
        text = "Dan gaan we over naar de OCMW-raad." if i == 500 else f"zin {i}"
        con.execute("INSERT INTO transcript_segments(session_id,start,end,text,speaker) VALUES('v1',?,?,?,?)", (i, i + 9, text, i // 1800))
    con.execute("INSERT INTO speaker_turns(session_id,speaker,start,end) VALUES('v1',0,0,1800),('v1',1,1800,3600)")
    con.execute("INSERT INTO speaker_names VALUES('v1',0,'Jos Sypré','CD&V','burgemeester',0.9,'[]')")
    decided = json.dumps(["Notulen goedgekeurd", "Belasting aangenomen", "Rangorde vastgesteld"] + [f"Besluit {i}" for i in range(6)])
    con.execute("INSERT INTO session_notes VALUES('v1','m','h',?,'[]','t')", (decided,))
    con.commit()
    db.advance(con, "v1", "transcribed")


def test_build_writes_expected_json(tmp_db, tmp_path, monkeypatch):
    from raadzaal import config
    monkeypatch.setattr(config, "DOCS_DATA", tmp_path / "data")
    _seed(tmp_db)
    r = build.write(tmp_db)
    assert r["sessions"] == 1 and r["items_total"] == 1
    p = json.loads((tmp_path / "data" / "sessions" / "v1.json").read_text(encoding="utf-8"))
    assert p["agenda"][0]["summary"]["nl"].startswith("Notulen") and p["agenda"][2]["start"] is None
    assert p["agenda"][0]["end"] == 500  # the last placed item stops where the chair opens the OCMW council
    doubtful = next(a for a in p["agenda"] if a["title"] == "Belasting")
    assert doubtful["summary"] is None and doubtful["doubtful"] and doubtful["start"] is None and doubtful["placed_at"] == 600
    assert doubtful["disagreement"] == 200 and p["method"]["disagreements_over_120s"] == 1
    assert p["speakers"][0]["name"] == "Jos Sypré" and p["attributed_share"] == 0.5
    assert p["speakers"][0]["label"] == "Jos Sypré" and p["speakers"][1]["label"] == "Spreker 1"
    assert "confidence" not in p["speakers"][0]  # a near-constant score that said nothing about the name
    assert p["notes"]["decided"] == ["Belasting aangenomen", "Besluit 0", "Besluit 1", "Besluit 2", "Besluit 3"]  # routine lines out, five at most
    idx = json.loads((tmp_path / "data" / "index.json").read_text(encoding="utf-8"))
    assert idx["sessions"][0]["items"] == 1 and idx["municipalities"][0]["slug"] == "haacht"
    docs = json.loads((tmp_path / "data" / "search.json").read_text(encoding="utf-8"))
    assert sum(1 for d in docs if d["type"] == "item") == 1 and sum(1 for d in docs if d["type"] == "chunk") >= 80
    st = json.loads((tmp_path / "data" / "stats.json").read_text(encoding="utf-8"))
    assert st["contested"][0]["votes"]["tegen"] == 9 and st["contested"][0]["start"] is None
    assert "party_minutes" not in st["municipalities"]["beernem"] and st["municipalities"]["beernem"]["attributed_share"] == 0.5
    text = report.render(idx, st, [p])
    assert "| Beernem | 1 |" in text and "Belasting" in text
