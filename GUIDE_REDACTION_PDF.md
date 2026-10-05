# Guide d'écriture du PDF

Ce guide regroupe **toutes les contraintes** données depuis le début du travail, plus les exigences du cours.
Le PDF concerné est `Atelier1_Diagnostic_compact.pdf` (à la racine). **Il sert à évaluer ma compréhension du module et je suis noté dessus.**

---

## 1. Objectif et lecteur
- Le lecteur est un **correcteur** qui évalue si j'ai **compris** le module, pas seulement si j'ai exécuté des commandes.
- Chaque affirmation doit être **vraie, chiffrée et reliée à une mesure ou à une slide**.
- Le PDF doit **montrer** la compréhension : expliquer le « pourquoi », pas seulement le « quoi ».

## 2. Contraintes demandées dans la conversation
| # | Contrainte | Où elle s'applique |
|---|---|---|
| 1 | Le PDF est **à la racine du projet** | Emplacement du fichier |
| 2 | **Expliquer ce qu'on fait à chaque étape** de l'atelier | Une section par étape, avec « ce qu'on fait » et « pourquoi » |
| 3 | Montrer **les résultats** et **expliquer en bref** | Phrases concises, détails et plans complets en annexe |
| 4 | Explications en **français simple** | Phrases courtes, termes techniques expliqués (nœud, granularité…) |
| 5 | Ajouter l'**Atelier 2** (slide 31) au même PDF | Pages dédiées après l'atelier 1 |
| 6 | Dire **ce que j'ai compris, moi**, pour chaque atelier | Encadré « Ce que j'ai compris » à la **première personne** après chaque atelier |
| 7 | Montrer la **compréhension** (notation) | Encadrés + réponses aux 6 questions de la slide 33 |
| 8 | **Vérifier l'exactitude** de tout ce qui est écrit | Voir section 5 |
| 10 | Les **optimisations doivent être claires** (objectif du cours) | Section « Optimisations testées » : avant, après, gain, coût, verdict |
| 9 | Mettre à jour **`SYNTHESE.md`** à chaque point pertinent | Voir section 6 |

> **Longueur : aucune limite imposée**, mais rester **raisonnable**. Le corps (5 pages) va à l'essentiel ; les plans complets sont en annexe (3 pages). Ne pas ajouter de contenu qui ne sert pas la démonstration de la compréhension.

## 3. Contenu obligatoire par atelier

### Atelier 1 : diagnostic initial (slide 23)
Livrable attendu : une page de diagnostic avec
1. le **contexte et la version de PostgreSQL** (`SELECT version();`) ;
2. les **deux requêtes SQL** complètes (historique du client 42, agrégation) ;
3. les **résultats fonctionnels vérifiés** (nombre de lignes et total, comparés à une référence) ;
4. les **cinq mesures** de chaque requête (après échauffement) ;
5. les **plans `EXPLAIN (ANALYZE, BUFFERS)` complets** (annexe possible) ;
6. le **nœud coûteux** identifié ;
7. une **hypothèse** qui explique son coût.

Preuves à conserver : SQL complet, plan complet, version, résultats fonctionnels, 5 temps, informations BUFFERS.
**Interdit à ce stade : tout index supplémentaire.**

### Atelier 2 : réécriture équivalente (slide 31)
Livrable attendu : **SQL avant/après, contrôle du contenu, plans et interprétation.**
- Comparer une **jointure qui duplique les clients** avec une version **`EXISTS`**.
- Construire un **total par commande sans multiplier `commandes.total`**.
- Utiliser un **client avec plusieurs commandes** (client 42) et une **commande avec plusieurs lignes** (commande 42).
- **Prouver l'équivalence** du résultat pertinent, puis mesurer avec le **même protocole**.
- Si les plans sont identiques, **l'expliquer**. Si la réécriture perd des lignes, **la rejeter même si elle est plus rapide**.

### Questions de compréhension (slide 33)
Répondre aux 6 questions **avec un exemple et une condition d'application, pas uniquement une définition.**

## 4. Règles de rédaction
0. **Les optimisations sont le cœur du cours** : chacune doit apparaître dans un **tableau** (problème visé, avant, après, gain, coût ou risque, verdict) avec la preuve que **le résultat est inchangé**. Une optimisation sans mesure ni coût n'est qu'une idée : l'étiqueter « piste, non testée ».
1. **Première personne** dans les encadrés « Ce que j'ai compris » (« je vérifie », « j'ai compris que… »).
2. **Un chiffre = une source** : chaque valeur vient d'une mesure, d'une requête ou d'une slide, et on la cite.
3. **Distinguer mesure et hypothèse** : les volumes du laboratoire sont des hypothèses ; les durées sont des mesures ; les explications du type « parce que… » sont des hypothèses tant qu'elles ne sont pas testées. L'écrire (« hypothèse », « à tester »).
4. **Relier observation et cause** : pas « Seq Scan lent », mais « *X lignes lues pour en garder Y* ».
5. **Ne rien modifier** à ce stade : aucun index, aucune statistique ajoutée. Les pistes sont annoncées comme « à tester ensuite ».
6. **Même protocole** pour toutes les mesures : 3 exécutions d'échauffement, puis 5 mesures, médiane. Préciser l'état du cache (chaud ou froid).
7. **Toujours prouver avant de comparer** : contrôle du contenu (lignes, totaux, `EXCEPT`) avant les durées.
8. **Plans complets lisibles** : pas de lignes coupées en bout de page.
9. **Citer les slides** quand une règle vient du cours (ex. « slide 24 : granularité »).
10. **Pas de jargon sans explication** : définir « nœud », « granularité », « semi-jointure » en une phrase.
11. Pas de valeurs inventées : les exemples fictifs du cours (slide 8) sont signalés comme **fictifs**.

