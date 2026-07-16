# Prompt — Sélection (tri des candidats)

> Source de vérité : `pipeline/generate_issue.py`, fonction `select_items`
> (schéma `SELECT_SCHEMA`). Ce fichier documente le prompt réellement utilisé ;
> il est tenu à jour avec le code. Le tri tourne sur un modèle léger
> (`MODEL_SELECT`).

L'IA reçoit la liste des candidats PubMed de la semaine (format
`PMID | revue | IF≈ | types | titre`) et rend **deux listes** :

- **`items`** — les publications vraiment marquantes, à synthétiser en détail
  (PMID, `type` ∈ {reco, pnds, essai, meta, alerte, autre}, titre reformulé en
  français). **Pas de nombre imposé** : le volume suit ce qui a été publié.
- **`aussi_parus`** — les autres publications pertinentes, qui recevront un
  résumé court (PMID + titre).

Critères de sélection, par ordre de priorité :

1. **Pertinence** pour un service de médecine interne français (périmètre
   strict : maladies systémiques et auto-immunes, vascularites, auto-inflammatoire,
   sarcoïdose, amylose, IgG4, hématologie non maligne, MTEV/SAPL, infectiologie
   complexe, fièvre inexpliquée, immunodéprimé, polypathologie). Un article hors
   périmètre n'est jamais retenu, même prestigieux.
2. **Portée pratique** (reco/PNDS, essai de phase 3, méta-analyse structurante,
   alerte de sécurité). Les essais négatifs sont retenus s'ils recadrent la
   pratique.
3. À pertinence comparable, **impact factor** de la revue (indicatif) — sans
   jamais primer sur la pertinence, ni pénaliser une recommandation française
   (souvent sans IF).

Les publications rétractées sont exclues en amont (requête PubMed + filtre).
