# Synthèse : Optimisation BDD

Fichier vivant : on y ajoute tout ce qui est pertinent à retenir, au fil du cours et des ateliers.
Cas fil rouge : **ShopFlow** (PostgreSQL 18, schéma `shopflow`, 1 000 clients, 200 produits, 100 000 commandes, 300 000 lignes).

---

## 1. Cours, Jour 1 : Diagnostiquer les requêtes SQL

### Principes de méthode
- **Diagnostiquer avant de modifier** : observation chiffrée, cause possible, expérience pour la tester. « Seq Scan lent » ne suffit pas.
- **Performance ET exactitude** : une optimisation doit conserver les deux. Le résultat (lignes, totaux au centime) doit rester identique.
- Une réécriture qui **perd ou duplique des lignes est rejetée**, même si elle est plus rapide.
- La base n'est qu'une partie de la latence d'une API (réseau, pool de connexions, SQL, sérialisation). Un gain local est borné par sa part du total.

### Mesurer correctement
- **Latence** = durée d'une opération. **Débit** = opérations terminées par seconde. **Concurrence** = opérations simultanées. Trois grandeurs différentes.
- **Médiane et percentiles (p95, p99)** plutôt que la moyenne : ils révèlent la queue de latence que la moyenne masque. Un p95 n'a pas de sens avec 5 mesures.
- **Benchmark comparable** : mêmes données, même requête, même résultat, même charge, même machine, mêmes versions. On change **un facteur à la fois**, on répète, on garde les résultats bruts.
- **Cache chaud / froid** : la première lecture charge les pages depuis le stockage, les suivantes sont en mémoire. Même SQL, durées très différentes (observé : 1 096 ms à froid contre 84 ms à chaud). On documente toujours l'état du cache. Relancer le serveur ne garantit pas un cache système froid.
- L'échauffement stabilise le scénario mais ne doit pas cacher une vraie difficulté.

### Modèle et types
- Clés primaires, clés étrangères et contraintes (`NOT NULL`, `CHECK`) évitent les états impossibles.
- Montants : `numeric(12,2)` (exact). Dates d'événement : `timestamptz`.
- **Normalisation** : un fait à un seul endroit. **Duplication contrôlée** seulement si elle a une définition métier (ex. `prix_unitaire` dans `lignes` = prix au moment de l'achat, distinct du prix actuel du catalogue).
- `SELECT *` à éviter : on projette les colonnes du contrat de l'API. La projection ne remplace ni filtre ni `LIMIT`.

### Planificateur et EXPLAIN
- Le SQL exprime un résultat. Le **planificateur** choisit comment l'obtenir à partir des statistiques, des index et des coûts.
- `EXPLAIN` = plan **estimé**. `EXPLAIN ANALYZE` = **exécute** la requête et mesure. Sur une écriture (INSERT/UPDATE/DELETE), ANALYZE modifie réellement les données.
- `EXPLAIN (ANALYZE, BUFFERS)` est le format de référence.
- Un **nœud** = une étape du plan. On lit **de bas en haut** (enfants vers parents).
- Le temps d'un parent **inclut** celui de ses enfants : on ne les additionne pas. Coût propre d'un nœud = sa fin moins la fin de son enfant.
- Quand `loops > 1`, les temps et lignes affichés sont des **moyennes par boucle**.
- Comparer **lignes estimées (`rows=`) et observées (`actual rows=`)** : un grand écart pointe une statistique ancienne, une distribution asymétrique ou des colonnes corrélées. Ajouter un index sans regarder la cardinalité ne règle pas la cause.

### Lire les compteurs
| Élément | Signification |
|---|---|
| `shared hit` | Blocs trouvés dans les buffers PostgreSQL. Très élevé = beaucoup de données examinées, même en mémoire |
| `shared read` | Blocs chargés dans les buffers (peut venir du cache système, pas forcément du disque) |
| `Rows Removed by Filter` | Lignes lues puis écartées. Élevé = chemin d'accès peu sélectif |
| `Sort Method: external merge Disk` | Le tri dépasse `work_mem` et écrit sur disque |
| `temp read / written` | Fichiers temporaires (tri ou hachage débordant) |

### Méthodes d'accès
- **Seq Scan** : lit toute la table. Raisonnable si la table est petite ou si la requête retourne une grande part des lignes (ex. agrégation sur tout).
- **Index Scan / Bitmap Scan** : pour une recherche très sélective. Le nom du nœud ne suffit pas : on regarde le volume traité et la durée.
- **Prédicat exploitable par un index** : condition directe sur la colonne. Une fonction appliquée à la colonne (`created_at::date`) empêche l'index, sauf index sur expression ou réécriture.
- Intervalle de dates : borne basse **incluse**, borne haute **exclue** (`>= '2026-10-01' AND < '2026-11-01'`), fuseau explicite.

### Statistiques
- Le moteur **échantillonne** les valeurs pour estimer la sélectivité. Après un gros chargement : `ANALYZE`.
- **Statistiques étendues** (`CREATE STATISTICS`) : dépendances entre colonnes, ou sur une expression. Elles ne remplacent ni le modèle ni un index utile.

### Jointures
- **Granularité** : toujours se demander « qu'identifie une ligne du résultat ? » avant d'agréger. Une jointure un-à-plusieurs multiplie les lignes du parent et fausse les sommes.
- Algorithmes :

| Algorithme | Situation favorable |
|---|---|
| Nested Loop | Peu de lignes, recherche ciblée, bon accès interne |
| Hash Join | Égalité sur grands ensembles |
| Merge Join | Entrées déjà ordonnées |

  Il n'existe pas d'algorithme gagnant partout : le moteur décide selon volumes et sélectivité.
- **INNER JOIN** garde les lignes avec correspondance. **LEFT JOIN** garde aussi celles de gauche sans correspondance. Un filtre sur la table de droite mis dans `WHERE` retire les lignes sans correspondance (le LEFT JOIN devient un INNER JOIN) ; mis dans `ON`, il garde le comportement externe.
- **EXISTS** répond à « existe-t-il au moins un… ? » sans multiplier les lignes. Le planificateur le transforme souvent en **semi-jointure**.
- Une sous-requête corrélée **n'est pas toujours exécutée une fois par ligne**. On regarde le plan.
- **Agréger avant de joindre** explicite la granularité, mais n'est pas toujours plus rapide (travail inutile si on ne demande qu'un sous-ensemble).

