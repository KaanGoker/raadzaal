# Evaluation

Built 2026-10-11T06:51:22+00:00. 14 sessions, 26.3 hours of council recordings, 333 agenda items of which 286 are placed on the timeline. This file is written by `python -m raadzaal report` from the same JSON the site reads.

## Agenda item placement

Placed item starts against 44 starts labelled by hand from the chair's announcements in three meetings (`tests/fixtures/gold_spans.json`), 60 s tolerance. `agenda_dp` is the embedding alignment alone, `llm` the Gemini reading alone, `final` what the site shows.

```
agenda_dp beernem   2026-01-22  gold  9  placed 15  recall 89%  precision 67%  median error 11.2 s
agenda_dp tervuren  2026-03-26  gold 13  placed 15  recall 85%  precision 80%  median error 5.7 s
llm       haacht    2026-01-26  gold 22  placed 28  recall 100%  precision 82%  median error 0.5 s
llm       beernem   2026-01-22  gold  9  placed 13  recall 89%  precision 77%  median error 0.6 s
llm       tervuren  2026-03-26  gold 13  placed 12  recall 100%  precision 100%  median error 0.7 s
final     haacht    2026-01-26  gold 22  placed 28  recall 100%  precision 82%  median error 0.5 s
final     beernem   2026-01-22  gold  9  placed 12  recall 89%  precision 83%  median error 0.7 s
final     tervuren  2026-03-26  gold 13  placed 15  recall 100%  precision 93%  median error 0.7 s
```

The embedding alignment alone places most starts within a minute but lands them 6 to 11 seconds off; the Gemini reading, which copies time stamps from the transcript, brings the median error under a second, and the combination keeps the recall of the reading with the coverage of the alignment.

Two council habits make placement harder than it sounds. Chairs often count differently from the official order: in Beernem and Tervuren the spoken number runs one off for the later items, so a spoken "punt 10" can be item 11. And related items are often handled together, which leaves one of them without a start of its own. Items the model says it cannot find at the placed spot are shown without a summary and marked doubtful.

## Speaker separation

Tuned on ten minutes of Beernem where five people were labelled by what they said. Balanced F-score of purity and inverse purity:

| Setting | F |
|---|---|
| CAM++ embeddings, best threshold | 0.68 |
| ERes2Net, threshold 0.7 | 0.94 |
| ERes2Net 0.7 plus the cluster merge at 0.4 | 0.96 |

Transcription runs at 5 to 20% of real time on an RTX 3070 Ti laptop GPU, and speaker separation at about half of real time on the CPU. The whole set uses three or four Gemini free-tier calls per meeting.

## Speaker names

3 of 18 name assignments are backed by a direct cue quoted from the transcript and are shown; the rest are not shown. Names were not checked by ear.

A cluster becomes a candidate when one council member wins at least two cues and beats the runner-up two to one. DIRECT means one of those cues is a transcript line that gives the floor to, thanks, or introduces the member with an explicit phrase; INDIRECT means the cues are a bare name as vocative ("Patricia.", "Ja, Lode."), the chair detection, or the name in an agenda title. Only DIRECT names are published; the others are listed here so the rule can be checked. The time links to that second in the municipality's video.

