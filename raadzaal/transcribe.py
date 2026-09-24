"""Speech to text with faster-whisper. One JSON per session with segments and word timestamps."""
import json
import re
import time
from pathlib import Path

from raadzaal import config, db, fetch

CREDIT_RE = re.compile(r"ondertitel|ondertiteling|amara\.org|bedankt voor het kijken|abonneer", re.I)
_model = None


def model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE, compute_type=config.WHISPER_COMPUTE,
                              download_root=str(config.MODELS / "whisper"))
    return _model


def transcript_path(session_id: str) -> Path:
    return config.TRANSCRIPTS / f"{session_id}.json"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def clean(segments: list[dict]) -> list[dict]:
    """Drop hallucinations: silence-born segments, subtitle credits, and text repeated back to back."""
    out, prev = [], None
    for s in segments:
        t = s["text"].strip()
        if not t:
            continue
        if (s.get("no_speech_prob") or 0) > 0.6 and (s.get("avg_logprob") or 0) < -1.0:
            continue
        if CREDIT_RE.search(t) and len(t) < 60:
            continue
        n = _norm(t)
        if prev is not None and n == prev and len(n) > 3:
            continue
        if len(n.split()) >= 4 and out and _norm(out[-1]["text"]) == n:
            continue
        prev = n
        out.append({**s, "text": t})
    return out


def transcribe_file(wav: Path, initial_prompt: str = "") -> tuple[list[dict], float]:
    segs, info = model().transcribe(str(wav), language="nl", beam_size=5, vad_filter=True,
                                    vad_parameters={"min_silence_duration_ms": 700},
                                    word_timestamps=True, condition_on_previous_text=False,
                                    initial_prompt=initial_prompt or None)
    out = []
    for s in segs:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                    "avg_logprob": round(s.avg_logprob, 3), "no_speech_prob": round(s.no_speech_prob, 3),
                    "words": [[round(w.start, 2), round(w.end, 2), w.word] for w in (s.words or [])]})
    return out, info.duration


def prompt_for(session: dict) -> str:
    m = config.municipality(session["municipality"])
    return f"Gemeenteraad van {m['name']}. Agendapunt, notulen, schepen, raadslid, burgemeester, voorzitter, stemming."


def save(session: dict, segments: list[dict], meta: dict) -> None:
    config.TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    transcript_path(session["id"]).write_text(
        json.dumps({"session": session["id"], "municipality": session["municipality"], "date": session["date"],
                    **meta, "segments": segments}, ensure_ascii=False), encoding="utf-8")


def load(session_id: str) -> dict | None:
    p = transcript_path(session_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def store_segments(con, session_id: str, segments: list[dict]) -> None:
    rows = [{"session_id": session_id, "start": s["start"], "end": s["end"], "text": s["text"], "speaker": s.get("speaker"),
             "avg_logprob": s.get("avg_logprob"), "no_speech_prob": s.get("no_speech_prob")} for s in segments]
    db.replace_rows(con, "transcript_segments", session_id, rows)


def run(con, session: dict, args) -> int:
    if transcript_path(session["id"]).exists() and not args.force:
        data = load(session["id"])
        store_segments(con, session["id"], data["segments"])
        db.advance(con, session["id"], "transcribed")
        return 0
    rid = db.run_start(con, "transcribe", session["id"])
    wav = None
    try:
        src = fetch.audio_path(session)
        if not src.exists():
            src = next(src.parent.glob(f"{session['id']}.*"))
        wav = fetch.to_wav(src)
        t0 = time.time()
        raw, dur = transcribe_file(wav, prompt_for(session))
        segs = clean(raw)
        el = time.time() - t0
        save(session, segs, {"model": config.WHISPER_MODEL, "compute": config.WHISPER_COMPUTE, "duration_s": dur,
                             "wall_s": round(el, 1), "rtf": round(el / max(dur, 1), 3),
                             "dropped": len(raw) - len(segs)})
        store_segments(con, session["id"], segs)
        db.advance(con, session["id"], "transcribed")
        db.run_end(con, rid, True, f"{len(segs)} segments, rtf {el / max(dur, 1):.3f}")
        print(f"{session['municipality']:<10} {session['date']}  {len(segs)} segments in {el / 60:.1f} min (rtf {el / max(dur, 1):.3f})")
    except Exception as exc:
        db.run_end(con, rid, False, str(exc))
        print(f"{session['municipality']:<10} {session['date']}  transcribe failed: {exc}")
        return 1
    finally:
        if wav and wav.exists():
            wav.unlink(missing_ok=True)
            try:
                wav.parent.rmdir()
            except OSError:
                pass
    return 0
