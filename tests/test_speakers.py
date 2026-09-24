from raadzaal import db, speakers
from raadzaal.diarise import merge_turns, assign

COUNCIL = {"members": [{"name": "Els De Wit", "party": "N-VA", "role": "schepen"},
                       {"name": "Jos Sypré", "party": "CD&V", "role": "burgemeester"},
                       {"name": "Vicky Reynaert", "party": "Vooruit", "role": "schepen"}]}


def test_cues():
    assert speakers.cues_from_text("Dan is het woord aan schepen De Wit.") == [("handover", "De Wit")]
    assert speakers.cues_from_text("Dank u wel, mevrouw Reynaert. Volgend punt.") == [("thanks", "Reynaert")]
    assert speakers.cues_from_text("Ik geef het woord aan raadslid Jan Van den Broeck") == [("handover", "Jan Van den Broeck")]
    assert speakers.cues_from_text("Goedenavond, ik ben Jos Sypré, burgemeester.") == [("self", "Jos Sypré")]
    assert speakers.cues_from_text("We gaan over naar punt vier.") == []


def test_name_from_title():
    assert speakers.name_from_title("Voorstel over de N3 (raadslid Van Roy)") == "Van Roy"
    assert speakers.name_from_title("Vraag van Veerle Pas (Cd&v-Plus) betreffende asfalt") == "Veerle Pas"
    assert speakers.name_from_title("Goedkeuring notulen") is None


def test_match_member_fuzzy():
    assert speakers.match_member("schepen De Wit", COUNCIL)["name"] == "Els De Wit"
    assert speakers.match_member("Reynaert", COUNCIL)["party"] == "Vooruit"
    assert speakers.match_member("Sypre", COUNCIL)["name"] == "Jos Sypré"
    assert speakers.match_member("Peeters", COUNCIL) is None


def test_two_cue_rule():
    one = {3: {"De Wit": ["handover"]}}
    assert speakers.decide(one, COUNCIL) == {}
    two = {3: {"De Wit": ["handover", "thanks"]}}
    assert speakers.decide(two, COUNCIL)[3]["name"] == "Els De Wit"
    tie = {3: {"De Wit": ["handover", "thanks"], "Reynaert": ["handover", "thanks"]}}
    assert speakers.decide(tie, COUNCIL) == {}
    assert speakers.decide({4: {"Peeters": ["handover", "thanks", "thanks", "self"]}}, COUNCIL) == {}  # not on the council


def test_votes_use_neighbouring_speakers():
    segs = [{"start": 0, "end": 4, "text": "Het woord is aan schepen De Wit.", "speaker": 0},
            {"start": 5, "end": 30, "text": "Dank u voorzitter. Over het dossier.", "speaker": 1},
            {"start": 31, "end": 34, "text": "Dank u wel, schepen De Wit.", "speaker": 0}]
    votes = speakers.collect_votes(segs, [], {0: 7, 1: 25})
    assert votes == {1: {"De Wit": ["handover", "thanks"]}}
    assert speakers.decide(votes, COUNCIL)[1]["name"] == "Els De Wit"


def test_attributed_share():
    assert speakers.attributed_share({0: 60, 1: 40}, {0: {"name": "x"}}) == 0.6
    assert speakers.attributed_share({}, {}) == 0.0


def test_store_segments_keeps_the_speaker(tmp_db):
    from raadzaal import transcribe
    db.upsert_session(tmp_db, {"id": "v", "municipality": "haacht", "date": "2026-01-01", "title": "t", "duration_s": 1, "url": "u"})
    transcribe.store_segments(tmp_db, "v", [{"start": 0, "end": 1, "text": "a", "speaker": 3}, {"start": 1, "end": 2, "text": "b"}])
    assert [r[0] for r in tmp_db.execute("SELECT speaker FROM transcript_segments ORDER BY start")] == [3, None]


def test_merge_and_assign():
    turns = merge_turns([{"start": 0, "end": 5, "speaker": 0}, {"start": 5.5, "end": 9, "speaker": 0},
                         {"start": 9.2, "end": 20, "speaker": 1}])
    assert [(t["start"], t["end"], t["speaker"]) for t in turns] == [(0, 9, 0), (9.2, 20, 1)]
    segs = [{"start": 1, "end": 4, "text": "a", "words": [[1, 2, "a"], [2, 4, "b"]]},
            {"start": 8, "end": 12, "text": "b", "words": [[8, 9, "x"], [9.5, 12, "y"]]},
            {"start": 30, "end": 31, "text": "c", "words": []}]
    out = assign(segs, turns)
    assert [s["speaker"] for s in out] == [0, 1, None]


