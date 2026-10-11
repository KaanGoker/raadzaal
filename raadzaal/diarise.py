"""Who spoke when: sherpa-onnx offline speaker diarisation (pyannote segmentation 3.0 + 3D-Speaker embeddings)."""
import os
import json
import tarfile
import time
from pathlib import Path

import requests

from raadzaal import config, db, fetch, transcribe

SEG_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMB_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
THRESHOLD = 0.7  # tuned on ten hand-labelled minutes of Beernem, see EVALUATION.md: ERes2Net at 0.7 beats CAM++ at any threshold
MERGE_GAP = 1.0
THREADS = int(os.environ.get('DIAR_THREADS', '4'))
CHUNK_S = 45 * 60  # the one-pass clustering needs about 8 GB on a 150-minute session; chunks keep it under 1 GB
CHUNK_ID = 1000    # speaker ids of chunk k start at k * CHUNK_ID; the regroup pass merges voices across chunks


def ensure_models() -> tuple[Path, Path]:
    d = config.MODELS / "diar"
    d.mkdir(parents=True, exist_ok=True)
    seg = d / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
    emb = d / EMB_URL.rsplit("/", 1)[-1]
    if not seg.exists():
        tb = d / "seg.tar.bz2"
        with requests.get(SEG_URL, stream=True, timeout=300) as r:
            r.raise_for_status()
            tb.write_bytes(r.content)
        with tarfile.open(tb) as tf:
            tf.extractall(d, filter="data")
        tb.unlink()
    if not emb.exists():
        with requests.get(EMB_URL, stream=True, timeout=300) as r:
            r.raise_for_status()
            emb.write_bytes(r.content)
    return seg, emb


def _diariser(threshold: float):
    import sherpa_onnx
    seg, emb = ensure_models()
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg)), num_threads=THREADS),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb), num_threads=THREADS),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=threshold),
        min_duration_on=0.3, min_duration_off=0.5)
    return sherpa_onnx.OfflineSpeakerDiarization(cfg)


def chunk_bounds(n_samples: int, sr: int, chunk_s: float = CHUNK_S) -> list[tuple[int, int]]:
    """Sample ranges of at most `chunk_s` seconds; a short tail is folded into the previous chunk."""
    size = int(chunk_s * sr)
    bounds = [(a, min(a + size, n_samples)) for a in range(0, n_samples, size)]
    if len(bounds) > 1 and bounds[-1][1] - bounds[-1][0] < size // 4:
        a, _ = bounds[-2]
        bounds = bounds[:-2] + [(a, n_samples)]
    return bounds


def diarise_wav(wav: Path, threshold: float = THRESHOLD) -> list[dict]:
    import soundfile as sf
    sd = _diariser(threshold)
    audio, sr = sf.read(str(wav), dtype="float32")
    if sr != sd.sample_rate:
        raise ValueError(f"expected {sd.sample_rate} Hz, got {sr}")
    turns = []
    for k, (a, b) in enumerate(chunk_bounds(len(audio), sr)):
        res = sd.process(audio[a:b]).sort_by_start_time()
        off = a / sr
        turns += [{"start": round(r.start + off, 2), "end": round(r.end + off, 2), "speaker": int(r.speaker) + k * CHUNK_ID} for r in res]
    return merge_turns(turns)


def merge_turns(turns: list[dict], gap: float = MERGE_GAP) -> list[dict]:
    """Join consecutive turns of the same speaker separated by less than `gap` seconds."""
    out: list[dict] = []
    for t in sorted(turns, key=lambda x: x["start"]):
        if out and out[-1]["speaker"] == t["speaker"] and t["start"] - out[-1]["end"] <= gap:
            out[-1]["end"] = max(out[-1]["end"], t["end"])
        else:
            out.append(dict(t))
    return out


def assign(segments: list[dict], turns: list[dict]) -> list[dict]:
    """Give every transcript segment the speaker with the largest overlap (word-weighted when words exist)."""
    if not turns:
        return [{**s, "speaker": None} for s in segments]
    out = []
    ti = 0
    for s in segments:
        pieces = [(w[0], w[1]) for w in s.get("words") or [] if w[1] > w[0]] or [(s["start"], s["end"])]
        overlap: dict[int, float] = {}
        while ti > 0 and turns[ti - 1]["end"] > s["start"]:
            ti -= 1
        j = ti
        while j < len(turns) and turns[j]["start"] < s["end"]:
            t = turns[j]
            for a, b in pieces:
                o = min(b, t["end"]) - max(a, t["start"])
                if o > 0:
                    overlap[t["speaker"]] = overlap.get(t["speaker"], 0.0) + o
            j += 1
        while ti < len(turns) and turns[ti]["end"] < s["start"]:
            ti += 1
        spk = max(overlap, key=overlap.get) if overlap else None
        out.append({**s, "speaker": spk})
    return out


def speaking_time(turns: list[dict]) -> dict[int, float]:
    tot: dict[int, float] = {}
    for t in turns:
        tot[t["speaker"]] = tot.get(t["speaker"], 0.0) + (t["end"] - t["start"])
    return tot


def run(con, session: dict, args) -> int:
    data = transcribe.load(session["id"])
    if data is None:
        print(f"{session['id']}: no transcript yet")
        return 1
    if data.get("turns") and not args.force:
        segs = assign(data["segments"], data["turns"])
        transcribe.store_segments(con, session["id"], segs)
        db.replace_rows(con, "speaker_turns", session["id"], [{"session_id": session["id"], **t} for t in data["turns"]])
        db.advance(con, session["id"], "diarised")
        return 0
    rid = db.run_start(con, "diarise", session["id"])
    wav = None
    try:
        src = fetch.audio_path(session)
        if not src.exists():
            src = next(src.parent.glob(f"{session['id']}.*"))
        wav = fetch.to_wav(src)
        t0 = time.time()
        turns = diarise_wav(wav)
        el = time.time() - t0
        segs = assign(data["segments"], turns)
        data.pop("turns_first_pass", None); data.pop("regrouped", None)  # a new first pass invalidates the second
        data.update(turns=turns, segments=segs, diar_wall_s=round(el, 1), diar_threshold=THRESHOLD)
        transcribe.transcript_path(session["id"]).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        transcribe.store_segments(con, session["id"], segs)
        db.replace_rows(con, "speaker_turns", session["id"], [{"session_id": session["id"], **t} for t in turns])
        db.advance(con, session["id"], "diarised")
        n = len({t["speaker"] for t in turns})
        db.run_end(con, rid, True, f"{n} speakers, {len(turns)} turns, {el:.0f} s")
        print(f"{session['municipality']:<10} {session['date']}  {n} speakers, {len(turns)} turns in {el / 60:.1f} min")
    except Exception as exc:
        db.run_end(con, rid, False, str(exc))
        print(f"{session['municipality']:<10} {session['date']}  diarise failed: {exc}")
        return 1
    finally:
        if wav and wav.exists():
            wav.unlink(missing_ok=True)
            try:
                wav.parent.rmdir()
            except OSError:
                pass
    return 0
