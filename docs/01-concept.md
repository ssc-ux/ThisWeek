# 01 — Concept produit

## Le problème

Un médecin interniste doit couvrir un champ immense : maladies auto-immunes,
infectiologie, médecine vasculaire, hématologie non maligne, maladies rares…
Le flux de nouveautés est ingérable manuellement :

- **Recommandations** : HAS, PNDS des filières maladies rares, sociétés
  savantes françaises (SNFMI, SPILF, SFR…), européennes (ESC, EULAR, ERS,
  EASL…) et américaines (ACR, IDSA, ACP, KDIGO…). Publiées de façon
  irrégulière, sur des dizaines de sites différents, sans canal unifié.
- **Articles majeurs** : NEJM, Lancet, JAMA, Annals of Internal Medicine,
  BMJ + revues de spécialité. Des centaines d'articles par semaine, dont une
  poignée seulement change réellement la pratique.
- Les outils existants ne répondent pas exactement au besoin :
  - **UpToDate / DynaMed** : excellents comme référence *à la demande*, mais
    ne poussent pas une veille synthétique hebdomadaire, et couvrent mal les
    sources françaises (PNDS, HAS).
  - **Alertes PubMed / RSS** : exhaustives mais brutes — pas de tri, pas de
    synthèse, pas de mise en contexte.
  - **Newsletters existantes** (NEJM Journal Watch, Univadis…) : éditoriales
    et de qualité, mais généralistes, souvent anglophones, et ne couvrent pas
    les recommandations françaises.

**Le manque : personne ne dit à l'interniste francophone, chaque semaine, en
15 minutes de lecture : « voici ce qui est sorti, voici ce que ça change, voici
ce que tu dois retenir ».**

## La proposition de valeur

Un digest hebdomadaire (email + archive web) contenant 5 à 15 items triés par
pertinence, chacun présenté selon un gabarit fixe :

1. **Quoi** — titre, source, type (reco / PNDS / essai / méta-analyse / consensus), lien.
2. **Résumé** — 5 à 10 lignes, factuel.
3. **Ce qui change** — diff explicite avec la version précédente de la reco ou
   avec la pratique standard antérieure. C'est la section la plus
   différenciante : personne ne la fait systématiquement.
4. **Message à retenir** — 1 à 3 phrases actionnables.
5. **Mise en contexte** — niveau de preuve, limites, controverses, comment ça
   s'articule avec les autres référentiels (ex. divergence reco US vs
   européenne), pertinence pour la pratique française.

Principes éditoriaux :

- **Sélectivité assumée** : mieux vaut 8 items importants que 40 items exhaustifs.
  Une rubrique « aussi parus cette semaine » en liste brute pour l'exhaustivité.
- **Traçabilité** : chaque affirmation renvoie à la source primaire. Le digest
  est une porte d'entrée, pas un substitut à la lecture de la reco.
- **Transparence sur la méthode** : mention claire de ce qui est généré par IA
  et de ce qui est relu par un médecin.

## Personas

| Persona | Besoin | Usage |
|---|---|---|
| **Interniste hospitalier (CHU/CH)** | Rester à jour sur un champ très large, préparer les staffs | Lecture du digest le week-end, partage d'items en staff |
| **Interne / assistant en médecine interne** | Se constituer une culture des référentiels, préparer l'EDN/DES | Lecture + archive consultable par thème |
| **Interniste libéral / polyvalent** | Veille efficace sans temps dédié | Lecture rapide des « messages à retenir » |
| (plus tard) **Autres spécialités** | Même besoin, autre périmètre de sources | Déclinaisons par spécialité — le pipeline est réutilisable |

## Positionnement

- **Ce que c'est** : un outil de veille et de synthèse, avec relecture humaine,
  qui oriente vers les sources primaires.
- **Ce que ce n'est pas** : un outil d'aide à la décision au lit du malade, ni
  un dispositif médical (voir [05-risques-conformite.md](05-risques-conformite.md) —
  cette frontière conditionne le statut réglementaire).

## Modèle économique (pistes, à valider plus tard)

1. **Gratuit pendant la phase de validation** — l'enjeu initial est la qualité
   et la rétention des lecteurs, pas la monétisation.
2. Ensuite : abonnement individuel (comparable aux newsletters médicales
   payantes), licences institutionnelles (services hospitaliers, bibliothèques
   universitaires), ou sponsoring institutionnel *sans* publicité
   pharmaceutique (conflit d'intérêts rédhibitoire pour la crédibilité).

## Facteurs clés de succès

1. **La qualité de la sélection** — le tri est le produit. Un faux positif
   (item sans intérêt) coûte peu ; un faux négatif (reco majeure manquée)
   détruit la confiance.
2. **La justesse des synthèses** — une seule erreur factuelle grave peut tuer
   la crédibilité. D'où la relecture médicale systématique au début, et des
   synthèses qui citent leurs sources.
3. **La régularité** — même semaine creuse, le digest part à l'heure (quitte à
   être court : c'est aussi une information).
4. **La couverture des sources françaises** — c'est la niche défendable face
   aux acteurs anglophones.
