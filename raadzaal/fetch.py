"""Download the audio of a session (m4a) and convert it to 16 kHz mono WAV on demand."""
import hashlib
import os
import subprocess
import tempfile
import time
from pathlib import Path

from raadzaal import config, db

SLEEP_BETWEEN = 20  # seconds between two downloads; be gentle with YouTube


def _env() -> dict:
    env = dict(os.environ)
    env["PATH"] = os.path.expanduser("~/.deno/bin") + os.pathsep + env.get("PATH", "")
    return env


def audio_path(session: dict) -> Path:
    return config.AUDIO / session["municipality"] / f"{session['id']}.m4a"


def download(session: dict) -> Path:
    out = audio_path(session)
    if out.exists() and out.stat().st_size > 1_000_000:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["yt-dlp", "--remote-components", "ejs:github", "-f", "140/bestaudio[ext=m4a]/bestaudio",
           "--sleep-requests", "2", "--no-playlist", "-o", str(out.with_suffix(".%(ext)s")), session["url"]]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=_env())
    if r.returncode != 0 or not out.exists():
        # yt-dlp may have chosen another container
        cands = list(out.parent.glob(f"{session['id']}.*"))
        if cands and r.returncode == 0:
            return cands[0]
        raise RuntimeError(f"download failed: {r.stderr[-400:]}")
    return out


def to_wav(src: Path, dst: Path | None = None) -> Path:
    """16 kHz mono PCM WAV for the models. Caller deletes it."""
    dst = dst or Path(tempfile.mkdtemp(prefix="raadzaal_")) / (src.stem + ".wav")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-300:]}")
    return dst


def same_audio_as(path: Path, root: Path | None = None) -> Path | None:
    """Another downloaded file with identical bytes, or None. Municipalities sometimes re-upload a session under a new title."""
    root = root or config.AUDIO
    size = path.stat().st_size

    def digest(p: Path) -> str:
        h = hashlib.md5()
        with p.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

    mine = None
    for other in root.rglob("*.m4a"):
        if other == path or other.name.endswith(".temp.m4a") or other.stat().st_size != size:
            continue
        mine = mine or digest(path)
        if digest(other) == mine:
            return other
    return None


def duration_s(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, timeout=120)
    return float(r.stdout.strip() or 0)


def run(con, session: dict, args) -> int:
    if session["status"] != "found" and not args.force and audio_path(session).exists():
        return 0
    rid = db.run_start(con, "fetch", session["id"])
    try:
        p = download(session)
        dup = same_audio_as(p)
        if dup is not None:
            raise RuntimeError(f"same audio as {dup.stem}; add {session['id']} to the exclude list of {session['municipality']} "
                               f"in municipalities.yaml if the titles disagree")
        d = duration_s(p)
        con.execute("UPDATE sessions SET duration_s=? WHERE id=? AND (duration_s IS NULL OR duration_s=0)", (d, session["id"]))
        db.advance(con, session["id"], "downloaded")
        db.run_end(con, rid, True, f"{p.stat().st_size // 1_000_000} MB, {d / 60:.0f} min")
        print(f"{session['municipality']:<10} {session['date']}  downloaded {p.stat().st_size // 1_000_000} MB")
        time.sleep(SLEEP_BETWEEN)
    except Exception as exc:
        db.run_end(con, rid, False, str(exc))
        print(f"{session['municipality']:<10} {session['date']}  fetch failed: {exc}")
        return 1
    return 0
