#!/usr/bin/env python3
"""Génère automatiquement le numéro hebdomadaire (brouillon) via l'API Claude.

Chaîne complète, sans intervention humaine :
  1. interroge PubMed (E-utilities) sur les 7 derniers jours, périmètre médecine
     interne (maladies auto-immunes/systémiques, vascularites, hématologie non
     maligne, MTEV…) ;
  2. demande à Claude de sélectionner les items réellement pertinents pour un
     service de médecine interne français ;
  3. récupère les abstracts (et le texte intégral libre si disponible via
     Europe PMC) ;
  4. demande à Claude de rédiger, pour chaque item, une synthèse structurée
     ancrée sur la source (résumé, ce qui change, message clé, contexte) ;
  5. écrit content/issues/AAAA-MM-JJ.yaml.

Le numéro est publié tel quel : entièrement généré par IA, SANS relecture par un
médecin. C'est un parti pris assumé, affiché sur chaque numéro et sur la page
Méthode. Chaque item renvoie à sa source, à vérifier avant tout usage clinique.

Prérequis : variable d'environnement ANTHROPIC_API_KEY. NCBI_API_KEY optionnelle
(augmente la limite de débit PubMed).

Usage : python3 pipeline/generate_issue.py [--days 7] [--max-items 6]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

try:
    import anthropic
except ImportError:  # pragma: no cover
    sys.exit("Le paquet 'anthropic' est requis : pip install anthropic")

ROOT = Path(__file__).resolve().parent.parent
ISSUES = ROOT / "content" / "issues"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MODEL = "claude-opus-4-8"

TYPE_LABELS = {"reco", "pnds", "essai", "meta", "alerte", "autre"}

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]

# Périmètre médecine interne (termes MeSH), croisé avec des types de publication.
MI_MESH = (
    '("lupus erythematosus, systemic"[mh] OR vasculitis[mh] OR "Sjogren\'s syndrome"[mh] '
    'OR "Behcet syndrome"[mh] OR sarcoidosis[mh] OR amyloidosis[mh] OR myositis[mh] '
    'OR "scleroderma, systemic"[mh] OR "giant cell arteritis"[mh] OR "antiphospholipid syndrome"[mh] '
    'OR "hereditary autoinflammatory diseases"[mh] OR "fever of unknown origin"[mh] '
    'OR "purpura, thrombotic thrombocytopenic"[mh] OR "purpura, thrombocytopenic, idiopathic"[mh] '
    'OR "anemia, hemolytic, autoimmune"[mh] OR "venous thromboembolism"[mh] '
    'OR "immunoglobulin g4-related disease"[mh] OR "still\'s disease, adult-onset"[mh] '
    'OR "arthritis, rheumatoid"[mh] OR "polymyalgia rheumatica"[mh] OR "granulomatosis with polyangiitis"[mh])'
)
PUB_TYPES = (
    '(Guideline[pt] OR Practice Guideline[pt] OR "Randomized Controlled Trial"[pt] '
    'OR Meta-Analysis[pt] OR "Systematic Review"[pt] OR Consensus Development Conference[pt])'
)


def eutils(endpoint: str, params: dict) -> dict:
    params = {**params, "retmode": "json"}
    if os.environ.get("NCBI_API_KEY"):
        params["api_key"] = os.environ["NCBI_API_KEY"]
    url = f"{EUTILS}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=40) as resp:
        return json.load(resp)


def search_candidates(days: int) -> list[dict]:
    ids = eutils("esearch.fcgi", {
        "db": "pubmed", "term": f"{MI_MESH} AND {PUB_TYPES}",
        "reldate": days, "datetype": "pdat", "retmax": 120,
    })["esearchresult"]["idlist"]
    out: list[dict] = []
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        data = eutils("esummary.fcgi", {"db": "pubmed", "id": ",".join(chunk)})
        for pmid in chunk:
            doc = data["result"].get(pmid)
            if not doc:
                continue
            doi = next((i["value"] for i in doc.get("articleids", [])
                        if i.get("idtype") == "doi"), None)
            out.append({
                "pmid": pmid,
                "titre": doc.get("title", "").rstrip("."),
                "revue": doc.get("fulljournalname") or doc.get("source", ""),
                "date_publication": doc.get("pubdate", ""),
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "pubtypes": doc.get("pubtype", []),
            })
        time.sleep(0.4)
    return out


def fetch_abstract(pmid: str) -> str:
    url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "text"})
    try:
        with urllib.request.urlopen(url, timeout=40) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        return ""


def fetch_fulltext(pmid: str, doc_pmcid: str | None) -> str:
    """Texte intégral libre via Europe PMC (introduction/discussion), si dispo."""
    if not doc_pmcid:
        return ""
    try:
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/PMC{doc_pmcid}/fullTextXML"
        with urllib.request.urlopen(url, timeout=40) as resp:
            xml = resp.read().decode("utf-8", "replace")
    except Exception:
        return ""
    chunks = []
    for sec in re.findall(r"<sec[^>]*>.*?</sec>", xml, re.S):
        title = re.search(r"<title[^>]*>(.*?)</title>", sec, re.S)
        t = re.sub("<[^>]+>", "", title.group(1)).strip() if title else ""
        if re.search(r"introduction|background|discussion", t, re.I):
            body = re.sub("<[^>]+>", " ", sec)
            chunks.append(re.sub(r"\s+", " ", body).strip())
    return "\n\n".join(chunks)[:6000]


def get_pmcid(pmid: str) -> str | None:
    try:
        data = eutils("elink.fcgi", {"dbfrom": "pubmed", "db": "pmc", "id": pmid})
        for ls in data.get("linksets", []):
            for db in ls.get("linksetdbs", []):
                if db.get("dbto") == "pmc" and db.get("links"):
                    return db["links"][0]
    except Exception:
        pass
    return None


def claude_json(client, prompt: str, schema: dict, max_tokens: int = 4000) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    return json.loads(text)


SELECT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pmid": {"type": "string"},
                    "type": {"type": "string",
                             "enum": ["reco", "pnds", "essai", "meta", "alerte", "autre"]},
                    "titre_fr": {"type": "string"},
                },
                "required": ["pmid", "type", "titre_fr"],
            },
        },
    },
    "required": ["items"],
}

ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "resume": {"type": "string"},
        "message_cle": {"type": "string"},
        "contexte": {"type": "array", "items": {"type": "string"}},
        "base_texte": {"type": "string", "enum": ["texte_integral", "abstract_seul"]},
        "a_ce_qui_change": {"type": "boolean"},
        "ce_qui_change_reference": {"type": "string"},
        "ce_qui_change_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["resume", "message_cle", "contexte", "base_texte",
                 "a_ce_qui_change", "ce_qui_change_reference", "ce_qui_change_points"],
}


def select_items(client, candidates: list[dict], max_items: int) -> list[dict]:
    listing = "\n".join(
        f'{c["pmid"]} | {c["revue"]} | {"/".join(c["pubtypes"])} | {c["titre"]}'
        for c in candidates)
    prompt = (
        "Tu es documentaliste pour une veille destinée aux MÉDECINS INTERNISTES "
        "exerçant en FRANCE. Périmètre STRICT : maladies auto-immunes et "
        "systémiques (lupus, Sjögren, sclérodermie, myosites, connectivites), "
        "vascularites (Horton, Takayasu, ANCA, PAN, Behçet), maladies "
        "auto-inflammatoires, sarcoïdose, amylose, IgG4, hématologie non maligne "
        "(PTI, PTT/microangiopathies, anémies hémolytiques auto-immunes, cytopénies), "
        "MTEV et SAPL, infectiologie complexe, fièvre prolongée inexpliquée, "
        "immunodéprimé, polypathologie. EXCLURE tout ce qui relève d'une autre "
        "spécialité d'organe (cardiologie, diabétologie, pneumologie, gastro, "
        "oncologie, néphrologie de dialyse, chirurgie, pédiatrie exclusive), sauf "
        "si cela concerne directement la pratique interniste (ex. tolérance au long "
        "cours d'un immunosuppresseur). Inclure les essais négatifs s'ils recadrent "
        "la pratique.\n\n"
        f"Sélectionne au maximum {max_items} items VRAIMENT pertinents parmi la "
        "liste ci-dessous (format : PMID | revue | types | titre). Donne pour "
        "chacun le PMID, un type (reco, pnds, essai, meta, alerte, autre) et un "
        "titre reformulé en français, clair et fidèle. S'il n'y a rien de "
        "pertinent, renvoie une liste vide.\n\n" + listing)
    data = claude_json(client, prompt, SELECT_SCHEMA, max_tokens=2000)
    picked = []
    by_pmid = {c["pmid"]: c for c in candidates}
    for it in data.get("items", [])[:max_items]:
        c = by_pmid.get(it["pmid"])
        if c:
            picked.append({**c, "type": it["type"], "titre_fr": it["titre_fr"]})
    return picked


def synthesize(client, item: dict, source_text: str) -> dict:
    prompt = (
        "Tu rédiges pour un digest hebdomadaire destiné aux MÉDECINS INTERNISTES "
        "francophones, en français, ton factuel et sobre.\n\n"
        f"Titre : {item['titre_fr']}\nSource : {item['revue']}\n\n"
        "À partir UNIQUEMENT du texte source ci-dessous, produis :\n"
        "- resume : 5 à 10 lignes factuelles (chiffres/HR/effectifs uniquement "
        "s'ils figurent dans le texte) ;\n"
        "- a_ce_qui_change : true seulement si le texte décrit explicitement un "
        "changement par rapport à une version antérieure ou à la pratique "
        "standard ; sinon false ;\n"
        "- ce_qui_change_reference : la référence du diff (ex. 'version 2021', "
        "'pratique antérieure') si a_ce_qui_change, sinon chaîne vide ;\n"
        "- ce_qui_change_points : liste de points (vide si a_ce_qui_change=false) ;\n"
        "- message_cle : 1 à 3 phrases actionnables ;\n"
        "- contexte : liste de 3 à 4 paragraphes détaillés expliquant la maladie "
        "et sa place en médecine interne, le standard de prise en charge actuel, "
        "pourquoi cette étude et où elle s'inscrit, et la pertinence pour la "
        "pratique française (centres de référence, AMM, remboursement) ainsi que "
        "les limites ;\n"
        "- base_texte : 'texte_integral' si le texte fourni dépasse l'abstract, "
        "sinon 'abstract_seul'.\n"
        "N'invente aucun chiffre ni aucun diff absent du texte.\n\n"
        "=== TEXTE SOURCE ===\n" + source_text[:14000])
    d = claude_json(client, prompt, ITEM_SCHEMA, max_tokens=4000)
    out = {
        "type": item["type"],
        "titre": item["titre_fr"],
        "source": item["revue"],
        "url": item["url"],
        "base_texte": d["base_texte"],
        "resume": d["resume"],
        "message_cle": d["message_cle"],
        "contexte": d["contexte"],
    }
    if d.get("a_ce_qui_change") and d.get("ce_qui_change_points"):
        out["ce_qui_change"] = {
            "reference": d.get("ce_qui_change_reference") or "pratique antérieure",
            "points": d["ce_qui_change_points"],
        }
    return out


def next_numero() -> int:
    n = 0
    for path in ISSUES.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            n = max(n, int(data.get("numero", 0)))
        except Exception:
            pass
    return n + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max-items", type=int, default=6)
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY manquante.")

    client = anthropic.Anthropic()
    today = dt.date.today()
    start = today - dt.timedelta(days=args.days - 1)
    semaine = (f"{start.day} {MOIS_FR[start.month - 1]} au "
               f"{today.day} {MOIS_FR[today.month - 1]} {today.year}")

    print(f"Recherche PubMed médecine interne ({args.days} j)…")
    candidates = search_candidates(args.days)
    print(f"  {len(candidates)} candidats bruts")
    if not candidates:
        candidates = []

    selected = select_items(client, candidates, args.max_items) if candidates else []
    print(f"  {len(selected)} items retenus par Claude")

    items = []
    for it in selected:
        pmcid = get_pmcid(it["pmid"])
        abstract = fetch_abstract(it["pmid"])
        fulltext = fetch_fulltext(it["pmid"], pmcid)
        source_text = (abstract + "\n\n" + fulltext).strip() or it["titre"]
        try:
            items.append(synthesize(client, it, source_text))
        except Exception as e:  # pragma: no cover
            print(f"  ! synthèse échouée pour {it['pmid']}: {e}")
        time.sleep(0.4)

    issue = {
        "numero": next_numero(),
        "semaine": semaine,
        "date": today.isoformat(),
        "edito": ("Sélection et synthèses des publications de médecine interne de "
                  "la semaine, générées automatiquement par IA sans relecture "
                  "humaine. Chaque item renvoie à sa source."
                  if items else
                  "Semaine calme : aucune publication majeure de médecine interne "
                  "retenue cette semaine par la sélection automatique."),
        "items": items,
    }

    ISSUES.mkdir(parents=True, exist_ok=True)
    out_path = ISSUES / f"{today.isoformat()}.yaml"
    header = ("# Numéro généré automatiquement par IA, sans relecture humaine.\n")
    out_path.write_text(
        header + yaml.safe_dump(issue, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8")
    print(f"✓ écrit {out_path.relative_to(ROOT)} ({len(items)} items)")


if __name__ == "__main__":
    main()
