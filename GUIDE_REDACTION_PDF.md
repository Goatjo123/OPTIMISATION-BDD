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
| 11 | **Consigne du prof : mettre en avant les optimisations** de requêtes ou de scripts qui donnent **le même résultat** (optimiser = moins coûteux et plus rapide à résultat identique), avec des **schémas ou des images**. **Présenter chaque optimisation comme la transformation d'une ancienne requête en une nouvelle**, sans comparer des techniques entre elles (par exemple jointure contre EXISTS) | PDF séparé `Optimisations.pdf` : ancienne version / nouvelle version, schéma du plan, graphiques, preuve d'identité |
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

### Preuves à conserver de l'Atelier 3 (slide 12) : où les trouver dans le PDF
| Exigence de la slide | Emplacement |
|---|---|
| La **requête** | Section A (API) et **annexe 5.0** (les 3 requêtes exactes) |
| Le **plan** | **Annexe 4** : 3 requêtes × 5 variantes, client 42 (les 75 plans sont dans `atelier3/resultats/plans/`) |
| Les **buffers** | Sections C, D, E, F, annexes 4 et 5.2 |
| La **taille des index** | Section B |
| Les **répétitions** | **Annexe 5.2** : les 5 mesures brutes des 75 combinaisons ; 5.3 et 5.4 pour les mesures renforcées (médiane, p95, minimum seulement) |
| Un **lot d'insertion** dans une transaction de laboratoire | Section G (SQL `BEGIN … ROLLBACK`, WAL, durées) et annexe 5.4 |
| **Expliquer le gain ou l'absence de gain** | Sections C et I, encadré « Ce que j'ai compris de l'atelier 3 » |

### Preuves de l'Atelier 8 (slide 34 et fiche) : où les trouver dans le PDF
| Exigence | Emplacement |
|---|---|
| Pattern et clé justifiés | Section « Atelier 8 » (Solution choisie et pourquoi), annexe 10.2 |
| Prix initial, valeurs avant/après, CSV | Annexe 10.1, 10.4, `atelier8/resultats/mesures_atelier8.csv` |
| Miss à 1 SELECT, hit à 0 SQL (5 paires) | Étape 2, annexe 10.3 |
| Copie ancienne prouvée après UPDATE direct, nouvelle valeur après DEL | Étape 3, annexe 10.4 et 10.5 |
| PATCH et invalidation automatique | Étape 4, annexe 10.4 et 10.5 |
| Expiration (TTL puis −2) et repli (Redis arrêté) | Étape 5, annexe 10.4 et 10.5 |
| Prix initial restauré | Étape 6, annexe 10.1 et 10.5 |
| Traces liées par TraceId | Annexe 10.4, `atelier8/resultats/api_extraits_par_traceid.txt` |
| Durées hit / miss / panne | Section « Miss contre hit », annexe 10.6 |
| Course de reconstruction (analyse + reproduction) | Section « La fraîcheur », annexe 10.4 |
| Fraîcheur acceptée et contrôle transactionnel de l'achat | Section « La fraîcheur » |
| Rafale (ajout) | Section « Panne, rafale et repli », annexe 10.7 |

