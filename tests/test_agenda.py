import json
from pathlib import Path

from raadzaal import agenda

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def test_beernem_chain_order_and_votes():
    d = load("agenda_beernem_2026-03-19.json")
    items = agenda.order_items(d["rows"])
    titles = [i["title"] for i in items]
    assert titles[0].startswith("Mededelingen bij de opening")
    assert titles[-1].startswith("Eventuele vragen")
    assert [i["position"] for i in items] == list(range(1, len(items) + 1))
    assert "(zonder titel)" in titles  # an untitled item keeps its place in the chain
    voted = [i for i in items if i["votes_for"] is not None]
    assert voted and all(i["votes_against"] is not None for i in voted)


def test_tervuren_has_vote_counts_and_public_flags():
    d = load("agenda_tervuren_2026-03-26.json")
    items = agenda.order_items(d["rows"])
    assert len(items) == 15
    assert all(i["public"] for i in items)
    fought = [i for i in items if (i["votes_against"] or 0) > 0]
    assert fought, "the March 2026 session had contested votes"


def test_position_from_title():
    assert agenda.position_from_title("12. Goedkeuring notulen") == 12
    assert agenda.position_from_title("1) Opening") == 1
    assert agenda.position_from_title("Goedkeuring notulen") is None
    assert agenda.position_from_title("2025_GR_00585 iets") is None


def test_local_date_handles_offsets():
    assert agenda.local_date("2026-09-22T20:00:00+02:00") == "2026-09-22"
    assert agenda.local_date("2026-09-22T22:30:00Z") == "2026-09-23"


def test_find_zitting_none_without_rows(monkeypatch):
    monkeypatch.setattr(agenda, "zittingen", lambda m, a, b: [])
    assert agenda.find_zitting({"lblod_harvester": 0, "lblod_label": "X", "lblod_org": "Y"}, "2026-01-01") is None
