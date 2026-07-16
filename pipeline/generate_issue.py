#!/usr/bin/env python3
"""Génère automatiquement le numéro hebdomadaire via l'API Claude.

Chaîne, sans intervention humaine :
  1. interroge PubMed (recherche partagée `pubmed_query`) sur les N derniers
     jours, périmètre médecine interne, publications rétractées exclues ;
  2. sélection des items pertinents (modèle léger) ;
  3. récupère abstracts (+ texte intégral libre Europe PMC si dispo) ;
  4. synthèse structurée par item (modèle de haut niveau), avec un niveau de
     confiance auto-déclaré ;
  5. PASSE DE VÉRIFICATION : un second appel relit chaque synthèse face à la
     source ; tout item dont un chiffre/une affirmation n'est pas retrouvé, ou
     de confiance « faible », est RÉTROGRADÉ en « Aussi paru » (résumé court)
     au lieu d'être publié en synthèse détaillée ;
  6. écrit content/issues/AAAA-MM-JJ.yaml.

Publié tel quel : généré par IA, SANS relecture humaine — parti pris assumé et
affiché. Chaque item renvoie à sa source, à vérifier avant tout usage clinique.

Prérequis : ANTHROPIC_API_KEY. NCBI_API_KEY optionnelle (débit PubMed).

Usage : python3 pipeline/generate_issue.py [--days 7] [--max-items 15] [--force]
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

from pubmed_query import (
    EUTILS,
    eutils_get,
    is_retracted,
    search_internal_medicine,
)

try:
    import anthropic
except ImportError:  # pragma: no cover
    sys.exit("Le paquet 'anthropic' est requis : pip install anthropic")

ROOT = Path(__file__).resolve().parent.parent
ISSUES = ROOT / "content" / "issues"
PNDS_REGISTRY = ROOT / "content" / "pnds.yaml"

# Modèle léger pour le tri d'un grand nombre de candidats, modèle de haut niveau
# pour la synthèse et la vérification.
MODEL_SELECT = "claude-sonnet-5"
MODEL_SYNTH = "claude-opus-4-8"

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]

# Impact factor APPROXIMATIF des revues, uniquement pour départager des articles
# de pertinence comparable. Valeurs indicatives (ordre de grandeur), pas des
# chiffres officiels. Motifs testés sur le nom complet de la revue en minuscules,
# du plus spécifique au plus générique (un sous-journal du Lancet prime sur
# « lancet »).
JOURNAL_IF = [
    ("lancet rheumatol", 42), ("lancet haematol", 25), ("lancet infect", 37),
    ("lancet respir", 38), ("lancet diabetes", 44), ("lancet public health", 25),
    ("lancet regional", 10), ("lancet", 98),
    ("new england journal of medicine", 96),
    ("nature reviews rheumatol", 40), ("nature reviews immunol", 100),
    ("nature reviews nephrol", 41), ("nature reviews disease primers", 76),
    ("nature medicine", 58), ("nature communications", 15),
    ("jama internal medicine", 25), ("jama network open", 11), ("jama", 63),
    ("bmj open", 3), ("bmj (clinical", 93), ("the bmj", 93),
    ("annals of internal medicine", 40),
    ("annals of the rheumatic diseases", 20),
    ("annals of rheumatic diseases", 20),
    ("blood advances", 8), ("blood cancer", 12), ("blood", 21),
    ("immunity", 32), ("circulation", 37),
    ("arthritis & rheumatol", 12), ("arthritis and rheumatol", 12),
    ("arthritis care", 4), ("arthritis research", 5),
    ("rheumatology (oxford", 5), ("rheumatology (oxf", 5),
    ("journal of thrombosis and haemostasis", 11),
    ("journal of autoimmunity", 12), ("autoimmunity reviews", 13),
    ("clinical infectious diseases", 11), ("journal of infection", 14),
    ("haematologica", 10), ("american journal of hematology", 12),
    ("kidney international", 15), ("journal of internal medicine", 9),
    ("chest", 9), ("thorax", 9), ("european respiratory journal", 24),
    ("seminars in arthritis and rheumatism", 5), ("rmd open", 5),
    ("clinical rheumatology", 3), ("lupus", 3),
    ("journal of clinical immunology", 8),
    ("frontiers in immunology", 6), ("plos one", 3),
]


def journal_if(name: str) -> int | None:
    low = (name or "").lower()
    for motif, val in JOURNAL_IF:
        if motif in low:
            return val
    return None


def _http_text(url: str, retries: int = 3) -> str:
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=40) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    print(f"  ! récupération échouée ({last}) : {url[:70]}")
    return ""


def search_candidates(days: int) -> list[dict]:
    docs = search_internal_medicine(days, retmax=150)
    out = []
    for d in docs:
        if is_retracted(d):  # filet en plus de l'exclusion dans la requête
            print(f"  ⦸ écarté (rétracté) : {d['pmid']}")
            continue
        out.append({**d, "if_approx": journal_if(d["revue"])})
    return out


def fetch_abstract(pmid: str) -> str:
    url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "text"})
    return _http_text(url)


def fetch_fulltext(pmid: str, doc_pmcid: str | None) -> str:
    """Texte intégral libre via Europe PMC (introduction/discussion), si dispo."""
    if not doc_pmcid:
        return ""
    xml = _http_text(
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/PMC{doc_pmcid}/fullTextXML")
    if not xml:
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
        data = eutils_get("elink.fcgi", {"dbfrom": "pubmed", "db": "pmc", "id": pmid})
        for ls in data.get("linksets", []):
            for db in ls.get("linksetdbs", []):
                if db.get("dbto") == "pmc" and db.get("links"):
                    return db["links"][0]
    except Exception:
        pass
    return None


def claude_json(client, prompt: str, schema: dict, model: str = MODEL_SYNTH,
                max_tokens: int = 4000, retries: int = 3) -> dict:
    last = None
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": prompt}],
            )
            text = next((b.text for b in resp.content if b.type == "text"), "{}")
            return json.loads(text)
        except Exception as e:  # réseau, 429, JSON tronqué (max_tokens)…
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"appel Claude échoué ({model}): {last}")


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
        "aussi_parus": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pmid": {"type": "string"},
                    "titre_fr": {"type": "string"},
                },
                "required": ["pmid", "titre_fr"],
            },
        },
    },
    "required": ["items", "aussi_parus"],
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
        # Comparaisons détaillées, remplies pour les recommandations et PNDS.
        "comparaisons": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "titre": {"type": "string"},
                    "reference": {"type": "string"},
                    "points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["titre", "reference", "points"],
            },
        },
        # Auto-évaluation, exploitée par la passe de vérification.
        "confiance": {"type": "string", "enum": ["elevee", "moyenne", "faible"]},
        "points_a_verifier": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["resume", "message_cle", "contexte", "base_texte",
                 "a_ce_qui_change", "ce_qui_change_reference", "ce_qui_change_points",
                 "comparaisons", "confiance", "points_a_verifier"],
}

BRIEF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "resumes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pmid": {"type": "string"},
                    "resume": {"type": "string"},
                },
                "required": ["pmid", "resume"],
            },
        },
    },
    "required": ["resumes"],
}

VERIFY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "valide": {"type": "boolean"},
        "problemes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["valide", "problemes"],
}


def synthesize_brief(client, refs: list[dict]) -> list[dict]:
    """Résumé court (2-3 phrases) pour chaque « aussi paru », ancré sur l'abstract."""
    if not refs:
        return []
    blocks = []
    for r in refs:
        abstract = fetch_abstract(r["pmid"])[:2500]
        blocks.append(f'PMID {r["pmid"]} — {r["titre_fr"]} ({r["revue"]})\n{abstract}')
        time.sleep(0.3)
    prompt = (
        "Pour chaque publication ci-dessous (séparées par « --- »), rédige un "
        "résumé COURT de 2 à 3 phrases, factuel et en français, à partir "
        "UNIQUEMENT de son abstract. N'invente aucun chiffre absent du texte ; "
        "si les résultats chiffrés manquent, décris l'objectif et la portée. "
        "Renvoie un objet {pmid, resume} par publication.\n\n"
        + "\n\n---\n\n".join(blocks))
    data = claude_json(client, prompt, BRIEF_SCHEMA, model=MODEL_SELECT, max_tokens=3000)
    by = {d["pmid"]: d["resume"] for d in data.get("resumes", [])}
    out = []
    seen = set()
    for r in refs:
        if r["pmid"] in seen:
            continue
        seen.add(r["pmid"])
        entry = {"titre": r["titre_fr"], "source": r["revue"], "url": r["url"]}
        if r["pmid"] in by:
            entry["resume"] = by[r["pmid"]]
        if r.get("if_approx") is not None:
            entry["impact_factor"] = r["if_approx"]
        out.append(entry)
    return out


