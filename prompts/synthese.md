# Prompts — Synthèse puis vérification d'un item

> Source de vérité : `pipeline/generate_issue.py`, fonctions `synthesize`
> (schéma `ITEM_SCHEMA`) et `verify_synthesis` (schéma `VERIFY_SCHEMA`). Ces
> deux appels tournent sur un modèle de haut niveau (`MODEL_SYNTH`).

## 1. Synthèse (`synthesize`)

À partir du texte source (texte intégral libre si disponible, sinon abstract —
la base est précisée), l'IA produit un objet structuré :

- `resume` — 5 à 10 lignes factuelles. **Aucun chiffre** (posologie, seuil,
  HR/RR/OR, p, IC, effectif) absent du texte source. **Règle anti-sous-groupe** :
  si le critère de jugement principal est négatif, énoncer d'abord ce résultat,
  et ne jamais présenter un sous-groupe comme le résultat principal (le qualifier
  d'« analyse de sous-groupe exploratoire, génératrice d'hypothèses »).
- `a_ce_qui_change` / `ce_qui_change_reference` / `ce_qui_change_points` —
  uniquement si le document décrit lui-même un changement ; jamais de diff déduit.
- `comparaisons` — **pour les reco et PNDS uniquement** : jusqu'à trois axes
  (version précédente ; autres grandes recommandations internationales ;
  recommandations françaises / PNDS). Peut s'appuyer sur des connaissances
  générales, sans rien inventer de précis ; affiché avec un avertissement
  « à vérifier ». Vide pour les autres types.
- `message_cle` — 1 à 3 phrases actionnables.
- `contexte` — 3 à 4 paragraphes (maladie et place en médecine interne, standard
  de prise en charge, où s'inscrit l'étude, pertinence française, limites).
- `base_texte` — `texte_integral` ou `abstract_seul`.
- `confiance` — `elevee` / `moyenne` / `faible` ; abaissée dès que le texte est
  ambigu, partiel, ou que l'IA extrapole.
- `points_a_verifier` — liste des points qu'un relecteur contrôlerait en priorité.

## 2. Vérification (`verify_synthesis`)

Un **second appel** relit `resume` + `message_cle` face au texte source et
vérifie que chaque chiffre et chaque affirmation factuelle y figure sans
déformation (signale notamment : chiffre absent/modifié, sous-groupe présenté
comme résultat principal, conclusion plus forte que la source). Il renvoie
`{valide: bool, problemes: [...]}`.

## Rétrogradation

Si `confiance == faible` **ou** `valide == false`, l'item n'est pas publié en
synthèse détaillée : il est **rétrogradé en « Aussi paru »** (résumé court). Ce
mécanisme est automatique — ce n'est pas une relecture médicale.
