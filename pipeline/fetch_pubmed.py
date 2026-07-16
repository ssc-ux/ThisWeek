#!/usr/bin/env python3
"""Prépare la page « Veille » : candidats PubMed des 7 derniers jours.

Utilise EXACTEMENT la même recherche « médecine interne » que la génération du
numéro (`pipeline/pubmed_query.py`) : la veille affichée reflète donc bien le
vivier dans lequel le numéro est sélectionné (une seule vérité). Les candidats
sont répartis en deux rubriques (recommandations/consensus, essais/méta) pour
l'affichage. Aucun résumé n'est généré ici — ce script ne fait que collecter.

Usage : python3 pipeline/fetch_pubmed.py [--days 7]
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import yaml

from pubmed_query import bucket, search_internal_medicine

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    docs = search_internal_medicine(args.days, retmax=200)
    reco, essai = bucket(docs)
    print(f"reco   : {len(reco)} candidats")
    print(f"essai  : {len(essai)} candidats")

    draft: dict = {
        "genere_le": date.today().isoformat(),
        "periode_jours": args.days,
        "note": (
            "Brouillon automatique : candidats PubMed (même recherche que le "
            "numéro). Étapes suivantes : sélection + synthèse par IA "
            "(pipeline/generate_issue.py)."
        ),
        "candidats": {"reco": reco, "essai": essai},
    }

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