def select_items(client, candidates: list[dict], max_items: int) -> tuple[list[dict], list[dict]]:
    listing = "\n".join(
        f'{c["pmid"]} | {c["revue"]} | IF≈{c["if_approx"] if c["if_approx"] is not None else "?"}'
        f' | {"/".join(c["pubtypes"])} | {c["titre"]}'
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
        "CRITÈRES DE SÉLECTION, par ordre de priorité :\n"
        "1. la PERTINENCE pour un service de médecine interne français (périmètre "
        "ci-dessus) — critère absolu, un article hors périmètre n'est jamais retenu, "
        "même publié dans une revue prestigieuse ;\n"
        "2. la PORTÉE pratique (reco/PNDS, essai de phase 3, méta-analyse "
        "structurante, alerte de sécurité) ;\n"
        "3. à pertinence comparable, l'IMPACT FACTOR de la revue (indiqué « IF≈ » "
        "dans la liste, valeur approximative ; « IF≈? » = revue non répertoriée, "
        "à juger sur le fond) : privilégie la revue au facteur d'impact le plus "
        "élevé, sans jamais faire de l'IF un critère supérieur à la pertinence, "
        "et sans jamais pénaliser une recommandation française (souvent sans IF).\n\n"
        "RÈGLE STRICTE SUR LES RECOMMANDATIONS ET CONSENSUS : ne retiens une "
        "recommandation, une guideline ou un consensus QUE s'il s'agit (a) d'un "
        "texte INTERNATIONAL d'une grande société savante (EULAR, ACR, KDIGO, ASH, "
        "ISTH, ATS/ERS, EAN, EHA…) OU (b) d'une référence FRANÇAISE (HAS, PNDS, "
        "filières de santé maladies rares, SNFMI, CRI…). Les recommandations ou "
        "consensus NATIONAUX d'un autre pays (ex. mexicain, coréen, chinois, "
        "brésilien…) ne sont PAS pertinents pour un interniste français : ne les "
        "sélectionne NI en « items » NI en « aussi_parus », écarte-les purement.\n\n"
        "Rends DEUX listes (format des candidats : PMID | revue | IF≈ | types | titre) :\n"
        "- « items » : les publications VRAIMENT marquantes, à synthétiser en "
        "détail. Pour chacune : PMID, type (reco, pnds, essai, meta, alerte, autre) "
        "et un titre reformulé en français, clair et fidèle. PAS DE NOMBRE IMPOSÉ : "
        "le nombre dépend de ce qui a réellement été publié — souvent 3 à 8, parfois "
        "plus une semaine riche, parfois moins une semaine calme. N'inclus jamais un "
        "item tiède pour « faire du volume ».\n"
        "- « aussi_parus » : les AUTRES publications pertinentes pour un interniste "
        "mais moins prioritaires (PMID + titre français), sans limite fixe non plus. "
        "Elles recevront un résumé court, sans synthèse détaillée.\n"
        "Une même publication ne doit jamais figurer dans les deux listes. Écarte "
        "franchement ce qui est hors périmètre. S'il n'y a rien de pertinent, "
        "renvoie deux listes vides.\n\n" + listing)
    data = claude_json(client, prompt, SELECT_SCHEMA, model=MODEL_SELECT, max_tokens=3000)
    by_pmid = {c["pmid"]: c for c in candidates}
    picked = []
    seen = set()
    for it in data.get("items", [])[:max_items]:
        c = by_pmid.get(it["pmid"])
        if c and it["pmid"] not in seen:
            seen.add(it["pmid"])
            picked.append({**c, "type": it["type"], "titre_fr": it["titre_fr"]})
    aussi = []
    for it in data.get("aussi_parus", [])[:max_items * 2]:
        c = by_pmid.get(it["pmid"])
        if c and it["pmid"] not in seen:
            seen.add(it["pmid"])
            aussi.append({**c, "titre_fr": it["titre_fr"]})
    return picked, aussi


