from raadzaal import build, topics


def _item(id_, title, topic, start, end):
    return {"id": id_, "title": title, "start": start, "end": end, "votes": None, "summary": {"topic": topic}}


def test_needs_windows_picks_long_questions_rounds_and_long_other_items():
    assert topics.needs_windows(_item(1, "Eventuele vragen en suggesties", "veiligheid", 0, 600))
    assert topics.needs_windows(_item(2, "Varia-punten gemeenteraad", "mobiliteit", 0, 600))
    assert topics.needs_windows(_item(3, "Verpachting jachtrecht", "andere", 0, 600))
    assert not topics.needs_windows(_item(4, "Varia: parkeerbeleid", "mobiliteit", 0, 600))  # one subject
    assert not topics.needs_windows(_item(5, "Eventuele vragen en suggesties", "andere", 0, 100))  # too short
    assert not topics.needs_windows(_item(6, "Eventuele vragen", "andere", None, None))
    assert not topics.needs_windows({**_item(7, "Eventuele vragen", "andere", 0, 600), "summary": None})


def test_windows_cover_the_item_without_gaps():
    transcript = [[float(t), float(t + 9), f"zin {t}", 0] for t in range(0, 1000, 10)]
    w = topics.windows(transcript, 95, 400)
    assert [x["start"] for x in w] == [95, 220, 340]  # the first window starts with the item, the next on a line
    assert [x["end"] for x in w] == [220, 340, 400]
    assert w[0]["text"].startswith("zin 100 ") and "zin 400" not in w[-1]["text"]
    assert topics.windows(transcript, 2000, 2100) == []


def test_minutes_clip_to_the_span_and_give_the_rest_to_the_item_topic():
    rows = [{"start": 0, "end": 120, "topic": "mobiliteit"}, {"start": 120, "end": 240, "topic": "wonen"},
            {"start": 240, "end": 360, "topic": "mobiliteit"}]
    assert topics.minutes(0, 360, rows, "andere") == {"mobiliteit": 4.0, "wonen": 2.0}
    assert topics.minutes(0, 180, rows, "andere") == {"mobiliteit": 2.0, "wonen": 1.0}  # span cut since
    assert topics.minutes(0, 480, rows, "andere") == {"mobiliteit": 4.0, "wonen": 2.0, "andere": 2.0}  # span grew since


def test_stats_count_split_items_by_window_and_per_municipality():
    a = {"id": "s1", "municipality": "beernem", "municipality_name": "Beernem", "date": "2026-03-19", "duration_s": 3600, "speakers": [],
         "agenda": [_item(1, "Eventuele vragen en suggesties", "andere", 0, 600), _item(2, "Budget", "financiën", 600, 900)]}
    b = {"id": "s2", "municipality": "haacht", "municipality_name": "Haacht", "date": "2026-03-20", "duration_s": 3600, "speakers": [],
         "agenda": [_item(3, "Fietspad", "mobiliteit", 0, 120)]}
    windows = {1: [{"start": 0, "end": 420, "topic": "mobiliteit"}, {"start": 420, "end": 600, "topic": "andere"}]}
    st = build.stats([a, b], windows)
    assert st["topic_minutes"] == {"mobiliteit": 9, "financiën": 5, "andere": 3}
    assert list(st["topic_minutes"]) == ["mobiliteit", "financiën", "andere"]
    assert st["topic_minutes_by_municipality"] == {"beernem": {"mobiliteit": 7, "financiën": 5, "andere": 3}, "haacht": {"mobiliteit": 2}}
    assert build.stats([a, b])["topic_minutes"] == {"andere": 10, "financiën": 5, "mobiliteit": 2}  # without windows: the item topic
