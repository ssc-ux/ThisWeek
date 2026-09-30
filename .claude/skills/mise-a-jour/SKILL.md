---
name: mise-a-jour
description: Génère et publie le numéro hebdomadaire de ThisWeek (veille de médecine interne). À utiliser quand l'utilisateur dit « mise à jour », « nouveau numéro », « génère le numéro de la semaine », ou lance /mise-a-jour — typiquement le lundi.
---

# Mise à jour hebdomadaire de ThisWeek

Objectif : produire le numéro de la semaine, le publier, et signaler franchement
ce qui n'a pas marché. Le produit est une veille de médecine interne pour
internistes français, générée par IA sans relecture humaine du contenu (parti
pris assumé et affiché sur le site). `ANTHROPIC_API_KEY` ne sera jamais
configurée en secret de dépôt : `pipeline/generate_issue.py` ne tourne pas via
GitHub Actions (déclenchement planifié désactivé, voir
`.github/workflows/weekly-issue.yml`). **C'est une session Claude Code qui fait
le travail décrit ci-dessous**, lancée de deux façons :

- à la main, quand le mainteneur écrit « mise à jour » ;
- **automatiquement chaque lundi**, par une Routine Claude Code (tâche
  planifiée côté claude.ai, pas dans ce dépôt) qui relance la session.

**Exécution automatique = personne devant l'écran.** Dans ce cas : ne poser
aucune question et ne rien attendre de l'utilisateur ; sauter l'étape 2 bis
(texte intégral fourni à la main) ; combler un éventuel trou de semaines sans
demander ; publier ; puis laisser en fin de session un compte rendu complet
(étape 6), que le mainteneur lira à son retour.

**Conteneur neuf à chaque session** : installer d'abord les dépendances du
build et se resynchroniser avec la branche distante.

```bash
pip install -q pyyaml jinja2 markdown
git pull -q origin claude/medical-guidelines-digest-3w16xl
```

## 1. Situer la semaine

```bash
date -u +"%Y-%m-%d %A"
ls content/issues/ | tail -3
```

Le numéro se date en général du **lundi** et couvre les 7 jours écoulés, mais
il faut couvrir la période réellement écoulée depuis le dernier numéro.
Vérifier qu'aucun numéro n'existe déjà pour cette date, et repérer un éventuel
**trou** de semaines (c'est arrivé plusieurs fois) : le combler en produisant
un numéro par semaine manquante, chaque article étant rattaché à sa semaine
d'après sa date `sortpubdate` exacte.

## 2. Générer

Chercher les candidats PubMed réels par **trois** recherches, puis les classer
par date exacte (`sortpubdate`) pour ne garder que la semaine visée :

- générale et recommandations, par termes MeSH et types de publication ;
- **titre/résumé** (`search_recent_tiab`), indispensable : les champs MeSH et
  types de publication n'existent qu'après l'indexation MEDLINE, qui prend des
  jours à des semaines. Sans cette recherche, un article publié dans la semaine
  mais pas encore indexé est perdu définitivement (mesuré le 30/09/2026 :
  5 candidats par MeSH, 26 par titre/résumé). Elle est plus bruitée : le tri
  éditorial fait le reste.

```bash
cd pipeline && python3 -c "
import pubmed_query as q
reco = {d['pmid'] for d in q.search_recommendations(10)}
ids = []
for d in q.search_recommendations(10) + q.search_internal_medicine(10) + q.search_recent_tiab(10):
    if d['pmid'] not in ids: ids.append(d['pmid'])
r = q.eutils_get('esummary.fcgi', {'db':'pubmed','id':','.join(ids),'version':'2.0'})['result']
for x in sorted((r[p].get('sortpubdate','')[:10], p, ('RECO ' if p in reco else '     ') + r[p].get('source','')[:26], r[p].get('title','')[:90]) for p in r['uids']):
    print(' | '.join(x))
"
```

Ajuster `10` si un trou de plusieurs semaines est à combler. Un article dont la
date tombe après la fin de la semaine visée appartient au numéro suivant.
Écarter les articles sans résultats (protocoles, « design and rationale »).

Puis récupérer les **abstracts réels** des candidats retenus via E-utilities
(`efetch`, `rettype=abstract`) et rédiger le YAML dans `content/issues/`,
exactement comme pour tous les numéros précédents de ce dépôt — aucun chiffre
inventé, tout vient de l'abstract lu. Vérifier qu'aucun PMID n'a déjà été
publié :

```bash
grep -rho 'pubmed.ncbi.nlm.nih.gov/[0-9]*' content/issues/*.yaml | grep -o '[0-9]*$' | sort -u
```

**Texte intégral : ordre des tentatives.** `fetch_fulltext(pmid, pmcid)` essaie
Europe PMC, puis `efetch db=pmc` du NCBI (Europe PMC est en retard sur les
articles très récents et répond 404 alors que le dépôt PMC existe). En dernier
recours seulement, `fetch_fulltext_unpaywall(doi)` cherche une version en accès
libre légale ailleurs ; l'adresse de contact exigée par Unpaywall est
configurée en dur dans `pubmed_query.py`.

Deux garde-fous à ne jamais relâcher :

- `get_pmcid()` ne doit accepter que `linkname == "pubmed_pmc"`. Le jeu
  `pubmed_pmc_refs` liste les articles **qui citent** la publication : s'en
  servir ferait résumer un article sans rapport sous le titre et le lien de la
  source. Le bug a existé, il a été corrigé le 25/08/2026.
- Ne jamais tenter de contourner un blocage (403, CAPTCHA, mur JavaScript).

Rendement réel, mesuré sur les 7 articles du numéro 16 : PMC donne le texte de
ceux qui y sont déposés ; Unpaywall n'en a ajouté **aucun** (les éditeurs
bloquent les requêtes automatiques même quand une version libre existe). Ne pas
compter dessus, et se méfier du texte qu'il renvoie parfois : sur un des
articles, c'était une page d'atterrissage pleine de menus et de publicités, pas
l'article. Vérifier que le texte récupéré commence bien par le bon article.

