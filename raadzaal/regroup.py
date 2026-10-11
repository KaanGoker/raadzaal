"""Second clustering pass: one voice embedding per diarised cluster from up to a minute of its own audio,
then clusters with matching voices are merged. Short segments give noisy embeddings in the first pass, so one
person ends up in many small clusters; a centroid over a minute of speech is far steadier."""
import os
import json

import numpy as np

from raadzaal import config, db, diarise, fetch, transcribe

MAX_AUDIO_S = 60.0
MIN_TURN_S = 1.0
MERGE_THRESHOLD = float(os.environ.get("REGROUP_THRESHOLD", "0.4"))  # cosine distance; 0.4 gives F 0.96 on the labelled excerpt, 0.5 merges people


def _extractor():
    import sherpa_onnx
    _, emb = diarise.ensure_models()
    return sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb), num_threads=diarise.THREADS))


def cluster_embeddings(audio: np.ndarray, sr: int, turns: list[dict]) -> dict[int, np.ndarray]:
    ext = _extractor()
    by: dict[int, list] = {}
    for t in turns:
        if t["end"] - t["start"] >= MIN_TURN_S:
            by.setdefault(t["speaker"], []).append(t)
    out = {}
    for spk, ts in by.items():
        ts.sort(key=lambda t: -(t["end"] - t["start"]))
        pieces, total = [], 0.0
        for t in ts:
            if total >= MAX_AUDIO_S:
                break
            a, b = int(t["start"] * sr), int(min(t["end"], t["start"] + MAX_AUDIO_S - total) * sr)
            pieces.append(audio[a:b]); total += (b - a) / sr
        if total < MIN_TURN_S:
            continue
        stream = ext.create_stream()
        stream.accept_waveform(sr, np.concatenate(pieces))
        stream.input_finished()
        v = np.asarray(ext.compute(stream), dtype=np.float32)
        out[spk] = v / (np.linalg.norm(v) or 1.0)
    return out


def merge_map(embs: dict[int, np.ndarray], weight: dict[int, float], threshold: float = MERGE_THRESHOLD) -> dict[int, int]:
    """Average-linkage agglomerative merge on cosine distance; each group is labelled by its member with the most time."""
    ids = list(embs)
    if len(ids) < 2:
        return {i: i for i in ids}
    from sklearn.cluster import AgglomerativeClustering
    X = np.stack([embs[i] for i in ids])
    lab = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average", distance_threshold=threshold).fit_predict(X)
    groups: dict[int, list] = {}
    for i, l in zip(ids, lab):
        groups.setdefault(int(l), []).append(i)
    out = {}
    for members in groups.values():
        head = max(members, key=lambda m: weight.get(m, 0.0))
        for m in members:
            out[m] = head
    return out


def apply(turns: list[dict], mapping: dict[int, int]) -> list[dict]:
    return diarise.merge_turns([{**t, "speaker": mapping.get(t["speaker"], t["speaker"])} for t in turns])


def run(con, session: dict, args) -> int:
    import soundfile as sf
    data = transcribe.load(session["id"])
    if not data or not data.get("turns"):
        print(f"{session['id']}: not diarised")
        return 1
    if data.get("regrouped") and not args.force:
        return 0
    wav = None
    try:
        src = fetch.audio_path(session)
        if not src.exists():
            src = next(src.parent.glob(f"{session['id']}.*"))
        wav = fetch.to_wav(src)
        audio, sr = sf.read(str(wav), dtype="float32")
        turns = data.get("turns_first_pass") or data["turns"]
        embs = cluster_embeddings(audio, sr, turns)
        mapping = merge_map(embs, diarise.speaking_time(turns))
        new = apply(turns, mapping)
        segs = diarise.assign(data["segments"], new)
        data.update(turns_first_pass=turns, turns=new, segments=segs, regrouped={"threshold": MERGE_THRESHOLD,
                    "before": len({t["speaker"] for t in turns}), "after": len({t["speaker"] for t in new})})
        transcribe.transcript_path(session["id"]).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        transcribe.store_segments(con, session["id"], segs)
        db.replace_rows(con, "speaker_turns", session["id"], [{"session_id": session["id"], **t} for t in new])
        print(f"{session['municipality']:<10} {session['date']}  clusters {data['regrouped']['before']} -> {data['regrouped']['after']}")
    finally:
        if wav and wav.exists():
            wav.unlink(missing_ok=True)
            try:
                wav.parent.rmdir()
            except OSError:
                pass
    return 0
