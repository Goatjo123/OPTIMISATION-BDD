# Cours Jour 2 expliqué simplement (jusqu'à l'Atelier 3)

Sujet du jour : **indexer et faire évoluer le schéma**. Ce fichier couvre les slides 1 à 12 (jusqu'à l'Atelier 3 inclus). Les exemples viennent de ShopFlow et de nos propres mesures.

---

## 1. L'objectif de la journée (slides 2 à 3)

Le jour 1 était un **diagnostic** : trouver ce qui est lent. Le jour 2 est une **intervention** : on corrige, puis on **prouve** que ça marche.

Le dossier doit contenir :
1. une **migration** (le SQL qui crée l'index) ;
2. un **plan avant/après** ;
3. une comparaison des **lectures ET des écritures**.

> **Règle importante** : un index qui n'est pas utilisé, ou un gain qu'on ne peut pas reproduire, **n'est pas présenté comme une réussite**.

Priorité du jour : l'**historique d'un client** et les **filtres du catalogue**.

---

## 2. Le rôle d'un index (slide 4)

Un **index** est une structure supplémentaire qui range des valeurs dans l'ordre et pointe vers les lignes de la table.

> Image : l'index à la fin d'un livre. Au lieu de lire tout le livre (Seq Scan), tu regardes l'index, qui te donne la page.

```
Filtre client = 42  →  Index (valeurs ordonnées)  →  Références aux lignes  →  Table commandes
```

Ce qu'il faut retenir :
- Il **évite de parcourir toute la table**.
- Il **prend de la place** et doit être **mis à jour à chaque modification**.
- Créer un index, c'est **faire un pari** sur la façon dont l'application utilise la table.
- Une table lue par plusieurs endpoints peut avoir besoin de **plusieurs index**.

> **La liste des requêtes utiles vient avant la liste des index.** On ne crée pas d'index « au cas où ».

---

## 3. Le B-tree (slide 5)

C'est le type d'index **par défaut** de PostgreSQL. Ses clés sont rangées dans une structure **équilibrée et ordonnée** : PostgreSQL descend rapidement jusqu'à la bonne zone, puis lit les entrées utiles à la suite.

Il convient à :
- une **égalité** (`client_id = 42`) ;
- un **intervalle** (`created_at >= ... AND created_at < ...`) ;
- certains **tris** (`ORDER BY created_at DESC`).

Chez nous : l'index sur `client_id` **regroupe les commandes par client**. Si on y ajoute `created_at`, les commandes d'un même client sont **rangées par date**.

Attention : l'index range des **valeurs**, il ne **mémorise pas la réponse** d'une requête.

> **Un index aide quand le travail qu'il évite dépasse son propre coût.**

---

## 4. Sélectivité et distribution (slide 6)

- **Sélectivité** = la part des lignes que garde une condition. Peu de lignes gardées = très sélectif = l'index est utile.
- **Cardinalité** = le nombre de valeurs **différentes** dans une colonne.

Une colonne très variée n'a pas forcément des valeurs rares : un client très actif peut avoir beaucoup plus de commandes que les autres.

| Condition (sur nos 100 000 commandes) | Lignes gardées | Sélectif ? |
|---|---|---|
| `id = 1` | 1 | Très |
| `client_id = 42` | 100 (0,1 %) | Oui |
| `statut = 'payee'` | 80 000 (80 %) | **Non** : un index n'aide presque pas |
| `statut = 'en_attente'` | ≈ 10 000 (10 %) | Moyen |

> Le tableau de la slide est une **simulation fictive** ; les chiffres de notre tableau, eux, ont été comptés sur la base.

On teste donc des paramètres **courants** et des cas **défavorables**, pas un seul client.

---

## 5. Index composé : l'ordre des colonnes (slide 7)

Un index composé porte sur **plusieurs colonnes**. Leur **ordre compte**.

Pour l'historique d'un client :

```sql
CREATE INDEX idx_hist_client
ON commandes (client_id, created_at DESC, id DESC);
```

Pourquoi cet ordre ?
1. `client_id` d'abord : l'**égalité** isole les commandes du client (le « groupe »).
2. `created_at DESC` ensuite : à l'intérieur du groupe, elles sont **déjà de la plus récente à la plus ancienne**.
3. `id DESC` en dernier : rend l'ordre **toujours le même** quand deux commandes ont la même date.

Règles à retenir :
- L'ordre se choisit **d'après les usages**, pas seulement d'après « la colonne la plus variée d'abord ».
- Une requête qui filtre **sans** la première colonne n'est pas forcément servie par l'index : **on vérifie dans le plan**. PostgreSQL peut parfois faire un *skip scan*.

---

## 6. Index et `ORDER BY` + `LIMIT` (slide 8)

Si l'index donne les lignes **déjà dans l'ordre demandé**, PostgreSQL n'a plus à **trier** : il lit les premières lignes et **s'arrête**. Avec `LIMIT 20`, il lit donc 20 entrées au lieu de tout lire puis trier.

```sql
SELECT id, created_at, total
FROM commandes
WHERE client_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Mais attention :
- Le **sens** (`ASC` / `DESC`), les `NULL` et la **première colonne** comptent. Un tri global par `total` ne profite pas d'un index qui commence par `client_id`.
- Un index compatible **n'oblige pas** le planificateur à l'utiliser. **Le plan doit montrer ce qui est vraiment évité.**

**Ce qu'on a mesuré** (Atelier 3, vraie table, requête exacte de l'API, client 42, 51 tours en alternance) :

| | Sans l'index composé | Avec |
|---|---|---|
| Plan | Bitmap Heap Scan puis **Sort** | **Index Scan seul**, plus de Sort |
| Buffers lus | 96 | **27** |
| Durée (médiane) | 0,690 ms | **0,274 ms** (×2,5) |

Et pour un client très actif (20 100 commandes) : **23,3 ms → 0,26 ms** (×91). Sans index, le coût **grandit avec le nombre de commandes du client** ; avec l'index il reste constant.

> **Piège vu pendant l'atelier :** l'API écrit `ORDER BY commandes.created_at`. Sans le préfixe `commandes.`, SQL trie sur les colonnes de **sortie** (des textes formatés) et l'index composé n'est plus utilisé (93 buffers, comme sans index).

---

## 7. Index couvrant et `INCLUDE` (slide 9)

`INCLUDE` ajoute des colonnes **dans** l'index sans qu'elles servent à l'ordre. Si l'index contient **toutes les colonnes demandées**, PostgreSQL n'a plus besoin d'aller lire la table : c'est un **Index Only Scan**.

```sql
CREATE INDEX idx_hist_couvrant
ON commandes (client_id, created_at DESC, id DESC) INCLUDE (statut, total);
```

Les pièges :
- Ça ne marche que **si ces colonnes sont toute la projection** : notre requête lit `id, created_at, total`, donc `statut` n'est pas utile pour elle.
- Même avec `INCLUDE`, PostgreSQL peut devoir **visiter la table** pour vérifier qu'une ligne est visible (la « visibilité »). On le voit dans le plan : **`Heap Fetches`**. Une table très modifiée en a davantage.
- L'index est **plus gros** et coûte plus à maintenir.

> **Avoir `INCLUDE` ne prouve pas qu'on évite la table.** Seul le plan le prouve.

---

## 8. Le coût d'écriture des index (slide 10)

Chaque index doit être **mis à jour** quand on écrit :
- un **INSERT** crée la ligne **et** une entrée dans chaque index ;
- un **UPDATE** d'une colonne indexée crée de nouvelles entrées ;
- tout cela produit du **WAL** (le journal d'écriture), de la mémoire et du stockage.

Donc : **plus d'index = lectures plus rapides, écritures plus lentes.** Dix index pour dix requêtes rares peuvent ralentir fortement un gros import.

> Le graphique de la slide (110, 145, 250 ms) est **fictif**. Le nôtre est mesuré.

**Ce qu'on a mesuré** (Atelier 3) : insérer 20 000 commandes écrit **+35 % de WAL** avec l'index composé (+42 % avec le couvrant). Chaque index ajoute environ 20 000 enregistrements de journal, un par ligne insérée. Les **durées** sont trop bruitées pour être chiffrées précisément (de +23 % à +62 % selon l'exécution) : on s'appuie sur le WAL. L'index pèse 3 984 kB, soit **≈ 30 %** de la table (13 392 kB).

Pour décider, on compare le **gain de lecture** à la **fréquence des écritures** : il faut regarder la charge complète.

---

## 9. Index redondants et index inutilisés (slide 11)

- Deux index qui commencent par les **mêmes colonnes** peuvent se recouvrir **sans être équivalents** : leur taille, leur unicité, leur condition ou leurs colonnes incluses peuvent justifier de garder les deux.
- Un **compteur d'utilisation à zéro** sur une courte période **ne prouve pas** qu'un index est inutile : il peut protéger une contrainte ou servir à une opération rare (mensuelle).
- Avant de supprimer : on observe une **période représentative** et on **vérifie les usages**.
- Une migration garde toujours un **retour arrière** et documente les requêtes concernées.

**Chez nous** : l'index composé `(client_id, created_at, id)` et l'index unique `(client_id, cle_idempotence)` commencent tous les deux par `client_id`, mais le second **garantit l'unicité** et ne doit **jamais** être supprimé pour « faire du ménage ».

---

## 10. Atelier 3 : l'historique client (slide 12)

**Durée prévue : 1 h 30. Livrable : un tableau de décision.**

### Ce qu'on te demande
1. **Comparer quatre états** :
   - la base **initiale** ;
   - un **index simple** sur `client_id` ;
   - l'**index composé** `(client_id, created_at DESC, id DESC)` ;
   - sa **variante couvrante** (`INCLUDE`).
2. **Tester plusieurs clients**, dont le client 42 (pas un seul : un client très actif est un cas défavorable).
3. **Réinitialiser** chaque variante avant de passer à la suivante (supprimer l'index), pour que **deux index ne se fassent pas concurrence** dans le plan.

### Ce qu'on te demande de conserver
- la **requête**, le **plan**, les **buffers** ;
- la **taille des index** ;
- les **répétitions** (même protocole qu'au jour 1 : échauffement puis 5 mesures) ;
- un **lot d'insertion dans une transaction de laboratoire** (avec `ROLLBACK`, pour ne rien garder) ;
- l'**explication du gain, ou de l'absence de gain**.

### Pourquoi « un tableau de décision »
Pour chaque variante, tu dois **trancher** avec des chiffres (rempli dans `atelier3/README.md`, section 7) :

| Variante | Plan | Buffers | Durée lecture | Taille index | Coût insertion | Décision |
|---|---|---|---|---|---|---|
| Initiale | | | | | | |
| Index simple `client_id` | | | | | | |
| Composé | | | | | | |
| Couvrant | | | | | | |

### Points d'attention propres à notre base
- La base **initiale** a déjà un index qui commence par `client_id` (l'index unique de la contrainte). Un « index simple sur `client_id` » apporterait donc probablement **peu ou pas de gain** : c'est un résultat à **mesurer et à expliquer**, pas une erreur. La slide dit explicitement : expliquer *l'absence de gain*.
- Le gain principal attendu vient de la **suppression du tri** (composé), et peut-être de la **suppression des lectures de table** (couvrant, si les `Heap Fetches` sont faibles).
- Il faut **comparer les écritures** dans chaque cas : le couvrant est plus gros, donc probablement plus coûteux à maintenir.
- Rappel : **mêmes résultats fonctionnels** avant et après (mêmes lignes, mêmes totaux).

### État de notre travail : Atelier 3 fait
Résultats complets dans [`atelier3/README.md`](atelier3/README.md) :
- **Index simple** : aucun gain (même plan, 96 buffers), car l'index unique existant commence déjà par `client_id`. **Rejeté.**
- **Composé** : ×2,5 sur l'API, ×91 pour un client très actif, WAL +35 %. **Retenu.**
- **Couvrant `(statut, total)`** : ×3,5, mais 45 % plus gros et sensible à `VACUUM`. **Option.**
- **Couvrant `(total)`** : inutile pour l'API (elle lit aussi `statut`). **Rejeté.**
- Migration prête dans `atelier3/migration/`, **non appliquée** au labo.

---

## 11. Glossaire express
| Mot | En une phrase |
|---|---|
| Index | Structure triée qui indique où sont les lignes |
| B-tree | Type d'index par défaut, bon pour égalité, intervalle et tri |
| Sélectivité | Part des lignes gardées par une condition (petite = très sélectif) |
| Cardinalité | Nombre de valeurs distinctes d'une colonne |
| Index composé | Index sur plusieurs colonnes, l'ordre compte |
| `INCLUDE` | Colonnes ajoutées à l'index pour éviter de lire la table |
| Index Only Scan | Réponse lue uniquement dans l'index |
| Heap Fetches | Visites à la table malgré un Index Only Scan (vérification de visibilité) |
| WAL | Journal d'écriture : chaque modification en produit |
| Index redondant | Index qui en recouvre un autre (mais il peut avoir une raison d'exister) |
