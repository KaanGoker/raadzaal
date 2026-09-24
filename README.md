# Raadzaal

![Wat zei de raad?](assets/banner.png)

Flemish council meetings, transcribed, split into agenda items and searchable: what was said, what was decided, who spoke, and a link to the second in the municipality's own video.

**Site:** [Wat zei de raad?](https://kaangoker.github.io/raadzaal/) (Dutch) · **Report:** [report.md](report.md)

![Session page](assets/session-1280.png)

Flemish municipalities film their public council meetings and put the whole evening online as one video of one to four hours. Almost nobody watches those. Raadzaal turns each recording into one page per meeting: the agenda with the minute each item starts, a short neutral summary and the vote per item, a quote you can click to hear in context, a bar of who spoke how long, and one search box across every meeting.

I wanted to start with Leuven, where I live, but Leuven only plays its recordings on the city's own portal. So the first three municipalities are its neighbour Haacht, plus Tervuren and Beernem: 14 meetings of 2026, 26 hours of audio, 289 agenda items placed on the timeline. Adding another one takes a few lines of configuration.

## Features

- **A time on every line.** faster-whisper large-v3-turbo on the audio of the municipality's YouTube recording, in Dutch, with word timestamps. Repeated lines and subtitle credits, which Whisper sometimes invents in silence, are filtered out first.
- **Agenda items on the timeline.** For municipalities in the Flemish open data (Lokaal Beslist), the official agenda and vote counts come from its SPARQL endpoints. Gemini reads the whole transcript once and says where each item is announced, and those starts become anchors. Items it did not recognise are filled in by aligning the agenda titles to 45-second transcript windows with a multilingual sentence model. For Haacht, which has no official agenda online, the Gemini reading is the agenda.
- **Summaries that are checked.** One Gemini call per meeting writes two or three sentences per item and five bullets for the meeting. A quote is only shown if it exists in the transcript, and its time is looked up in the transcript rather than taken from the model. The model also says whether the transcript at that spot really deals with the item; if not, the page says the placement is doubtful and shows no summary. Only council members who held a seat on that date are named.
- **Who spoke how long.** Speaker turns from sherpa-onnx (pyannote segmentation 3.0 and 3D-Speaker ERes2Net embeddings), run in 45-minute chunks and merged afterwards by comparing one voice embedding per cluster. A cluster gets a name only on two independent cues, such as the chair giving the floor ("Claudio.", "Meneer Van Besien.") or thanking someone, and every page shows what share of the speaking time got a name.
- **Council lists from the source.** Members, roles, groups, chairs and mayors come from the Flemish Mandatendatabank, including the people who left or joined during the term.
- **No server.** The audio is processed on one laptop and never published. The site is static JSON on GitHub Pages. Every passage links back to the municipality's video, which stays the reference.

![Search across every meeting](assets/search-1280.png)

## Numbers

Where each agenda item starts, compared with starts I labelled by hand from the chair's announcements in three meetings (44 starts). A start counts as found when it is within 60 seconds.

| Meeting | Starts labelled | Found | Placed starts that are right | Median error |
|---|---|---|---|---|
| Haacht, 26 Jan 2026 (no official agenda) | 22 | 100% | 82% | 0.5 s |
| Beernem, 22 Jan 2026 | 9 | 89% | 83% | 0.7 s |
| Tervuren, 26 Mar 2026 | 13 | 100% | 93% | 0.7 s |

Without the Gemini reading, the embedding alignment alone finds 89% (Beernem) and 85% (Tervuren), with a median error of 11 s and 6 s. Two council habits make placement harder than it sounds. Chairs often count differently from the official order: in Beernem and Tervuren the spoken number runs one off for the later items, so a spoken "punt 10" can be item 11. And related items are often handled together, which leaves one of them without a start of its own.

Speaker separation was tuned on ten minutes of Beernem where I labelled five people by what they said. Balanced F-score of purity and inverse purity:

| Setting | F |
|---|---|
| CAM++ embeddings, best threshold | 0.68 |
| ERes2Net, threshold 0.7 | 0.94 |
| ERes2Net 0.7 plus the cluster merge at 0.4 | 0.96 |

Naming is the weak part, and I would rather show that than hide it. In the median meeting 10% of the speaking time is attributed to a named council member (range 0 to 42%). Many chairs give the floor without saying a name ("ik geef u graag het woord"), and one person can still be split over several clusters. A name needs a direct cue (the chair giving the floor or thanking by name, or a self-introduction) plus a second cue. Being the chair or the name in an agenda title only supports a name: on their own they put a schepen's answers under the councillor who asked, and councillors who were merged into the chair's voice cluster under the chair's name. So the rule leaves a voice unnamed instead of guessing.

Transcription runs at 5 to 20% of real time on an RTX 3070 Ti laptop GPU, and speaker separation at about half of real time on the CPU. The whole set uses three or four Gemini free-tier calls per meeting.

## How it works

```
municipalities.yaml   channel, title pattern, Lokaal Beslist harvester, exclusions
   |
discover      YouTube Videos and Live tabs, five date formats, commissions and OCMW-only meetings left out
councils      Mandatendatabank (data.lblod.info): members, roles, groups, term dates
agenda        Lokaal Beslist harvester SPARQL: meeting on that date, items in order, votes, public flag
fetch         yt-dlp audio; a download with the same bytes as another meeting is refused
transcribe    faster-whisper large-v3-turbo, CUDA, VAD, word timestamps, hallucination filter
diarise       sherpa-onnx in 45-minute chunks
regroup       one voice embedding per cluster, clusters with the same voice merged
align         Gemini reading as anchors, embedding alignment in between, LLM-only without an agenda
speakers      handover, thanks and self-introduction cues, chair detection; a direct cue plus a second one
summarise     one Gemini call per meeting, quote, name and placement checks
names         second pass: anyone in a summary who is not on the council is replaced by a role, quotes naming them dropped
build         docs/data: index, one JSON per meeting, search corpus, stats; report.md
```

Everything lives in one SQLite file under `data/`; every step can be rerun per meeting.

## Adding a municipality

Add an entry to `municipalities.yaml` with the YouTube channel, a title pattern and, when the municipality is in Lokaal Beslist, the harvester number and labels. Then run `python -m raadzaal councils -m <slug>` and `bash scripts/run_pipeline.sh -m <slug>`. Leuven is on the list but switched off: its portal does not answer requests from outside the EU, so it waits until the recordings can be fetched from Belgium.

## Running it

```bash
python3.12 -m venv venv && ./venv/bin/pip install -r requirements-gpu.txt
curl -fsSL https://deno.land/install.sh | sh     # yt-dlp needs a JavaScript runtime for YouTube
cp .env.example .env                             # GEMINI_API_KEY
./venv/bin/python -m raadzaal discover && ./venv/bin/python -m raadzaal councils
bash scripts/run_pipeline.sh
python -m http.server -d docs
```

Tests: `./venv/bin/python -m pytest -q` (the models themselves only run in the pipeline). `requirements-lock.txt` pins the exact versions the published data was made with.

## Project structure

```
raadzaal/        one module per step, plus config, db, llm
councils/        one YAML per municipality, written by the councils step
prompts/         the Gemini prompts
docs/            the static site (index.html, app.js, style.css) and its data
tests/           pytest, with recorded SPARQL answers and hand-labelled item starts
scripts/         pipeline runners, CUDA environment, screenshots
```

## Limits and removal

Speech recognition makes mistakes, more so with dialect, bad microphones and people talking over each other. The video is always the source. Only public meetings that a municipality published itself are used, and only agenda items marked public. Summaries name only council members who held a seat on that date; the transcript is verbatim, so it holds whatever was said in the room. If something on the site should not be there, mail nadirkaangoker@gmail.com or open an issue, and it comes down within 48 hours.

## License

MIT