### Preuves de l'Atelier 7 (slide 13 et fiche) : où les trouver dans le PDF
| Exigence | Emplacement |
|---|---|
| Contrat de l'endpoint (data / hasNextPage / nextCursor, limites 20 et 100, ordre, formats) | Section « Atelier 7 », annexe 9.2 et 9.6 |
| SQL expliqué (OFFSET, curseur, N+1, groupé) | Annexe 9.2 (extraits de `commandes.mjs`) |
| Comptage des requêtes (21 contre 2, 6/51/101) | Section « N+1 contre chargement groupé », annexe 9.3 et 9.4 |
| Trace (TraceId, journal de l'API) | Annexe 9.3, `atelier7/resultats/api_extraits_par_traceid.txt` |
| Contrôle des résultats (réponses identiques) | Étapes 2 et 3 du tableau, annexe 9.3 |
| Dates identiques (2042, 1042, 42) | Section dédiée, annexe 9.5 |
| Parcours 100 / 100 / 5, droits, restauration | Annexe 9.6 |
| OFFSET contre curseur à grande profondeur (ajout) | Section dédiée, annexe 9.7, `Optimisations.pdf` page 10 |
| PgBouncer : connexions, attente, refus, TPS, limites | Section « Partie B », annexe 9.8 |

### Preuves de l'Atelier 4 bis (slide 43) : où les trouver dans le PDF
| Trace demandée | Emplacement |
|---|---|
| 01 SQL d'ajout, défaut, lots et contrainte | Annexe 8.2 (fichiers 01 à 09 rejoués tels quels), `atelier4bis/resultats/transcript.txt` |
| 02 Volumes et NULL avant, pendant, après ; nombre et durée de chaque lot | Section « Le remplissage lot par lot », annexe 8.3 |
| 03 Compatibilité des lecteurs, défaut, rejet de NULL, comparaison historique à 0 écart | Annexe 8.4 (erreur 23502, md5 identiques) |
| 04 État de la contrainte avant et après validation | Annexe 8.5 (`convalidated` false puis true, message DEBUG1 « pas de second scan ») |
| 05 Verrou : erreur de B, COMMIT de A, réussite de B, avec la chronologie | Section « Verrous : A, B et C », annexe 8.6 (instantané `pg_locks`, scénario C derrière B) |
| 06 SQL de retour arrière et contrôles ; limites et précautions | Annexe 8.7, note « Ce que j'ai compris de l'atelier 4 bis » (limites) |
| Ancienne version → nouvelle version (à 3 000 000 lignes) | Section dédiée, annexe 8.8, `Optimisations.pdf` page 8 |

### Preuves de l'Atelier 4 (slide 26) : où les trouver dans le PDF
| Exigence de la slide | Emplacement |
|---|---|
| Variantes **partielle** et **GIN** dans le laboratoire | Sections A et B de l'atelier 4 ; DDL dans l'annexe 7.0 |
| Filtre qui **correspond** au prédicat et filtre qui **ne correspond pas** | Section A (en_attente contre payee et annulee), annexe 6 |
| **Taille** et **usage** des index | Section A (tailles, `idx_scan`), section B, annexe 7.2 |
| Sur la petite table `produits`, **Seq Scan rationnel** : l'expliquer | Section B (200 lignes, 3 pages, coûts estimés, diagnostic Seq Scan interdit) |
| **Test à plus grand volume** | Section B (200 000 produits) |
| **GiST** : deux périodes qui se chevauchent et une disjointe | Section C (ids 1 et 2, 3 disjointe, 4 contiguë) |
| **Choix d'index, opérateurs, résultats et conditions** (livrable) | Section D et encadré « Ce que j'ai compris de l'atelier 4 » |

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
11. **Tester le SQL réellement émis par l'application** (slide 13), pas seulement celui du cours : lire le code de l'API (`commandes.mjs`) et reprendre sa requête exacte, qualificatifs compris.
12. **Durées sub-milliseconde bruitées** : comparer des mesures **alternées** (un tour de chaque variante), s'appuyer sur les valeurs déterministes (buffers, plans, WAL, tailles) et annoncer la variabilité. Ne jamais comparer une durée d'une session à une durée d'une autre.
13. **Prouver que le laboratoire est restauré** après toute expérience qui crée des objets (index, tables) et que **chaque variante** renvoie le même résultat (empreinte md5).
14. **Une absence de gain est un résultat** : la présenter et l'expliquer (slide 12), ne pas la cacher.
15. **Les preuves sont dans le PDF, pas seulement les médianes** : fournir en annexe les mesures brutes (les 5 répétitions de chaque combinaison), l'empreinte du résultat, l'état du laboratoire avant/après et la version. Dire explicitement ce qui n'est pas conservé (ex. les 51 valeurs des mesures renforcées : seuls médiane, p95 et minimum).
16. **Les buffers se comptent en `hit` + `read`** : ne jamais lire seulement `shared hit`. Vérifier que `read` est nul (ou l'annoncer) avant de comparer des plans.
17. **Comparer des plans de même forme** : un `Parallel Seq Scan` n'est pas comparable à un `Seq Scan` simple. Fixer `max_parallel_workers_per_gather` pour les mesures alternées sur des tables différentes, et le dire.
18. **Contrôler le rendu des nombres** : séparateur de milliers (espace) et virgule décimale ne doivent pas se confondre (par exemple « 10,1 » et non « 10 1 »). Rechercher les motifs suspects dans le texte extrait du PDF.
19. **Un défaut de mesure trouvé en cours de route se documente** (ce qui était faux, comment il a été corrigé) et les chiffres viennent de l'exécution corrigée.
20. **Pour chaque solution : la situation, pourquoi on la choisit (et laquelle on écarte), et si elle fonctionne** (gain, résultat identique, limites vérifiées, verdict). Ne jamais présenter une solution sans dire si elle marche et dans quelles conditions.
21. **Une optimisation = la transformation d'une ancienne requête en une nouvelle, avec le même résultat, moins coûteuse et plus rapide.** Ne pas présenter une comparaison de techniques (jointure contre EXISTS) mais la transformation de la requête d'origine. Toujours montrer l'*ancienne version* et la *nouvelle version* (SQL ou DDL), **prouver que le résultat est identique**, chiffrer le gain **et** le coût, et l'exprimer par un schéma (plan d'exécution) et un graphique avant/après, pas seulement par des tableaux. Une variante plus rapide mais au résultat différent n'est pas une optimisation.
22. Pas de valeurs inventées : les exemples fictifs du cours (slide 8) sont signalés comme **fictifs**.
23. **Pour une migration, l'optimisation est la réduction du blocage des autres utilisateurs, pas la durée totale.** Quand la nouvelle méthode est plus lente au total (remplissage ×2,7 à l'atelier 4 bis), le dire. Ne jamais présenter l'ajout d'une colonne comme un gain de vitesse de requête (le cours le dit). À 1 000 lignes tout est instantané : mesurer à plus grand volume sur une table jetable et signaler que c'est **une seule exécution**.
24. **Un script de mesure se contrôle lui-même** : ne pas se fier à un tube unique pour les sorties et les erreurs de psql (une erreur peut arriver après la commande suivante) ; poser une sentinelle sur chaque flux, vérifier les contrôles attendus (le script s'arrête sur un écart) et relancer le script entier après toute correction.
25. **Compter les requêtes avant de parler de durée, et ne pas annoncer un gain non mesuré** : séparer le nombre de requêtes SQL (X-SQL-Count), la durée côté client (HttpMs) et la durée SQL (sqlMs). Quand le jeu fourni est trop petit pour un effet (100 commandes), le dire et mesurer sur une table de travail jetable. Un outil qui limite une ressource (PgBouncer : connexions) n'est pas une optimisation de vitesse : l'écrire si le débit baisse.
26. **Un test instable n'est pas conclu** : le relancer, présenter toutes les campagnes (même quand l'ordre s'inverse) et écrire « aucune conclusion ». Un essai interrompu a des mesures « non mesurables », pas zéro.
27. **Un cache se présente avec sa limite de fraîcheur** : chiffrer le gain (avec un outil de mesure qui ne le noie pas : un processus par appel ajoute un coût fixe qui masque une différence de quelques ms), mais montrer aussi que la copie peut être périmée (UPDATE direct, invalidation échouée, course), déclarer la fraîcheur acceptée et préciser ce qui n'est jamais caché (achat, stock). Le gain principal d'un hit est la charge évitée sur la base, pas toujours la durée.
28. **Distinguer miss, hit et repli** dans chaque tableau de durées, et dire quand une panne du cache déplace la charge sur la base (une lecture = un SELECT).

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
- Les optimisations **O1 et O2** (atelier 1) ont été testées **sur une copie** (`shopflow_opt`) ; l'Atelier 3 a été mesuré sur la **vraie table** du labo (index créés puis supprimés, labo vérifié identique avant/après) et sur des tables de travail jetables. La copie est plus compacte (840 pages contre 1 674) : on ne compare qu'**au sein d'une même mesure**.
- Le coût de `CREATE STATISTICS` n'a pas été mesuré ; le coût en écriture des index a été mesuré à l'Atelier 3 (WAL +35 % pour le composé ; durées trop bruitées pour un pourcentage unique).
- Les explications sur la **cause** (le bitmap lit 85 à 88 pages parce que les commandes sont dispersées) restent des hypothèses ; celles sur le tri et l'estimation sont **confirmées** par les tests.

### Dernière vérification effectuée : atelier 4 (06/10/2026)
Chaque mesure du README et du PDF a été recontrôlée contre `atelier4/resultats/resultats.json` (aucun écart). Trois défauts ont été trouvés et corrigés pendant le travail :
| Défaut | Correction |
|---|---|
| Buffers : seul `shared hit` était lu (un plan affichait `hit=841 read=1554`) | Buffers = `hit` + `read` ; tous les `read` valent 0 dans l'exécution finale |
| Un `Parallel Seq Scan` (22 ms) comparé à un `Seq Scan` simple (≈ 42 ms) sur des tables différentes | Parallélisme désactivé pour les mesures alternées ; plan parallèle conservé comme observation |
| Dans le PDF, « 10,1 » devenait « 10 1 » (virgule décimale remplacée par une espace) | Milliers formatés séparément ; recherche automatique de motifs suspects dans le texte du PDF |

## 6. Mise à jour de `SYNTHESE.md`
À chaque point pertinent (concept, résultat mesuré, piège, correction), l'ajouter dans la bonne section de `SYNTHESE.md`, en français, concis, avec les chiffres. Ne pas attendre qu'on le redemande.

## 7. Structure actuelle des PDF
**`Atelier1_Diagnostic_compact.pdf` (59 pages, détail des ateliers 1 à 4 bis, 7 et 8 ; le contenu des 38 premières pages d'origine est conservé, l'atelier 4 bis a été **ajouté** à la demande de l'utilisateur)**

| Pages | Contenu |
|---|---|
| 1 à 2 | Atelier 1 : contexte, requêtes, résultats vérifiés, 5 mesures, nœud coûteux, **Ce que j'ai compris** |
| 3 à 4 | Atelier 2 : jointure contre EXISTS, total par commande, **Ce que j'ai compris** |
| 5 à 6 | Optimisations testées : le bilan (O1 `work_mem`, O2 statistique) |
| 7 à 10 | **Atelier 3** : historique client (requêtes réelles de l'API, variantes, lecture, 5 clients, client très actif, piège de l'alias, écriture, `Heap Fetches`, décision, migration 001) |
| 11 à 15 | **Atelier 4** : situation, puis pour chaque partie (A partiel, B GIN, C GiST) **situation, solution choisie et pourquoi, résultats, « est-ce que ça fonctionne ? »** ; livrable, migration 002, **Ce que j'ai compris** |
| 16 à 18 | **Atelier 4 bis** : situation, solution et pourquoi, est-ce que ça fonctionne ; déroulement étape par étape ; lots ; verrous A, B et C ; ancienne → nouvelle version à 3 000 000 lignes ; **Ce que j'ai compris** |
| 19 à 21 | **Atelier 7** (Jour 4) : situation, solution et pourquoi, est-ce que ça fonctionne ; N+1 contre groupé ; OFFSET contre curseur à 1 000 000 de commandes ; dates identiques ; PgBouncer ; **Ce que j'ai compris** |
| 22 à 24 | **Atelier 8** (Jour 4) : situation, solution et pourquoi, est-ce que ça fonctionne ; miss contre hit ; fraîcheur (UPDATE direct, invalidation échouée, course) ; panne, rafale et repli ; **Ce que j'ai compris** |
| 25 | Questions de compréhension du cours |
| 26 à 39 | Annexes 1 à 5 : plans (ateliers 1 à 3, O1 et O2) et preuves de l'atelier 3 |
| 40 à 44 | **Annexe 6** : plans de l'atelier 4 |
| 45 à 47 | **Annexe 7** : preuves de l'atelier 4 |
| 48 à 52 | **Annexe 8** : preuves de l'atelier 4 bis (les six traces de la slide 43, mesure à 3 000 000 lignes) |
| 53 à 56 | **Annexe 9** : preuves de l'atelier 7 (SQL, traces par TraceId, mesures, dates identiques, droits, OFFSET / curseur à grande échelle, campagnes PgBouncer) |
| 57 à 59 | **Annexe 10** : preuves de l'atelier 8 (code du cache, paires miss/hit, appels par TraceId, TTL, mesures répétées, rafale) |

**`Optimisations.pdf` (13 pages, PDF séparé qui met en avant les optimisations)**
| Page | Contenu |
|---|---|
| 1 | Définition (ancienne version → nouvelle version, même résultat, plus rapide), **graphique des gains**, tableau récapitulatif avec preuve d'identité du résultat (ligne 7 : temps sous verrou exclusif, une exécution) |
| 2 à 7 | Une page par transformation : **ancienne version / nouvelle version** (SQL ou DDL), **schéma du plan d'exécution**, graphiques avant/après, résultat identique, pourquoi, coût : 1 agrégation (statistique), 2 clients avec commande payée (réécriture EXISTS), 3 historique client (index composé), 4 file en attente (index partiel), 5 filtre JSON (colonne typée), 6 chevauchement de périodes (GiST) |
| 8 | **7 Migration NOT NULL** : ancienne (un UPDATE + SET NOT NULL direct) → nouvelle (lots, CHECK NOT VALID, VALIDATE, SET NOT NULL sans scan) : temps sous verrou exclusif 3 324 → 46,3 ms, **mais** remplissage plus long |
| 9 | **8 Page avec ses lignes** : N+1 (21 requêtes) → chargement groupé (2), réponse identique |
| 10 | **9 Pagination profonde** : OFFSET → curseur, même page, 944 → 0,18 ms à 1 000 000 de commandes (table de travail), aucun gain à petite profondeur |
| 11 | **10 Fiche produit** : lecture SQL → cache Redis, même contenu, 2,7 → 0,99 ms, avec son coût de fraîcheur (copie périmée mesurée) |
| 12 | Transformations écartées (dont TTL qui ne rafraîchit pas un UPDATE direct, PgBouncer qui n'accélère pas) et prix d'un index à l'écriture |
| 13 | Méthode de preuve et limites |

**`test.pdf` (71 pages, essai Jour 5)** : le PDF principal (59 pages, identiques) + chapitre **Jour 5** (p. 60 à 67 : observation, tuning, Atelier 9, avant/après, export et contrat, conclusion limitée, pièces du dossier) + **annexe 11** (p. 68 à 71). Chaque point du cours Jour 5 (slides 4 à 31) y est relié à une mesure réelle (copie jetable `a9-pg`, dossier `atelier9/`) ; style concis (tableaux, une ligne de lecture), pas de valeur fictive.

**`test_compact.pdf` (4 pages, dossier essentiel)** : généré par `dossier/build_dossier.py`, organisé selon les six pièces du dossier collectif (slide 30) et la grille de relecture (slide 31) : diagnostic initial, DDL et déploiement, SQL et trace API, benchmark avant/après, tests de correction, décision finale. Sans notes de compréhension ni annexes : les chiffres sont lus dans les fichiers de mesures (aucune saisie manuelle). `test.pdf` (71 pages) reste la version détaillée.

## 8. Modèle de phrase « Ce que j'ai compris »
> **Je [action]** parce que [raison]. Exemple : [chiffre mesuré]. Condition : [quand cela s'applique / ne s'applique plus].
