/* Wat zei de raad?  A static reader for the JSON in data/. No build step. Dutch and English. */
const PARTY_COLORS = {"N-VA": "#f2c500", "CD&V": "#ff8000", "Vooruit": "#e30613", "Open Vld": "#0047ab", "Groen": "#5aa02c",
  "Vlaams Belang": "#3b3b3b", "PVDA": "#a50021", "Team 3150": "#365ea8", "Groen-CD&V": "#2e9e6a", "Voor Tervuren": "#5da9e9",
  "Groen+Vooruit": "#8bbf3f", "Tervuren Unie + Volt": "#6c3c96"};
const GREY = ["#9a968e", "#7e7a73", "#b4b0a8", "#68655f", "#c8c4bc", "#55524d"];
const state = {index: null, stats: null, sessions: {}, search: null, docs: null, en: null};
const CONTACT = "nadirkaangoker@gmail.com";
const REPO = "https://github.com/KaanGoker/raadzaal";
const HOME = "https://kaangoker.dev/";
const app = document.getElementById("app");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmt = s => { s = Math.max(0, Math.round(s || 0)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60; return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`; };
const hours = s => { const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60); return h ? `${h} ${LANG === "en" ? "h" : "u"} ${String(m).padStart(2, "0")}` : `${m} min`; };
const ytAt = (url, s) => `${url}&t=${Math.max(0, Math.floor(s || 0))}s`;
const colorFor = (spk, i) => spk.party && PARTY_COLORS[spk.party] ? PARTY_COLORS[spk.party] : (spk.name ? "#3d3b38" : GREY[i % GREY.length]);
const cap = t => t.charAt(0).toUpperCase() + t.slice(1);

/* Language: ?lang= in the address, then the last choice, then Dutch. */
const LANGS = ["nl", "en"];
const store = {get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }};
let LANG = (() => {
  const q = new URLSearchParams(location.search).get("lang");
  if (LANGS.includes(q)) return q;
  const s = store.get("lang");
  if (LANGS.includes(s)) return s;
  return "nl";
})();
const EN = () => LANG === "en";
const tr = t => (EN() && state.en && t && state.en[t]) || t;  // Dutch data line -> English, when a translation exists

const MONTHS = {nl: ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"],
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]};
const date = d => { const [y, m, dd] = d.split("-"); return `${+dd} ${MONTHS[LANG][+m - 1]} ${y}`; };
const TOPICS_EN = {"mobiliteit": "mobility", "ruimtelijke ordening": "spatial planning", "financiën": "finance", "wonen": "housing",
  "milieu en klimaat": "environment and climate", "onderwijs en jeugd": "education and youth", "welzijn en zorg": "welfare and care",
  "cultuur en sport": "culture and sport", "veiligheid": "safety", "economie en handel": "economy and trade",
  "personeel en organisatie": "staff and organization", "participatie en bestuur": "participation and governance",
  "nutsvoorzieningen en afval": "utilities and waste", "andere": "other"};
const OUTCOMES_EN = {"aangenomen": "adopted", "verworpen": "rejected", "kennisname": "noted", "uitgesteld": "postponed", "onbekend": "unknown"};
const topic = t => cap(EN() ? TOPICS_EN[t] || t : t);
const outcomeText = o => EN() ? OUTCOMES_EN[o] || o : o;
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

const T = {
  nl: {
    nav_search: "Zoeken", nav_method: "Methode", nav_code: "Code", switch: "EN", switch_title: "English",
    foot_h: "Disclaimer",
    foot: ["Dit is een demoproject: onafhankelijk en niet-commercieel.",
      "Alles is automatisch gemaakt door AI en niet nagekeken. Er staan fouten in.",
      "Dit is geen officieel verslag. De video en de notulen van de gemeente zijn de bron.",
      "Controleer een citaat of samenvatting in de video voor u het overneemt.",
      "Alleen raadsleden en het college krijgen een naam, nooit burgers of gemeentepersoneel.",
      `Een fout gezien of wilt u iets laten verwijderen? Mail <a href="mailto:${CONTACT}">${CONTACT}</a>. Ik pas het aan of haal het weg.`],
    foot_links: `<a href="#/methode">Methode</a> · <a href="${REPO}" rel="noopener">Code</a> · Een project van <a href="${HOME}">Kaan Goker</a>`,
    pillars: [["Gezegd", "Het volledige transcript van elke zitting."], ["Beslist", "Per agendapunt een samenvatting en de stemming."], ["Bekeken", "Elke regel springt naar dat moment in de video."]],
    notice: "Demoproject. Automatisch gemaakt door AI en niet nagekeken. De video van de gemeente is de bron.",
    all: "Alle", minutes_total: m => `${m} minuten in totaal`,
    search_ph: "Bv. fietspad of zwembad", search_btn: "Zoek",
    municipalities: "Gemeenten", sessions: n => plural(n, "zitting", "zittingen"), hours_n: h => `${String(h).replace(".", ",")} uur`,
    sessions_w: n => n === 1 ? "zitting" : "zittingen", hours_w: "uur", num: h => String(h).replace(".", ","),
    items: n => plural(n, "punt", "punten"),
    time_h: "Tijd per onderwerp", no_summaries: "Nog geen samenvattingen.",
    muni_no_agenda: "Geen officiële agenda: de punten komen uit de opname.",
    not_found_session: "Deze zitting bestaat niet (meer).",
    other_speaker: "Andere spreker", speaker: n => `Spreker ${n}`, other_speakers: "anderen",
    votes: v => `${v.voor} voor, ${v.tegen} tegen, ${v.onthouding} onthouding${v.onthouding === 1 ? "" : "en"}`,
    raised_by: w => `Van ${w}.`, watch: "Bekijk", transcript: "Transcript",
    doubtful: "Niet met zekerheid teruggevonden in de opname.", not_found_item: "Niet teruggevonden in de opname.",
    dossier: "Dossier", not_found_short: "niet gevonden",
    decided: "Beslist", council: (m, d) => `Gemeenteraad ${m}`, video: "Video", official: "Officiële zitting",
    who_h: "Spreektijd", who_note: s => `${s}% heeft een naam (<a href="#/methode">waarom zo weinig</a>).`,
    agenda: "Agenda",
    search_h: "Zoeken", index_loading: "Laden...",
    index_failed: `De zoekindex laadt niet. Herlaad de pagina.`,
    hits: (all, shown) => all > shown ? `${all} resultaten, eerste ${shown}` : plural(shown, "resultaat", "resultaten"),
    type_transcript: "transcript", nothing: "Geen resultaten.",
    method_t: "Methode", contested_none: "Nog geen.", th: ["Datum", "Gemeente", "Punt", "Voor", "Tegen", "Onth."],
  },
  en: {
    nav_search: "Search", nav_method: "Method", nav_code: "Code", switch: "NL", switch_title: "Nederlands",
    foot_h: "Disclaimer",
    foot: ["This is a demo project: independent and non-commercial.",
      "Everything is made automatically by AI and not checked. It contains errors.",
      "This is not an official record. The municipality's video and minutes are the source.",
      "Check a quote or summary against the video before you repeat it.",
      "Only council members and the college are named, never citizens or municipal staff.",
      `Seen a mistake, or want something removed? Mail <a href="mailto:${CONTACT}">${CONTACT}</a>. I will fix it or take it down.`],
    foot_links: `<a href="#/methode">Method</a> · <a href="${REPO}" rel="noopener">Code</a> · A project by <a href="${HOME}">Kaan Goker</a>`,
    pillars: [["Said", "The full transcript of every meeting."], ["Decided", "A summary and the vote for each agenda item."], ["Watched", "Every line jumps to that moment in the video."]],
    notice: "Demo project. Made automatically by AI and not checked. The municipality's video is the source.",
    all: "All", minutes_total: m => `${m} minutes in total`,
    search_ph: "E.g. bike path or swimming pool", search_btn: "Search",
    municipalities: "Municipalities", sessions: n => plural(n, "meeting", "meetings"), hours_n: h => `${h} hours`,
    sessions_w: n => n === 1 ? "meeting" : "meetings", hours_w: "hours", num: h => String(h),
    items: n => plural(n, "item", "items"),
    time_h: "Time per topic", no_summaries: "No summaries yet.",
    muni_no_agenda: "No official agenda: the items come from the recording.",
    not_found_session: "This meeting does not exist (anymore).",
    other_speaker: "Other speaker", speaker: n => `Speaker ${n}`, other_speakers: "others",
    votes: v => `${v.voor} for, ${v.tegen} against, ${plural(v.onthouding, "abstention", "abstentions")}`,
    raised_by: w => `From ${w}.`, watch: "Watch", transcript: "Transcript (Dutch)",
    doubtful: "Not found in the recording with certainty.", not_found_item: "Not found in the recording.",
    dossier: "File", not_found_short: "not found",
    decided: "Decided", council: (m, d) => `${m} council`, video: "Video", official: "Official record",
    who_h: "Speaking time", who_note: s => `${s}% has a name (<a href="#/methode">why so little</a>).`,
    agenda: "Agenda", official_title: "Dutch", translation: "translated",
    search_h: "Search", index_loading: "Loading...",
    index_failed: `The search index did not load. Reload the page.`,
    hits: (all, shown) => all > shown ? `${all} results, first ${shown}` : plural(shown, "result", "results"),
    type_transcript: "transcript", nothing: "No results.",
    method_t: "Method", contested_none: "None yet.", th: ["Date", "Municipality", "Item", "For", "Against", "Abst."],
  },
};
const t = k => T[LANG][k];

async function getJSON(path) { const r = await fetch(path, {cache: "no-cache"}); if (!r.ok) throw new Error(path); return r.json(); }
async function loadEN() { if (EN() && !state.en) { try { state.en = await getJSON("data/en.json"); } catch (e) { state.en = {}; } } }
async function loadIndex() {
  if (!state.index) { [state.index, state.stats] = await Promise.all([getJSON("data/index.json"), getJSON("data/stats.json")]); }
  await loadEN();
  return state.index;
}
async function loadSession(id) { if (!state.sessions[id]) state.sessions[id] = await getJSON(`data/sessions/${id}.json`); return state.sessions[id]; }
async function loadSearch() {
  if (state.search) return state.search;
  if (typeof MiniSearch === "undefined") throw new Error("vendor/minisearch-7.1.0.js did not load");
  await loadEN();
  state.docs = await getJSON("data/search.json");
  // an item's text is its title, a space and its summary; the English of both is searchable next to the Dutch
  const en = d => { if (!state.en || d.type !== "item") return ""; const rest = d.text.startsWith(d.title) ? d.text.slice(d.title.length).trim() : ""; return `${tr(d.title)} ${tr(rest)}`; };
  const ms = new MiniSearch({fields: ["title", "text", "en"], storeFields: ["type", "session", "municipality", "date", "title", "text", "start"],
    extractField: (d, f) => f === "en" ? en(d) : d[f],
    searchOptions: {prefix: true, fuzzy: 0.15, boost: {title: 2}}});
  ms.addAll(state.docs);
  state.search = ms;
  return ms;
}

const SITE = "Wat zei de raad?";
const setTitle = s => { document.title = s ? `${s} | ${SITE}` : SITE; };
const decode = s => { try { return decodeURIComponent(s); } catch (e) { return s; } };
const ICON_SEARCH = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`;
const searchForm = (q = "", autofocus = false) => `<form class="search" role="search" onsubmit="location.hash='#/zoek?q='+encodeURIComponent(this.q.value);return false;"><label>${ICON_SEARCH}<input name="q" type="search" value="${esc(q)}" placeholder="${esc(t("search_ph"))}" aria-label="${t("search_h")}"${autofocus ? " autofocus" : ""}></label><button>${t("search_btn")}</button></form>`;

function chrome() {
  document.documentElement.lang = LANG;
  document.getElementById("nav").innerHTML = `<a href="#/zoek">${t("nav_search")}</a><a href="#/methode">${t("nav_method")}</a><a href="${REPO}" rel="noopener">${t("nav_code")}</a><a href="${HOME}">Kaan Goker</a>`
    + `<a href="?lang=${EN() ? "nl" : "en"}${esc(location.hash)}" class="lang" lang="${EN() ? "nl" : "en"}" title="${esc(t("switch_title"))}" onclick="return switchLang()">${t("switch")}</a>`;
  document.getElementById("foot").innerHTML = `<h2>${t("foot_h")}</h2><ul>${t("foot").map(x => `<li>${x}</li>`).join("")}</ul><p class="links">${t("foot_links")}</p>`;
}

function switchLang() {
  LANG = EN() ? "nl" : "en";
  store.set("lang", LANG);
  history.replaceState(null, "", `?lang=${LANG}${location.hash}`);
  state.search = null;  // the index holds the English of the other language
  chrome();
  route();
  return false;
}

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

const sessionRow = (s, withName) => `<li><span class="main"><a href="#/s/${s.id}">${withName ? `${esc(s.municipality_name)}, ` : ""}${date(s.date)}</a></span>
      <span class="side">${t("items")(s.items)} · ${hours(s.duration_s)}</span>
      ${s.decided && s.decided.length ? `<span class="note">${esc(tr(s.decided[0]))}</span>` : ""}</li>`;

async function viewHome() {
  const idx = await loadIndex(), st = state.stats;
  const munis = idx.municipalities.map(m => `<li><a href="#/g/${m.slug}"><span><span class="name">${esc(m.name)}</span><span class="prov">${esc(m.province || "")}</span></span>
      <span class="nums"><span><b>${m.sessions}</b>${t("sessions_w")(m.sessions)}</span><span><b>${t("num")(m.hours)}</b>${t("hours_w")}</span></span></a></li>`).join("");
  app.innerHTML = `<section class="hero"><h1>Wat zei de raad?</h1>${EN() ? `<p class="sub">What did the council say?</p>` : `<p class="sub">Vlaamse gemeenteraden, uitgeschreven en doorzoekbaar.</p>`}
    <ul class="pillars">${t("pillars").map(([h, x]) => `<li><b>${h}</b><span>${x}</span></li>`).join("")}</ul>
    ${searchForm()}</section>
    <h2>${t("municipalities")}</h2><ul class="cards">${munis}</ul>
    <h2>${t("time_h")}</h2><div class="panel" id="topics"></div>`;
  topicPanel(idx, st, state.topicMuni || "");
}

function topicPanel(idx, st, slug) {
  const by = st.topic_minutes_by_municipality;
  if (!by || !by[slug]) slug = "";
  state.topicMuni = slug;
  const data = slug ? by[slug] : st.topic_minutes;
  const total = Object.values(data || {}).reduce((x, v) => x + v, 0);
  const chips = by ? `<div class="chips" role="group" aria-label="${esc(t("municipalities"))}">${[["", t("all")], ...idx.municipalities.map(m => [m.slug, m.name])].map(([k, n]) =>
      `<button type="button" aria-pressed="${k === slug}" onclick="topicPanel(state.index, state.stats, '${k}')">${esc(n)}</button>`).join("")}</div>` : "";
  document.getElementById("topics").innerHTML = chips + topicBars(data) + (total ? `<p class="meta">${t("minutes_total")(total)}</p>` : "");
}

function topicBars(topics) {
  const entries = Object.entries(topics || {}).filter(e => e[1] > 0).sort((x, y) => y[1] - x[1]);
  if (!entries.length) return `<p class="muted">${t("no_summaries")}</p>`;
  const max = Math.max(...entries.map(e => e[1])) || 1;
  return `<div class="topics">${entries.map(([k, v]) => `<span class="label">${esc(topic(k))}</span>
      <span class="track"><span class="fill" style="width:${(100 * v / max).toFixed(1)}%"></span></span><span class="v">${v} min</span>`).join("")}</div>`;
}

async function viewMunicipality(slug) {
  const idx = await loadIndex();
  const m = idx.municipalities.find(x => x.slug === slug);
  if (!m) return viewHome();
  setTitle(m.name);
  const sessions = idx.sessions.filter(s => s.municipality === slug).map(s => sessionRow(s, false)).join("");
  app.innerHTML = `<h1>${esc(m.name)}</h1><p class="meta">${t("sessions")(m.sessions)} · ${t("hours_n")(m.hours)}</p>
    ${m.has_agenda ? "" : `<p class="muted">${t("muni_no_agenda")}</p>`}
    <ul class="rows">${sessions}</ul>`;
}

async function viewSession(id) {
  await loadIndex();
  let p; try { p = await loadSession(id); } catch (e) { app.innerHTML = `<p>${t("not_found_session")}</p>`; return; }
  setTitle(`${p.municipality_name}, ${date(p.date)}`);
  const spkName = l => { const m = /^Spreker (\d+)$/.exec(l || ""); return m ? t("speaker")(m[1]) : l; };
  const names = {}; p.speakers.forEach(s => { names[s.speaker] = spkName(s.label) || t("other_speaker"); });
  const label = spk => spk == null ? "?" : (names[spk] || t("other_speaker"));
  const items = p.agenda.filter(a => a.public !== false).map(a => {
    const placed = a.start != null;
    const sm = a.summary;
    const outcome = sm ? sm.outcome : (a.votes && a.votes.gevolg ? a.votes.gevolg.toLowerCase() : null);
    const out = outcome && outcome !== "onbekend" ? `<span class="out ${outcome === "aangenomen" ? "ok" : outcome === "verworpen" ? "no" : ""}">${esc(outcomeText(outcome))}</span>` : "";
    const lines = placed ? p.transcript.filter(x => x[1] >= a.start && x[0] <= a.end).map(x => `<p><a class="t" href="${ytAt(p.url, x[0])}" rel="noopener">${fmt(x[0])}</a><span class="who">${esc(label(x[3]))}</span>${esc(x[2])}</p>`).join("") : "";
    const quoteEn = sm && sm.quote && EN() && tr(sm.quote) !== sm.quote ? `<br><span class="small muted">${esc(tr(sm.quote))} (${t("translation")})</span>` : "";
    const facts = [sm && sm.topic ? esc(topic(sm.topic)) : "", a.votes ? t("votes")(a.votes) : "", sm && sm.raised_by ? t("raised_by")(esc(sm.raised_by)) : "",
      a.source_url ? `<a href="${esc(a.source_url)}" rel="noopener">${t("dossier")}</a>` : ""].filter(Boolean).join(" · ");
    const body = `<div class="body">
        ${sm ? `<p>${esc(tr(sm.nl))}</p>` : ""}
        ${!placed ? `<p class="muted">${a.doubtful ? t("doubtful") : t("not_found_item")}</p>` : ""}
        ${sm && sm.quote ? `<div class="quote"><span lang="nl">“${esc(sm.quote)}”</span>${quoteEn}</div>` : ""}
        ${facts ? `<p class="meta">${facts}</p>` : ""}
        ${EN() && tr(a.title) !== a.title ? `<p class="meta">${t("official_title")}: <span lang="nl">${esc(a.title)}</span></p>` : ""}
        ${placed ? `<p><a class="play" href="${ytAt(p.url, a.start)}" rel="noopener">${t("watch")} ${fmt(a.start)}</a></p>
          <details class="transcript"><summary>${t("transcript")}</summary><div class="lines" lang="nl">${lines}</div></details>` : ""}
      </div>`;
    return `<details class="item"><summary><span class="num">${a.position ?? ""}</span><span class="title">${esc(tr(a.title))}${out}</span><span class="time">${placed ? fmt(a.start) : t("not_found_short")}</span></summary>${body}</details>`;
  }).join("");
  const tot = p.speakers.reduce((x, s) => x + s.seconds, 0) || 1;
  const shown = p.speakers.filter(s => s.label).slice(0, 8);
  const restSec = tot - shown.reduce((x, s) => x + s.seconds, 0);
  const slices = shown.map((s, i) => ({text: spkName(s.label) + (s.party ? ` (${s.party})` : ""), sec: s.seconds, color: colorFor(s, i)}));
  if (restSec > 0) slices.push({text: t("other_speakers"), sec: restSec, color: "#dedad2"});
  const bar = `<div class="bar">${slices.map(x => `<span style="width:${(100 * x.sec / tot).toFixed(1)}%;background:${x.color}" title="${esc(x.text)}: ${fmt(x.sec)}"></span>`).join("")}</div>
    <div class="legend">${slices.map(x => `<span><i style="background:${x.color}"></i>${esc(x.text)} ${fmt(x.sec)}</span>`).join("")}</div>`;
  const decided = p.notes.decided && p.notes.decided.length ? `<h2>${t("decided")}</h2><ul class="decided">${p.notes.decided.map(d => `<li>${esc(tr(d))}</li>`).join("")}</ul>` : "";
  app.innerHTML = `<h1>${esc(t("council")(p.municipality_name))}<br><span class="muted">${date(p.date)}</span></h1>
    <p class="meta"><a href="#/g/${p.municipality}">${esc(p.municipality_name)}</a> · ${hours(p.duration_s)} · <a href="${esc(p.url)}" rel="noopener">${t("video")}</a>${p.lblod_zitting ? ` · <a href="${esc(p.lblod_zitting)}" rel="noopener">${t("official")}</a>` : ""}</p>
    <p class="notice">${t("notice")}</p>
    ${decided}
    <h2>${t("agenda")}</h2><div class="agenda">${items}</div>
    <h2>${t("who_h")}</h2>${bar}<p class="meta">${t("who_note")(Math.round(100 * p.attributed_share))}</p>`;
}

async function viewSearch(q) {
  setTitle(t("search_h"));
  app.innerHTML = `<h1>${t("search_h")}</h1>${searchForm(q, true)}<div id="res"></div>`;
  const res = document.getElementById("res");
  if (!q) return;
  res.innerHTML = `<p class="muted">${t("index_loading")}</p>`;
  let ms;
  try { ms = await loadSearch(); } catch (e) { res.innerHTML = `<p class="muted">${t("index_failed")}</p>`; return; }
  const all = ms.search(q), hits = all.slice(0, 60);
  const idx = await loadIndex();
  const urlOf = sid => (idx.sessions.find(s => s.id === sid) || {}).url || "";
  const rx = new RegExp("(" + q.split(/\s+/).filter(Boolean).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "ig");
  const snippet = s => {  // about 240 characters around the first hit, cut at word boundaries
    const i = Math.max(0, s.search(rx)); let from = i > 90 ? s.indexOf(" ", i - 90) + 1 : 0; let to = s.lastIndexOf(" ", from + 240);
    if (to <= i || from + 240 >= s.length) to = s.length;
    return (from ? "... " : "") + esc(s.slice(from, to)).replace(rx, "<mark>$1</mark>") + (to < s.length ? " ..." : ""); };
  // in English an agenda hit shows its English title and summary; a transcript hit stays Dutch
  const textOf = h => { if (!EN() || h.type !== "item") return h.text; const rest = h.text.startsWith(h.title) ? h.text.slice(h.title.length).trim() : ""; return rest ? tr(rest) : tr(h.title); };
  res.innerHTML = hits.length ? `<p class="meta">${t("hits")(all.length, hits.length)}</p><ul class="rows">` + hits.map(h => `<li class="hit"><span class="main">
      ${h.title ? `<a href="#/s/${h.session}"><strong>${esc(tr(h.title))}</strong></a>` : `<a href="#/s/${h.session}">${t("type_transcript")}</a>`}
      <div class="small"${h.type === "item" && EN() ? "" : ' lang="nl"'}>${snippet(textOf(h))}</div></span>
      <span class="side">${esc(h.municipality)}, ${date(h.date)} · <a href="${ytAt(urlOf(h.session), h.start)}" rel="noopener">${fmt(h.start)}</a></span></li>`).join("") + "</ul>" : `<p class="muted">${t("nothing")}</p>`;
}

function contestedTable(st) {
  if (!st.contested.length) return `<p class="muted">${t("contested_none")}</p>`;
  const th = t("th");
  return `<div class="scroll"><table><tr><th>${th[0]}</th><th>${th[1]}</th><th>${th[2]}</th><th class="n">${th[3]}</th><th class="n">${th[4]}</th><th class="n">${th[5]}</th></tr>${st.contested.slice(0, 10).map(c => `<tr><td>${date(c.date)}</td><td>${esc(c.municipality)}</td><td><a href="#/s/${c.session}">${esc(tr(c.title))}</a></td><td class="n">${c.votes.voor}</td><td class="n">${c.votes.tegen}</td><td class="n">${c.votes.onthouding}</td></tr>`).join("")}</table></div>`;
}

const METHOD = {
  nl: st => `<h1>Methode</h1>
    <p class="lead">Alles hier is automatisch gemaakt uit de openbare opnames van de gemeenten. De video en de notulen van de gemeente blijven de bron.</p>
    <section class="limits"><h2>Grenzen van deze site</h2><ul>
    <li>Dit is een demoproject. Het toont wat automatische verwerking met openbare raadsopnames kan, niet een afgewerkte dienst.</li>
    <li>Alles op deze site is automatisch gemaakt. Software en AI-modellen doen de spraakherkenning, de sprekerherkenning, de koppeling aan de agendapunten, de samenvattingen en de vertaling (onder meer Gemini van Google).</li>
    <li>Niemand heeft de opnames herbeluisterd. Niemand heeft de samenvattingen, citaten, stemmingen of namen manueel nagekeken. Ik deed alleen enkele steekproeven.</li>
    <li>De transcripties zijn woordelijk en automatisch. Er staan herkenningsfouten en verkeerd verstane namen in, en ook wat in de zaal over anderen gezegd werd.</li>
    <li>Een samenvatting of citaat kan iemand verkeerd voorstellen. Wilt u iets overnemen of doorvertellen? Controleer het dan eerst in de video van de gemeente.</li>
    <li>Ik noem alleen gemeenteraadsleden en het college (burgemeester en schepenen), als publieke mandatarissen in een openbare zitting. Burgers en gemeentepersoneel krijgen nooit een naam.</li>
    <li>Dit is een onafhankelijk, niet-commercieel project en geen officieel verslag. De officiële bronnen zijn de video van de gemeente en haar besluitenlijst en notulen. De site is niet verbonden aan de gemeenten, VVSG of Lokaal Beslist.</li>
    <li>Ziet u een fout of iets dat hier niet hoort? Of wilt u als raadslid of gemeente niet op deze site staan? Mail naar <a href="mailto:${CONTACT}">${CONTACT}</a> of open een issue op <a href="${REPO}/issues" rel="noopener">GitHub</a>. Dan pas ik het aan of haal ik het weg.</li></ul></section>
    <h2>Bronnen</h2><ul><li>Video: het YouTube-kanaal van de gemeente.</li>
    <li>Agenda en stemmingen: <a href="https://lokaalbeslist.vlaanderen.be" rel="noopener">Lokaal Beslist</a>. Zonder officiële agenda komen de punten uit de opname.</li>
    <li>Raadsleden: de Vlaamse Mandatendatabank.</li></ul>
    <h2>Stappen</h2><ol>
    <li>Transcriptie met faster-whisper large-v3-turbo.</li>
    <li>Sprekersherkenning met sherpa-onnx, zonder namen.</li>
    <li>Een raadslid krijgt pas een naam als de voorzitter hem of haar bij naam het woord geeft, en een tweede aanwijzing dat bevestigt. Daarom heeft maar een klein deel van de spreektijd een naam.</li>
    <li>Gemini en een zinsmodel plaatsen de agendapunten in de opname. Op 44 met de hand aangeduide begintijden zit 89 tot 100% binnen de minuut.</li>
    <li>Gemini vat elk punt samen. Een citaat verschijnt alleen als het letterlijk in het transcript staat. Namen van wie geen raadslid is, worden verwijderd. Het label aangenomen of verworpen volgt de officiële stemming.</li></ol>
    <h2>Cijfers</h2><p>${String(st.hours_total).replace(".", ",")} uur opname, ${st.items_total} agendapunten.</p>
    <h2>Verdeelde stemmingen</h2>${contestedTable(st)}
    <p class="meta">Details en evaluatie: <a href="${REPO}" rel="noopener">GitHub</a> (Engels).</p>`,
  en: st => `<h1>Method</h1>
    <p class="lead">Everything here is made automatically from the municipalities' public recordings. The municipality's video and minutes remain the source.</p>
    <section class="limits"><h2>Limits of this site</h2><ul>
    <li>This is a demo project. It shows what automatic processing can do with public council recordings; it is not a finished service.</li>
    <li>Everything on this site is made automatically. Software and AI models do the speech recognition, the speaker diarization, the matching to agenda items, the summaries and the translation (Gemini by Google, among others).</li>
    <li>Nobody listened back to the recordings. Nobody checked the summaries, quotes, votes or names by hand. I only did a few spot checks.</li>
    <li>The transcripts are verbatim and automatic. They contain recognition errors, misheard names, and what people in the room said about others.</li>
    <li>A summary or quote can misrepresent someone. Before you repeat or share anything, check it against the municipality's own video.</li>
    <li>I only name council members and the college (mayor and aldermen), as public office holders in a public meeting. Citizens and municipal staff are never named.</li>
    <li>This is an independent, non-commercial project, not an official record. The official sources are the municipality's video and its official decisions and minutes. The site is not affiliated with the municipalities, VVSG or Lokaal Beslist.</li>
    <li>Did you see an error or something that should not be here? Or do you not want to be on this site, as a councillor or a municipality? Mail <a href="mailto:${CONTACT}">${CONTACT}</a> or open an issue on <a href="${REPO}/issues" rel="noopener">GitHub</a>. I will fix it or take it down.</li></ul></section>
    <h2>Sources</h2><ul><li>Video: the municipality's YouTube channel.</li>
    <li>Agendas and votes: <a href="https://lokaalbeslist.vlaanderen.be" rel="noopener">Lokaal Beslist</a>. Without an official agenda, the items come from the recording.</li>
    <li>Councillors: the Flemish Mandatendatabank.</li></ul>
    <h2>Steps</h2><ol>
    <li>Transcription with faster-whisper large-v3-turbo.</li>
    <li>Speaker recognition with sherpa-onnx, without names.</li>
    <li>A councillor only gets a name when the chair gives them the floor by name and a second cue confirms it. That is why only a small share of the speaking time has a name.</li>
    <li>Gemini and a sentence model place the agenda items in the recording. On 44 item starts marked by hand, 89 to 100% are within a minute.</li>
    <li>Gemini summarizes each item. A quote only appears when it is word for word in the transcript. Names of people who are not councillors are removed. The adopted or rejected label follows the official vote.</li>
    <li>Summaries, decisions and titles are translated into English by Gemini. Quotes and transcripts stay in Dutch.</li></ol>
    <h2>Numbers</h2><p>${st.hours_total} hours of recording, ${st.items_total} agenda items.</p>
    <h2>Split votes</h2>${contestedTable(st)}
    <p class="meta">Details and evaluation: <a href="${REPO}" rel="noopener">GitHub</a>.</p>`,
};

async function viewMethod() {
  await loadIndex();
  setTitle(t("method_t"));
  app.innerHTML = `<div class="method">${METHOD[LANG](state.stats)}</div>`;
}

chrome();
addEventListener("hashchange", route);
route();