### CTE, vues, vues matérialisées
- **CTE** (`WITH`) : étape nommée, intégrée ou matérialisée selon le cas.
- **Vue** : définition SQL mémorisée, pas le résultat.
- **Vue matérialisée** : résultat stocké, à rafraîchir. Gain de vitesse au prix d'un décalage de fraîcheur : préciser qui rafraîchit, quand, et ce que l'API promet. Adaptée à un tableau de bord horaire, pas à un écran d'astreinte.

---

## 2. Atelier 1 : diagnostic initial

**Consigne (slide 23)** : charger le schéma et les données, lancer l'historique du client 42 et une agrégation, vérifier lignes et total, 5 répétitions après échauffement, identifier un nœud coûteux et une hypothèse. **Aucun index supplémentaire.**

### Mise en place
- Les scripts `01_schema.sql` et `02_donnees.sql` sont montés dans `/docker-entrypoint-initdb.d/` par `compose.yaml` : PostgreSQL les exécute au **premier démarrage** du volume. Pour repartir de zéro : `docker compose down -v`.
- Les tables sont dans le schéma **`shopflow`** : préfixer (`shopflow.commandes`) ou faire `SET search_path TO shopflow, public;` à chaque session.
- Accès : `docker exec -it api-postgres-1 psql -U cours -d shopflow`, ou pgAdmin sur `http://localhost:5050`.

### Protocole
1. Vérifier le **nombre de lignes et le total** avant de mesurer (référence calculée autrement, directement sur la table).
2. **3 exécutions d'échauffement**, puis **5 mesures** avec `EXPLAIN (ANALYZE, BUFFERS)`. Noter l'`Execution Time` de chacune, prendre la médiane.
3. Conserver : SQL complet, plan complet, version de PostgreSQL (`SELECT version();`), résultats fonctionnels, 5 temps, BUFFERS.