def synthesize(client, item: dict, source_text: str) -> tuple[dict, str]:
    is_reco = item["type"] in ("reco", "pnds")
    comp_instr = (
        "- comparaisons : "
        + (
            "COMME IL S'AGIT D'UNE RECOMMANDATION OU D'UN PNDS, remplis jusqu'à "
            "trois axes, chacun {titre, reference, points} : (1) par rapport à la "
            "VERSION PRÉCÉDENTE du même texte ; (2) par rapport aux AUTRES GRANDES "
            "RECOMMANDATIONS internationales sur le sujet (ex. EULAR, KDIGO, ACR/"
            "EULAR selon le thème) ; (3) par rapport aux RECOMMANDATIONS FRANÇAISES "
            "(PNDS de la HAS, filières de santé maladies rares). Fonde-toi sur la "
            "source et sur des connaissances GÉNÉRALES bien établies ; reste à un "
            "niveau dont tu es sûr, n'invente aucun contenu précis (pas de fausse "
            "date, pas de recommandation imaginaire) ; en cas de doute, formule "
            "prudemment (« à confronter à… »). Laisse un axe de côté si tu n'as rien "
            "de fiable à en dire.\n"
            if is_reco else
            "laisse la liste VIDE (ce n'est pas une recommandation ni un PNDS).\n"
        )
    )
    prompt = (
        "Tu rédiges pour un digest hebdomadaire destiné aux MÉDECINS INTERNISTES "
        "francophones, en français, ton factuel et sobre.\n\n"
        f"Type d'item : {item['type']}\nTitre : {item['titre_fr']}\n"
        f"Source : {item['revue']}\n\n"
        "À partir du texte source ci-dessous, produis :\n"
        "- resume : 5 à 10 lignes factuelles (chiffres/HR/effectifs uniquement "
        "s'ils figurent dans le texte). RÈGLE ANTI-SOUS-GROUPE : si le critère de "
        "jugement PRINCIPAL est négatif ou non atteint, énonce D'ABORD ce résultat "
        "principal ; ne présente jamais un résultat de sous-groupe ou secondaire "
        "comme s'il était le résultat principal, et qualifie-le explicitement "
        "d'« analyse de sous-groupe exploratoire, génératrice d'hypothèses » ;\n"
        "- a_ce_qui_change : true seulement si le texte décrit explicitement un "
        "changement par rapport à une version antérieure ou à la pratique "
        "standard ; sinon false ;\n"
        "- ce_qui_change_reference : la référence du diff si a_ce_qui_change, sinon "
        "chaîne vide ;\n"
        "- ce_qui_change_points : liste de points (vide si a_ce_qui_change=false) ;\n"
        + comp_instr +
        "- message_cle : 1 à 3 phrases actionnables ;\n"
        "- contexte : liste de 3 à 4 paragraphes détaillés expliquant la maladie "
        "et sa place en médecine interne, le standard de prise en charge actuel, "
        "pourquoi cette étude et où elle s'inscrit, et la pertinence pour la "
        "pratique française (centres de référence, AMM, remboursement) ainsi que "
        "les limites ;\n"
        "- base_texte : 'texte_integral' si le texte fourni dépasse l'abstract, "
        "sinon 'abstract_seul' ;\n"
        "- confiance : 'elevee', 'moyenne' ou 'faible' — abaisse-la dès que le "
        "texte est ambigu, partiel, ou que tu extrapoles ;\n"
        "- points_a_verifier : liste (éventuellement vide) des points qu'un "
        "relecteur devrait contrôler en priorité.\n"
        "Le resume et les chiffres ne doivent venir QUE du texte source. Les "
        "comparaisons peuvent s'appuyer sur des connaissances générales, mais sans "
        "rien inventer de précis.\n\n"
        "=== TEXTE SOURCE ===\n" + source_text[:14000])
    d = claude_json(client, prompt, ITEM_SCHEMA, model=MODEL_SYNTH, max_tokens=4500)
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
    if item.get("if_approx") is not None:
        out["impact_factor"] = item["if_approx"]
    comparaisons = [c for c in d.get("comparaisons", []) if c.get("points")]
    if comparaisons:
        out["comparaisons"] = comparaisons
    if d.get("a_ce_qui_change") and d.get("ce_qui_change_points"):
        out["ce_qui_change"] = {
            "reference": d.get("ce_qui_change_reference") or "pratique antérieure",
            "points": d["ce_qui_change_points"],
        }
    pav = [p for p in d.get("points_a_verifier", []) if p]
    if pav:
        out["points_a_verifier"] = pav
    return out, d.get("confiance", "moyenne")


