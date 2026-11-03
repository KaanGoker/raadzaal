from raadzaal import translate


def test_texts_collects_every_shown_line_once():
    payloads = [{"notes": {"decided": ["Het budget werd goedgekeurd."]},
                 "agenda": [{"title": "Budget 2026", "summary": {"nl": "De raad keurde het budget goed.", "quote": "Dat klopt."}},
                            {"title": "Budget 2026", "summary": None},
                            {"title": "Vragen", "summary": {"nl": "Een vraag over de Stationsstraat.", "quote": None}}]}]
    assert translate.texts(payloads) == ["Het budget werd goedgekeurd.", "Budget 2026", "De raad keurde het budget goed.",
                                         "Dat klopt.", "Vragen", "Een vraag over de Stationsstraat."]


def test_match_end_drops_the_period_a_title_does_not_have():
    assert translate.match_end("Eventuele vragen en suggesties", "Any questions and suggestions.") == "Any questions and suggestions"
    assert translate.match_end("Het werd goedgekeurd.", "It was approved.") == "It was approved."