### Résultats
| Requête | Lignes | Total | Médiane (chaud) |
|---|---|---|---|
| Q1 historique client 42 (`LIMIT 20`) | 20 (client : 100 commandes, 47 760,00 €) | 14 400,00 € | 0,229 ms |
| Q2 agrégation mensuelle | 30 groupes | 29 775 001,25 € (= table entière) | 84,1 ms |

### Diagnostic
- **Q2, nœud coûteux = `Sort`** (≈ 48 % du temps) : `external merge, Disk: 3040kB`, car `work_mem` = 4 MB est trop petit. Le Seq Scan est normal (toute la table est nécessaire).
- **Écart d'estimation** : 80 048 groupes estimés pour 30 réels, faute de statistique sur `date_trunc('month', created_at)`. Du coup le planificateur trie au lieu de faire un `HashAggregate`.
- **Pistes testées sur une copie** (voir 3bis) : `SET work_mem = '32MB'` (×1,7) et une statistique étendue sur l'expression (×1,9).
- **Q1, nœud le plus coûteux = `Bitmap Heap Scan`** : 88 pages lues pour 100 commandes dispersées, puis tri pour n'en garder que 20. L'index utilisé est l'index unique `(client_id, cle_idempotence)` issu d'une contrainte, qui ne contient pas `created_at`.
- **Piste testée à l'Atelier 3** (voir 3ter) : index composé `(client_id, created_at DESC, id DESC)`, 21 lignes dans l'ordre sans tri (×2,5 sur la requête de l'API, WAL +35 % à l'écriture).

### À retenir
- Un `LIMIT` ne réduit pas le travail si PostgreSQL doit d'abord lire et trier toutes les lignes du client.
- Un bon diagnostic relie un nœud précis à une cause chiffrée, puis propose une expérience.

### Ce que j'ai compris (Atelier 1)
- Avant de chercher à aller plus vite, je dois **vérifier que le résultat est juste** : nombre de lignes et total. Ces chiffres sont ma référence pour la suite.
- Une seule mesure ne veut rien dire. Je **chauffe** la requête, puis je la lance 5 fois et je regarde la **médiane**. La première exécution à froid était 13 fois plus lente (1 096 ms contre 84 ms) alors que la requête était la même.
- `EXPLAIN (ANALYZE, BUFFERS)` me montre **ce que PostgreSQL fait vraiment**, étape par étape (les « nœuds »). Je le lis de bas en haut, et le temps d'un parent contient déjà celui de ses enfants.
- Pour l'agrégation, le problème n'est pas la lecture de la table (normale, il faut tout lire) mais le **tri qui déborde sur le disque** : `work_mem` est trop petit, et PostgreSQL se trompe sur le nombre de groupes (80 048 prévus, 30 réels), donc il trie au lieu de compter en mémoire.
- Pour le client 42, la requête est déjà rapide, mais elle lit 100 commandes pour n'en garder que 20. L'index ne connaît pas la date : c'est la piste de la journée 2.
- Un bon diagnostic dit **quelle étape coûte, pourquoi, et comment le vérifier**. « C'est lent » n'est pas un diagnostic.

---

## 3. Atelier 2 : réécriture équivalente

**Consigne (slide 31)** : comparer une jointure qui duplique les clients avec EXISTS ; construire un total par commande sans multiplier `commandes.total` ; utiliser un client avec plusieurs commandes et une commande avec plusieurs lignes.

**Règle d'or** : prouver l'équivalence du résultat **avant** de comparer les durées. Si la réécriture perd des lignes, la rejeter même si elle est plus rapide. Si deux plans sont identiques, l'expliquer.

### A. Jointure contre EXISTS (clients ayant une commande payée)
| Variante | Lignes | Clients distincts | Médiane | Verdict |
|---|---|---|---|---|
| A1 jointure | 80 000 | 800 | 27,6 ms | Rejetée : le client 42 apparaît 100 fois |
| A2 jointure + `DISTINCT` | 800 | 800 | 40,2 ms | Correcte mais la plus lente |
| A3 `EXISTS` | 800 | 800 | **11,3 ms** | Correcte et la plus rapide |

