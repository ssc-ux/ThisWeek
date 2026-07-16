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

# Impact factor APPROXIMATIF des revues, uniquement pour départager des articles
# de pertinence comparable. Valeurs indicatives (ordre de grandeur), pas des
# chiffres officiels. Motifs testés sur le nom complet de la revue en minuscules,
# du plus spécifique au plus générique (un sous-journal du Lancet doit primer sur
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
            revue = doc.get("fulljournalname") or doc.get("source", "")
            out.append({
                "pmid": pmid,
                "titre": doc.get("title", "").rstrip("."),
                "revue": revue,
                "date_publication": doc.get("pubdate", ""),
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "pubtypes": doc.get("pubtype", []),
                "if_approx": journal_if(revue),
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
        # Publications pertinentes pour un interniste mais non retenues pour une
        # synthèse complète : elles alimentent la rubrique « Aussi parus ».
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
        # Comparaisons détaillées, remplies pour les recommandations et PNDS :
        # axes « version précédente », « autres grandes recommandations » et
        # « recommandations françaises / PNDS ». Vide pour les autres types.
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
    },
    "required": ["resume", "message_cle", "contexte", "base_texte",
                 "a_ce_qui_change", "ce_qui_change_reference", "ce_qui_change_points",
                 "comparaisons"],
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


def synthesize_brief(client, refs: list[dict]) -> list[dict]:
    """Résumé court (2-3 phrases) pour chaque « aussi paru », ancré sur l'abstract.

    Une seule requête Claude pour tout le lot (économe), à partir des abstracts
    réels. Aucun chiffre inventé.
    """
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
    data = claude_json(client, prompt, BRIEF_SCHEMA, max_tokens=3000)
    by = {d["pmid"]: d["resume"] for d in data.get("resumes", [])}
    out = []
    for r in refs:
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
        "élevé, sans jamais faire de l'IF un critère supérieur à la pertinence.\n\n"
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
    data = claude_json(client, prompt, SELECT_SCHEMA, max_tokens=3000)
    by_pmid = {c["pmid"]: c for c in candidates}
    picked = []
    seen = set()
    # Plafond de sécurité (coût/temps CI), pas un objectif : très au-dessus d'une
    # semaine normale, donc sans effet en pratique.
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


def synthesize(client, item: dict, source_text: str) -> dict:
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
        "s'ils figurent dans le texte) ;\n"
        "- a_ce_qui_change : true seulement si le texte décrit explicitement un "
        "changement par rapport à une version antérieure ou à la pratique "
        "standard ; sinon false ;\n"
        "- ce_qui_change_reference : la référence du diff (ex. 'version 2021', "
        "'pratique antérieure') si a_ce_qui_change, sinon chaîne vide ;\n"
        "- ce_qui_change_points : liste de points (vide si a_ce_qui_change=false) ;\n"
        + comp_instr +
        "- message_cle : 1 à 3 phrases actionnables ;\n"
        "- contexte : liste de 3 à 4 paragraphes détaillés expliquant la maladie "
        "et sa place en médecine interne, le standard de prise en charge actuel, "
        "pourquoi cette étude et où elle s'inscrit, et la pertinence pour la "
        "pratique française (centres de référence, AMM, remboursement) ainsi que "
        "les limites ;\n"
        "- base_texte : 'texte_integral' si le texte fourni dépasse l'abstract, "
        "sinon 'abstract_seul'.\n"
        "Le resume et les chiffres ne doivent venir QUE du texte source. Les "
        "comparaisons peuvent s'appuyer sur des connaissances générales, mais sans "
        "rien inventer de précis.\n\n"
        "=== TEXTE SOURCE ===\n" + source_text[:14000])
    d = claude_json(client, prompt, ITEM_SCHEMA, max_tokens=4500)
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
    if item.get("pnds_statut"):
        out["pnds_statut"] = item["pnds_statut"]
    comparaisons = [c for c in d.get("comparaisons", []) if c.get("points")]
    if comparaisons:
        out["comparaisons"] = comparaisons
    if d.get("a_ce_qui_change") and d.get("ce_qui_change_points"):
        out["ce_qui_change"] = {
            "reference": d.get("ce_qui_change_reference") or "pratique antérieure",
            "points": d["ce_qui_change_points"],
        }
    return out


PNDS_REGISTRY = ROOT / "content" / "pnds.yaml"


def load_pnds_for_week(start: dt.date, end: dt.date) -> list[dict]:
    """PNDS (HAS) parus dans la fenêtre de la semaine, depuis le registre suivi.

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
    # Plafond de sécurité (coût/temps CI), pas un objectif de volume : le nombre
    # réel d'items dépend de ce qui a été publié dans la semaine.
    parser.add_argument("--max-items", type=int, default=15)
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

    selected, aussi_refs = (select_items(client, candidates, args.max_items)
                            if candidates else ([], []))
    print(f"  {len(selected)} items retenus, {len(aussi_refs)} en « aussi parus »")

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

    aussi_parus = synthesize_brief(client, aussi_refs)

    pnds_items = load_pnds_for_week(start, today)
    if pnds_items:
        print(f"  {len(pnds_items)} PNDS de la semaine ajouté(s) depuis le registre")
    # Les PNDS ouvrent le numéro (documents de référence pour la pratique française).
    items = pnds_items + items

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
    if aussi_parus:
        issue["aussi_parus"] = aussi_parus

    ISSUES.mkdir(parents=True, exist_ok=True)
    out_path = ISSUES / f"{today.isoformat()}.yaml"
    header = ("# Numéro généré automatiquement par IA, sans relecture humaine.\n")
    out_path.write_text(
        header + yaml.safe_dump(issue, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8")
    print(f"✓ écrit {out_path.relative_to(ROOT)} ({len(items)} items)")


if __name__ == "__main__":
    main()
