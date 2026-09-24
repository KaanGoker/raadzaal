"""The official agenda of a session from the Lokaal Beslist harvester SPARQL endpoints."""
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from raadzaal import config, db

PREFIXES = """
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX besluit: <http://data.vlaanderen.be/ns/besluit#>
PREFIX mandaat: <http://data.vlaanderen.be/ns/mandaat#>
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
_POS = re.compile(r"^\s*[A-Z]?\.?\s*(\d{1,3})\s*[.):]\s*\S")
TZ = ZoneInfo(config.TZ)


def sparql(harvester: int, query: str, retries: int = 3, timeout: int = 90) -> list[dict]:
    url = config.HARVESTER_URL.format(n=harvester)
    last = None
    for attempt in range(retries):
        try:
            r = requests.post(url, data={"query": PREFIXES + query}, timeout=timeout,
                              headers={"Accept": "application/sparql-results+json", "User-Agent": "raadzaal/0.1"})
            if r.status_code == 200:
                return [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        except (requests.RequestException, ValueError) as exc:
            last = str(exc)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"SPARQL failed on harvester {harvester}: {last}")


def _lit(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


def zittingen(m: dict, date_from: str, date_to: str) -> list[dict]:
    """Council sessions of the municipality's Gemeenteraad with a planned start inside the window."""
    q = f"""
SELECT DISTINCT ?z ?start ?location WHERE {{
  ?be a besluit:Bestuurseenheid ; skos:prefLabel {_lit(m['lblod_label'])} .
  ?org besluit:bestuurt ?be ; skos:prefLabel {_lit(m['lblod_org'])} .
  ?orgt mandaat:isTijdspecialisatieVan ?org .
  ?z besluit:isGehoudenDoor ?orgt ; besluit:geplandeStart ?start .
  OPTIONAL {{ ?z <http://www.w3.org/ns/prov#atLocation> ?location }}
  FILTER(?start >= "{date_from}T00:00:00"^^xsd:dateTime && ?start < "{date_to}T00:00:00"^^xsd:dateTime)
}} ORDER BY ?start"""
    return sparql(m["lblod_harvester"], q)


def local_date(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).date().isoformat()


def find_zitting(m: dict, date: str) -> dict | None:
    d = datetime.fromisoformat(date).date()
    rows = zittingen(m, (d - timedelta(days=1)).isoformat(), (d + timedelta(days=2)).isoformat())
    same = [r for r in rows if local_date(r["start"]) == date]
    return same[0] if same else None


def agenda_items(harvester: int, zitting: str) -> list[dict]:
    q = f"""
SELECT ?ap ?title ?public ?source ?beh ?after ?vfor ?vagainst ?vabst ?gevolg WHERE {{
  <{zitting}> besluit:behandelt ?ap .
  OPTIONAL {{ ?ap dct:title ?title }}
  OPTIONAL {{ ?ap besluit:geplandOpenbaar ?public }}
  OPTIONAL {{ ?ap prov:wasDerivedFrom ?source }}
  OPTIONAL {{
    ?beh dct:subject ?ap .
    OPTIONAL {{ ?beh besluit:gebeurtNa ?after }}
    OPTIONAL {{ ?beh besluit:heeftStemming ?st .
      OPTIONAL {{ ?st besluit:aantalVoorstanders ?vfor }}
      OPTIONAL {{ ?st besluit:aantalTegenstanders ?vagainst }}
      OPTIONAL {{ ?st besluit:aantalOnthouders ?vabst }}
      OPTIONAL {{ ?st besluit:gevolg ?gevolg }} }}
  }}
}}"""
    return sparql(harvester, q)


def position_from_title(title: str) -> int | None:
    m = _POS.match(title)
    return int(m.group(1)) if m else None


def order_items(rows: list[dict]) -> list[dict]:
    """One item per agendapunt, ordered by title number, then by the gebeurtNa chain, then by title."""
    items: dict[str, dict] = {}
    after: dict[str, str] = {}
    for r in rows:
        it = items.setdefault(r["ap"], {"lblod_uri": r["ap"], "title": (r.get("title") or "(zonder titel)").strip(),
                                         "public": r.get("public", "true") in ("true", "1"),
                                         "source_url": r.get("source"), "beh": r.get("beh"),
                                         "votes_for": None, "votes_against": None, "abstentions": None, "outcome": None})
        if r.get("vfor") is not None and it["votes_for"] is None:
            it.update(votes_for=int(r["vfor"]), votes_against=int(r.get("vagainst") or 0),
                      abstentions=int(r.get("vabst") or 0), outcome=(r.get("gevolg") or None))
        if r.get("beh") and r.get("after"):
            after[r["beh"]] = r["after"]
    lst = list(items.values())
    for it in lst:
        it["position"] = position_from_title(it["title"])
    if all(it["position"] is not None for it in lst) and lst:
        lst.sort(key=lambda x: x["position"])
        return lst
    # chain order: the behandeling that nothing comes after is first
    by_beh = {it["beh"]: it for it in lst if it.get("beh")}
    if by_beh and len(after) >= len(by_beh) - 1:
        successors = {v: k for k, v in after.items()}  # prev -> next
        heads = [b for b in by_beh if after.get(b) not in by_beh]
        ordered, seen = [], set()
        for h in heads:
            cur = h
            while cur and cur in by_beh and cur not in seen:
                seen.add(cur); ordered.append(by_beh[cur]); cur = successors.get(cur)
        if len(heads) == 1 and len(ordered) == len(lst):
            for i, it in enumerate(ordered, 1):
                it["position"] = i
            return ordered
    lst.sort(key=lambda x: (x["position"] is None, x["position"] or 0, x["title"]))
    for i, it in enumerate(lst, 1):
        it["position"] = it["position"] or i
    return lst


def attach(con, m: dict, session: dict) -> int:
    """Store the agenda of one session. Returns the number of items (0 when no zitting exists)."""
    z = find_zitting(m, session["date"])
    if z is None:
        return 0
    rows = agenda_items(m["lblod_harvester"], z["z"])
    items = order_items(rows)
    con.execute("DELETE FROM agenda_items WHERE session_id=? AND origin='lblod'", (session["id"],))
    for it in items:
        con.execute(
            "INSERT OR IGNORE INTO agenda_items(session_id,position,title,public,lblod_uri,source_url,votes_for,votes_against,abstentions,outcome,origin) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,'lblod')",
            (session["id"], it["position"], it["title"], int(it["public"]), it["lblod_uri"], it["source_url"],
             it["votes_for"], it["votes_against"], it["abstentions"], it["outcome"]))
    con.execute("UPDATE sessions SET lblod_zitting=?, updated_at=? WHERE id=?", (z["z"], db.now(), session["id"]))
    con.commit()
    return len(items)


def run(con, session: dict, args) -> int:
    m = config.municipality(session["municipality"])
    if m.get("lblod_harvester") is None:
        return 0
    rid = db.run_start(con, "agenda", session["id"])
    try:
        n = attach(con, m, session)
        db.run_end(con, rid, True, f"{n} items")
        print(f"{session['municipality']:<10} {session['date']}  {n:>3} agenda items")
    except Exception as exc:
        db.run_end(con, rid, False, str(exc))
        print(f"{session['municipality']:<10} {session['date']}  agenda failed: {exc}")
        return 1
    return 0