def verify_synthesis(client, out: dict, source_text: str) -> tuple[bool, list[str]]:
    """Second appel : chaque chiffre/affirmation du résumé + message figure-t-il
    bien dans la source ? Renvoie (valide, problèmes)."""
    a_verifier = f"RÉSUMÉ :\n{out['resume']}\n\nMESSAGE CLÉ :\n{out['message_cle']}"
    prompt = (
        "Tu es vérificateur factuel d'un digest médical. On te donne un TEXTE "
        "SOURCE (abstract ou texte intégral) et une SYNTHÈSE rédigée à partir de "
        "lui. Vérifie que CHAQUE chiffre (effectif, %, HR/RR/OR, p, IC, posologie, "
        "seuil) et CHAQUE affirmation factuelle de la synthèse figure bien dans le "
        "texte source, sans déformation. Signale en particulier : un chiffre "
        "absent ou modifié ; un résultat de sous-groupe présenté comme résultat "
        "principal ; une conclusion plus forte que ce que dit la source. Ne juge "
        "pas le style ni les mises en contexte générales. Réponds valide=false s'il "
        "existe au moins un problème factuel, et liste les problèmes.\n\n"
        f"=== TEXTE SOURCE ===\n{source_text[:14000]}\n\n=== SYNTHÈSE ===\n{a_verifier}")
    d = claude_json(client, prompt, VERIFY_SCHEMA, model=MODEL_SYNTH, max_tokens=1200)
    return bool(d.get("valide")), [p for p in d.get("problemes", []) if p]