- Contrôle d'équivalence : différence symétrique (`EXCEPT` dans les deux sens) entre A2 et A3 = **0 ligne**.
- Plan de A3 : `Nested Loop Semi Join` (s'arrête dès qu'une commande payée est trouvée).
- `DISTINCT` pour masquer des doublons n'est pas une réécriture : il rajoute un `HashAggregate` sur 80 000 lignes.

### B. Total par commande
| Variante | Total (client 42) | Médiane | Verdict |
|---|---|---|---|
| Référence `commandes.total` | 47 760,00 € | | |
| B1 `sum(c.total)` après jointure avec `lignes` | 143 280,00 € | 1,10 ms | Rejetée : total × 3 (3 lignes par commande) |
| B2 `sum(l.qte * l.prix_unitaire)` | 47 760,00 € | 2,05 ms | Correcte |

- Exemple commande 42 : B1 = 720,00 €, B2 = 240,00 € = 58,75 + 80,00 + 101,25 = `commandes.total`.
- B1 est presque deux fois plus rapide uniquement parce qu'elle est fausse (`Index Only Scan`, rien à lire dans la table). **Le surcoût de B2 est le prix de l'exactitude.**

### À retenir
- Une jointure **un-à-plusieurs change la granularité** : n'agréger que ce qui est à la bonne granularité (les lignes, pas `commandes.total`).
- **EXISTS** pour une question de présence : correct, sans doublons, et souvent plus rapide.
- On ne choisit jamais une requête sur sa seule durée.

### Ce que j'ai compris (Atelier 2)
- Réécrire une requête, c'est changer **comment** on la dit, pas **ce qu'elle répond**. Je dois le **prouver** (même nombre de lignes, mêmes clients, même total) avant de comparer les temps.
- Une jointure avec une table « plusieurs » (commandes, lignes) **multiplie les lignes** : le client 42 apparaissait 100 fois, et chaque total comptait 3 fois. Je me demande toujours : *qu'est-ce qu'une ligne de mon résultat ?*
- Pour savoir **si quelque chose existe**, j'utilise `EXISTS` : pas de doublons, et PostgreSQL s'arrête dès qu'il trouve. Ici : 11 ms contre 27 ms pour la jointure, et 40 ms avec `DISTINCT`.
- `DISTINCT` pour cacher les doublons n'est pas une vraie réécriture : on construit 80 000 lignes puis on les supprime.
- Une requête **plus rapide mais fausse est rejetée** (B1 : 1,1 ms mais total × 3). Celle qui est juste (B2 : 2,05 ms) coûte un peu plus, et c'est normal : c'est le prix de l'exactitude.
- Pour un total, je somme **à la bonne granularité** (les lignes de commande), jamais `commandes.total` après une jointure un-à-plusieurs.

---

## 3bis. Optimisations testées (sur une copie, hors atelier 1)

L'atelier 1 interdit d'ajouter index ou statistiques dans la base du labo. Les pistes ont été testées sur une **copie** (`shopflow_opt`), **un seul changement à la fois**, même protocole (3 échauffements, 5 mesures, médiane), **résultat identique prouvé** (empreinte md5 du résultat complet).

| Optimisation | Requête | Avant | Après | Gain | Coût / limite |
|---|---|---|---|---|---|
| O1 `SET work_mem = '32MB'` | Q2 agrégation | 84,6 ms | 50,2 ms | ×1,7 | Mémoire par opération et par connexion : à limiter à une session |
| **O2** `CREATE STATISTICS` sur `(date_trunc('month', created_at)), statut` + `ANALYZE` | Q2 agrégation | 84,6 ms | 45,5 ms | ×1,9 | Faible (non mesuré). **Recommandée : corrige la cause** |
| O1 + O2 | Q2 agrégation | 84,6 ms | 47,9 ms | ×1,8 | Pas mieux que O2 seule |
| Réécriture EXISTS (atelier 2) | clients avec commande payée | 27,6 ms | 11,3 ms | ×2,4 | Aucun |

- **Hypothèse de l'atelier 1 confirmée** : donner plus de mémoire **ou** corriger l'estimation remplace le gros tri par un `HashAggregate`. Le `Sort` qui reste ne trie plus que 30 lignes (`ORDER BY`).
- L'optimisation de Q1 (index) est traitée, avec les vraies requêtes de l'API, à l'**Atelier 3** (section 3ter). Les mesures préliminaires faites sur la copie ont été remplacées.