| Session | Cluster | Name | Speaking time | Cues | Verdict | Transcript line |
|---|---|---|---|---|---|---|
| Beernem 2026-01-22 | 91 | Jos Sypré | 0:09:19 | vocative, vocative | INDIRECT | [0:20:34](https://www.youtube.com/watch?v=sRt4a96jGV8&t=1234s) "Ja, dan nog een trage weg, Jos." |
| Beernem 2026-01-22 | 36 | Patricia Waerniers | 0:07:20 | vocative, vocative | INDIRECT | [0:06:58](https://www.youtube.com/watch?v=sRt4a96jGV8&t=418s) "Puntje 3. De projectvereniging Vrije Tijds Regio Brugge, Patricia." |
| Beernem 2026-01-22 | 84 | Jan Vanassche | 0:02:05 | vocative, vocative | INDIRECT | [0:19:33](https://www.youtube.com/watch?v=sRt4a96jGV8&t=1173s) "Om een of ander in de rieren, Jan." |
| Beernem 2026-02-26 | 1042 | Jos Sypré | 0:27:44 | handover, vocative, vocative, vocative | DIRECT | [0:01:40](https://www.youtube.com/watch?v=bwketAO3KFk&t=100s) "En ik geef het woord aan Jos." |
| Beernem 2026-02-26 | 41 | Ruben Strobbe | 0:25:40 | vocative, vocative | INDIRECT | [0:09:19](https://www.youtube.com/watch?v=bwketAO3KFk&t=559s) "Dan een omgevingsverginning, Ruben." |
| Beernem 2026-02-26 | 0 | Kris Vincke | 0:09:50 | chair, chair | INDIRECT | none: chair detection or agenda title only |
| Beernem 2026-02-26 | 2028 | Lode Vanneste | 0:07:51 | vocative, vocative_thanks | INDIRECT | [1:38:22](https://www.youtube.com/watch?v=bwketAO3KFk&t=5902s) "Tot slot, Lode." |
| Beernem 2026-03-19 | 21 | Patricia Waerniers | 0:08:44 | vocative, vocative | INDIRECT | [0:07:23](https://www.youtube.com/watch?v=-lvejwNh-6w&t=443s) "De uitbatingsovereenkomst concessie voor het cultuurcafé, Patricia?" |
| Beernem 2026-04-23 | 214 | Patricia Waerniers | 0:14:43 | vocative, vocative | INDIRECT | [1:08:35](https://www.youtube.com/watch?v=lbzlr-Xz1A8&t=4115s) "Het kunstgrasveld, Patricia." |
| Beernem 2026-04-23 | 2 | Kris Vincke | 0:13:21 | chair, chair | INDIRECT | none: chair detection or agenda title only |
| Beernem 2026-04-23 | 102 | Ruben Strobbe | 0:12:57 | vocative, vocative | INDIRECT | [0:24:02](https://www.youtube.com/watch?v=lbzlr-Xz1A8&t=1442s) "Ruben." |
| Beernem 2026-04-23 | 21 | Jan Vanassche | 0:08:48 | vocative, vocative, vocative, vocative | INDIRECT | [0:01:50](https://www.youtube.com/watch?v=lbzlr-Xz1A8&t=110s) "Ja, Jan." |
| Beernem 2026-04-23 | 121 | Jan Vanassche | 0:03:23 | vocative, vocative, vocative | INDIRECT | [0:43:57](https://www.youtube.com/watch?v=lbzlr-Xz1A8&t=2637s) "Jan." |
| Beernem 2026-05-21 | 7 | Kris Vincke | 0:07:03 | chair, chair | INDIRECT | none: chair detection or agenda title only |
| Beernem 2026-05-21 | 63 | Ruben Strobbe | 0:04:34 | vocative, handover | DIRECT | [0:24:31](https://www.youtube.com/watch?v=Hnqkx5mYqLE&t=1471s) "Mag ik geven het woord aan Ruben?" |
| Beernem 2026-05-21 | 144 | Patricia Waerniers | 0:02:32 | vocative, vocative | INDIRECT | [0:27:51](https://www.youtube.com/watch?v=Hnqkx5mYqLE&t=1671s) "En dan gaan we kanaalzwemmen, Patricia." |
| Beernem 2026-06-18 | 2002 | Kris Vincke | 0:14:34 | chair, chair | INDIRECT | none: chair detection or agenda title only |
| Beernem 2026-09-17 | 1000 | Kris Vincke | 0:17:06 | chair, chair | INDIRECT | none: chair detection or agenda title only |
| Beernem 2026-09-17 | 4008 | Lode Vanneste | 0:09:32 | vocative, vocative | INDIRECT | [0:22:30](https://www.youtube.com/watch?v=bXE2JkLMD8A&t=1350s) "Ja, Lode." |
| Haacht 2026-02-23 | 1060 | Bernard Lemaitre | 0:06:56 | vocative, vocative | INDIRECT | [0:36:07](https://www.youtube.com/watch?v=cSppfmeNUN4&t=2167s) "Zijn er over dit punt vragen of opmerkingen, meneer Lemaitre?" |
| Haacht 2026-04-20 | 8 | Marianne Ursi | 0:07:19 | vocative, vocative | INDIRECT | [0:00:59](https://www.youtube.com/watch?v=jIg1niOoCpg&t=59s) "En ik ga ervan uit dat alle vragen daar gesteld zijn. Nee, mevrouw Ursti." |
| Haacht 2026-06-22 | 0 | Annelotte Van Meldert | 0:19:27 | chair, chair | INDIRECT | none: chair detection or agenda title only |
| Haacht 2026-06-22 | 56 | Bernard Lemaitre | 0:06:52 | vocative, vocative | INDIRECT | [0:24:10](https://www.youtube.com/watch?v=thm4MzeMoB4&t=1450s) "meneer Lemaitre" |
| Tervuren 2026-01-29 | 1038 | Carine Borghans | 0:03:41 | agenda, agenda | INDIRECT | none: chair detection or agenda title only |
| Tervuren 2026-04-30 | 44 | Geoffroy de Visscher | 0:18:02 | handover, handover | DIRECT | [0:51:34](https://www.youtube.com/watch?v=KzLwJVaCxig&t=3094s) "Meneer Lisenborgs, u geeft het woord aan meneer De Visser." |
| Tervuren 2026-04-30 | 90 | Geoffroy de Visscher | 0:16:03 | agenda, agenda | INDIRECT | none: chair detection or agenda title only |

Many chairs give the floor without saying a name ("ik geef u graag het woord"), and one person can still be split over several clusters, so most speaking time stays unnamed. The share of named time is shown on every session page.

## Sessions

| Date | Municipality | Length | Items placed | Summarised | Alignment | Named share |
|---|---|---|---|---|---|---|
| 2026-09-17 | Beernem | 3:33:20 | 11/21 | 11 | agenda_dp (7 items where the two methods differ by more than 2 min) | 0% |
| 2026-06-22 | Haacht | 1:47:31 | 53/53 | 53 | llm (0 items where the two methods differ by more than 2 min) | 0% |
| 2026-06-18 | Beernem | 2:58:48 | 17/19 | 17 | agenda_dp (4 items where the two methods differ by more than 2 min) | 0% |
| 2026-05-21 | Beernem | 0:57:07 | 11/18 | 11 | agenda_dp (13 items where the two methods differ by more than 2 min) | 9% |
| 2026-04-30 | Tervuren | 1:49:00 | 18/32 | 18 | agenda_dp (17 items where the two methods differ by more than 2 min) | 20% |
| 2026-04-23 | Beernem | 2:09:29 | 17/21 | 17 | agenda_dp (3 items where the two methods differ by more than 2 min) | 0% |
| 2026-04-20 | Haacht | 1:09:21 | 20/20 | 20 | llm (0 items where the two methods differ by more than 2 min) | 0% |
| 2026-03-26 | Tervuren | 2:45:32 | 15/15 | 15 | agenda_dp (1 items where the two methods differ by more than 2 min) | 0% |
| 2026-03-19 | Beernem | 1:01:05 | 10/11 | 10 | agenda_dp (1 items where the two methods differ by more than 2 min) | 0% |
| 2026-02-26 | Beernem | 2:29:01 | 18/21 | 18 | agenda_dp (3 items where the two methods differ by more than 2 min) | 19% |
| 2026-02-23 | Haacht | 1:47:17 | 37/37 | 37 | llm (0 items where the two methods differ by more than 2 min) | 0% |
| 2026-01-29 | Tervuren | 1:15:06 | 19/22 | 19 | agenda_dp (12 items where the two methods differ by more than 2 min) | 0% |
| 2026-01-26 | Haacht | 0:59:01 | 28/28 | 28 | llm (0 items where the two methods differ by more than 2 min) | 0% |
| 2026-01-22 | Beernem | 1:36:46 | 12/15 | 12 | agenda_dp (6 items where the two methods differ by more than 2 min) | 0% |

## Municipalities

| Municipality | Sessions | Hours | Items placed | Summarised | Speaking time named |
|---|---|---|---|---|---|
| Haacht | 4 | 5.7 | 138 | 138 | 0% |
| Tervuren | 3 | 5.8 | 52 | 52 | 6% |
| Beernem | 7 | 14.8 | 96 | 96 | 4% |

## Minutes per topic (summarised items)

| Topic | Minutes |
|---|---|
| nutsvoorzieningen en afval | 178 |
| andere | 158 |
| veiligheid | 138 |
| ruimtelijke ordening | 132 |
| onderwijs en jeugd | 116 |
| wonen | 111 |
| financiën | 107 |
| milieu en klimaat | 104 |
| mobiliteit | 96 |
| cultuur en sport | 93 |
| participatie en bestuur | 84 |
| personeel en organisatie | 47 |
| welzijn en zorg | 19 |
| economie en handel | 7 |

Share of the placed time spent on questions, proposals and interpellations from council members: 31%. The last item of a meeting ends where the chair opens the OCMW council, so that part of the recording is not counted.

## Contested votes

| Date | Municipality | Item | For | Against | Abstained |
|---|---|---|---|---|---|
| 2026-04-30 | Tervuren | Voorstel om de toegang tot ondergrondse containers uit te breiden voor alle inwo | 3 | 21 | 0 |
| 2026-01-29 | Tervuren | Voorstel over de tussenkomst in de kosten van de bestrijding van de Aziatische h | 9 | 18 | 0 |
| 2026-03-26 | Tervuren | Voorstel over het voormalig politiecommissariaat (raadslid Peeters) | 5 | 18 | 4 |
| 2026-03-26 | Tervuren | Voorstel over sociale woningen op de site oude jongensschool Duisburg (raadslid  | 9 | 18 | 0 |
| 2026-04-30 | Tervuren | Voorstel over bijkomende onderhouds- en controlemaatregelen rond ondergrondse co | 4 | 16 | 4 |
| 2026-04-30 | Tervuren | Voorstel over realtime informatievoorziening rond de vulgraad van ondergrondse c | 4 | 16 | 4 |
| 2026-04-30 | Tervuren | Voorstel tot deelname aan en ondersteuning van het subsidieprogramma voor gezond | 4 | 16 | 4 |
| 2026-04-23 | Beernem | Extra agendapunt ingediend door de N-VA-fractie in toepassing van artikel 21 van | 8 | 12 | 0 |
| 2026-02-26 | Beernem | Instap in de intergemeentelijke recyclageparken van IVBO volgens het 'reglement  | 15 | 9 | 0 |
| 2026-05-21 | Beernem | Vivendo - algemene vergadering - 8 juni 2026 | 15 | 8 | 0 |
| 2026-06-18 | Beernem | Lokaal toewijzingsreglement sociale huurwoningen vanaf 2027: conceptnota vanuit  | 13 | 8 | 1 |
| 2026-06-18 | Beernem | Toetreding tot het DifTar-systeem van IVBO voor de huis-aan-huisinzameling in co | 14 | 8 | 0 |
| 2026-06-18 | Beernem | Politieverordening betreffende de inzameling en het beheer van huishoudelijke af | 14 | 8 | 0 |
| 2026-06-18 | Beernem | Belastingreglement op de inzameling en verwerking van huishoudelijke afvalstoffe | 14 | 8 | 0 |
| 2026-06-18 | Beernem | Subsidiereglement Diftar voor medische en financiële redenen | 14 | 8 | 0 |
| 2026-06-18 | Beernem | Aanpassing reglement bibliotheek Beernem | 13 | 8 | 1 |
| 2026-03-26 | Tervuren | Niet-indiening van een projectaanvraag en niet-invoering van subsidies voor wate | 18 | 5 | 4 |
| 2026-01-22 | Beernem | Projectvereniging Vrijetijdsregio Brugge - aanduiden vertegenwoordigers gemeente | 23 | 1 | 1 |
| 2026-01-22 | Beernem | IVBO - aanduiden éénmalige vertegenwoordiger gemeente Beernem in de buitengewone | 24 | 1 | 0 |
| 2026-02-26 | Beernem | Definitieve beslissing toekenning straatnaam Burgemeester Urbain De Cuyperstraat | 14 | 1 | 9 |

## Method

Audio from the municipality's own YouTube channel. Transcription with faster-whisper large-v3-turbo (Dutch, VAD, word timestamps). Speaker turns from sherpa-onnx (pyannote segmentation 3.0 and 3D-Speaker embeddings). Agenda and vote counts from the Lokaal Beslist harvester SPARQL endpoints where the municipality is harvested. A Gemini reading of the transcript says where each item is announced, and those starts are kept as anchors; the remaining items are placed by a monotone alignment of the agenda titles to 45-second transcript windows (multilingual MiniLM embeddings plus spoken cues); for municipalities without an official agenda the Gemini reading is the only source. Summaries by Gemini 2.5 Flash Lite, verified: a quote must exist in the transcript, and a person is named only when they are on the council list or in the agenda title. A second pass replaces anyone else who is still named in a summary by a role; how many names that pass removed is not recorded.