def load_pnds_for_week(start: dt.date, end: dt.date) -> list[dict]:
    """PNDS (HAS) parus dans la semaine, depuis le registre suivi.

    La HAS ne publiant pas de flux exploitable, on tient un petit registre
    (content/pnds.yaml). Chaque entrée entièrement rédigée dont la date tombe
    dans la semaine devient un item « pnds » du numéro, avec son avant/après.
    """
    if not PNDS_REGISTRY.exists():
        return []
    data = yaml.safe_load(PNDS_REGISTRY.read_text(encoding="utf-8")) or {}
    out = []
    for e in data.get("pnds", []) or []:
        d = e.get("date")
        if not isinstance(d, dt.date):
            try:
                d = dt.datetime.strptime(str(d), "%Y-%m-%d").date()
            except Exception:
                continue
        if not (start <= d <= end):
            continue
        if not e.get("resume"):
            print(f"  ! PNDS « {e.get('titre', '?')} » sans résumé rédigé — ignoré")
            continue
        item = {
            "type": "pnds",
            "titre": e["titre"],
            "source": e.get("source", "HAS · Protocole National de Diagnostic et de Soins"),
            "url": e.get("url"),
            "base_texte": e.get("base_texte", "abstract_seul"),
            "resume": e["resume"],
            "message_cle": e.get("message_cle", ""),
            "contexte": e.get("contexte", []),
        }
        if e.get("statut"):
            item["pnds_statut"] = e["statut"]
        if e.get("comparaisons"):
            item["comparaisons"] = e["comparaisons"]
        out.append(item)
    return out