### Ce que j'ai compris (optimisations)
- Optimiser = mesurer **un gain ET un coût**, avec un **résultat inchangé**.
- On corrige **d'abord la cause** (la statistique règle l'erreur d'estimation) plutôt que de masquer le symptôme (augmenter `work_mem`).
- **Un index n'est pas gratuit** : il accélère la lecture mais ajoute du travail à chaque insertion (Atelier 3 : WAL +35 % pour le composé) et prend de la place (≈ 30 % de la table).
- Je compare **dans le même environnement** : la copie est plus compacte que le labo (840 pages contre 1 674 pour `commandes`), donc les gains O1 et O2 se lisent au sein de la copie.

---

## 3ter. Atelier 3 : l'historique client (Jour 2)

Documentation complète, scripts, mesures brutes et migration : dossier [`atelier3/`](atelier3/README.md). Le labo a été vérifié avant et après : **état initial retrouvé** (6 index, 0 statistique). Résultat fonctionnel **identique** pour les 75 combinaisons testées.

**Les requêtes testées** : celle du cours, **celle de l'API** (`01_server/api/commandes.mjs`, 21 lignes, renvoie aussi `statut`) et sa page suivante par **curseur**.

| Variante | API, client 42 (médiane, 51 tours) | Buffers | Client à 20 100 commandes | Taille | WAL (20 000 insertions) | Décision |
|---|---|---|---|---|---|---|
| Initiale | 0,690 ms (avec `Sort`) | 96 | 23,3 ms | index unique : 1 864 kB | référence | |
| Index simple `(client_id)` | 0,729 ms | 96 | 23,3 ms | 688 kB | +28,2 % | **Rejeté : aucun gain** |
| **Composé** `(client_id, created_at DESC, id DESC)` | **0,274 ms (×2,5)** | 27 | **0,256 ms (×91)** | 3 984 kB | +35,0 % | **Retenu** |
| Couvrant `INCLUDE (statut, total)` | 0,199 ms (×3,5) | 7 | 0,189 ms (×123) | 5 792 kB | +42,1 % | Option |
| Couvrant `INCLUDE (total)` | 0,267 ms (×2,6) | 27 | 0,276 ms (×84) | 4 864 kB | +38,4 % | **Rejeté : ne couvre pas l'API** |

