"""Council members, their roles and political groups from the Flemish mandate database (data.lblod.info)."""
from collections import defaultdict
from datetime import date

import requests
import yaml

from raadzaal import config

EP = "https://data.lblod.info/sparql"
GEMEENTE = "http://data.vlaanderen.be/id/concept/BestuurseenheidClassificatieCode/5ab0e9b8a3b2ca7c5e000001"
PREFIXES = """PREFIX skos: <http://www.w3.org/2004/02/skos/core#> PREFIX besluit: <http://data.vlaanderen.be/ns/besluit#>
PREFIX mandaat: <http://data.vlaanderen.be/ns/mandaat#> PREFIX org: <http://www.w3.org/ns/org#>
PREFIX persoon: <http://data.vlaanderen.be/ns/persoon#> PREFIX foaf: <http://xmlns.com/foaf/0.1/> """
PARTY_LABELS = {"cd&v": "CD&V", "vlaams belang": "Vlaams Belang", "groen-cd&v": "Groen-CD&V", "vooruit beernem": "Vooruit",
                "groen beernem": "Groen", "n-va": "N-VA", "pvda": "PVDA", "open vld": "Open Vld", "groen": "Groen", "vooruit": "Vooruit"}
ROLE_ORDER = ["Burgemeester", "Voorzitter van de gemeenteraad", "Schepen", "Toegevoegde schepen", "Gemeenteraadslid"]
ROLE_SHORT = {"Burgemeester": "burgemeester", "Voorzitter van de gemeenteraad": "voorzitter", "Schepen": "schepen",
              "Toegevoegde schepen": "schepen", "Gemeenteraadslid": "raadslid"}


def q(query: str) -> list[dict]:
    r = requests.post(EP, data={"query": PREFIXES + query}, headers={"Accept": "application/sparql-results+json"}, timeout=180)
    r.raise_for_status()
    return [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]


def party_label(raw: str | None) -> str | None:
    if not raw:
        return None
    return PARTY_LABELS.get(raw.strip().lower(), raw.strip())


def fetch(label: str, since: str = "2024-12-01") -> list[dict]:
    """Mandates of one municipality's council and college since `since`. The group needs separate queries: this endpoint
    does not return the group's name when the membership and the name are joined in one pattern (checked 24 Sep 2026)."""
    lit = '"' + label.replace('"', '\\"') + '"'
    rows = q(f"""SELECT DISTINCT ?m ?rol ?voornaam ?naam ?start ?einde WHERE {{
      ?be a besluit:Bestuurseenheid ; skos:prefLabel {lit} ; besluit:classificatie <{GEMEENTE}> .
      ?org besluit:bestuurt ?be . ?orgt mandaat:isTijdspecialisatieVan ?org ; org:hasPost ?post .
      ?post org:role ?rolc . ?rolc skos:prefLabel ?rol .
      ?m a mandaat:Mandataris ; org:holds ?post ; mandaat:isBestuurlijkeAliasVan ?p ; mandaat:start ?start .
      OPTIONAL {{ ?m mandaat:einde ?einde }}
      ?p persoon:gebruikteVoornaam ?voornaam ; foaf:familyName ?naam .
      FILTER(?start >= "{since}T00:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime>) }}""")
    ms = sorted({r["m"] for r in rows})
    m2f: dict[str, set] = defaultdict(set)
    for i in range(0, len(ms), 40):
        vals = " ".join(f"<{m}>" for m in ms[i:i + 40])
        for r in q(f"SELECT ?m ?fr WHERE {{ VALUES ?m {{ {vals} }} ?m org:hasMembership ?mem . ?mem org:organisation ?fr }}"):
            m2f[r["m"]].add(r["fr"])
    names = {}
    for f in sorted({f for s in m2f.values() for f in s}):
        for r in q(f"SELECT ?p ?o WHERE {{ <{f}> ?p ?o }}"):
            if r["p"].endswith("legalName"):
                names[f] = r["o"]
    for r in rows:
        groups = sorted({names[f] for f in m2f.get(r["m"], ()) if f in names})
        r["fractie"] = groups[0] if groups else None
    return rows


