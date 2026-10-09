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

## 3quater. Atelier 4 : index spécialisés (Jour 2)

Documentation complète, script, mesures brutes et migration : dossier [`atelier4/`](atelier4/README.md). Laboratoire vérifié avant/après : **état initial retrouvé**. Résultats fonctionnels **identiques** entre variantes (empreinte md5).

| Besoin | Index | Résultat mesuré | Coût d'écriture | Décision |
|---|---|---|---|---|
| File des commandes `en_attente` (10 % de la table) | **Partiel** `(created_at, id) WHERE statut = 'en_attente'` | **×145**, 1 680 → 3 buffers, index de **328 kB** (2,4 % de la table) | WAL **+3,2 %** | **Retenu** (migration 002) |
| Même file, tous statuts | Complet `(statut, created_at, id)` | ×130 à ×184, 4 072 kB (**12,4 fois** le partiel) | WAL **+36,5 %** | Rejeté |
| Attributs de `produits` (200 lignes) | GIN | **jamais utilisé** (`idx_scan = 0`), Seq Scan sur 3 pages | n/a | **Rejeté** |
| Attributs à 200 000 lignes | GIN | valeur rare (0,1 %) **×17** ; valeur à 24,9 % ×2,0 ; **inutile pour `->>`** | WAL **+120,7 %** | Conditionnel |
| Propriété connue (`categorie`) | Expression ou colonne typée | **×28** / **×30** | WAL +34,6 % / +38,9 % | **Préférable** |
| Chevauchement de périodes | GiST `&&` | **×164**, 1 474 → 8 buffers | WAL **+54,1 %**, insertion **×7,8** | Retenu si le besoin existe |

- **Un partiel ne sert que son prédicat** : pour `payee` et `annulee` le plan reste un Seq Scan. L'écriture d'une ligne qui **quitte** la file ne coûte rien (WAL identique), celle d'une ligne qui y **entre** coûte une entrée.
- **Piège de la requête paramétrée** : avec `statut = $1` et un plan **générique**, l'index partiel n'est pas utilisé (PostgreSQL ne peut pas prouver que la condition implique le prédicat). Il faut le littéral.
- **`now()` dans un prédicat** : refusé (`functions in index predicate must be marked IMMUTABLE`).
- **Un Seq Scan peut être rationnel** : sur 200 produits (3 pages), ni le GIN ni l'index d'expression ne sont utilisés. Test à 200 000 lignes réalisé.
- **Le GIN sert `@>`, pas `->>`** ; l'index d'expression sert `->>`, pas `@>`. Le GIN est le plus **petit** mais le plus **coûteux** à maintenir.
- **GiST** : les intervalles sont semi-ouverts `[)` : une période contiguë ne chevauche pas.
- **Deux défauts de mesure trouvés et corrigés** : buffers incomplets (il faut `hit` **+** `read`) et plans parallèles non comparables à des plans simples (parallélisme désactivé pour les mesures alternées).

### Ce que j'ai compris (Atelier 4)
- Je **choisis l'index d'après la requête et l'opérateur**, pas l'inverse.
- Un index partiel est **petit et peu coûteux** mais ne répond qu'à son prédicat.
- Je **teste la requête telle que l'application l'enverra** (paramètre, plan générique).
- Un **Seq Scan peut être le bon choix** sur une petite table ; je vérifie à plus grand volume.
- L'utilité d'un index dépend de la **rareté de la valeur** (GIN : ×17 à 0,1 %, ×2,0 à 24,9 %).
- **Mes propres mesures se vérifient** avant de conclure.

## 3quinquies. Atelier 4 bis : migration de schéma compatible (Jour 2, slides 33 à 43)

Détail complet pour l'oral : [`ATELIER4BIS_DE_A_A_Z.md`](ATELIER4BIS_DE_A_A_Z.md). Scripts et résultats : `atelier4bis/`.

