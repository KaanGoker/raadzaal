"""report.md: the numbers behind the dashboard, regenerated from the same JSON."""
import json

from raadzaal import config


def fmt_time(s: float) -> str:
    s = int(s or 0)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def render(index: dict, stats: dict, sessions: list[dict], eval_lines: list[str] | None = None) -> str:
    L = ["# Raadzaal report", "", f"Built {index['built_at']}. {stats['hours_total']} hours of council recordings, "
         f"{stats['items_total']} agenda items placed on the timeline, {len(sessions)} sessions.", ""]
    L += ["## Municipalities", "", "| Municipality | Sessions | Hours | Items | Summarised | Speaking time attributed | Minutes per party (named speakers only) |",
          "|---|---|---|---|---|---|---|"]
    for m in index["municipalities"]:
        st = stats["municipalities"].get(m["slug"], {})
        party = ", ".join(f"{k} {v}" for k, v in st.get("party_minutes", {}).items()) or "none yet"
        L.append(f"| {m['name']} | {m['sessions']} | {m['hours']} | {st.get('items', 0)} | {st.get('summarised', 0)} | {st.get('attributed_share', 0):.0%} | {party} |")
    L += ["", "## Sessions", "", "| Date | Municipality | Length | Items | Summarised | Alignment | Named share |", "|---|---|---|---|---|---|---|"]
    for p in sorted(sessions, key=lambda p: p["date"], reverse=True):
        placed = sum(1 for a in p["agenda"] if a["start"] is not None)
        summ = sum(1 for a in p["agenda"] if a["summary"])
        L.append(f"| {p['date']} | {p['municipality_name']} | {fmt_time(p['duration_s'])} | {placed}/{len(p['agenda'])} | {summ} | "
                 f"{p['method']['alignment']} ({p['method']['disagreements_over_120s']} items where the two methods differ by more than 2 min) | {p['attributed_share']:.0%} |")
    L += ["", "## Minutes per topic (summarised items)", "", "| Topic | Minutes |", "|---|---|"]
    for k, v in stats["topic_minutes"].items():
        L.append(f"| {k} | {v} |")
    L += ["", f"Share of the placed time spent on questions, proposals and interpellations from council members: {stats['questions_share']:.0%}.", ""]
    L += ["## Contested votes", "", "| Date | Municipality | Item | For | Against | Abstained |", "|---|---|---|---|---|---|"]
    for c in stats["contested"][:20]:
        v = c["votes"]
        L.append(f"| {c['date']} | {c['municipality']} | {c['title'][:80]} | {v['voor']} | {v['tegen']} | {v['onthouding']} |")
    if not stats["contested"]:
        L.append("| | | no contested votes in the sessions with an official agenda | | | |")
    L += ["", "## Alignment evaluation", ""]
    if eval_lines:
        L += ["Placed item starts against hand-labelled starts (`tests/fixtures/gold_spans.json`), 60 s tolerance. "
              "`agenda_dp` is the embedding alignment alone, `llm` the Gemini reading alone, `final` what the site shows.", "", "```"]
        L += eval_lines + ["```"]
    L += [] if eval_lines else ["Not run yet (`python -m raadzaal align --eval` with `tests/fixtures/gold_spans.json`)."]
    L += ["", "## Method", "",
          "Audio from the municipality's own YouTube channel. Transcription with faster-whisper large-v3-turbo (Dutch, VAD, word timestamps). "
          "Speaker turns from sherpa-onnx (pyannote segmentation 3.0 and 3D-Speaker embeddings). Agenda and vote counts from the Lokaal Beslist "
          "harvester SPARQL endpoints where the municipality is harvested. A Gemini reading of the transcript says where each item is announced, and those starts are kept as anchors; "
          "the remaining items are placed by a monotone alignment of the agenda titles to 45-second transcript windows (multilingual MiniLM embeddings plus spoken cues); "
          "for municipalities without an official agenda the Gemini reading is the only source. Summaries by Gemini 2.5 Flash Lite, verified: a quote must "
          "exist in the transcript, and a person is named only when they are on the council list or in the agenda title.", ""]
    return "\n".join(L)


def run(con, args, eval_lines: list[str] | None = None) -> int:
    index = json.loads((config.DOCS_DATA / "index.json").read_text(encoding="utf-8"))
    stats = json.loads((config.DOCS_DATA / "stats.json").read_text(encoding="utf-8"))
    sessions = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((config.DOCS_DATA / "sessions").glob("*.json"))]
    text = render(index, stats, sessions, eval_lines)
    (config.ROOT / "report.md").write_text(text, encoding="utf-8")
    print(f"report.md written ({len(text.splitlines())} lines)")
    return 0
