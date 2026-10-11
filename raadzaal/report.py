"""EVALUATION.md: the numbers behind the site, regenerated from the published JSON and the database."""
import json

from raadzaal import config, db

SPOKEN_CUES = {"handover", "thanks", "self", "vocative", "vocative_thanks"}


def fmt_time(s: float) -> str:
    s = int(s or 0)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def name_rows(con) -> list[dict]:
    """Every speaker cluster that is a candidate for a name, with the transcript line behind it."""
    rows = con.execute(
        "SELECT n.session_id, s.municipality, s.date, s.url, n.speaker, n.name, n.party, n.direct, n.cue_start, n.cue_text, n.cues, "
        "(SELECT SUM(t.end - t.start) FROM speaker_turns t WHERE t.session_id=n.session_id AND t.speaker=n.speaker) AS seconds "
        "FROM speaker_names n JOIN sessions s ON s.id=n.session_id ORDER BY s.municipality, s.date, seconds DESC").fetchall()
    return [dict(r) for r in rows]


def names_section(names: list[dict], index: dict) -> list[str]:
    munis = {m["slug"]: m["name"] for m in index["municipalities"]}
    assigned = [n for n in names if set(db.loads(n["cues"]) or []) & SPOKEN_CUES]
    shown = [n for n in assigned if n["direct"]]
    L = ["## Speaker names", "",
         f"{len(shown)} of {len(assigned)} name assignments are backed by a direct cue quoted from the transcript and are shown; "
         "the rest are not shown. Names were not checked by ear.", "",
         "A cluster becomes a candidate when one council member wins at least two cues and beats the runner-up two to one. "
         "DIRECT means one of those cues is a transcript line that gives the floor to, thanks, or introduces the member with an "
         "explicit phrase; INDIRECT means the cues are a bare name as vocative (\"Patricia.\", \"Ja, Lode.\"), the chair detection, "
         "or the name in an agenda title. Only DIRECT names are published; the others are listed here so the rule can be checked. "
         "The time links to that second in the municipality's video.", ""]
    if not names:
        return L + ["No candidates yet.", ""]
    L += ["| Session | Cluster | Name | Speaking time | Cues | Verdict | Transcript line |", "|---|---|---|---|---|---|---|"]
    for n in names:
        cues = ", ".join(db.loads(n["cues"]) or [])
        if n["cue_start"] is not None:
            link = f"[{fmt_time(n['cue_start'])}]({n['url']}&t={int(n['cue_start'])}s)"
            line = f"{link} \"{(n['cue_text'] or '').replace('|', '/').strip()}\""
        else:
            line = "none: chair detection or agenda title only"
        L.append(f"| {munis.get(n['municipality'], n['municipality'])} {n['date']} | {n['speaker']} | {n['name']} | {fmt_time(n['seconds'])} | "
                 f"{cues} | {'DIRECT' if n['direct'] else 'INDIRECT'} | {line} |")
    return L + [""]


