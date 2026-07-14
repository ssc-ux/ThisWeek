#!/usr/bin/env python3
"""Prépare le brouillon hebdomadaire : candidats PubMed des 7 derniers jours.

Interroge les E-utilities NCBI (gratuit, sans clé — une clé via la variable
d'environnement NCBI_API_KEY augmente la limite de débit) avec deux requêtes :

  1. « recommandations » : guidelines / practice guidelines / consensus, tous
     champs confondus ;
  2. « essais majeurs » : essais randomisés publiés dans les grandes revues
     généralistes.

Écrit content/drafts/AAAA-MM-JJ-brouillon.yaml : une liste de candidats
(titre, revue, date, PMID, DOI, lien) à trier puis synthétiser par l'éditeur.
Aucun résumé n'est généré ici — ce script ne fait que collecter.

Usage : python3 pipeline/fetch_pubmed.py [--days 7]
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

MAJOR_JOURNALS = [
    "N Engl J Med", "Lancet", "JAMA", "Ann Intern Med", "BMJ",
    "JAMA Intern Med", "Lancet Rheumatol", "Lancet Infect Dis",
    "Ann Rheum Dis", "Blood", "Kidney Int", "Clin Infect Dis",
]

QUERIES = {
    "reco": (
        "(Guideline[pt] OR Practice Guideline[pt] "
        "OR Consensus Development Conference[pt])"
    ),
    "essai": (
        "Randomized Controlled Trial[pt] AND ("
        + " OR ".join(f'"{j}"[ta]' for j in MAJOR_JOURNALS)
        + ")"
    ),
}


def eutils_get(endpoint: str, params: dict) -> dict:
    params = {**params, "retmode": "json"}
    if os.environ.get("NCBI_API_KEY"):
        params["api_key"] = os.environ["NCBI_API_KEY"]
    url = f"{EUTILS}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def search(term: str, days: int) -> list[str]:
    data = eutils_get(
        "esearch.fcgi",
        {"db": "pubmed", "term": term, "reldate": days,
         "datetype": "pdat", "retmax": 200},
    )
    return data["esearchresult"]["idlist"]


def summaries(pmids: list[str]) -> list[dict]:
    out = []
    for start in range(0, len(pmids), 50):
        chunk = pmids[start:start + 50]
        data = eutils_get(
            "esummary.fcgi", {"db": "pubmed", "id": ",".join(chunk)}
        )
        for pmid in chunk:
            doc = data["result"].get(pmid)
            if not doc:
                continue
            doi = next(
                (i["value"] for i in doc.get("articleids", [])
                 if i.get("idtype") == "doi"), None,
            )
            out.append({
                "pmid": pmid,
                "titre": doc.get("title", "").rstrip("."),
                "revue": doc.get("fulljournalname") or doc.get("source", ""),
                "date_publication": doc.get("pubdate", ""),
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "types_publication": doc.get("pubtype", []),
            })
        time.sleep(0.4)  # limite NCBI sans clé : 3 requêtes/seconde
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    draft: dict = {
        "genere_le": date.today().isoformat(),
        "periode_jours": args.days,
        "note": (
            "Brouillon automatique : candidats PubMed à trier. "
            "Étapes suivantes : scorer (prompts/scoring.md), sélectionner, "
            "synthétiser (prompts/synthese.md), relire, puis créer le numéro "
            "dans content/issues/."
        ),
        "candidats": {},
    }

    seen: set[str] = set()
    for label, term in QUERIES.items():
        pmids = [p for p in search(term, args.days) if p not in seen]
        seen.update(pmids)
        docs = summaries(pmids)
        draft["candidats"][label] = docs
        print(f"{label:6s} : {len(docs)} candidats")
        time.sleep(0.4)

    out_dir = ROOT / "content" / "drafts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}-brouillon.yaml"
    out_path.write_text(
        yaml.safe_dump(draft, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(f"✓ brouillon écrit : {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
