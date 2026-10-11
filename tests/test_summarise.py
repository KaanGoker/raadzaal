from raadzaal import summarise, llm
from raadzaal.summarise import ItemSummary


def test_quote_must_exist_in_text():
    text = "[12] Spreker 1: Wij stellen voor om het reglement goed te keuren zoals het voorligt. [20] Spreker 0: Dank u."
    assert summarise.quote_in_text("wij stellen voor om het reglement goed te keuren zoals het voorligt", text)
    assert summarise.quote_in_text("Wij stellen voor om het reglement goed te keuren zoals het voorlag.", text)  # one slip
    assert not summarise.quote_in_text("De burgemeester beloofde een nieuw zwembad.", text)
    assert not summarise.quote_in_text("Dank u.", text)


def test_verify_drops_unknown_names_and_bad_quotes():
    allowed = ["Els De Wit"]
    item = {"title": "Vraag over het fietspad", "text": "[1] Spreker 1: het fietspad is gevaarlijk zegt iedereen hier."}
    s = ItemSummary(nl="x", topic="mobiliteit", outcome="kennisname", raised_by="Jan Peeters",
                    quote="het zwembad is gesloten", quote_start=3)
    v = summarise.verify(s, item, allowed)
    assert v.raised_by is None and v.quote is None and v.quote_start is None
    s2 = ItemSummary(nl="x", topic="mobiliteit", outcome="kennisname", raised_by="schepen De Wit",
                     quote="het fietspad is gevaarlijk zegt iedereen hier", quote_start=1)
    v2 = summarise.verify(s2, item, allowed)
    assert v2.raised_by == "Els De Wit" and v2.quote


def test_raised_by_from_title_is_allowed():
    assert summarise.check_raised_by("Van Roy", [], "Voorstel over de N3 (raadslid Van Roy)") == "Van Roy"


def test_span_text_labels_and_truncates_on_line_boundaries():
    segs = [{"start": i, "end": i + 1, "text": "woord " * 20, "speaker": i % 2} for i in range(400)]
    t = summarise.span_text(segs, {0: "Jos Sypré"}, 0, 500)
    lines = t.split("\n")
    assert lines[0].startswith("[0] Jos Sypré:") and "[...]" in lines and lines[-1].startswith("[399] Spreker 1:")
    assert len(t) <= summarise.MAX_SPAN_CHARS + 10
    assert all(l == "[...]" or l.startswith("[") for l in lines)


def test_llm_cache_roundtrip(tmp_path, monkeypatch):
    from raadzaal import config
    monkeypatch.setattr(config, "CACHE", tmp_path)
    key = llm.cache_key("m", "prompt", "ItemSummary")
    llm.cache_path(key).write_text(ItemSummary(nl="n", topic="andere", outcome="onbekend").model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(config, "LLM_MODEL", "m")
    got = llm.generate("prompt", ItemSummary)
    assert got.nl == "n"  # served from the cache, no client needed


def test_quota_detection():
    assert llm._is_quota(Exception("429 RESOURCE_EXHAUSTED: quota"))
    assert not llm._is_quota(Exception("500 internal"))


def test_match_by_number_survives_a_dropped_item():
    items = [{"position": 1}, {"position": 2}, {"position": 3}]
    got = [ItemSummary(number=1, nl="a", topic="andere", outcome="onbekend"),
           ItemSummary(number=3, nl="c", topic="andere", outcome="onbekend")]
    out = summarise.match_by_number(items, got)
    assert [o.nl if o else None for o in out] == ["a", None, "c"]


def test_split_by_size_keeps_order_and_limits():
    items = [{"title": "t", "text": "x" * 1000} for _ in range(10)]
    parts = summarise.split_by_size(items, limit=3000)
    assert sum(len(p) for p in parts) == 10 and all(len(p) <= 2 for p in parts)


def test_one_call_per_session(monkeypatch):
    from raadzaal import config
    calls = []

    def fake_generate(prompt, schema, **kw):
        calls.append(schema.__name__)
        return summarise.SessionSummary(items=[ItemSummary(number=i, nl=f"n{i}", topic="andere", outcome="onbekend") for i in (1, 2)],
                                        decided=["x"])
    monkeypatch.setattr(llm, "generate", fake_generate)
    monkeypatch.setattr(config, "municipality", lambda slug: {"name": "Beernem"})
    items = [{"position": 1, "title": "a", "text": "t"}, {"position": 2, "title": "b", "text": "t"}]
    got, notes = summarise.summarise_session({"municipality": "beernem", "date": "2026-01-22"}, items, [])
    assert calls == ["SessionSummary"] and [g.nl for g in got] == ["n1", "n2"] and notes.decided == ["x"]


def test_raised_by_only_for_questions_and_from_the_title():
    allowed = ["Kris Vincke", "Els Peeters"]
    base = dict(nl="x", topic="andere", outcome="onbekend")
    plain = {"title": "Kosteloze grondafstand Biezemoerstraat", "text": ""}
    assert summarise.verify(ItemSummary(raised_by="Kris Vincke", **base), plain, allowed).raised_by is None
    titled = {"title": "Voorstel over het voormalig politiecommissariaat (raadslid Peeters)", "text": ""}
    assert summarise.verify(ItemSummary(raised_by="Kris Vincke", **base), titled, allowed).raised_by == "Els Peeters"


def test_quote_time_comes_from_the_transcript():
    segs = [{"start": 10.0, "end": 12, "text": "Goedenavond iedereen."}, {"start": 40.0, "end": 45, "text": "Wij stellen voor om het reglement goed te keuren."}]
    item = {"title": "Reglement", "text": "[40] Spreker 1: Wij stellen voor om het reglement goed te keuren.", "segments": segs}
    s = ItemSummary(nl="x", topic="andere", outcome="onbekend", quote="Wij stellen voor om het reglement goed te keuren.", quote_start=999)
    assert summarise.verify(s, item, []).quote_start == 40.0