def render(index: dict, stats: dict, sessions: list[dict], eval_lines: list[str] | None = None, names: list[dict] | None = None) -> str:
    agenda_total = sum(len(p["agenda"]) for p in sessions)
    L = ["# Evaluation", "",
         f"Built {index['built_at']}. {len(sessions)} sessions, {stats['hours_total']} hours of council recordings, "
         f"{agenda_total} agenda items of which {stats['items_total']} are placed on the timeline. "
         "This file is written by `python -m raadzaal report` from the same JSON the site reads.", ""]

    L += ["## Agenda item placement", "",
          "Placed item starts against 44 starts labelled by hand from the chair's announcements in three meetings "
          "(`tests/fixtures/gold_spans.json`), 60 s tolerance. `agenda_dp` is the embedding alignment alone, `llm` the Gemini "
          "reading alone, `final` what the site shows.", ""]
    if eval_lines:
        L += ["```"] + eval_lines + ["```", ""]
    else:
        L += ["Not run yet (`python -m raadzaal align --eval`).", ""]
    L += ["The embedding alignment alone places most starts within a minute but lands them 6 to 11 seconds off; the Gemini "
          "reading, which copies time stamps from the transcript, brings the median error under a second, and the combination "
          "keeps the recall of the reading with the coverage of the alignment.", "",
          "Two council habits make placement harder than it sounds. Chairs often count differently from the official order: in "
          "Beernem and Tervuren the spoken number runs one off for the later items, so a spoken \"punt 10\" can be item 11. And "
          "related items are often handled together, which leaves one of them without a start of its own. Items the model "
          "says it cannot find at the placed spot are shown without a summary and marked doubtful.", ""]

    L += ["## Speaker separation", "",
          "Tuned on ten minutes of Beernem where five people were labelled by what they said. Balanced F-score of purity and "
          "inverse purity:", "", "| Setting | F |", "|---|---|",
          "| CAM++ embeddings, best threshold | 0.68 |", "| ERes2Net, threshold 0.7 | 0.94 |",
          "| ERes2Net 0.7 plus the cluster merge at 0.4 | 0.96 |", "",
          "Transcription runs at 5 to 20% of real time on an RTX 3070 Ti laptop GPU, and speaker separation at about half of "
          "real time on the CPU. The whole set uses three or four Gemini free-tier calls per meeting.", ""]

    L += names_section(names or [], index)
    L += ["Many chairs give the floor without saying a name (\"ik geef u graag het woord\"), and one person can still be split "
          "over several clusters, so most speaking time stays unnamed. The share of named time is shown on every session page.", ""]

    L += ["## Sessions", "", "| Date | Municipality | Length | Items placed | Summarised | Alignment | Named share |", "|---|---|---|---|---|---|---|"]
    for p in sorted(sessions, key=lambda p: p["date"], reverse=True):
        placed = sum(1 for a in p["agenda"] if a["start"] is not None)
        summ = sum(1 for a in p["agenda"] if a["summary"])
        L.append(f"| {p['date']} | {p['municipality_name']} | {fmt_time(p['duration_s'])} | {placed}/{len(p['agenda'])} | {summ} | "
                 f"{p['method']['alignment']} ({p['method']['disagreements_over_120s']} items where the two methods differ by more than 2 min) | {p['attributed_share']:.0%} |")
    L += ["", "## Municipalities", "", "| Municipality | Sessions | Hours | Items placed | Summarised | Speaking time named |",
          "|---|---|---|---|---|---|"]
    for m in index["municipalities"]:
        st = stats["municipalities"].get(m["slug"], {})
        L.append(f"| {m['name']} | {m['sessions']} | {m['hours']} | {st.get('items', 0)} | {st.get('summarised', 0)} | {st.get('attributed_share', 0):.0%} |")

    L += ["", "## Minutes per topic (summarised items)", "", "| Topic | Minutes |", "|---|---|"]
    for k, v in stats["topic_minutes"].items():
        L.append(f"| {k} | {v} |")
    L += ["", f"Share of the placed time spent on questions, proposals and interpellations from council members: {stats['questions_share']:.0%}. "
          "The last item of a meeting ends where the chair opens the OCMW council, so that part of the recording is not counted.", ""]

    L += ["## Contested votes", "", "| Date | Municipality | Item | For | Against | Abstained |", "|---|---|---|---|---|---|"]
    for c in stats["contested"][:20]:
        v = c["votes"]
        L.append(f"| {c['date']} | {c['municipality']} | {c['title'][:80]} | {v['voor']} | {v['tegen']} | {v['onthouding']} |")
    if not stats["contested"]:
        L.append("| | | no contested votes in the sessions with an official agenda | | | |")

    L += ["", "## Method", "",
          "Audio from the municipality's own YouTube channel. Transcription with faster-whisper large-v3-turbo (Dutch, VAD, word timestamps). "
          "Speaker turns from sherpa-onnx (pyannote segmentation 3.0 and 3D-Speaker embeddings). Agenda and vote counts from the Lokaal Beslist "
          "harvester SPARQL endpoints where the municipality is harvested. A Gemini reading of the transcript says where each item is announced, and those starts are kept as anchors; "
          "the remaining items are placed by a monotone alignment of the agenda titles to 45-second transcript windows (multilingual MiniLM embeddings plus spoken cues); "
          "for municipalities without an official agenda the Gemini reading is the only source. Summaries by Gemini 2.5 Flash Lite, verified: a quote must "
          "exist in the transcript, and a person is named only when they are on the council list or in the agenda title. A second pass "
          "replaces anyone else who is still named in a summary by a role; how many names that pass removed is not recorded.", ""]
    return "\n".join(L)


def run(con, args, eval_lines: list[str] | None = None) -> int:
    index = json.loads((config.DOCS_DATA / "index.json").read_text(encoding="utf-8"))
    stats = json.loads((config.DOCS_DATA / "stats.json").read_text(encoding="utf-8"))
    sessions = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((config.DOCS_DATA / "sessions").glob("*.json"))]
    text = render(index, stats, sessions, eval_lines, name_rows(con))
    (config.ROOT / "EVALUATION.md").write_text(text, encoding="utf-8")
    print(f"EVALUATION.md written ({len(text.splitlines())} lines)")
    return 0
