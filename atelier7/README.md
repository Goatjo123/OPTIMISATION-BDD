# Atelier 7 : la page et ses relations, puis PgBouncer

Jour 4, slide 13 et fiche étudiant du kit (`Kit_Jour4_Windows_Linux/02_Laboratoire/Jour4/Atelier_07_Fiche_etudiant_Linux.pdf`). Partie A : OFFSET contre curseur, dates identiques, N+1 contre chargement groupé. Partie B : PgBouncer (mutualisation des connexions).

Explication pas à pas, pensée pour comprendre l'intérêt : **[`../ATELIER7_DE_A_A_Z.md`](../ATELIER7_DE_A_A_Z.md)**.

L'API (`01_server/api`) et le kit ne sont **pas modifiés**. Les scripts ci-dessous appellent l'aide du kit (`jour4_http.mjs`), rejouent ses scripts SQL tels quels et pilotent PgBouncer avec son propre pilote (`pooling.mjs`).

---

## Situation

L'écran « mes commandes » du client 42 affiche 20 commandes avec leurs lignes. Trois coûts différents menacent l'API : le **nombre de requêtes** (N+1), le **travail de pagination** (OFFSET relit ce qu'il saute) et le **nombre de connexions** à PostgreSQL.

## Solution et pourquoi

| Problème | Solution | Pourquoi |
|---|---|---|
| N+1 | **chargement groupé** : une requête de lignes pour toute la page (`commande_id = ANY(…)`) | le nombre de requêtes ne dépend plus de la taille de la page |
| OFFSET | **curseur** (created_at, id) | la page suivante reprend au repère ; l'id départage les dates identiques |
| Connexions | **PgBouncer**, mode transaction | il borne les connexions serveur et remplace un refus par de l'attente |

## Est-ce que ça fonctionne ?

| Contrôle | Attendu | Obtenu |
|---|---|---|
| Client 42 | 100 commandes, 3 lignes chacune | oui |
| N+1 contre groupé, 20 commandes | réponses identiques, 21 puis 2 SQL | **identiques, 21 et 2** (aussi vérifié pour 5, 50, 100 : 6, 51, 101 contre 2 ; page vide : 1) |
| OFFSET contre curseur, page 2 | réponses identiques, 2 SQL chacune | **identiques, 2 et 2** |
| Dates identiques (limite 2) | page 1 : 2042, 1042 ; page 2 : 42 et une autre | **2042, 1042 puis 42, 86042** ; avec la date seule : 86042, 83042 (42 perdue) |
| Parcours | 5 pages, 100 ids uniques | **5 / 100 / 100**, même ordre que PostgreSQL |
| Droits | 401 sans jeton ; 400 avec `client_id` | **401, 400** ; curseur falsifié : 400 |
| Restauration des dates | 3 dates restaurées | **3**, empreinte md5 des dates identique à l'état initial |
| Laboratoire ShopFlow | état initial | **identique** (6 index, 0 statistique, mêmes tables, mêmes dates) |

### Durées (partie A, 30 tours alternés après 5 échauffements, ms)

| Page | HttpMs N+1 | HttpMs groupé | sqlMs N+1 | sqlMs groupé |
|---|---|---|---|---|
| 20 | 55,3 | 43,9 | 14,2 | 2,2 |
| 50 | 68,5 | 44,2 | 29,0 | 2,6 |

Le gain de durée est **modeste** : la base est locale. Une baisse du nombre de requêtes n'est pas, à elle seule, un gain mesuré.

### OFFSET contre curseur à 1 000 000 de commandes (ajout, table de travail jetable)

La fiche interdit de conclure sur de grands décalages avec 100 commandes. Sur une table jetable (un client, 1 000 000 de commandes, dates en double, index de l'atelier 3, colonnes de l'API), la même page :

| Décalage | OFFSET | Curseur |
|---|---|---|
| 0 | 0,171 ms | 0,154 ms |
| 1 000 | 1,2 ms | 0,174 ms |
| 100 000 | 99,7 ms | 0,168 ms |
| 999 000 | **944 ms** (1 003 945 pages) | **0,177 ms** (24 pages) |

Pages identiques (md5) à chaque profondeur. À petite profondeur, **aucun gain**.

### PgBouncer (laboratoire séparé : PostgreSQL 17.11, PgBouncer 1.18.0, 5 connexions serveur)

| Campagne | Connexions PostgreSQL direct / pool | TPS direct / pool (médiane de 3) | Latence direct / pool |
|---|---|---|---|
| 40 clients | 40 / 5 | 260,7 / 93,8 | 153 / 422 ms |
| 10 clients, reconnexion (campagne 1) | 10 / 5 | 22,6 / 29,7 | 301 / 258 ms |
| 10 clients, reconnexion (campagne 2) | 10 / 5 | 36,5 / 33,1 | 206 / 246 ms |
| 80 clients | refus (FATAL) / 5 | non mesurable / 90,7 | non mesurable / 860 ms |

PgBouncer **limite les connexions** mais **n'accélère rien** (5 connexions de 50 ms : 100 transactions/s au plus). Le test avec reconnexion est instable (résultats inversés entre deux campagnes) : aucune conclusion.

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `run_partie_a.py` | rejoue la partie A de la fiche, vérifie chaque résultat attendu, restaure les dates, contrôle le laboratoire |
| `bench_offset_curseur.py` | mesure OFFSET contre curseur sur une table de travail de 1 000 000 de commandes |
| `resultats/resultats_partie_a.json`, `mesures_partie_a.csv` | mesures de la partie A |
| `resultats/api_journal.log`, `api_extraits_par_traceid.txt` | journal de l'API et extraits par TraceId |
| `resultats/offset_curseur_volume.json`, `plan_*.txt` | mesures à grande échelle et plans |
| `resultats/pgbouncer/` | campagnes PgBouncer (synthese.csv, sorties pgbench, connexions, SHOW POOLS, configuration) ; `b_*.log` : sorties du pilote |

Rejouer : `python3 atelier7/run_partie_a.py` (environ 2 minutes), `python3 atelier7/bench_offset_curseur.py` (environ 1 minute). PgBouncer : depuis `Kit_Jour4_Windows_Linux/02_Laboratoire/Jour4/PgBouncer`, `node pooling.mjs up`, `compare`, `saturation`, puis `down`.

## Limites

Base locale, 100 commandes pour le client 42 ; durées HTTP bruitées ; mesure OFFSET / curseur sur une table de travail ; campagnes PgBouncer de 20 secondes (démonstration), pic de connexions échantillonné (une fois par seconde), `pgbench` mesure un scénario avec attentes artificielles et non du temps HTTP ; le test avec reconnexion est instable ; un curseur n'est pas un instantané. L'atelier 8 (Redis) n'est pas fait.

## Défauts trouvés et corrigés dans mes propres mesures

1. L'`ORDER BY` de ma mesure OFFSET / curseur triait sur les alias de sortie (texte) : l'index devenait inutile (lecture complète, 3 s). Colonnes qualifiées (`commandes.created_at`), comme l'API ; mesure refaite.
2. Première version de la mesure qui ne lisait que `id` et `created_at` (index seul) : elle sous-estimait OFFSET. Colonnes de l'API (`statut`, `total`) ajoutées ; mesure refaite.
3. Un opérateur Python 3.8 non pris en charge : corrigé avant l'exécution complète.