- **Simple : absence de gain.** La base a déjà un index qui commence par `client_id` (l'unique). PostgreSQL utilise le nouveau (plus petit) mais le **plan est identique** : il lit les 100 commandes et les trie.
- **Le coût sans index grandit avec le volume** : 96 buffers (100 commandes), 287 (20 100 commandes) ; avec l'index composé il reste ≈ 27. C'est l'argument principal.
- **Piège de l'alias** : les colonnes de sortie de l'API s'appellent aussi `id` et `created_at`. `ORDER BY created_at` sans qualificatif trie sur ces **textes** : l'index composé n'est plus utilisé (0,783 ms, 93 buffers). L'API écrit `commandes.created_at`, ce qui est indispensable.
- **`INCLUDE (total)` ne couvre pas l'API** : elle lit `statut`. Bon pour la requête du cours, inutile pour le SQL réellement émis.
- **`INCLUDE` ne garantit pas zéro `Heap Fetches`** : 0 → 40 après une modification sans `VACUUM`.
- **Écriture** : le **WAL** est la mesure fiable (≈ 20 000 enregistrements de plus par index). Les durées sont très bruitées (+23 % à +62 % pour le composé selon l'exécution).
- **Mesures bruitées** : la même requête a pris 0,23 ms à l'Atelier 1 et ≈ 0,55 ms plus tard. On compare des **mesures alternées**, et on s'appuie sur les buffers, les plans et le WAL.
- **Migration** `atelier3/migration/` : montée, rejeu sans erreur, vérification, retour arrière, variante `CONCURRENTLY` (échoue bien dans une transaction). **Testée sur une base jetable, non appliquée au labo.**

### Ce que j'ai compris (Atelier 3)
- Un index ne sert que s'il **fournit ce que la requête demande** (ici l'ordre). Une **absence de gain est un résultat**, pas un échec à cacher.
- L'ordre des colonnes suit l'usage : égalité (`client_id`), puis tri (`created_at DESC, id DESC`) : 21 entrées lues, plus de tri.
- **Je teste le SQL réellement émis par l'application** : un `INCLUDE` ou un `ORDER BY` mal choisi peut rendre un index inutile.
- Un index **se paie à chaque écriture** (WAL +35 %) et prend de la place (≈ 30 % de la table).
- Je **décide avec des chiffres et je dis ce qui me ferait changer d'avis** : composé retenu, couvrant en option, simple et couvrant `(total)` rejetés.

---

## 4. Réponses aux questions de compréhension (slide 33)
1. **Pourquoi ne pas additionner les durées de tous les nœuds ?** Les nœuds imbriqués partagent du travail : le temps d'un parent inclut celui de ses enfants.
2. **Quand un parcours séquentiel est-il raisonnable ?** Table petite, ou requête qui lit une grande part des lignes.
3. **Pourquoi une moyenne faible peut masquer un problème ?** Les percentiles (p95, p99) rendent visible la queue de latence.
4. **Qu'est-ce qui rend deux benchmarks comparables ?** Un scénario et un environnement stables.
5. **Pourquoi `incidents` JOIN `incident_events` change la granularité ?** Il produit une ligne par événement, pas une ligne par incident.
6. **Une sous-requête corrélée = une exécution par ligne ?** Non : le planificateur peut la transformer en semi-jointure ou autre plan équivalent. Examiner `EXPLAIN (ANALYZE, BUFFERS)`.

---

## 5. Aide-mémoire

```sql
SET search_path TO shopflow, public;                -- en début de session

EXPLAIN (ANALYZE, BUFFERS) <requête>;               -- plan + mesures (exécute la requête)
SELECT version();                                   -- version PostgreSQL
SHOW work_mem;  SET work_mem = '32MB';              -- mémoire de tri (session seulement)
ANALYZE shopflow.commandes;                         -- rafraîchir les statistiques
CREATE STATISTICS ... ON ... FROM ...;              -- statistiques étendues
DROP STATISTICS IF EXISTS shopflow.nom;             -- les retirer
```

```bash
docker compose up -d --wait        # démarrer (dans 01_server/api)
docker compose down -v             # tout effacer, base comprise
docker exec -it api-postgres-1 psql -U cours -d shopflow
```

**Pièges fréquents** : tables introuvables (oublier le schéma `shopflow`) ; `EXPLAIN ANALYZE` sur une écriture (elle est vraiment exécutée) ; comparer une mesure à froid et une à chaud ; sommer une colonne du parent après une jointure un-à-plusieurs ; oublier que `WHERE` sur la table de droite annule un `LEFT JOIN`.

---

## 5bis. Jour 2 : indexer

Explication simple du cours (jusqu'à l'atelier 3) : voir [`COURS_JOUR2_SIMPLE.md`](COURS_JOUR2_SIMPLE.md).

- **Index** = structure triée qui évite de parcourir la table, mais il **prend de la place et ralentit les écritures** (mesuré à l'Atelier 3 : WAL +35 % pour 20 000 insertions avec l'index composé).
- **Ordre des colonnes** d'un index composé : égalité d'abord (`client_id`), puis tri (`created_at DESC, id DESC`). Avec `LIMIT`, l'index évite le tri.
- **`INCLUDE` ne garantit pas** d'éviter la table : on vérifie `Heap Fetches` dans le plan.
- Un **compteur d'usage nul ne prouve pas** qu'un index est inutile (il peut protéger une contrainte, comme l'index unique `(client_id, cle_idempotence)`).
- **Un gain non reproductible ou un index inutilisé n'est pas une réussite** ; on présente aussi les variantes rejetées.

---

## 6. À venir
- Appliquer la migration 001 (index composé) au labo quand le cours le demandera (`atelier3/migration/`), puis Atelier 4 (index spécialisés : partiel, GIN, GiST) et migration/bilan.
- Les optimisations O1 (`work_mem`) et O2 (statistique) ne sont testées que sur une copie ; les refaire dans le labo si besoin.