def next_numero(exclude: Path | None = None) -> int:
    n = 0
    for path in ISSUES.glob("*.yaml"):
        if exclude and path == exclude:
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            n = max(n, int(data.get("numero", 0)))
        except Exception:
            pass
    return n + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    # Plafond de sécurité (coût/temps CI), pas un objectif de volume.
    parser.add_argument("--max-items", type=int, default=15)
    parser.add_argument("--force", action="store_true",
                        help="régénère même si un numéro existe déjà pour aujourd'hui")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY manquante.")

    today = dt.date.today()
    out_path = ISSUES / f"{today.isoformat()}.yaml"
    if out_path.exists() and not args.force:
        print(f"Un numéro existe déjà pour {today.isoformat()} — rien à faire "
              f"(--force pour régénérer).")
        return

    client = anthropic.Anthropic()
    start = today - dt.timedelta(days=args.days - 1)
    semaine = (f"{start.day} {MOIS_FR[start.month - 1]} au "
               f"{today.day} {MOIS_FR[today.month - 1]} {today.year}")

    print(f"Recherche PubMed médecine interne ({args.days} j)…")
    candidates = search_candidates(args.days)
    print(f"  {len(candidates)} candidats bruts")

    try:
        selected, aussi_refs = (select_items(client, candidates, args.max_items)
                                if candidates else ([], []))
    except Exception as e:
        print(f"  ! sélection échouée : {e}")
        selected, aussi_refs = [], []
    print(f"  {len(selected)} items retenus, {len(aussi_refs)} en « aussi parus »")

    items = []
    downgraded = []
    for it in selected:
        pmcid = get_pmcid(it["pmid"])
        abstract = fetch_abstract(it["pmid"])
        fulltext = fetch_fulltext(it["pmid"], pmcid)
        source_text = (abstract + "\n\n" + fulltext).strip() or it["titre"]
        try:
            out, confiance = synthesize(client, it, source_text)
        except Exception as e:
            print(f"  ! synthèse échouée pour {it['pmid']} ({e}) — passe en aussi paru")
            downgraded.append(it)
            continue
        try:
            valide, problemes = verify_synthesis(client, out, source_text)
        except Exception as e:
            valide, problemes = False, [f"vérification impossible: {e}"]
        if confiance == "faible" or not valide:
            raison = "confiance faible" if confiance == "faible" else "; ".join(problemes)[:140]
            print(f"  ↓ rétrogradé {it['pmid']} → aussi paru ({raison})")
            downgraded.append(it)
        else:
            items.append(out)
        time.sleep(0.4)

    # Les items rétrogradés rejoignent les « aussi parus » (résumé court).
    aussi_parus = synthesize_brief(client, aussi_refs + downgraded)

    pnds_items = load_pnds_for_week(start, today)
    if pnds_items:
        print(f"  {len(pnds_items)} PNDS de la semaine ajouté(s) depuis le registre")
    # Les PNDS ouvrent le numéro (documents de référence pour la pratique française).
    items = pnds_items + items

    issue = {
        "numero": next_numero(exclude=out_path),
        "semaine": semaine,
        "date": today.isoformat(),
        "edito": ("Sélection et synthèses des publications de médecine interne de "
                  "la semaine, générées automatiquement par IA sans relecture "
                  "humaine, puis vérifiées automatiquement face à leur source. "
                  "Chaque item renvoie à sa source."
                  if items else
                  "Semaine calme : aucune publication majeure de médecine interne "
                  "retenue cette semaine par la sélection automatique."),
        "items": items,
    }
    if aussi_parus:
        issue["aussi_parus"] = aussi_parus

    ISSUES.mkdir(parents=True, exist_ok=True)
    header = "# Numéro généré automatiquement par IA, sans relecture humaine.\n"
    out_path.write_text(
        header + yaml.safe_dump(issue, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8")
    print(f"✓ écrit {out_path.relative_to(ROOT)} "
          f"({len(items)} items, {len(aussi_parus)} aussi parus, {len(downgraded)} rétrogradés)")


if __name__ == "__main__":
    main()
