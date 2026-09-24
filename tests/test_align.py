import numpy as np

from raadzaal import align


def test_windows_cover_the_session():
    segs = [{"start": 0, "end": 10, "text": "a"}, {"start": 40, "end": 50, "text": "b"}, {"start": 100, "end": 110, "text": "c"}]
    w = align.windows(segs, win=45, stride=15)
    assert w[0]["start"] == 0 and w[-1]["start"] >= 95
    assert "a" in w[0]["text"] and "b" in w[0]["text"] and "c" not in w[0]["text"]


def test_dp_is_monotone_and_prefers_high_scores():
    S = np.array([[0.9, 0.1, 0.1, 0.1, 0.1, 0.1],
                  [0.1, 0.1, 0.9, 0.1, 0.1, 0.1],
                  [0.1, 0.1, 0.1, 0.1, 0.9, 0.1]])
    assert align.dp_align(S, min_gap=2) == [0, 2, 4]
    S2 = np.array([[0.1, 0.1, 0.9, 0.1], [0.9, 0.1, 0.1, 0.1]])  # item 2 cannot start before item 1
    starts = align.dp_align(S2, min_gap=1)
    assert starts[0] < starts[1]


def test_spans_mark_not_found_below_floor():
    wins = [{"start": 0, "end": 45}, {"start": 15, "end": 60}, {"start": 30, "end": 75}]
    S = np.array([[0.9, 0, 0], [0, 0, 0.05]])
    out = align.spans([0, 2], wins, S, 100)
    assert out[0]["found"] and out[0]["end"] == 30
    assert not out[1]["found"] and out[1]["end"] == 100


def test_cue_bonus():
    item = {"position": 7, "title": "7. Goedkeuring belastingreglement inname openbaar domein"}
    assert align.cue_bonus("we gaan over naar punt zeven, het belastingreglement inname openbaar domein", item) > 0.4
    assert align.cue_bonus("het weer is mooi vandaag", item) == 0


def test_number_cue_only_when_the_title_is_numbered():
    numbered = {"position": 9, "title": "9. Fietspad Torenweg"}
    unnumbered = {"position": 9, "title": "Aanvullend reglement parkeerverbod"}
    assert align.cue_bonus("dan punt negen", numbered) >= 0.25
    assert align.cue_bonus("dan punt negen", unnumbered) == align.ORDER_NUMBER_WEIGHT < 0.25


def test_stitch_merges_overlap_duplicates():
    found = [{"start": 100, "title": "Goedkeuring notulen", "number": 1},
             {"start": 130, "title": "goedkeuring van de notulen", "number": None},
             {"start": 400, "title": "Belastingreglement", "number": 2}]
    out = align.stitch(found)
    assert [f["start"] for f in out] == [100, 400]


def test_map_to_agenda_titles_beat_spoken_numbers():
    items = [{"id": 5, "position": 5, "title": "IVBO buitengewone algemene vergadering standpuntbepaling"},
             {"id": 6, "position": 6, "title": "Kosteloze grondafstand Biezemoerstraat"}]
    li = [{"start": 870, "title": "IVBO vertegenwoordiger buitengewone algemene vergadering", "number": 5},
          {"start": 992, "title": "Agenda buitengewone algemene vergadering IVBO", "number": 6},
          {"start": 1162, "title": "Kosteloze grondafstand Biezemoerstraat", "number": 7}]
    got = align.map_to_agenda(li, items)
    assert got[6] == 1162 and got[5] in (870, 992)


def test_final_spans_keep_disagreement():
    items = [{"id": 1}, {"id": 2}]
    dp = [{"start": 10, "end": 100, "found": True}, {"start": 100, "end": 200, "found": False}]
    out = align.final_spans(items, dp, {1: 40}, 200)
    assert out[0]["score"] == 30 and out[0]["start"] == 40 and out[1]["start"] is None and out[0]["end"] == 200


def test_final_spans_prefer_anchors_and_fill_between():
    items = [{"id": i} for i in range(1, 6)]
    dp = [{"start": s, "end": None, "found": True} for s in (0, 400, 900, 2500, 3000)]
    llm = {1: 5, 2: 380, 4: 1500, 5: 1800}  # item 3 unseen by Gemini
    out = align.final_spans(items, dp, llm, 4000)
    assert [o["start"] for o in out] == [5, 380, 900, 1500, 1800]
    assert [o["end"] for o in out] == [380, 900, 1500, 1800, 4000]


def test_final_spans_drop_dp_outside_anchors_and_llm_out_of_order():
    items = [{"id": i} for i in range(1, 5)]
    dp = [{"start": s, "end": None, "found": True} for s in (0, 3000, 200, 300)]
    llm = {1: 10, 3: 500, 4: 400}  # 4 before 3 breaks the agenda order: one of them goes
    out = align.final_spans(items, dp, llm, 4000)
    starts = [o["start"] for o in out]
    assert starts[0] == 10 and starts[1] is None  # dp 3000 is not between 10 and the next anchor
    assert (starts[2], starts[3]) in ((500, None), (None, 400))


def test_boundary_scores():
    sc = align.boundary_scores([10, 100, 500], [12, 130, 900])
    assert sc["n_gold"] == 3 and sc["recall"] == round(2 / 3, 3) and sc["precision"] == round(2 / 3, 3) and sc["median_error_s"] == 16
    assert align.boundary_scores([], [1, 2])["recall"] == 0.0