## 5. Vérification de l'exactitude (à refaire à chaque modification)

### Checklist
- [ ] Version de PostgreSQL = celle affichée par `SELECT version();`
- [ ] Paramètres cités (`work_mem`, `shared_buffers`) = `SHOW …`
- [ ] Base **inchangée** : `SELECT count(*) FROM pg_statistic_ext;` = 0, et seulement les index des contraintes
- [ ] Lignes et totaux de l'atelier 1 et 2 **recalculés** par requête, pas recopiés de mémoire
- [ ] Chaque **temps** du PDF = `Execution Time` d'un fichier de mesure brute
- [ ] Chaque **médiane** recalculée (5 valeurs triées, la 3e)
- [ ] Chaque **pourcentage** et **rapport** recalculé (ex. 1 096,8 / 84,1 = 13)
- [ ] Les **plans** de l'annexe sont ceux de la mesure indiquée, non tronqués
- [ ] Les **estimations vs observé** (`rows=` / `actual rows=`) correspondent au plan
- [ ] Les **numéros de slides** cités sont exacts
- [ ] Les affirmations « les plans sont identiques » ont été vérifiées sur les 5 plans
- [ ] Chaque **hypothèse** est présentée comme telle

### Dernière vérification effectuée (05/10/2026)
Tous les chiffres du PDF ont été recalculés à partir des mesures brutes et de la base. Corrections apportées :
| Avant | Après | Raison |
|---|---|---|
| Sort ≈ 47 % (parts 32 / 47 / 20) | Sort ≈ **48 %** (parts 33 / 48 / 20) | 37,2 / 77,9 = 47,7 % |
| « 2,5 fois plus rapide » (EXISTS) | « **2,4** fois » | 27,56 / 11,28 = 2,44 |
| « B1 deux fois plus rapide » | « **presque** deux fois » (1,10 contre 2,05 ms) | 2,05 / 1,10 = 1,86 |
| p50 = 80 ms, p99 = 610 ms (slide 8) | précisé « **valeurs fictives** du cours » | ces valeurs ne viennent pas de ShopFlow |

Points restant à connaître :
- La mesure à froid de 1 096,8 ms a été prise dans **pgAdmin** (interface graphique), les mesures à chaud via **psql**. Les deux sont du temps d'exécution côté serveur, mais ce n'est pas le même client.
- Le temps propre d'un nœud (ex. Sort ≈ 37 ms) est **calculé par soustraction** sur le plan de la mesure n°5, pas relevé directement.
- Les optimisations ont été testées **sur une copie** (`shopflow_opt`), pas dans la base du labo. La copie est plus compacte (840 pages contre 1 674) : ses temps de référence diffèrent, on ne compare qu'**au sein de la copie**.
- Le coût de `CREATE STATISTICS` n'a pas été mesuré ; le coût en écriture de l'index l'a été (+44 %).
- Les explications sur la **cause** (le bitmap lit 85 à 88 pages parce que les commandes sont dispersées) restent des hypothèses ; celles sur le tri et l'estimation sont **confirmées** par les tests.

## 6. Mise à jour de `SYNTHESE.md`
À chaque point pertinent (concept, résultat mesuré, piège, correction), l'ajouter dans la bonne section de `SYNTHESE.md`, en français, concis, avec les chiffres. Ne pas attendre qu'on le redemande.

## 7. Structure actuelle du PDF
| Pages | Contenu |
|---|---|
| 1 | Contexte, requêtes, résultats vérifiés, 5 mesures, froid/chaud |
| 2 | Atelier 1 : nœud coûteux, hypothèses, **Ce que j'ai compris** |
| 3 | Atelier 2 partie A : jointure contre EXISTS |
| 4 | Atelier 2 partie B : total par commande, conclusion |
| 5 à 7 | Atelier 2 (suite), **Optimisations testées : le bilan**, questions de compréhension |
| 8 à 12 | Annexes : plans complets (atelier 1, atelier 2, optimisations) |

## 8. Modèle de phrase « Ce que j'ai compris »
> **Je [action]** parce que [raison]. Exemple : [chiffre mesuré]. Condition : [quand cela s'applique / ne s'applique plus].
