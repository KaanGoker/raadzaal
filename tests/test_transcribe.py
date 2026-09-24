from raadzaal.transcribe import clean, _norm


def seg(text, start=0.0, lp=-0.3, ns=0.1):
    return {"start": start, "end": start + 2, "text": text, "avg_logprob": lp, "no_speech_prob": ns, "words": []}


def test_clean_drops_silence_hallucination_and_credits():
    segs = [seg("Goedenavond allemaal."), seg("Ondertiteling door Amara.org", lp=-0.5),
            seg("Bedankt.", lp=-1.4, ns=0.9), seg("Volgend agendapunt.")]
    assert [s["text"] for s in clean(segs)] == ["Goedenavond allemaal.", "Volgend agendapunt."]


def test_clean_drops_back_to_back_repeats_only():
    segs = [seg("Dank u wel voor uw vraag."), seg("Dank u wel voor uw vraag."), seg("Ja."), seg("Ja."),
            seg("Dank u wel voor uw vraag.")]
    out = [s["text"] for s in clean(segs)]
    assert out == ["Dank u wel voor uw vraag.", "Ja.", "Ja.", "Dank u wel voor uw vraag."]  # short repeats are real speech


def test_norm():
    assert _norm("  Dank U, wel! ") == "dank u wel"
