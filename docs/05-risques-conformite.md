# 05 — Risques, qualité et conformité

Ce document liste les points de vigilance identifiés en phase de conception.
**Rien ici ne constitue un avis juridique** — les points marqués ⚖️ devront
être validés avec un juriste avant l'ouverture publique (phase 3).

## 1. Exactitude médicale — le risque produit n° 1

| Risque | Parade |
|---|---|
| Hallucination LLM (chiffre, posologie, conclusion inventée) | Synthèses ancrées sur citations ; appel de vérification ; **relecture médicale systématique** avant envoi ; interdiction de publier une synthèse `confiance: faible` non relue |
| Diff « ce qui change » inventé faute de version antérieure | Règle explicite : sans version antérieure en base, pas de diff (cf. [03-architecture.md](03-architecture.md)) |
| Item majeur manqué (faux négatif) | PubMed en filet de sécurité par-dessus les sources directes ; jeu d'évaluation du rappel ; rubrique feedback lecteurs « il manque X » |
| Synthèse fondée sur abstract seul présentée comme complète | Champ visible « synthèse sur abstract / sur texte intégral » |
| Erreur découverte après envoi | Procédure d'erratum : correction en tête du numéro suivant + correction de l'archive web |

## 2. Positionnement réglementaire ⚖️

- Tant que le service **résume des publications et renvoie aux sources**, sans
  produire de recommandation individualisée ni d'aide à la décision pour un
  patient donné, il s'apparente à de la presse/veille professionnelle — pas à
  un dispositif médical (règlement UE 2017/745). **Cette frontière doit rester
  une contrainte de conception** : pas de Q&A clinique, pas de moteur de
  décision.
- Mentions systématiques dans chaque numéro : public exclusivement
  professionnel de santé ; ne remplace pas la lecture des recommandations
  sources ni le jugement clinique.
- Transparence IA : mention explicite que les synthèses sont générées par IA
  et relues par un médecin (exigence de loyauté, et argument de confiance —
  cf. AI Act européen pour les obligations de transparence).

## 3. Droit d'auteur ⚖️

- **Ce qui est sûr** : résumer avec ses propres mots, citer titre/auteurs/
  source, courtes citations attribuées, lien vers l'original. Le digest doit
  être construit ainsi.
- **Ce qui est interdit** : reproduire des abstracts entiers de revues sous
  copyright, des figures, des tableaux de recos, ou le texte intégral.
- Les documents publics HAS/PNDS sont plus permissifs mais ont leurs propres
  conditions de réutilisation — à vérifier.
- Le pipeline peut *ingérer* des textes sous copyright pour les analyser
  (usage interne) ; c'est la *republication* qui est encadrée. La sortie ne
  contient que : métadonnées + synthèse originale + courtes citations + lien.

## 4. RGPD (dès qu'il y a des abonnés) ⚖️

- Base légale : consentement à l'inscription ; désinscription en un clic.
- Minimisation : email + profil déclaratif (spécialité, mode d'exercice), rien
  d'autre.
- Prestataire d'emailing avec hébergement UE et DPA ; registre des
  traitements ; pas de tracking au-delà des stats d'ouverture standard.

## 5. Indépendance éditoriale

- Pas de financement par l'industrie pharmaceutique (même « sans influence ») :
  c'est la condition de la confiance, qui est l'actif du produit.
- Déclaration des liens d'intérêts du ou des relecteurs.
- Les critères de sélection des items sont publics (page « méthode »).

## 6. Risques opérationnels

| Risque | Parade |
|---|---|
| Sites sources qui changent de structure (page-watch cassé) | Alerte automatique si une source ne produit plus rien depuis N jours ; revue trimestrielle du registre |
| Dépendance à une personne (relecture) | Binôme de relecteurs dès que possible ; le digest peut être court mais doit partir |
| Coût/latence API LLM | Négligeable au volume prévu ; cache des synthèses ; modèle léger pour le scoring |
| Perte de données | Base sauvegardée ; les numéros publiés sont aussi des fichiers Markdown versionnés dans un repo |
