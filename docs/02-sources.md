# 02 — Inventaire des sources et modes d'accès

Le cœur du système est un **registre de sources** : chaque source est décrite
par son type, son mode d'accès technique, sa fréquence de publication et son
poids éditorial. Ce document sert de première version de ce registre.

> ⚠️ Les modes d'accès (existence d'un flux RSS, d'une API…) sont à **vérifier
> un par un** au moment de l'implémentation — les sites institutionnels
> changent souvent. La colonne « Accès pressenti » est une hypothèse de départ.

## 1. Recommandations françaises

| Source | Contenu | Accès pressenti | Priorité MVP |
|---|---|---|---|
| **HAS** (has-sante.fr) | Recommandations de bonne pratique, avis, fiches bon usage | Flux RSS par thème + surveillance des pages « publications » | ★★★ |
| **PNDS** (via HAS + filières maladies rares : FAI²R, MARIH, FAVA-Multi, G2M…) | Protocoles nationaux de diagnostic et de soins, maladies rares | Pas d'API unifiée → surveillance de la page HAS listant les PNDS + pages des filières | ★★★ |
| **SNFMI** (Société Nationale Française de Médecine Interne) | Recos, protocoles, La Revue de Médecine Interne | Surveillance site + RSS de la revue (Elsevier) | ★★★ |
| **SPILF** (infectiologie) | Recos infectiologie, avis | Surveillance site (infectiologie.com) | ★★ |
| **SFR** (rhumatologie), **SFD** (dermato), **SFNDT** (néphro), **SFC** (cardio)… | Recos de spécialités frontières de la médecine interne | Surveillance sites | ★★ |
| **ANSM** | Alertes de pharmacovigilance, MARR, retraits | RSS / page actualités | ★★ |
| **Santé publique France / HCSP / DGS-Urgent** | Avis, conduites à tenir (infectieux, vaccination) | RSS + emailing DGS-Urgent | ★★ |

## 2. Sociétés savantes internationales

| Source | Domaine | Accès pressenti | Priorité MVP |
|---|---|---|---|
| **EULAR** | Rhumatologie / auto-immunité | Recos publiées dans ARD (RSS revue) + site | ★★★ |
| **ACR** (American College of Rheumatology) | Rhumatologie | Recos publiées dans Arthritis Care & Research / A&R | ★★ |
| **ESC** | Cardiologie | Guidelines publiées dans EHJ, calendrier annuel prévisible (congrès ESC) | ★★★ |
| **IDSA / ESCMID** | Infectiologie | Recos via CID / CMI | ★★ |
| **KDIGO** | Néphrologie | Site + Kidney International | ★★ |
| **ERS / ATS** | Pneumologie | ERJ / AJRCCM | ★★ |
| **EASL / AASLD** | Hépatologie | J Hepatol / Hepatology | ★★ |
| **GINA / GOLD** | Asthme / BPCO | Mises à jour annuelles, sites dédiés | ★ |
| **ACP** (American College of Physicians) | Médecine interne | Recos publiées dans Annals of Internal Medicine | ★★★ |
| **ASH / ISTH** | Hématologie / hémostase | Blood Advances / JTH | ★★ |

## 3. Grandes revues (articles qui changent la pratique)

| Revue | Accès | Filtrage nécessaire |
|---|---|---|
| **NEJM** | RSS + PubMed | Élevé — ne garder que ce qui concerne l'interniste |
| **The Lancet** (+ Rheumatology, Infectious Diseases…) | RSS + PubMed | Élevé |
| **JAMA** (+ Internal Medicine) | RSS + PubMed | Moyen (JAMA IM très pertinent) |
| **Annals of Internal Medicine** | RSS + PubMed | Faible — quasi tout est pertinent |
| **BMJ** | RSS + PubMed | Moyen |
| **Annals of the Rheumatic Diseases, Blood, Kidney Int, CID…** | RSS + PubMed | Moyen — recos et essais majeurs seulement |
| **La Revue de Médecine Interne** | RSS Elsevier | Faible |

## 4. Méta-sources et API (l'épine dorsale technique)

Plutôt que de scraper chaque revue, s'appuyer au maximum sur les agrégateurs :

| Méta-source | Ce qu'elle apporte | API |
|---|---|---|
| **PubMed / NCBI E-utilities** | Requêtes sauvegardées par type de publication (`Guideline[pt]`, `Practice Guideline[pt]`, `Randomized Controlled Trial[pt]`) croisées avec des filtres thématiques ; c'est le filet de sécurité qui rattrape ce que la surveillance de sites manque | Oui, gratuite (esearch/efetch), clé API recommandée |
| **Europe PMC** | Alternative/complément à PubMed, bonne API REST, inclut preprints | Oui, gratuite |
| **Crossref** | Métadonnées DOI, dates de publication | Oui, gratuite |
| **Unpaywall / OpenAlex** | Accès au texte intégral libre quand il existe | Oui, gratuite |
| **ClinicalTrials.gov** | Résultats d'essais (phase aval, pas MVP) | Oui |

### Stratégie PubMed type (à affiner)

```
(Guideline[pt] OR Practice Guideline[pt] OR Consensus Development Conference[pt])
AND ("2026/07/07"[dp] : "2026/07/14"[dp])
AND (internal medicine OR <liste de MeSH terms du périmètre interniste>)
```

- Une requête « recommandations » large + une requête « essais majeurs »
  restreinte aux ~10 grandes revues (filtre par ISSN).
- Le périmètre thématique de l'interniste = liste maintenue de termes MeSH
  (maladies systémiques, vascularites, sarcoïdose, amylose, fièvre prolongée,
  MTEV, infections complexes…) — versionnée dans le repo, ajustée selon les
  retours lecteurs.

## 5. Modes d'accès techniques : trois familles

1. **RSS/Atom** — le cas idéal : revues Elsevier/Springer/NEJM/JAMA, HAS.
   Ingestion triviale, fiable.
2. **API REST** — PubMed, Europe PMC, Crossref. Structuré, fiable, gratuit.
3. **Surveillance de pages** (change detection) — pour les sites sans flux
   (filières maladies rares, sociétés savantes françaises) : snapshot
   périodique de la page « publications », diff, extraction des nouveaux
   liens. C'est la partie la plus fragile → prévoir des alertes quand une
   page change de structure, et accepter qu'elle soit semi-manuelle au début.

## 6. Ce que le registre de sources doit encoder (schéma cible)

```yaml
- id: has-reco
  nom: Haute Autorité de Santé — recommandations
  type: reco            # reco | pnds | revue | alerte | agrégateur
  langue: fr
  acces:
    methode: rss        # rss | api | page-watch
    url: https://…      # à vérifier
    frequence_poll: 6h
  poids_editorial: 10   # 1-10, influence le scoring de pertinence
  pertinence_defaut: haute   # court-circuite le filtre : une reco HAS passe toujours
```

## 7. Périmètre MVP recommandé

Pour la première version, **10 à 15 sources maximum**, celles marquées ★★★ :
HAS, PNDS, SNFMI, ACP/Annals, ESC, EULAR + PubMed en filet de sécurité +
les 5 grandes revues généralistes. Ce périmètre couvre l'essentiel du besoin
d'un interniste et reste maintenable par une personne.
