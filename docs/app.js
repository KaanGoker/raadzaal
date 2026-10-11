/* Wat zei de raad?  A static reader for the JSON in data/. No build step. */
const PARTY_COLORS = {"N-VA": "#f2c500", "CD&V": "#ff8000", "Vooruit": "#e30613", "Open Vld": "#0047ab", "Groen": "#5aa02c",
  "Vlaams Belang": "#3b3b3b", "PVDA": "#a50021", "Team 3150": "#365ea8", "Groen-CD&V": "#2e9e6a", "Voor Tervuren": "#5da9e9",
  "Groen+Vooruit": "#8bbf3f", "Tervuren Unie + Volt": "#6c3c96"};
const GREY = ["#9aa5b4", "#7f8a99", "#b7c0cc", "#6a7482", "#c9d0d9", "#55606e"];
const TOPIC_LABEL = t => t.charAt(0).toUpperCase() + t.slice(1);
const state = {index: null, stats: null, sessions: {}, search: null, docs: null};
const CONTACT = "nadirkaangoker@gmail.com";
const app = document.getElementById("app");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmt = s => { s = Math.max(0, Math.round(s || 0)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60; return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`; };
const dateNL = d => { const [y, m, dd] = d.split("-"); const M = ["januari","februari","maart","april","mei","juni","juli","augustus","september","oktober","november","december"]; return `${+dd} ${M[+m - 1]} ${y}`; };
const ytAt = (url, s) => `${url}&t=${Math.max(0, Math.floor(s || 0))}s`;
const colorFor = (spk, i) => spk.party && PARTY_COLORS[spk.party] ? PARTY_COLORS[spk.party] : (spk.name ? "#4b5563" : GREY[i % GREY.length]);

async function getJSON(path) { const r = await fetch(path, {cache: "no-cache"}); if (!r.ok) throw new Error(path); return r.json(); }
async function loadIndex() { if (!state.index) { [state.index, state.stats] = await Promise.all([getJSON("data/index.json"), getJSON("data/stats.json")]); } return state.index; }
async function loadSession(id) { if (!state.sessions[id]) state.sessions[id] = await getJSON(`data/sessions/${id}.json`); return state.sessions[id]; }
async function loadSearch() {
  if (state.search) return state.search;
  if (typeof MiniSearch === "undefined") throw new Error("vendor/minisearch-7.1.0.js did not load");
  state.docs = await getJSON("data/search.json");
  const ms = new MiniSearch({fields: ["title", "text"], storeFields: ["type", "session", "municipality", "date", "title", "text", "start"],
    searchOptions: {prefix: true, fuzzy: 0.15, boost: {title: 2}}});
  ms.addAll(state.docs);
  state.search = ms;
  return ms;
}

const SITE = "Wat zei de raad?";
const setTitle = t => { document.title = t ? `${t} | ${SITE}` : SITE; };
const decode = s => { try { return decodeURIComponent(s); } catch (e) { return s; } };
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function route() {
  const h = location.hash || "#/";
  window.scrollTo(0, 0);
  setTitle("");
  const m = h.match(/^#\/s\/([^/?]+)/);
  if (m) return viewSession(m[1]);
  if (h.startsWith("#/zoek")) return viewSearch(decode(h.split("?q=")[1] || ""));
  if (h.startsWith("#/methode")) return viewMethod();
  const g = h.match(/^#\/g\/([^/?]+)/);
  if (g) return viewMunicipality(g[1]);
  return viewHome();
}

async function viewHome() {
  const idx = await loadIndex(), st = state.stats;
  const munis = idx.municipalities.map(m => `<div class="card"><a class="block" href="#/g/${m.slug}"><h3>${esc(m.name)}</h3>
      <div class="kpi">${m.sessions}</div><div class="small muted">zittingen, ${m.hours} uur${m.has_agenda ? "" : ", zonder officiële agenda"}</div>
      <div class="small muted">laatste: ${m.last_date ? dateNL(m.last_date) : "nog geen"}</div></a></div>`).join("");
  const recent = idx.sessions.slice(0, 8).map(s => `<li><a href="#/s/${s.id}"><strong>${esc(s.municipality_name)}</strong>, ${dateNL(s.date)}</a>
      <span class="badge">${s.items} punten</span>${s.summarised ? "" : '<span class="badge">samenvatting volgt</span>'}
      ${s.decided && s.decided.length ? `<div class="small">${s.decided.map(esc).join(" · ")}</div>` : ""}
      <div class="meta">${fmt(s.duration_s)} opname</div></li>`).join("");
  app.innerHTML = `<h1>Wat zei de raad?</h1>
    <p class="lead">Drie Vlaamse gemeenteraden, automatisch uitgeschreven en doorzoekbaar. Per agendapunt: wat er gezegd is, wat er beslist is, wie sprak hoe lang, en de sprong naar de seconde in de video van de gemeente.</p>
    <form class="search" onsubmit="location.hash='#/zoek?q='+encodeURIComponent(this.q.value);return false;"><input name="q" placeholder="Zoek in alles: fietspad, belasting, zwembad..." aria-label="Zoeken"><button>Zoek</button></form>
    <div class="grid">${munis}</div>
    <h2>Laatste zittingen</h2><ul class="list">${recent}</ul>
    <h2>Waar ging de tijd naartoe?</h2><p class="small muted">Minuten per onderwerp over alle samengevatte agendapunten (${st.items_total} punten, ${st.hours_total} uur opname).</p>
    ${topicBars(st.topic_minutes)}`;
}

function topicBars(topics) {
  const entries = Object.entries(topics || {});
  if (!entries.length) return "<p class='muted small'>Nog geen samenvattingen.</p>";
  const max = Math.max(...entries.map(e => e[1])) || 1;
  return `<div class="hbars">${entries.map(([t, v]) => `<div class="hbar"><span class="hbar-label">${esc(TOPIC_LABEL(t))}</span>
      <span class="hbar-track"><span class="hbar-fill" style="width:${(100 * v / max).toFixed(1)}%"></span></span><span class="hbar-value">${v} min</span></div>`).join("")}</div>`;
}

async function viewMunicipality(slug) {
  const idx = await loadIndex(), st = state.stats;
  const m = idx.municipalities.find(x => x.slug === slug);
  if (!m) return viewHome();
  setTitle(m.name);
  const ms = st.municipalities[slug] || {};
  const sessions = idx.sessions.filter(s => s.municipality === slug).map(s => `<li><a href="#/s/${s.id}">${dateNL(s.date)}</a>
      <span class="badge">${s.items} punten</span>${s.summarised ? "" : '<span class="badge">samenvatting volgt</span>'}
      ${s.decided && s.decided.length ? `<div class="small">${s.decided.map(esc).join(" · ")}</div>` : ""}<div class="meta">${fmt(s.duration_s)} opname</div></li>`).join("");
  app.innerHTML = `<h1>${esc(m.name)}</h1><p class="lead">${m.sessions} zittingen, ${m.hours} uur opname, ${ms.items || 0} agendapunten op de tijdlijn.${m.has_agenda ? "" : " Voor deze gemeente is er geen officiële agenda in Lokaal Beslist; de agendapunten zijn uit de opname zelf gelezen."}</p>
    <h2>Zittingen</h2><ul class="list">${sessions}</ul>`;
}

async function viewSession(id) {
  const idx = await loadIndex();
  let p; try { p = await loadSession(id); } catch (e) { app.innerHTML = `<p>Zitting niet gevonden.</p>`; return; }
  setTitle(`${p.municipality_name}, ${dateNL(p.date)}`);
  const names = {}; p.speakers.forEach(s => { names[s.speaker] = s.label || "Andere spreker"; });
  const label = spk => spk == null ? "?" : (names[spk] || "Andere spreker");
  const items = p.agenda.filter(a => a.public !== false).map(a => {
    const placed = a.start != null;
    const sm = a.summary;
    const outcome = sm ? sm.outcome : (a.votes && a.votes.gevolg ? a.votes.gevolg.toLowerCase() : null);
    const badge = outcome ? `<span class="badge ${outcome === "aangenomen" ? "ok" : outcome === "verworpen" ? "no" : ""}">${esc(outcome)}</span>` : "";
    const votes = a.votes ? `<div class="votes">Stemming: ${a.votes.voor} voor, ${a.votes.tegen} tegen, ${plural(a.votes.onthouding, "onthouding", "onthoudingen")}</div>` : "";
    const lines = placed ? p.transcript.filter(t => t[1] >= a.start && t[0] <= a.end).map(t => `<p><a class="t" href="${ytAt(p.url, t[0])}" rel="noopener" title="Bekijk in de video">${fmt(t[0])}</a><span class="who">${esc(label(t[3]))}</span>${esc(t[2])}</p>`).join("") : "";
    const body = `<div class="body">
        ${sm ? `<p>${esc(sm.nl)}</p>` : placed ? `<p class="muted small">Geen samenvatting voor dit punt.</p>` : ""}
        ${sm && sm.raised_by ? `<p class="small">Ingediend of gevraagd door ${esc(sm.raised_by)}.</p>` : ""}
        ${sm && sm.topic ? `<span class="badge">${esc(TOPIC_LABEL(sm.topic))}</span>` : ""} ${votes}
        ${sm && sm.quote ? `<div class="quote">“${esc(sm.quote)}” ${sm.quote_start != null ? `<a class="small" href="${ytAt(p.url, sm.quote_start)}" rel="noopener">bekijk (${fmt(sm.quote_start)})</a>` : ""}</div>` : ""}
        ${placed ? `<p class="small"><a class="btn" href="${ytAt(p.url, a.start)}" rel="noopener">Bekijk in de video vanaf ${fmt(a.start)}</a></p><div class="transcript">${lines}</div>`
          : a.doubtful ? `<p class="muted small">Dit punt is niet met zekerheid in de opname teruggevonden (het transcript op de gevonden plek gaat over iets anders), daarom staat hier geen samenvatting.</p>`
          : `<p class="muted small">Dit punt is niet in de opname teruggevonden.</p>`}
        ${a.source_url ? `<p class="small"><a href="${esc(a.source_url)}" rel="noopener">Officieel dossier</a></p>` : ""}
      </div>`;
    return `<details class="item"><summary><span class="num">${a.position ?? ""}</span><span>${esc(a.title)}${badge}</span><span class="time">${placed ? `${fmt(a.start)} tot ${fmt(a.end)}` : "niet gevonden"}</span></summary>${body}</details>`;
  }).join("");
  const tot = p.speakers.reduce((a, s) => a + s.seconds, 0) || 1;
  const shown = p.speakers.filter(s => s.label).slice(0, 14);
  const restSec = tot - shown.reduce((a, s) => a + s.seconds, 0);
  const restN = p.speakers.length - shown.length;
  const slices = shown.map((s, i) => ({text: s.label + (s.party ? ` (${s.party})` : ""), sec: s.seconds, color: colorFor(s, i)}));
  if (restSec > 0) slices.push({text: `andere sprekers (${restN})`, sec: restSec, color: "#d5d9df"});
  const bar = `<div class="bar">${slices.map(x => `<span style="width:${(100 * x.sec / tot).toFixed(1)}%;background:${x.color}" title="${esc(x.text)}: ${fmt(x.sec)}"></span>`).join("")}</div>
    <div class="legend">${slices.map(x => `<span><i style="background:${x.color}"></i>${esc(x.text)} ${fmt(x.sec)}</span>`).join("")}</div>`;
  const decided = p.notes.decided && p.notes.decided.length ? `<h2>Beslist</h2><ul>${p.notes.decided.map(d => `<li>${esc(d)}</li>`).join("")}</ul>` : "";
  app.innerHTML = `<p class="small sans"><a href="#/g/${p.municipality}">${esc(p.municipality_name)}</a></p>
    <h1>Gemeenteraad ${esc(p.municipality_name)}, ${dateNL(p.date)}</h1>
    <p class="lead">${fmt(p.duration_s)} opname, ${p.agenda.filter(a => a.start != null).length} agendapunten op de tijdlijn. <a href="${esc(p.url)}" rel="noopener">Video van de gemeente</a>${p.lblod_zitting ? ` · <a href="${esc(p.lblod_zitting)}" rel="noopener">Officiële zitting</a>` : ""}</p>
    ${decided}
    <h2>Wie sprak hoe lang</h2><p class="small muted">${Math.round(100 * p.attributed_share)}% van de spreektijd is aan een naam toegewezen; een naam komt er alleen als de voorzitter het woord uitdrukkelijk bij naam geeft (<a href="#/methode">methode</a>). Onbenoemde sprekers heten Spreker 1, 2, ... in volgorde van spreektijd; korte fragmenten staan samen onder "andere sprekers". Sprekerherkenning kan twee stemmen samennemen: de video is de bron.</p>${bar}
    <h2>Agenda</h2>${items}`;
}

async function viewSearch(q) {
  setTitle("Zoeken");
  app.innerHTML = `<h1>Zoeken</h1><form class="search" onsubmit="location.hash='#/zoek?q='+encodeURIComponent(this.q.value);return false;"><input name="q" value="${esc(q)}" placeholder="Zoekterm" aria-label="Zoeken" autofocus><button>Zoek</button></form><div id="res"><p class="muted">Index laden...</p></div>`;
  const res = document.getElementById("res");
  let ms;
  try { ms = await loadSearch(); } catch (e) {
    res.innerHTML = `<p class="muted">De zoekindex kon niet geladen worden. Herlaad de pagina; blijft het misgaan, mail dan <a href="mailto:${CONTACT}">${CONTACT}</a>.</p>`;
    return;
  }
  if (!q) { res.innerHTML = `<p class="muted">Zoek in alle agendapunten en transcripten. Resultaten linken naar de seconde in de video.</p>`; return; }
  const all = ms.search(q), hits = all.slice(0, 60);
  const idx = await loadIndex();
  const urlOf = sid => (idx.sessions.find(s => s.id === sid) || {}).url || "";
  const rx = new RegExp("(" + q.split(/\s+/).filter(Boolean).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "ig");
  const snippet = t => { const i = t.search(rx); const s = Math.max(0, i - 90); return esc(t.slice(s, s + 260)).replace(rx, "<mark>$1</mark>"); };
  res.innerHTML = hits.length ? `<p class="small muted">${all.length > hits.length ? `${all.length} treffers, de eerste ${hits.length} hieronder` : plural(hits.length, "treffer", "treffers")}</p><ul class="list">` + hits.map(h => `<li class="hit"><a href="#/s/${h.session}"><strong>${esc(h.municipality)}</strong>, ${dateNL(h.date)}</a>
      <span class="badge">${h.type === "item" ? "agendapunt" : "transcript"}</span> <a class="small" href="${ytAt(urlOf(h.session), h.start)}" rel="noopener">video ${fmt(h.start)}</a>
      ${h.title ? `<div><strong>${esc(h.title)}</strong></div>` : ""}<div class="small">${snippet(h.text)}</div></li>`).join("") + "</ul>" : `<p class="muted">Niets gevonden.</p>`;
}

async function viewMethod() {
  await loadIndex(); const st = state.stats;
  setTitle("Methode");
  app.innerHTML = `<h1>Methode</h1>
    <p class="lead">Alles op deze site is automatisch gemaakt uit de openbare opnames van de gemeenten. Dit is hoe, en waar het kan misgaan.</p>
    <p>Dit is een onafhankelijk project van één persoon, niet van of voor een gemeente. De officiële bron blijft de opname en de notulen van de gemeente. Er worden alleen openbare zittingen verwerkt die de gemeente zelf online zette.</p>
    <h2>Bronnen</h2><ul><li>Video: het YouTube-kanaal van de gemeente. Het geluid wordt alleen lokaal verwerkt en niet herverdeeld; elke passage linkt naar de video.</li>
    <li>Agenda en stemuitslagen: de open data van <a href="https://lokaalbeslist.vlaanderen.be" rel="noopener">Lokaal Beslist</a> (Vlaamse overheid), voor de gemeenten die daar ingelezen worden. Voor de andere gemeenten worden de agendapunten uit de opname zelf gelezen; die titels kunnen dus spraakherkenningsfouten bevatten.</li>
    <li>Raadsleden: de Vlaamse Mandatendatabank, met de raadsleden die op de datum van de zitting zetelden.</li></ul>
    <h2>Stappen</h2><ol><li>Transcriptie met faster-whisper large-v3-turbo (Nederlands, stiltedetectie, woordtijden). Herhalingen en ondertitelcredits die het model soms verzint worden weggefilterd. Het transcript is woordelijk en automatisch: het bevat fouten en ook wat er in de zaal over anderen gezegd wordt.</li>
    <li>Sprekerherkenning met sherpa-onnx (pyannote segmentation 3.0 en 3D-Speaker ERes2Net): wie spreekt wanneer, zonder namen. Soms worden twee stemmen samengenomen.</li>
    <li>Namen: een raadslid krijgt pas een naam als de voorzitter het woord uitdrukkelijk bij naam geeft of iemand bij naam bedankt ("ik geef het woord aan ..."), of als het raadslid zich voorstelt, en een tweede aanwijzing dat bevestigt. Een losse naam ("Patricia."), voorzitterschap of een naam in de agendatitel alleen is niet genoeg. De namen zijn niet op het gehoor gecontroleerd. Het percentage toegewezen spreektijd staat bij elke zitting; de rest blijft onbenoemd.</li>
    <li>Plaatsing van de agendapunten: Gemini leest het transcript en zegt waar elk punt aangekondigd wordt; die momenten zijn ankers. De overige punten worden met een meertalig zinsmodel op vensters van 45 seconden transcript gelegd, in de volgorde van de agenda. Op 44 met de hand aangeduide starts in drie zittingen wordt 89 tot 100% binnen een minuut gevonden, met een mediane fout onder een seconde.</li>
    <li>Samenvattingen door Gemini 2.5 Flash Lite, per punt en per zitting. Een citaat wordt alleen getoond als het letterlijk in het transcript staat, en het tijdstip komt uit het transcript. Het model zegt per punt of het transcript op die plek echt over dat punt gaat; zo niet, dan blijft de samenvatting weg. Een tweede controle haalt elke naam van iemand die geen raadslid is uit de samenvattingen. Bij een stemming volgt het label (aangenomen, verworpen) de officiële stemuitslag.</li></ol>
    <h2>Cijfers</h2><p>${st.hours_total} uur opname, ${st.items_total} agendapunten op de tijdlijn, ${Math.round(100 * st.questions_share)}% van de geplaatste tijd gaat naar vragen, voorstellen en interpellaties van raadsleden.</p>
    <h2>Omstreden stemmingen</h2>${st.contested.length ? `<div class="scroll"><table><tr><th>Datum</th><th>Gemeente</th><th>Punt</th><th>Voor</th><th>Tegen</th><th>Onth.</th></tr>${st.contested.slice(0, 15).map(c => `<tr><td>${dateNL(c.date)}</td><td>${esc(c.municipality)}</td><td><a href="#/s/${c.session}">${esc(c.title)}</a></td><td>${c.votes.voor}</td><td>${c.votes.tegen}</td><td>${c.votes.onthouding}</td></tr>`).join("")}</table></div>` : "<p class='muted'>Nog geen.</p>"}
    <h2>Fouten, privacy en verwijdering</h2><p>Spraakherkenning maakt fouten, zeker bij tussentaal, slechte microfoons en door elkaar praten. De samenvattingen zijn met AI gemaakt en zo gelabeld. De video is altijd de bron.</p>
    <p>Wie iets ziet dat niet klopt of niet hoort, bijvoorbeeld een naam of een persoonlijk detail in een transcript, mailt naar <a href="mailto:${CONTACT}">${CONTACT}</a>. Verwijderverzoeken worden binnen 48 uur verwerkt.</p>
    <h2 lang="en">About this site</h2><p lang="en">This site turns the public council recordings of three Flemish municipalities into one page per agenda item, in Dutch, the language of the meetings. Each recording is transcribed with speech recognition, split into speakers, matched to the official agenda from the Flemish open data, and summarized by a language model. Every quote is checked against the transcript, every vote comes from the official counts, and every passage links to the second in the municipality's own video. The code, the method and the evaluation numbers are on <a href="https://github.com/KaanGoker/raadzaal" rel="noopener">GitHub</a>, in English. It is an independent project by one person, not of or for any municipality.</p>`;
}

addEventListener("hashchange", route);
route();
