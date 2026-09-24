import pytest
from raadzaal.discover import parse_date, is_council, parse_title, discover


@pytest.mark.parametrize("title,expected", [
    ("2026/06 OCMW-raad en gemeenteraad van Haacht op  22/06/2026", "2026-06-22"),
    ("Gemeenteraad en raad voor maatschappelijk welzijn Beernem 21 mei 2026", "2026-05-21"),
    ("Gemeenteraad 2026/08/31", "2026-08-31"),
    ("Gemeenteraad Diepenbeek 16-03-2026", "2026-03-16"),
    ("Gemeente- en OCMW-raad  sept. 2026", None),
    ("Videoverslag gemeenteraad en raad voor maatschappelijk welzijn 23 febr", None),
    ("Gemeenteraad 1 september 2026 19u30", "2026-09-01"),
    ("Gemeenteraad 31/02/2026", None),
])
def test_parse_date(title, expected):
    assert parse_date(title) == expected


@pytest.mark.parametrize("title,expected", [
    ("Gemeenteraad en OCMW-raad 26 maart 2026", True),
    ("2026/06 OCMW-raad en gemeenteraad van Haacht op 22/06/2026", True),
    ("Commissievergadering gemeenteraad Beernem 9 juni 2026", False),
    ("Gemeenteraadscommissie Algemeen van 17 maart 2026", False),
    ("Raad voor maatschappelijk welzijn 27 augustus 2026", False),
    ("Infovergadering gemeenteraad 3 maart 2026", False),
    ("Dit was 2025 in Leuven", False),
])
def test_is_council(title, expected):
    assert is_council(title, "gemeenteraad") is expected


def test_discover_inserts_once(tmp_db, monkeypatch):
    entries = [{"id": "v1", "title": "Gemeenteraad 20 januari 2026", "duration": 5000, "url": "u"},
               {"id": "v2", "title": "Raad voor maatschappelijk welzijn 20 januari 2026", "duration": 5000, "url": "u"},
               {"id": "v3", "title": "Gemeenteraad 3 maart 2026", "duration": 120, "url": "u"}]
    monkeypatch.setattr("raadzaal.discover.list_channel", lambda url, use_cache=True: entries)
    m = {"slug": "x", "youtube": "http://y", "title_regex": "gemeenteraad"}
    assert [s["id"] for s in discover(tmp_db, m)] == ["v1"]
    assert discover(tmp_db, m) == []


def test_discover_respects_min_date(tmp_db, monkeypatch):
    entries = [{"id": "old", "title": "Gemeenteraad 20 januari 2021", "duration": 5000, "url": "u"},
               {"id": "new", "title": "Gemeenteraad 20 januari 2026", "duration": 5000, "url": "u"}]
    monkeypatch.setattr("raadzaal.discover.list_channel", lambda url, use_cache=True: entries)
    m = {"slug": "x", "youtube": "http://y", "title_regex": "gemeenteraad"}
    assert [s["id"] for s in discover(tmp_db, m, min_date="2026-01-01")] == ["new"]


def test_discover_skips_excluded_ids(tmp_db, monkeypatch):
    entries = [{"id": "dup", "title": "Gemeenteraad 20 maart 2026", "duration": 5000, "url": "u"},
               {"id": "ok", "title": "Gemeenteraad 20 februari 2026", "duration": 5000, "url": "u"}]
    monkeypatch.setattr("raadzaal.discover.list_channel", lambda url, use_cache=True: entries)
    m = {"slug": "x", "youtube": "http://y", "title_regex": "gemeenteraad", "exclude": {"dup": "same audio as ok"}}
    assert [s["id"] for s in discover(tmp_db, m, min_date="2026-01-01")] == ["ok"]