FULL = {"chair": "Kris Vincke", "members": [
    {"name": "Kris Vincke", "party": "CD&V", "role": "voorzitter"},
    {"name": "Claudio Saelens", "party": "CD&V", "role": "schepen"},
    {"name": "Patricia Waerniers", "party": "CD&V", "role": "schepen"},
    {"name": "Vicky Verstringe", "party": "Vooruit", "role": "schepen"},
    {"name": "Vicky Reynaert", "party": "Vooruit", "role": "schepen"},
    {"name": "Dieter Vanbesien", "party": "Groen-CD&V", "role": "raadslid"},
    {"name": "Kristel Godyns", "party": "N-VA", "role": "schepen"},
    {"name": "Bernard Lemaitre", "party": "Groen-CD&V", "role": "raadslid"}]}


def test_flemish_spelling_and_unique_first_names():
    assert speakers.match_member("Van Besien", FULL)["name"] == "Dieter Vanbesien"
    assert speakers.match_member("Goddijn", FULL)["name"] == "Kristel Godyns"
    assert speakers.match_member("Lemaitre", FULL)["name"] == "Bernard Lemaitre"
    assert speakers.match_member("Claudio", FULL)["name"] == "Claudio Saelens"
    assert speakers.match_member("Vicky", FULL) is None  # two members called Vicky
    assert speakers.match_member("Claudi", FULL) is None  # a first name must be exact


def test_vocative_cues():
    assert speakers.cues_from_text("Claudio.") == [("handover", "Claudio")]
    assert speakers.cues_from_text("Meneer Van Besien.") == [("handover", "Van Besien")]
    assert speakers.cues_from_text("Puntje 3. De projectvereniging Vrije Tijds Regio Brugge, Patricia.") == [("handover", "Patricia")]
    assert speakers.cues_from_text("Zijn hier vragen of opmerkingen, meneer Van Besien?") == [("handover", "Van Besien")]
    assert speakers.cues_from_text("Oké, dank u wel, mevrouw Goddijn.")[0][0] == "thanks"
    assert speakers.cues_from_text("Nee.") == []  # a stop word, never a name


def test_roll_call_is_skipped_and_chair_is_found():
    segs = [{"start": 0, "end": 3, "text": "Oké. Claudio. Nee. Patricia. Nee. Kristel. Ja. Bernard. Ja.", "speaker": 0}]
    assert speakers.members_mentioned(segs[0]["text"], FULL) >= 3
    assert speakers.collect_votes(segs, [], {0: 3}, FULL) == {}
    segs = []
    t = 0
    for name, spk in [("Claudio.", 1), ("Patricia.", 2), ("Meneer Van Besien.", 3), ("Claudio.", 1), ("Meneer Lemaitre.", 4), ("Patricia.", 2)]:
        segs.append({"start": t, "end": t + 2, "text": name, "speaker": 0}); t += 3
        segs.append({"start": t, "end": t + 20, "text": "Dank u voorzitter, ik heb een vraag over het dossier.", "speaker": spk}); t += 21
    votes = speakers.collect_votes(segs, [], {0: 12, 1: 40, 2: 40, 3: 20, 4: 20}, FULL)
    named = speakers.decide(votes, FULL)
    assert "chair" in votes[0]["Kris Vincke"]  # the chair is recognised
    assert 0 not in named  # but being the chair alone does not name a cluster
    assert named[1]["name"] == "Claudio Saelens" and named[2]["name"] == "Patricia Waerniers"
    assert 3 not in named  # one cue only


def test_agenda_title_alone_names_nobody():
    votes = {7: {"Claudio Saelens": ["agenda", "agenda"]}, 8: {"Patricia Waerniers": ["agenda", "handover"]}}
    named = speakers.decide(votes, FULL)
    assert 7 not in named and named[8]["name"] == "Patricia Waerniers"


def test_regroup_merge_map_and_apply():
    import numpy as np
    from raadzaal import regroup
    a = np.array([1.0, 0.0, 0.0]); b = np.array([0.98, 0.2, 0.0]); c = np.array([0.0, 1.0, 0.0])
    embs = {1: a / np.linalg.norm(a), 2: b / np.linalg.norm(b), 3: c}
    m = regroup.merge_map(embs, {1: 100, 2: 10, 3: 50}, threshold=0.4)
    assert m[2] == 1 and m[1] == 1 and m[3] == 3  # 1 and 2 are one voice, labelled by the one with more time
    turns = regroup.apply([{"start": 0, "end": 5, "speaker": 1}, {"start": 5.2, "end": 8, "speaker": 2}, {"start": 9, "end": 12, "speaker": 3}], m)
    assert [(t["speaker"], t["start"], t["end"]) for t in turns] == [(1, 0, 8), (3, 9, 12)]


def test_chunk_bounds_fold_a_short_tail():
    from raadzaal import diarise
    sr = 10
    assert diarise.chunk_bounds(100 * sr, sr, chunk_s=45) == [(0, 450), (450, 1000)]  # tail of 10 s folded
    assert diarise.chunk_bounds(40 * sr, sr, chunk_s=45) == [(0, 400)]
    assert diarise.chunk_bounds(120 * sr, sr, chunk_s=45) == [(0, 450), (450, 900), (900, 1200)]
