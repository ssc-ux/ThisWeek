# 04 — Feuille de route

Principe directeur : **valider la valeur éditoriale avant de construire de la
plomberie**. Le risque n° 1 n'est pas technique (le pipeline est classique),
c'est : « est-ce que des internistes lisent le digest et lui font confiance ? ».

## Phase 0 — Prototype manuel assisté (2–4 semaines)

Objectif : produire 3 à 4 numéros réels, sans presque aucun code.

- [ ] Figer le gabarit d'un item (les 5 sections) et la maquette du digest
      (cf. [exemple-digest.md](exemple-digest.md)).
- [ ] Choisir ~10 sources ★★★ (cf. [02-sources.md](02-sources.md)) et vérifier
      à la main leurs flux RSS / pages.
- [ ] Chaque semaine : collecter manuellement les nouveautés, générer les
      synthèses avec un LLM via des prompts standardisés (stockés dans ce
      repo), relire, corriger, envoyer à un cercle de 10–30 internistes
      (collègues, société savante junior…).
- [ ] Recueillir les retours : items manqués ? synthèses justes ? longueur ?
- **Critère de sortie** : les lecteurs ouvrent le mail chaque semaine et au
  moins quelques-uns disent spontanément qu'il leur manque quand il ne part pas.

Livrables dans le repo : `prompts/` (scoring, synthèse, vérification),
`sources/sources.yaml` (registre v1), 4 numéros publiés.

## Phase 1 — Automatiser l'ingestion et le tri (4–8 semaines)

Objectif : passer de « je cherche les items » à « les items m'attendent triés ».

- [ ] Connecteurs RSS + PubMed E-utilities + Europe PMC → SQLite/Postgres.
- [ ] Normalisation, dédoublonnage DOI/PMID/titre.
- [ ] Règles dures + scoring LLM ; jeu d'évaluation de ~100 items étiquetés,
      mesure rappel/précision à chaque itération de prompt.
- [ ] Sortie : un fichier Markdown hebdomadaire « candidats de la semaine »
      avec scores et justifications — la sélection finale reste humaine.
- **Critère de sortie** : sur 4 semaines consécutives, aucun item majeur
  manqué par le pipeline par rapport à la veille manuelle.

## Phase 2 — Automatiser la synthèse et la relecture (4–8 semaines)

- [ ] Génération automatique des synthèses (avec citations) + appel de
      vérification.
- [ ] Interface de relecture (même minimale) avec conservation des diffs
      relecteur ; mesure du temps de relecture hebdomadaire.
- [ ] Surveillance de pages pour les sources sans flux (PNDS, sociétés
      savantes françaises).
- [ ] Historisation des versions de recos pour la section « ce qui change ».
- **Critère de sortie** : produire le digest complet en < 1 h de travail
  humain par semaine, sans baisse de qualité perçue par les lecteurs.

## Phase 3 — Produit public (ensuite)

- [ ] Archive web consultable + recherche par pathologie/thème.
- [ ] Inscription publique, gestion des abonnés (RGPD), feedback 👍/👎 par item.
- [ ] Statut juridique, mentions légales, comité éditorial nommé.
- [ ] Éventuellement : déclinaisons par sous-profil (interniste hospitalier vs
      libéral), puis autres spécialités (le pipeline est générique, seuls le
      registre de sources et les prompts de scoring changent).

## Décisions à prendre rapidement (bloquantes pour la phase 0)

1. **Langue du digest** : français (recommandé — c'est la niche), avec les
   items anglophones résumés en français.
2. **Jour et heure d'envoi** : ex. vendredi 18 h ou dimanche matin — à tester.
3. **Qui relit** : au minimum vous-même ; idéalement un binôme pour la
   robustesse (congés, charge).
4. **Nom et identité** : « ThisWeek » est le nom de code du repo ; le nom
   public peut attendre la phase 3.

## Ce qu'on refuse de faire au MVP (liste anti-dérive)

- Pas d'app mobile.
- Pas de chatbot.
- Pas de couverture multi-spécialités.
- Pas de personnalisation par lecteur.
- Pas de traduction automatique intégrale des recos (résumé seulement + lien).
