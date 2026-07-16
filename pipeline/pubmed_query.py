#!/usr/bin/env python3
"""Recherche PubMed partagée — une seule vérité pour la veille et le numéro.

`fetch_pubmed.py` (page « Veille ») et `generate_issue.py` (numéro publié)
utilisaient deux stratégies de recherche différentes, vouées à diverger. Ce
module centralise la requête « médecine interne » (termes MeSH + types de
publication), l'exclusion des publications rétractées, et les appels
E-utilities avec retry/backoff.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

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
# On écarte les publications rétractées dès la requête (filet complété par
# `is_retracted` avant synthèse).
RETRACTED_EXCLUDE = 'NOT ("Retracted Publication"[pt])'

RECO_PUBTYPES = {"Guideline", "Practice Guideline", "Consensus Development Conference"}


def eutils_get(endpoint: str, params: dict, retries: int = 4) -> dict:
    """Appel E-utilities JSON avec retry/backoff exponentiel (2, 4, 8, 16 s)."""
    params = {**params, "retmode": "json"}
    if os.environ.get("NCBI_API_KEY"):
        params["api_key"] = os.environ["NCBI_API_KEY"]
    url = f"{EUTILS}/{endpoint}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=40) as resp:
                return json.load(resp)
        except Exception as e:  # réseau, 429, JSON tronqué…
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"E-utilities {endpoint} indisponible: {last}")


def summaries(pmids: list[str]) -> list[dict]:
    out: list[dict] = []
    for start in range(0, len(pmids), 50):
        chunk = pmids[start:start + 50]
        try:
            data = eutils_get("esummary.fcgi", {"db": "pubmed", "id": ",".join(chunk)})
        except Exception:
            continue
        result = (data or {}).get("result", {}) or {}
        for pmid in chunk:
            doc = result.get(pmid)
            if not isinstance(doc, dict):
                continue
            doi = next((i.get("value") for i in doc.get("articleids", [])
                        if i.get("idtype") == "doi"), None)
            revue = doc.get("fulljournalname") or doc.get("source", "")
            out.append({
                "pmid": pmid,
                "titre": (doc.get("title") or "").rstrip("."),
                "revue": revue,
                "date_publication": doc.get("pubdate", ""),
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "pubtypes": doc.get("pubtype", []) or [],
            })
        time.sleep(0.4)  # limite NCBI sans clé : 3 requêtes/seconde
    return out


def search_internal_medicine(days: int, retmax: int = 150) -> list[dict]:
    """Candidats « médecine interne » des `days` derniers jours, hors rétractés."""
    term = f"{MI_MESH} AND {PUB_TYPES} {RETRACTED_EXCLUDE}"
    try:
        data = eutils_get("esearch.fcgi", {
            "db": "pubmed", "term": term,
            "reldate": days, "datetype": "pdat", "retmax": retmax,
        })
    except Exception:
        return []
    ids = ((data or {}).get("esearchresult", {}) or {}).get("idlist", []) or []
    return summaries(ids)


def is_retracted(doc: dict) -> bool:
    return any("retract" in str(pt).lower() for pt in doc.get("pubtypes", []))


def bucket(docs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Sépare recommandations/consensus et essais/méta, pour la page Veille."""
    reco = [d for d in docs if RECO_PUBTYPES & set(d.get("pubtypes", []))]
    reco_ids = {d["pmid"] for d in reco}
    essai = [d for d in docs if d["pmid"] not in reco_ids]
    return reco, essai