**Note pour une éventuelle utilisation future du pipeline complet** (si le choix
de rester manuel changeait un jour) : `pipeline/generate_issue.py --days 7`
ferait tout automatiquement — sélection, synthèse, et une passe de
**vérification** qui rétrograde en « Aussi paru » tout item dont un chiffre
n'est pas retrouvé ou dont la confiance est faible. Toute la chaîne tourne sur
**Opus 5** (`MODEL_SELECT`/`MODEL_SYNTH`). Ce code est maintenu et testé
syntaxiquement, mais n'a jamais tourné en conditions réelles dans ce projet.

## 2 bis. Texte intégral manuel pour l'item phare (optionnel)

Pour l'article le plus important de la semaine, si l'automatique n'a rien
donné : proposer à l'utilisateur d'ouvrir l'article avec son accès
institutionnel (université) et de coller les sections Méthodes/Résultats. Ne
JAMAIS demander ses identifiants ni tenter de se connecter à sa place — c'est
lui qui lit ce qu'il a le droit de lire, l'IA ne fait que rédiger la synthèse
sur le texte qu'il transmet. Le site ne republie jamais ce texte, seulement la
synthèse et un lien vers la source. Marquer `base_texte: texte_integral` dans
ce cas. Ne pas insister si l'utilisateur préfère passer directement à l'étape
suivante avec l'abstract seul — c'est optionnel, pas un blocage.

## 3. Règles éditoriales non négociables

- **Aucun chiffre inventé** : tout HR, %, effectif, IC vient de l'abstract lu.
- **Critère principal d'abord** : si l'essai est négatif sur son critère
  principal, le dire en premier ; un sous-groupe favorable est qualifié
  d'« analyse exploratoire, génératrice d'hypothèses ».
- **Pas de causalité sur de l'observationnel** : « associé à », jamais
  « provoque » / « réduit », pour une cohorte, un registre ou une méta-analyse
  d'études non randomisées. Signaler le facteur confondant probable.
- **Recommandations** : uniquement les textes **internationaux** de grandes
  sociétés savantes (EULAR, ACR, ASH, KDIGO, ISTH…) ou les **références
  françaises** (HAS, PNDS, filières). Les consensus nationaux d'autres pays
  (mexicain, coréen, chinois…) sont écartés.
- **Périmètre** : maladies auto-immunes et systémiques, vascularites,
  auto-inflammatoire, sarcoïdose, amylose, IgG4, hématologie non maligne,
  MTEV/SAPL, infectiologie complexe, immunodéprimé. **La polyarthrite
  rhumatoïde pure est hors périmètre** (rhumatologie) — sauf si l'item porte sur
  la tolérance transversale d'un traitement utilisé en médecine interne.
- **Semaine calme = numéro court.** Publier 1 ou 2 items solides plutôt que
  gonfler avec des items tièdes, et le dire dans l'édito. Ne jamais sauter une
  semaine.
- Mentionner « hors AMM en France » quand c'est le cas.

## 4. Construire et vérifier

```bash
python3 site/build.py
```

Le build valide le YAML et échoue explicitement si un champ requis manque.
Vérifier ensuite **en HTTP réel** (la recherche utilise `fetch`, qui est bloqué
par CORS en `file://` — un test en `file://` donnerait un faux négatif) :

```bash
cd dist && python3 -m http.server 8532 &
```

Puis avec Playwright (`executablePath: '/opt/pw-browsers/chromium'`,
`NODE_PATH=/opt/node22/lib/node_modules`) : ouvrir l'accueil et le nouveau
numéro, tester la recherche, capturer desktop + mobile, et vérifier l'absence
d'erreur console et de débordement horizontal.

## 5. Publier

```bash
git add -A && git commit && git push origin HEAD:main
```

Pousser aussi sur la branche de travail `claude/medical-guidelines-digest-3w16xl`.

## 6. Rendre compte, sans enjoliver

Dire à l'utilisateur : les items retenus et pourquoi, **les candidats écartés et
pour quel motif**, et tout ce qui a échoué ou n'a pas pu être vérifié. Si le
numéro a été rédigé à la main faute de clé API, le dire — la passe de
vérification automatique n'a alors pas tourné.
