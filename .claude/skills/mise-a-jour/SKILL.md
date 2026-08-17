---
name: mise-a-jour
description: Génère et publie le numéro hebdomadaire de ThisWeek (veille de médecine interne). À utiliser quand l'utilisateur dit « mise à jour », « nouveau numéro », « génère le numéro de la semaine », ou lance /mise-a-jour — typiquement le lundi.
---

# Mise à jour hebdomadaire de ThisWeek

Objectif : produire le numéro de la semaine, le publier, et signaler franchement
ce qui n'a pas marché. Le produit est une veille de médecine interne pour
internistes français, générée par IA sans relecture humaine (parti pris assumé
et affiché sur le site).

## 1. Situer la semaine

```bash
date -u +"%Y-%m-%d %A"
ls content/issues/ | tail -3
```

Le numéro se date du **lundi** et couvre les 7 jours écoulés. Vérifier qu'aucun
numéro n'existe déjà pour cette date, et repérer un éventuel **trou** de semaine
depuis le dernier numéro (c'est déjà arrivé deux fois) : si un trou existe, le
signaler à l'utilisateur et proposer de le combler.

## 2. Générer

**Si `ANTHROPIC_API_KEY` est disponible**, le pipeline fait tout :

```bash
python3 pipeline/generate_issue.py --days 7
```

Toute la chaîne éditoriale tourne sur **Opus 5** (`MODEL_SELECT` et
`MODEL_SYNTH` dans `pipeline/generate_issue.py`). Le pipeline exécute deux
recherches PubMed (générale + une dédiée aux recommandations, pour qu'elles ne
soient jamais noyées par le volume des méta-analyses), sélectionne, synthétise,
puis **vérifie** chaque synthèse face à sa source — et rétrograde en « Aussi
paru » tout item dont un chiffre n'est pas retrouvé ou dont la confiance est
faible.

**Si la clé est absente** (cas actuel de cet environnement), faire le travail à
la main, sans jamais rien inventer :

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
(`efetch`, `rettype=abstract`) et rédiger le YAML dans `content/issues/`.
Vérifier qu'aucun PMID n'a déjà été publié :

```bash
grep -rho 'pubmed.ncbi.nlm.nih.gov/[0-9]*' content/issues/*.yaml | grep -o '[0-9]*$' | sort -u
```

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