def current_members(rows: list[dict], on: str) -> list[dict]:
    """One entry per person with a mandate running on `on`, with every role they hold."""
    people: dict[tuple, dict] = {}
    for r in rows:
        if r["start"][:10] > on or (r.get("einde") and r["einde"][:10] < on):
            continue
        key = (r["voornaam"].strip(), r["naam"].strip())
        p = people.setdefault(key, {"roles": set(), "fractie": None})
        p["roles"].add(r["rol"])
        p["fractie"] = p["fractie"] or r.get("fractie")
    out = []
    for (first, last), p in people.items():
        roles = sorted(p["roles"], key=lambda x: ROLE_ORDER.index(x) if x in ROLE_ORDER else 99)
        out.append({"name": f"{first} {last}", "first": first, "last": last, "party": party_label(p["fractie"]),
                    "role": ROLE_SHORT.get(roles[0], roles[0].lower()), "roles": roles})
    return sorted(out, key=lambda m: (ROLE_ORDER.index(m["roles"][0]) if m["roles"][0] in ROLE_ORDER else 99, m["last"]))


def term_members(rows: list[dict]) -> list[dict]:
    """Everyone who held a council or college seat during the term, with the first start and last end of their mandates."""
    people: dict[tuple, dict] = {}
    for r in rows:
        key = (r["voornaam"].strip(), r["naam"].strip())
        p = people.setdefault(key, {"from": r["start"][:10], "until": None, "open": False, "fractie": None})
        p["from"] = min(p["from"], r["start"][:10])
        if r.get("einde"):
            p["until"] = max(p["until"] or "", r["einde"][:10])
        else:
            p["open"] = True
        p["fractie"] = p["fractie"] or r.get("fractie")
    out = []
    for (first, last), p in people.items():
        out.append({"name": f"{first} {last}", "party": party_label(p["fractie"]), "from": p["from"],
                    "until": None if p["open"] else p["until"]})
    return sorted(out, key=lambda x: x["name"])


def write_yaml(m: dict, members: list[dict], on: str, former: list[dict] | None = None) -> dict:
    parties = defaultdict(int)
    for x in members:
        if "Gemeenteraadslid" in x["roles"] or x["role"] == "burgemeester":
            parties[x["party"] or "onbekend"] += 1
    doc = {"municipality": m["slug"], "term": "2025-2030", "seats": sum(1 for x in members if "Gemeenteraadslid" in x["roles"]),
           "source": f"Mandatendatabank via https://data.lblod.info/sparql, mandates running on {on}",
           "parties": [{"name": k, "seats": v} for k, v in sorted(parties.items(), key=lambda kv: -kv[1])],
           "mayor": next((x["name"] for x in members if x["role"] == "burgemeester"), None),
           "chair": next((x["name"] for x in members if "Voorzitter van de gemeenteraad" in x["roles"]), None),
           "members": [{"name": x["name"], "party": x["party"], "role": x["role"]} for x in members],
           "former": former or []}
    path = config.COUNCILS / f"{m['slug']}.yaml"
    path.write_text("# Written by `python -m raadzaal councils`; edit by hand only to add what the database lacks.\n"
                    + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=140), encoding="utf-8")
    return doc


def run(con, args) -> int:
    on = date.today().isoformat()
    munis = [config.municipality(args.municipality)] if args.municipality else config.municipalities()
    for m in munis:
        rows = fetch(m["lblod_label"])
        members = current_members(rows, on)
        if not members:
            print(f"{m['slug']}: no mandates found, file left as it is")
            continue
        current = {x["name"] for x in members}
        former = [x for x in term_members(rows) if x["name"] not in current and x["until"]]
        doc = write_yaml(m, members, on, former)
        print(f"{m['slug']:<10} {doc['seats']} seats, chair {doc['chair']}, mayor {doc['mayor']}, "
              + ", ".join(f"{p['name']} {p['seats']}" for p in doc["parties"]))
    return 0