- **Question** : ajouter `newsletter_ok` (NOT NULL, défaut false) à `clients` pendant que l'application tourne, sans la casser ni la bloquer. Fait sur une copie (`clients_migration_tp`), avec une table de référence pour comparer.
- **Méthode en étapes** : colonne nullable (instantané, 1 000 NULL) → `SET DEFAULT false` (**ne remplit pas** les anciennes lignes : toujours 1 000 NULL) → lots de 200 en autocommit (200, 200, 200, 200, 200, puis 0 ; rejouable : relancé après 0 il modifie 0 ligne) → `CHECK … NOT VALID` (`convalidated = false`, **refuse déjà** un NULL : erreur 23514) → `VALIDATE CONSTRAINT` (verrou léger) → `SET NOT NULL` (**saute le scan** grâce au CHECK validé : message DEBUG1 relevé).
- **Résultat identique** : 1 000 / 0 NULL / 1 000 false ; écriture de NULL refusée (23502) ; **0 écart** sur `id`, `email`, `nom` (`EXCEPT ALL` dans les deux sens, md5 identique à la table d'origine). Un comptage seul ne prouve pas l'égalité des valeurs.
- **Verrous** (deux vraies connexions) : A garde `ACCESS SHARE` (transaction ouverte) ; B (`ALTER`, `lock_timeout = 2 s`) échoue en **55P03 après 2,005 s** ; après le `COMMIT` de A, le même `ALTER` réussit. `lock_timeout` limite l'**attente**, pas la durée du DDL.
- **File d'attente (slide 31, vérifiée)** : avec B en attente, une simple lecture C arrivée après reste **bloquée 3,005 s** derrière lui, alors que A ne détient qu'un verrou de lecture compatible. C'est le danger réel d'un `ALTER` sur une table très lue.
- **Retour arrière** : le premier bloc retire contrainte, NOT NULL et défaut (colonne et valeurs encore là) ; `DROP COLUMN` **détruit** les valeurs. Le retour de structure ne reconstitue pas les données : en production, conserver les valeurs et prévoir le retour de la version applicative. 01 ne se rejoue pas (42P07), on reprend à 02.
- **Ancienne → nouvelle version à 3 000 000 lignes** (table jetable, une seule exécution, même résultat md5 `b227f2377b62`) : temps sous `ACCESS EXCLUSIVE` pour poser NOT NULL **3 324 → 46,3 ms** (×72 ; une première exécution : ×226) ; écriture la plus longue bloquée **30 989 → 416 ms** ; **mais** remplissage **57 → 156 s** (≈ ×2,7 plus long) et plus de WAL. On échange du temps total contre l'absence de blocage.
- **Preuve de verrouillage déterministe** : pendant `VALIDATE` (`ShareUpdateExclusiveLock`) lecture, UPDATE et INSERT concurrents passent ; pendant `SET NOT NULL` (`AccessExclusiveLock`) une lecture est bloquée (55P03 après 500 ms).
- **Ce n'est pas un gain de vitesse de requête** (le cours le dit) : optimiser une migration, c'est réduire l'attente des autres.
- **Défaut trouvé dans mon propre script et corrigé** : une erreur de psql (sortie d'erreur) pouvait arriver après la commande suivante dans le tube et être mal attribuée ; sentinelle sur chaque flux, deux scripts relancés en entier.

### Ce que j'ai compris (Atelier 4 bis)
- Je **découpe une migration** : chaque étape garde un verrou court ou léger, et l'ancienne version de l'application continue de fonctionner.
- Un **`DEFAULT` ne remplit pas l'existant** (1 000 NULL vérifiés) : il faut un remplissage par lots.
- **`NOT VALID` puis `VALIDATE`** : la règle protège tout de suite les nouvelles écritures, la vérification des anciennes lignes se fait ensuite avec un verrou qui ne bloque ni lectures ni écritures. Un CHECK validé permet à `SET NOT NULL` de **sauter le scan**.
- **`lock_timeout` borne l'attente**, pas le DDL, et une lecture simple peut rester coincée **derrière** un `ALTER` en attente.
- **Le retour arrière est partiel** : `DROP COLUMN` détruit les valeurs.
- **À grand volume la nouvelle méthode est plus lente au total mais bloque presque personne** ; je le dis au lieu de ne montrer que le bon chiffre. Limites : copie de 1 000 lignes, une seule exécution à 3 millions.

## 3sexies. Atelier 7 : la page et ses relations, puis PgBouncer (Jour 4)

Détail pour comprendre et expliquer : [`ATELIER7_DE_A_A_Z.md`](ATELIER7_DE_A_A_Z.md). Scripts et résultats : `atelier7/`. Cours Jour 4 (slides 1 à 12) : [`COURS_JOUR4_SIMPLE.md`](COURS_JOUR4_SIMPLE.md).

- **Trois problèmes différents, trois corrections séparées** : N+1 (nombre de requêtes), OFFSET (lignes parcourues), connexions (PgBouncer).
- **N+1 → chargement groupé** : 1 + N requêtes (6, 21, 51, 101 pour 5, 20, 50, 100 commandes) → **2**, **réponse JSON identique** (lignes comprises). Durée HTTP médiane (30 tours alternés) : 55,3 → 43,9 ms pour 20 commandes, 68,5 → 44,2 ms pour 50 : gain **modeste** en base locale ; une baisse du nombre de requêtes n'est pas à elle seule un gain mesuré. Page vide : 1 requête.
- **OFFSET contre curseur** : le curseur est la paire **(created_at, id)** de la dernière ligne ; `LIMIT 21` donne `hasNextPage` sans `COUNT(*)`. Page 2 identique par les deux méthodes (2 SQL chacune). Avec 100 commandes on ne peut pas conclure sur la vitesse (consigne de la fiche) : **table de travail de 1 000 000 de commandes**, même page à chaque profondeur (md5) : OFFSET 0,171 → 99,7 → **944 ms** (décalages 0, 100 000, 999 000 ; ≈ 1 page lue par ligne sautée), curseur **0,15 à 0,2 ms et 24 pages partout**. **Aucun gain à petite profondeur** ; le curseur ne sert qu'à « suivant ».
- **Dates identiques** (commandes 2042, 1042, 42, limite 2) : page 1 = 2042, 1042 ; page 2 = 42, 86042 ; avec **la seule date** la page suivante donne 86042, 83042 (**42 perdue**) : l'id départage les dates égales.
- **Droits** : 401 sans jeton, 400 avec `client_id` dans l'URL, 400 avec un curseur falsifié. Un curseur **signé n'est pas une autorisation** : le client vient du contexte (`LAB_CLIENT_ID`), jamais de l'URL. Un curseur n'est pas un instantané. Parcours : 5 pages, 100 ids uniques, même ordre que PostgreSQL.
- **PgBouncer** (labo séparé, 5 connexions serveur, mode transaction) : 40 clients : connexions PostgreSQL **40 → 5**, mais débit **261 → 94 transactions/s** et latence 153 → 422 ms (5 × 20 transactions/s = 100 au plus) : **moins de connexions ne signifie pas moins de latence**. 80 clients : refus en direct (« remaining connection slots are reserved ») ; avec PgBouncer tous servis, `cl_waiting` 66 à 69 : **un refus devient de l'attente**. Test avec reconnexion (`-C`) : **instable**, ordre inversé entre deux campagnes, aucune conclusion. PgBouncer ne corrige ni le N+1 ni les index.
- **Pièges rencontrés** : `ORDER BY` sur les alias de sortie (texte) neutralise l'index (qualifier `commandes.created_at`, 3 s au lieu de 0,2 ms) ; ma première mesure ne lisait que l'index et sous-estimait OFFSET (colonnes de l'API ajoutées).
- **Laboratoire** : dates restaurées (empreinte md5 identique), table de sauvegarde du kit supprimée, état initial retrouvé.

### Ce que j'ai compris (Atelier 7)
- Je **compte les requêtes avant de parler de durée** : N+1 se reconnaît au nombre qui croît avec N.
- Je **corrige séparément** requêtes, lignes parcourues et connexions.
- Le curseur contient **la date et l'id**, et **ne sert qu'à « suivant »** ; il n'apporte rien à petite profondeur.
- Un curseur signé **n'est pas** un contrôle d'accès.
- **PgBouncer limite les connexions, il n'accélère pas** ; il transforme un refus en attente.
- Un test **instable** se relance et se dit. Limites : base locale, 100 commandes, campagnes de 20 secondes.

## 3septies. Atelier 8 : cache Redis et fraîcheur (Jour 4)

Détail pour comprendre et expliquer : [`ATELIER8_DE_A_A_Z.md`](ATELIER8_DE_A_A_Z.md). Scripts et résultats : `atelier8/`. Cours (slides 14 à 33) : partie 2 de [`COURS_JOUR4_SIMPLE.md`](COURS_JOUR4_SIMPLE.md).

- **Cache-aside** (slide 24) : l'API lit Redis ; **hit** = 0 SQL ; **miss** = 1 SELECT puis une copie avec **TTL 60 s** ; le PATCH fait l'UPDATE puis supprime la clé. PostgreSQL reste la source de vérité. Clé `shopflow:produit:v1:42` (version de format incluse).
- **Miss/hit** : 1 SELECT contre 0, données identiques (5 paires + 100 paires). Mesure sur **connexion persistante** : **2,709 → 0,988 ms (×2,7)** ; temps dans l'API 2,08 → 0,671 ms. L'aide du kit (un processus Node par appel, ≈ 40 ms fixes) **noie** la différence (43,0 contre 42,0 ms). Gain **petit** en local ; le vrai gain est la **charge évitée sur PostgreSQL**.
- **Un cache peut mentir** : après un **UPDATE direct** en SQL (19,90), l'API a servi l'**ancien prix 57,50** (hit, 0 SQL) ; après `DEL` : 19,90 (miss). Le **TTL n'actualise pas la copie après une écriture**, il borne sa durée. Par l'API (PATCH) : `invalidation=ok`, GET suivant correct.
- **Invalidation échouée** (PATCH pendant que Redis est arrêté) : `invalidation=echouee`, **PostgreSQL = 34,90**, la copie ancienne (29,90) a survécu au redémarrage (Redis sauvegarde à l'arrêt) : **une erreur d'invalidation n'annule pas l'écriture**.
- **Course (slide 30)** reproduite à la main : A lit 34,90 ; B écrit 39,90 et supprime la clé ; A remet 34,90 : l'API sert 34,90, PostgreSQL a 39,90. Le `DEL` de B est avant le `SET` de A. Pistes : **version** (écriture conditionnelle), **invalidation rejouée** (outbox), TTL court.
- **Expiration** : TTL 60 → −2 après 61 s, puis miss à 1 SELECT. **Panne de Redis** : l'API répond (200, `indisponible`, 1 SELECT) mais **chaque lecture devient un SELECT** (30 appels : 30 SELECT contre 0) : risque de surcharge de la base (slide 32). Une erreur de cache ne signifie pas que le produit n'existe pas.
- **Rafale (slide 31)** : 20 lectures simultanées, clé absente : **6 miss, 6 SELECT** (au lieu d'un) ; clé présente : 20 hit, 0 SQL (une mesure, non reproductible à l'unité).
- **Fraîcheur déclarée** : catalogue : **quelques secondes à une minute** ; **achat/stock : pas de cache**, contrôle dans PostgreSQL dans la transaction.
- **Écart avec la fiche** : TTL passé par variable d'environnement, `.env` intact (empreinte vérifiée). Prix initial 57,50 **restauré**, table `produits` identique, Redis redémarré.

### Ce que j'ai compris (Atelier 8)
- Hit = 0 SQL, miss = 1 SELECT ; le gain de durée est **petit en local**, le gain réel est la **charge évitée**, et il faut le **mesurer avec le bon outil**.
- **Un cache peut mentir** : TTL ≠ fraîcheur après une écriture ; une écriture hors du chemin qui invalide laisse une copie périmée.
- **Invalider = supprimer la clé après l'écriture validée** ; si ça échoue, l'écriture reste et la copie reste ancienne ; supprimer la clé ne règle pas toutes les courses.
- **Redis en panne** : l'API se replie sur la base, au prix de plus de SQL ; **on ne cache pas ce qui engage** (achat, stock).
- Limites : un produit, tout en local, course reproduite à la main, rafale = une mesure.

## 3octies. Jour 5 : monitorer et prouver (document `test.pdf`, dossier `atelier9/`)

Chapitre ajouté au PDF principal dans **`test.pdf`** (71 pages : 59 identiques + pages 60 à 71). Détail : [`atelier9/README.md`](atelier9/README.md). Tests sur une **copie jetable** (mêmes données, md5 identiques) ; laboratoire intact.

- **`pg_stat_statements`** : le classement par temps cumulé montre le rapport mensuel (10 appels, 1 117 ms) ; le N+1 (20 000 appels × 0,018 ms = 369 ms) est invisible alors que l'API mesure 14,2 ms de `sqlMs` par page de 20 (×38 le temps vu par PostgreSQL) : le coût est dans les allers-retours. Le signal est le **nombre d'appels**. Le N+1 est **absent du journal des requêtes lentes** (`log_min_duration_statement`). L'extension coûte ×1,01 (mesure alternée).
- **`work_mem`** : budget **par opération** (calcul théorique 32 MB × 4 × 100 connexions = 12,5 Go) ; la requête de la slide 13 ne déborde pas (aucun effet) ; l'agrégation mensuelle passe de 84,0 à 53,5 ms (tri disque 3 040 kB → mémoire). **`effective_cache_size`** : aucun changement de plan observé, non modifié.
- **VACUUM** : bloqué par une transaction longue (0 supprimée, 200 000 mortes non supprimables) ; 200 000 supprimées après son COMMIT ; l'espace est réutilisable, pas rendu.
- **Atelier 9 (1/5/10/20 clients, un seul changement par série, 3 essais alternés)** : index composé 14 840 → 25 133 tps (×1,7), p95 2,8 → 1,5 ms ; chargement groupé 246,9 → 1 032,1 req/s (×4,2), p95 98,0 → 26,8 ms, 0 erreur, CPU constant (50 %) : gain = travail évité. Le N+1 plafonne dès 5 clients (≈ 247 req/s), la file du pool monte à 15.
- **Pool** (2 essais, indicatif) : 5 → 20 supprime l'attente et relève le débit, la base n'est pas saturée ; **corriger le N+1 vaut mieux qu'agrandir le pool** (1 032 contre ≈ 287 req/s).
- **Charge fermée / ouverte** : la fermée (0 erreur) **masque** la saturation ; l'ouverte est instable à 90 % et s'effondre à 130 % (503 : le pool abandonne après 1 s). **Rapports concurrents** sur la même instance : p95 des commandes +64 %, p99 ×2,2, médiane inchangée.
- **Export et contrat** : 240 lignes (jours UTC), Σ nb = 80 000 et Σ montant = 23 750 126,25 exacts, reproductible (même md5) ; une jointure aux lignes multiplie le montant par 3 ; 4 896 commandes changent de jour entre UTC et Paris ; une annulation tardive modifie une journée déjà publiée (333 / 137 287,50 → 332 / 136 950,00) : règle de republication. Lakehouse / Data Mesh : conçus, non déployés.
- **Classification (slide 2)** : reproductibles (index, groupé), variation de mesure (pool), instable (charge ouverte à 90 %), **déplacement du coût** (écriture de l'index +35 % de WAL, rapports concurrents, fraîcheur du cache).
- **Pièges** : mesure `work_mem` non alternée donnait 42 contre 31 ms pour un même plan (effet d'ordre) : refaite en tours alternés ; la taille de pool et la charge ouverte ne se résument pas par une médiane.

### Ce que j'ai compris (Jour 5)
- J'**observe avant de régler** : `pg_stat_statements` (cumulé, appels), journal lent, `pg_stat_activity`, et je recoupe plusieurs sources (le N+1 n'apparaît dans aucune seule).
- Un réglage a un **périmètre** (`work_mem` par opération) ; sans preuve (plan, mesure) je **ne change pas** (`effective_cache_size`).
- Une **transaction longue** bloque le nettoyage.
- Je mesure la **courbe de charge** avec **un seul changement par série**, en distinguant **reproductible**, **variation de mesure** et **déplacement du coût**, et j'écris des conclusions **bornées** à la machine, au jeu et à la charge.
- Charge **fermée** et **ouverte** ne se comparent pas : la fermée masque la saturation.

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
- Appliquer les migrations 001 (index composé, `atelier3/migration/`) et 002 (index partiel, `atelier4/migration/`) au labo quand le cours le demandera (non appliquées : le labo est resté à l'état initial). L'atelier 4 bis est fait (copie supprimée à la fin ; relancer `atelier4bis/run_atelier.py` pour le rejouer).
- Les optimisations O1 (`work_mem`) et O2 (statistique) ne sont testées que sur une copie ; les refaire dans le labo si besoin.

## Présentation orale de 5 minutes (Atelier 10, partie 8)
- `Presentation_V1_structure.pdf` : suit le plan de la fiche (besoin, mécanisme, mesures, correction et fraîcheur, décision), 5 diapos + 1 diapo de réserve (questions).
- `Presentation_V2_histoire.pdf` : même contenu raconté en 5 actes autour d'une problématique (« Pourquoi ça plafonne ? » jusqu'à « Quel est le prix ? »), avec une phrase de transition par diapo.
- Chaque diapo a un cadre « À DIRE » avec le texte à prononcer. Durée estimée à 130 mots/min : V1 5 min 12 s, V2 4 min 36 s.
- Tous les chiffres viennent des fichiers de mesures (atelier7, atelier8, atelier9/resultats). Source : `presentation/build_presentations.py`.
- Réserve à dire : les mesures utilisent 3 s d'échauffement et 10 s par essai, la fiche cite 10 s et 30 s en exemple.

## Dossier final Atelier 10 (PRINCIPAL+)
- `PRINCIPAL_PLUS_complet.pdf` (82 pages, autonome : aucun renvoi à un fichier extérieur) : couverture, page de contexte, dossier D-1 à D-9 reconstruit par `dossier/pages_dossier.py` puis annexes = `test.pdf` (PRINCIPAL p. 1-59, Jour 5 p. 60-71), avec signets. « PRINCIPAL p. N » = page N + 11 du fichier.
- `PRINCIPAL_PLUS.pdf` (8 pages) : ANCIENNE version du dossier, cite des fichiers extérieurs, à ne pas rendre. Assemblage : `dossier/assembler_principal_plus.py`.
- Contrôles : `dossier/verifier_conformite.py` (structure vs fiche) et `dossier/audit_chiffres.py` (104 nombres non triviaux retrouvés dans les sources ; tableau D-4 recalculé depuis p2_charge.json), sortie dans `dossier/audit_chiffres.txt`.
- À savoir dire : protocole 3 s + 10 s (la fiche cite 10 s + 30 s en exemple) ; en groupé la file du pool atteint encore 14 à 20 clients (20 clients pour 5 connexions), c'est la durée d'occupation qui baisse ; index composé et migration testés, non appliqués au laboratoire.
