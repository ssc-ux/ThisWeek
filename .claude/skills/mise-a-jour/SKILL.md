---
name: mise-a-jour
description: Génère et publie le numéro hebdomadaire de ThisWeek (veille de médecine interne). À utiliser quand l'utilisateur dit « mise à jour », « nouveau numéro », « génère le numéro de la semaine », ou lance /mise-a-jour — typiquement le lundi.
---

# Mise à jour hebdomadaire de ThisWeek

Objectif : produire le numéro de la semaine, le publier, et signaler franchement
ce qui n'a pas marché. Le produit est une veille de médecine interne pour
internistes français, générée par IA sans relecture humaine du contenu (parti
pris assumé et affiché sur le site) — mais **déclenchée à la main** : le
mainteneur a tranché, `ANTHROPIC_API_KEY` ne sera pas configurée en secret de
dépôt, donc `pipeline/generate_issue.py` ne tourne jamais tout seul via GitHub
Actions (son déclenchement planifié est désactivé pour cette raison, voir
`.github/workflows/weekly-issue.yml`). **C'est cette session Claude Code, avec
toi, qui fait le travail décrit ci-dessous — pas un cron.**

## 1. Situer la semaine

```bash
date -u +"%Y-%m-%d %A"
ls content/issues/ | tail -3
```

Le numéro se date en général du **lundi** et couvre les 7 jours écoulés, mais
rien n'oblige à un jour fixe puisque c'est déclenché à la main : générer pour
la période réellement écoulée depuis le dernier numéro. Vérifier qu'aucun
numéro n'existe déjà pour cette date, et repérer un éventuel **trou** de
semaine depuis le dernier numéro (c'est déjà arrivé deux fois) : si un trou
existe, le signaler à l'utilisateur et proposer de le combler.

## 2. Générer

Chercher les candidats PubMed réels (deux recherches : générale + une dédiée
aux recommandations, pour qu'elles ne soient jamais noyées par le volume des
méta-analyses) :

```bash
cd pipeline && python3 -c "
import datetime as dt, pubmed_query as q
docs = q.search_internal_medicine(7); recos = q.search_recommendations(7)
for lbl, ds in [('RECOS', recos), ('GÉNÉRAL', docs)]:
    print(f'--- {lbl} : {len(ds)} ---')
    for d in ds: print(d['pmid'], '|', d['revue'][:34], '|', d['titre'][:80])
"
```

Puis récupérer les **abstracts réels** des candidats retenus via E-utilities
(`efetch`, `rettype=abstract`) et rédiger le YAML dans `content/issues/`,
exactement comme pour tous les numéros précédents de ce dépôt — aucun chiffre
inventé, tout vient de l'abstract lu. Vérifier qu'aucun PMID n'a déjà été
publié :

```bash
grep -rho 'pubmed.ncbi.nlm.nih.gov/[0-9]*' content/issues/*.yaml | grep -o '[0-9]*$' | sort -u
```

**Repli Unpaywall pour le texte intégral** : `pipeline/pubmed_query.py:unpaywall_lookup(doi)`
repère une version en accès libre légale d'un article (Europe PMC en premier,
Unpaywall ensuite). Utile pour savoir où chercher, mais l'extraction
automatique du texte échoue la plupart du temps (mur anti-robot des éditeurs,
~0 % mesuré sur les articles hors PMC) — ne pas s'attendre à ce que ça
fonctionne systématiquement, et ne jamais tenter de contourner un blocage (403,
CAPTCHA, mur JavaScript).

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
