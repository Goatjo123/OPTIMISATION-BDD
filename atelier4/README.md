# Atelier 4 : index spécialisés

Jour 2, slide 26 : créer les variantes **partielle** et **GIN** dans le laboratoire, les comparer avec un filtre qui correspond au prédicat et un filtre qui n'y correspond pas, observer la taille et l'usage des index ; sur la petite table `produits` un Seq Scan peut rester rationnel (l'expliquer et proposer un test à plus grand volume) ; pour **GiST**, deux périodes qui se chevauchent et une période disjointe. Livrable : **choix d'index, opérateurs, résultats et conditions**.

L'atelier 4 bis (migration de schéma) est un travail distinct, non traité ici.

---

## 1. Résumé et décisions

| Besoin (slide 44) | Index | Résultat mesuré | Coût d'écriture | Décision |
|---|---|---|---|---|
| **File à traiter** : commandes `en_attente` (10 % de la table) | **Partiel** `(created_at, id) WHERE statut = 'en_attente'` | **×145** (10,1 → 0,07 ms), 1 680 → 3 buffers ; index de **328 kB** (2,4 % de la table) | insertions : WAL **+3,2 %** | **Retenu** (migration 002) |
| Idem, tous statuts | Complet `(statut, created_at, id)` | ×130 (en_attente) et ×184 (payee) ; index de 4 072 kB (**12,4 fois** le partiel) | insertions : WAL **+36,5 %** | Rejeté : 12 fois plus gros et 11 fois plus cher en écriture pour un besoin qui ne concerne que `en_attente` |
| **Attributs flexibles** sur `produits` (200 lignes) | **GIN** `(attributs)` | **jamais utilisé** : Seq Scan sur 3 pages (6 buffers), `idx_scan = 0` | n/a sur 200 lignes | **Rejeté pour le catalogue actuel** |
| Attributs flexibles à **200 000 lignes** | GIN | valeur rare (0,1 %) : **×17** ; valeur à 25 % : ×2,0 ; **inutile** pour `->>` | insertions : WAL **+120,7 %** | Réservé aux filtres sur clés variables ; voir 5 |
| Idem, une propriété connue | **Index d'expression** `((attributs->>'categorie'))` ou **colonne typée** | **×28** et **×30** sur la valeur rare | WAL **+34,6 %** et **+38,9 %** | **Préférable** si le filtre porte toujours sur `categorie` |
| **Réservations** (intervalles, `&&`) | **GiST** `(periode)` | **×164** à 200 000 périodes (27,5 → 0,168 ms), 1 474 → 8 buffers | WAL **+54,1 %**, durée d'insertion **×7,8** | Retenu **si** le besoin de chevauchement existe |

Tous les résultats fonctionnels sont **identiques** entre variantes (empreinte md5). Le laboratoire a retrouvé **exactement** son état initial (6 index, aucune statistique étendue, mêmes nombres de lignes).

---

## 2. Contexte et environnement

| Élément | Valeur |
|---|---|
| Version | PostgreSQL 18.6, conteneur Docker `api-postgres-1`, WSL2 |
| Paramètres | `work_mem` = 4 MB, `shared_buffers` = 128 MB |
| `commandes` | 100 000 lignes, 13 392 kB. Statuts : `payee` 80 000, `en_attente` 10 000, `annulee` 10 000 |
| `produits` | 200 lignes, 3 pages (24 kB). `categorie` : `materiel` 100, `accessoire` 50, `livre` 50 |
| Dates | mesures du 06/10/2026 |

L'API (`01_server/api`) n'émet **aucune** requête de filtre sur le catalogue ni sur la file `en_attente` (seulement la lecture d'un produit par `id` et la mise à jour d'un prix). Les requêtes testées sont donc celles du cours (slides 13 et 16) ; ce n'est pas du SQL réellement émis par l'application, et on le dit.

---

## Situation

ShopFlow grossit. L'équipe veut accélérer trois traitements **sans ralentir les créations de commandes** : la file des commandes à traiter, le filtre du catalogue sur les attributs JSONB et, plus tard, une fonction de réservation. On teste **un index par besoin**, on mesure le gain **et** son coût, et on garde le moins d'index possible (slide 44 : « on peut garder moins d'index que dans le laboratoire »).

---

## 3. Protocole et deux corrections de méthode

Identique à l'Atelier 3, avec **toutes les valeurs brutes conservées** dans `resultats/resultats.json` :

1. **Vraie table du laboratoire** : variantes créées puis **supprimées** une à une (jamais deux ensemble), 3 échauffements puis 5 mesures `EXPLAIN (ANALYZE, BUFFERS)`, médiane, empreinte md5, usage de l'index (`pg_stat_user_indexes.idx_scan`).
2. **Mesure renforcée** : une table de travail par variante (mêmes lignes), **51 tours en alternance**.
3. **Écriture** : lots dans une transaction annulée (`ROLLBACK`), **15 tours en alternance**, avec le volume de WAL (déterministe).
4. Tables de travail dans le schéma `a4_tmp`, supprimé à la fin ; laboratoire comparé avant/après.

**Deux défauts de mesure détectés et corrigés pendant l'atelier** (les chiffres de ce document viennent de l'exécution corrigée) :

- **Buffers incomplets.** Mon premier script ne lisait que `shared hit` : un plan affichait `hit=841 read=1554`, soit 2 395 pages touchées et non 841. Les buffers sont maintenant **hit + read** (tous les `read` valent 0 dans l'exécution finale : les tables tiennent en mémoire).
- **Parallélisme.** Sur une table, PostgreSQL a choisi un **Parallel Seq Scan** (2 processus : 22,274 ms, voir `plans/observation_seqscan_parallele_colonne_typee_contient_rare.txt`) alors que sur une autre table de taille voisine il faisait un Seq Scan simple (≈ 42 ms). Deux « Seq Scan » de formes différentes ne sont pas comparables : les mesures alternées sont donc faites avec `max_parallel_workers_per_gather = 0`. Conséquence : les gains mesurés contre un Seq Scan **simple** seraient environ deux fois moindres contre un Seq Scan parallèle.

**Ce qui est fiable :** plans, buffers, volume de WAL, tailles, résultats. **Ce qui est bruité :** les durées absolues ; on ne compare que des durées prises dans la même mesure alternée.

---

## 4. A. Index partiel : la file des commandes en attente

**Situation.** Un opérateur traite chaque jour les 100 plus anciennes commandes `en_attente`. Elles sont 10 000 sur 100 000 (10 %). Sans index, PostgreSQL lit toute la table (1 680 buffers, 10,1 ms) puis trie.

**Solution choisie et pourquoi.** Un **index partiel** `(created_at, id) WHERE statut = 'en_attente'`.
1. Le besoin ne concerne qu'un statut : il est inutile d'indexer les 90 % de lignes restantes.
2. L'index donne déjà l'ordre demandé : PostgreSQL lit les 100 premières entrées sans trier.
3. Il est **12,4 fois plus petit** que l'index complet (328 kB contre 4 072 kB) et ajoute beaucoup moins de WAL à l'insertion (**+3,2 %** contre **+36,5 %**).

**Écartée :** l'index complet `(statut, created_at, id)`, qui fonctionne aussi mais pour un besoin limité à un statut.

### Requêtes (slide 13)
```sql
SELECT id FROM shopflow.commandes
WHERE statut = '<statut>'          -- en_attente (correspond au prédicat), payee, annulee (ne correspondent pas)
ORDER BY created_at, id
LIMIT 100;
```

### Variantes
```sql
CREATE INDEX a4_idx_partiel ON shopflow.commandes (created_at, id) WHERE statut = 'en_attente';
CREATE INDEX a4_idx_complet ON shopflow.commandes (statut, created_at, id);
```
Le complet sert de comparaison : il fait voir ce que le partiel apporte (taille, coût d'écriture) et ce qu'il ne sert pas.

### Résultats sur la vraie table (5 mesures, médiane en ms / buffers)

| Variante | `en_attente` | `payee` | `annulee` |
|---|---|---|---|
| Initiale | 10,123 / 1 680, Seq Scan + tri | 17,448 / 1 720, Seq Scan + tri | 10,946 / 1 680, Seq Scan + tri |
| **Partiel** | **0,070 / 3**, Index Only Scan | 14,705 / 1 720, **Seq Scan** | 10,002 / 1 680, **Seq Scan** |
| Complet | 0,078 / 4, Index Only Scan | 0,095 / 4, Index Only Scan | 0,106 / 4, Index Only Scan |

- Le partiel n'améliore **que** le filtre qui correspond à son prédicat (×145). Pour `payee` et `annulee` le plan est **identique** à la base initiale ; l'écart de durée (14,7 contre 17,4 ms) est du bruit, la mesure renforcée donne 21,862 contre 22,219 ms.
- Le complet sert **tous** les statuts.
- Les 9 combinaisons donnent le même résultat que la base initiale (100 lignes) et le même plan sur les 5 mesures.

### Mesure renforcée (tables de travail, 51 tours, médiane / p95 en ms)

| Variante | `en_attente` | `payee` | Buffers |
|---|---|---|---|
| Initiale | 9,899 / 11,898 | 22,219 / 26,176 | 846 |
| Partiel | **0,071 / 0,141** (×139) | 21,862 / 25,128 (×1,02) | 3 ; 846 |
| Complet | 0,084 / 0,201 (×118) | 0,082 / 0,140 (×271) | 4 ; 4 |

Les tables de travail sont physiquement plus compactes que la vraie table (846 buffers contre 1 680 pour un Seq Scan), d'où les valeurs différentes de la section précédente.

### Taille et usage
| | Partiel | Complet |
|---|---|---|
| Taille | **328 kB** (2,4 % de la table) | 4 072 kB (30,4 %), soit **12,4 fois** le partiel |
| `idx_scan` après les mesures | **9** | **27** |

Le partiel n'a servi que pour `en_attente` (3 échauffements + 1 vérification + 5 mesures = 9 exécutions) ; le complet a servi pour les trois statuts (3 × 9 = 27). C'est la preuve de l'**usage** demandée par la slide.

### Le piège des requêtes paramétrées (slide 13)
Requête préparée `WHERE statut = $1`, avec la valeur `'en_attente'` :

| Plan | Index partiel | Index complet |
|---|---|---|
| Générique forcé (`plan_cache_mode = force_generic_plan`) | **Seq Scan + tri, 1 680 buffers : l'index n'est pas utilisé** | Index Only Scan, 4 buffers |
| Spécifique forcé (`force_custom_plan`) | Index Only Scan, 3 buffers | Index Only Scan, 4 buffers |

Dans un plan générique, PostgreSQL ne connaît pas la valeur : il ne peut pas **prouver** que `statut = $1` implique le prédicat `statut = 'en_attente'`. L'application doit donc envoyer le littéral, ou s'assurer d'un plan spécifique.

### Le prédicat avec `now()` (slide 14)
```sql
CREATE INDEX ... WHERE created_at >= now() - interval '7 days';
-- ERROR: functions in index predicate must be marked IMMUTABLE
```
Refusé : la date relative change sans que les lignes changent.

### Coût d'écriture (15 tours en alternance, WAL par lot)

| Lot | Initiale | Partiel | Complet |
|---|---|---|---|
| **Insertion** de 20 000 lignes (dont 2 000 `en_attente`) | 4 621 038 o, 60 275 enreg. | 4 768 498 (**+3,2 %**), 62 291 (+2 016) | 6 305 626 (**+36,5 %**), 80 607 (+20 332) |
| 2 000 lignes **quittent** la file (`en_attente` → `payee`) | 605 083 o, 8 037 enreg. | 605 083 (**+0,0 %**), 8 037 (+0) | 771 943 (+27,6 %), 10 066 (+2 029) |
| 2 000 lignes **entrent** dans la file (`payee` → `en_attente`) | 615 355 o, 8 015 enreg. | 769 824 (**+25,1 %**), 10 102 (+2 087) | 797 436 (+29,6 %), 10 042 (+2 027) |

- À l'insertion, le partiel n'écrit que pour les lignes `en_attente` (≈ 2 000 enregistrements de plus, un par ligne concernée), le complet écrit pour **toutes** (≈ 20 000).
- Une ligne qui **quitte** la file ne crée aucune entrée dans le partiel (WAL identique à la base initiale). L'ancienne entrée n'est probablement retirée que par un `VACUUM` (**hypothèse**, non vérifiée ici).
- Une ligne qui **entre** dans la file crée une entrée (≈ 1 enregistrement par ligne), comme pour le complet.
- Les durées de ces lots (par exemple insertion : 103,6 / 112,0 / 183,2 ms) sont bruitées ; on retient le WAL.

### Explication du gain et de l'absence de gain
- **Gain pour `en_attente`** : l'index ne contient que les 10 000 commandes en attente, rangées par `(created_at, id)` : PostgreSQL lit les 100 premières entrées dans l'ordre demandé et s'arrête (3 buffers), sans lire la table (`Heap Fetches: 0`, les deux colonnes demandées sont dans l'index) ni trier.
- **Absence de gain pour `payee` et `annulee`** : leurs lignes ne sont pas dans l'index. PostgreSQL le sait (le prédicat ne les contient pas) et retombe sur un Seq Scan + tri.

### Est-ce que ça fonctionne ?
**Oui, pour son périmètre.** Gain **×145** (10,123 → 0,070 ms), 1 680 → 3 buffers, résultat identique à la base initiale (empreinte md5), usage prouvé (`idx_scan` = 9).

**Limites vérifiées :** il ne sert ni `payee` ni `annulee` (Seq Scan, même plan qu'à l'origine) ; il n'est **pas** utilisé avec un plan générique (1 680 buffers) : l'application doit envoyer le littéral `'en_attente'`.

**Verdict : retenu**, à condition que la requête contienne le littéral et que la file reste une petite part de la table.

---

## 5. B. GIN : le filtre JSONB sur `produits.attributs`

**Situation.** Le catalogue stocke des attributs variables en JSONB (`categorie`, `couleur`). Un filtre par catégorie est envisagé (slide 16). Aujourd'hui : 200 produits sur 3 pages ; à terme le catalogue peut grossir.

**Solution choisie et pourquoi.** Une décision **en deux temps**.
- *Aujourd'hui : aucun index.* Lire 3 pages (6 buffers, ≈ 0,1 ms) coûte moins que passer par un index, qui ne serait jamais utilisé.
- *À volume, si le filtre porte toujours sur `categorie` :* **index d'expression ou colonne typée**, plus rapides (×28 et ×30) et moins coûteux en écriture (WAL +34,6 % et +38,9 % à l'insertion, contre +120,7 % pour le GIN).

**Écartée :** le GIN, réservé aux filtres sur des clés variables que l'on ne peut pas prévoir (slide 17).

### Requêtes (slide 16)
```sql
SELECT id, nom FROM shopflow.produits WHERE attributs @> '{"categorie":"livre"}'::jsonb ORDER BY id;
-- variantes : "materiel" (50 %), "inexistant" (0 ligne), et le filtre  attributs->>'categorie' = 'livre'
```
Variantes : `CREATE INDEX ... USING gin (attributs)` (classe `jsonb_ops` par défaut) et un index d'expression `((attributs->>'categorie'))`.

### Sur la vraie table (200 lignes) : le Seq Scan reste rationnel
| | Initiale | GIN | Expression |
|---|---|---|---|
| 4 requêtes | Seq Scan, 6 buffers, ≈ 0,1 ms | **identique** | **identique** |
| Taille de l'index | n/a | 16 kB (table : 24 kB) | 16 kB |
| `idx_scan` | n/a | **0** | **0** |

**Explication.** La table tient sur **3 pages** : la lire en entier coûte 6 buffers et environ 0,1 ms, moins qu'un passage par l'index. Le coût estimé le confirme. Pour la valeur absente, le Seq Scan est estimé à 5,51 et le GIN à 12,81 quand on interdit le Seq Scan (`SET enable_seqscan = off`, diagnostic de session, jamais laissé) ; pour `livre`, le Seq Scan est estimé à 7,04 et la meilleure autre voie à 17,64.

Ce diagnostic montre aussi ce que chaque index **sait** faire :
- le GIN **peut** servir `@>` (utilisé pour la valeur absente) mais **pas** `->>` (PostgreSQL retombe alors sur l'index de la clé primaire) ;
- l'index d'expression **peut** servir `->> 'categorie' = …` et **pas** `@>` ;
- pour `livre` et `materiel`, PostgreSQL préfère parcourir la clé primaire (la requête réclame `ORDER BY id`) plutôt que le GIN suivi d'un tri.

### Test à plus grand volume (proposé par la slide, réalisé)
Une table de **200 000 produits** par variante (même forme d'attributs que la vraie table) ; `categorie` : 50 % `materiel`, 25 % `accessoire`, 24,9 % `livre`, **0,1 % `rare` (200 lignes)**. 51 tours en alternance, sans parallélisme. Une quatrième variante ajoute une **colonne typée** `categorie` (colonne générée, indexée).

| Requête | Initiale (Seq Scan) | GIN | Index d'expression | Colonne typée |
|---|---|---|---|---|
| `@>` valeur à **24,9 %** | 48,7 ms, 2 855 buf. | **24,3 ms (×2,0)**, 947 buf. | Seq Scan 53,2 ms | Seq Scan 49,1 ms |
| `@>` valeur **rare (0,1 %)** | 43,9 ms, 2 855 buf. | **2,551 ms (×17,2)**, 257 buf. | Seq Scan 46,3 ms | Seq Scan 43,4 ms |
| `->> 'categorie' = 'rare'` | 30,9 ms | Seq Scan 32,8 ms (**GIN inutile**) | **1,104 ms (×28,0)**, 203 buf. | Seq Scan 31,9 ms |
| `categorie = 'rare'` (colonne typée) | n/a | n/a | n/a | **1,016 ms (×30,4)**, 203 buf. |

- Le GIN **sert** à `@>`, avec un gain qui dépend de la rareté de la valeur : ×17 pour 0,1 % des lignes, seulement ×2,0 pour 24,9 % (les buffers sont divisés par 3, 2 855 → 947).
- Pour **une propriété connue** et filtrée par égalité, l'index d'expression et la colonne typée sont **plus rapides** que le GIN (×28 et ×30) et sa requête `->>` est la seule qu'ils sachent servir.

| Taille | GIN | Expression | Colonne typée |
|---|---|---|---|
| Index | 0,93 MiB | 1,37 MiB | 1,37 MiB (+ **1,80 MiB** dans la table pour la colonne) |

### Coût d'écriture (15 tours en alternance, WAL par lot de 20 000 lignes)

| Lot | Initiale | GIN | Expression | Colonne typée |
|---|---|---|---|---|
| Insertion | 4 097 786 o | 9 044 567 (**+120,7 %**) | 5 515 841 (**+34,6 %**) | 5 690 863 (**+38,9 %**) |
| Modification de `attributs` | 5 547 001 o | 10 120 555 (**+82,5 %**) | 6 964 137 (**+25,5 %**) | 7 153 583 (**+29,0 %**) |

Le GIN est **le plus petit** des trois index mais **le plus coûteux** à maintenir : l'insertion écrit plus de deux fois le WAL de la base initiale.

### Décision
- **GIN : rejeté pour le catalogue actuel.** 200 produits : il n'est jamais utilisé (`idx_scan = 0`), et il coûterait cher en écriture.
- **Si le catalogue grandit** : si le filtre porte **toujours** sur `categorie`, préférer l'**index d'expression** ou la **colonne typée** (c'est la recommandation de la slide 17 pour une propriété structurante) ; ne garder un GIN que si les filtres portent sur des clés ou des valeurs **variables** que l'on ne peut pas prévoir.

### Est-ce que ça fonctionne ?
**Le GIN fonctionne techniquement** : il sert `@>` (×17,2 sur une valeur à 0,1 %, ×2,0 à 24,9 %), mais **pas pour ce besoin** : sur les 200 produits actuels il n'est jamais utilisé (`idx_scan` = 0), il ne sert pas `->>`, et il écrit +120,7 % de WAL à l'insertion. L'index d'expression et la colonne typée fonctionnent pour le filtre sur `categorie` (×28,0 et ×30,4). Résultats identiques dans toutes les variantes.

**Verdict : GIN rejeté pour le catalogue actuel** ; à reconsidérer si le catalogue atteint des dizaines de milliers de produits avec des filtres sur des clés variables.

---

## 6. C. GiST : les réservations et l'opérateur `&&`

**Situation.** Une fonction de réservation doit détecter si une période en chevauche une autre. **Ce besoin n'existe pas encore dans ShopFlow** : l'exemple de la slide 18 est indépendant du fil rouge.

**Solution choisie et pourquoi.** Un **GiST sur un `tstzrange`**, avec l'opérateur de chevauchement `&&`. La slide 18 prévoit GiST pour les intervalles et précise que « l'index doit prendre en charge l'opérateur employé » ; je l'ai vérifié en interdisant le Seq Scan : l'index sert bien `&&`. Je n'ai testé aucun autre type d'index pour ce besoin.

### Les cas demandés (slide 26)
Table indépendante du fil rouge (`reservations(id, periode tstzrange)`, index `gist (periode)`), intervalles semi-ouverts `[)`. Fenêtre testée : 14h00-16h00 (UTC+2).

| id | Période | Chevauche la fenêtre ? |
|---|---|---|
| 1 | 14h00-16h00 | **oui** |
| 2 | 15h00-17h00 | **oui** |
| 3 | 18h00-19h00 | non (disjointe) |
| 4 | 16h00-17h00 | non (**contiguë** : la fin est exclue) |

Résultat de `periode && fenêtre` : **ids 1 et 2** ; la période 4, qui touche la fenêtre sans la recouvrir, **n'est pas** retournée.

Sur ces 4 lignes, PostgreSQL choisit un **Seq Scan** (coût 1,08). Si on interdit le Seq Scan, l'index GiST **peut** servir la requête (coût 8,21) : l'opérateur `&&` est bien pris en charge.

### À plus grand volume
200 000 périodes d'une heure, une toutes les 10 minutes ; fenêtre de 2 heures qui en chevauche **17**. Même contenu avec et sans GiST, 51 tours en alternance, sans parallélisme :

| | Sans index | GiST |
|---|---|---|
| Lecture (médiane / p95) | 27,493 / 33,649 ms, 1 474 buffers | **0,168 / 0,294 ms (×164)**, 8 buffers |
| Taille de l'index | n/a | 6,95 MiB (**60,5 %** de la table de 11,49 MiB) |
| Insertion de 20 000 lignes : WAL | 3 029 330 o | 4 669 330 (**+54,1 %**) |
| Insertion : durée médiane (min) | 55,6 ms (32,7) | 434,9 ms (343,6) : **×7,8** (×10,5 sur le minimum) |

Le GiST rend la recherche de chevauchement quasi instantanée, mais ralentit beaucoup les insertions : c'est un choix à justifier par la fréquence des recherches face à celle des écritures.

### Décision
**Retenu si le besoin de détection de conflits existe** (réservations, planification). L'exemple est indépendant de ShopFlow : la décision dépend d'une fonctionnalité qui n'est pas dans l'application.

### Est-ce que ça fonctionne ?
**Oui.** Sur les 4 périodes de test, `&&` retourne exactement les ids 1 et 2 (la disjointe et la contiguë sont exclues). Sur 200 000 périodes : gain **×164**, 1 474 → 8 buffers, résultat identique (empreinte md5). **Coût :** WAL +54,1 %, insertions ×7,8 plus lentes.

**Verdict : retenu si le besoin de détection de conflits existe**, et si les recherches sont bien plus fréquentes que les insertions.

---

## 7. Livrable : choix d'index, opérateurs, résultats et conditions

| Besoin | Index | Opérateur / condition | Résultat | Condition de validité | Décision |
|---|---|---|---|---|---|
| File des commandes en attente | Partiel B-tree `(created_at, id) WHERE statut = 'en_attente'` | égalité littérale sur `statut`, tri sur `(created_at, id)` | ×145, 3 buffers, 328 kB, WAL +3,2 % | la requête contient le **littéral** `'en_attente'` (pas de plan générique) ; la file reste une petite part de la table | **Retenu** |
| Même file, tous statuts | Complet B-tree `(statut, created_at, id)` | égalité sur `statut` | ×130 à ×184, 4 072 kB, WAL +36,5 % | besoin réel de filtrer par plusieurs statuts | Rejeté (inutile ici) |
| Attributs flexibles (200 produits) | GIN `jsonb_ops` | `@>` | non utilisé | table de 3 pages : Seq Scan rationnel | **Rejeté** |
| Attributs flexibles (volume) | GIN `jsonb_ops` | `@>` uniquement (pas `->>`) | ×17 (rare), ×2,0 (24,9 %) ; WAL +120,7 % | filtres sur clés **variables** | Option conditionnelle |
| Propriété connue (`categorie`) | Expression `((attributs->>'categorie'))` ou colonne typée | `->> 'categorie' =` / `categorie =` | ×28 / ×30 ; WAL +34,6 % / +38,9 % | filtre **toujours** sur cette propriété | **Préférable** à volume |
| Chevauchement de périodes | GiST `(periode)` | `&&` sur `tstzrange` | ×164, 8 buffers ; WAL +54,1 % | recherches fréquentes de conflit ; écritures peu nombreuses | Retenu si le besoin existe |

**Conditions de remise en cause.**
- *Partiel* : si les filtres portent sur plusieurs statuts, ou si la part des commandes `en_attente` devient importante (l'index grossit et perd son avantage), ou si l'application passe le statut en paramètre sans plan spécifique.
- *GIN* : si le catalogue atteint des dizaines de milliers de produits avec des filtres sur des attributs variables.
- *GiST* : si les insertions de réservations deviennent le point chaud.
- *Tous* : le coût d'écriture se paie à chaque insertion (slide 44, « import fréquent : limiter les index »).

---

## 8. Limites

- **Durées bruitées** : on compare des mesures alternées ; on ne généralise pas un pourcentage (slide 45). Les ratios de durée varient d'une exécution à l'autre ; les buffers, plans, WAL, tailles et résultats sont stables.
- **Données générées** : les 200 000 produits et les 200 000 réservations sont synthétiques ; la distribution de `categorie` est choisie par le script.
- **Sans parallélisme** pour les mesures alternées (voir 3) : un Seq Scan parallèle réduirait environ de moitié les gains mesurés contre un Seq Scan simple.
- **Tables de travail compactes** : leurs buffers diffèrent de ceux de la vraie table (846 contre 1 680).
- **Mises à jour** : on a mesuré les changements de statut et les modifications d'`attributs`, pas les suppressions. La disparition des anciennes entrées du partiel après un changement de statut (VACUUM) est une hypothèse.
- **L'API n'émet pas ces requêtes** : on a utilisé celles du cours.

---

## 9. Migration

Dossier `atelier4/migration/` :

| Fichier | Rôle |
|---|---|
| `002_idx_file_attente_up.sql` | Crée `idx_attente` (laboratoire, `CREATE INDEX` ordinaire, `lock_timeout` de 5 s) |
| `002_idx_file_attente_prod_up.sql` | Même index avec `CREATE INDEX CONCURRENTLY` (déploiement, hors transaction) |
| `002_idx_file_attente_verifier.sql` | Contrôles : index valide, prédicat, aucun index invalide, plan avec littéral, **plan générique qui n'utilise pas l'index** |
| `002_idx_file_attente_down.sql` | Retour arrière : supprime uniquement `idx_attente` |

**Testé sur une base jetable** (copie de `shopflow`, supprimée ensuite) : montée (index valide, 328 kB, prédicat `statut = 'en_attente'`), rejeu sans erreur (`IF NOT EXISTS`), plan avec littéral en `Index Only Scan using idx_attente` sans tri, plan générique en Seq Scan (le piège est visible), retour arrière qui laisse la clé primaire et l'index unique, variante `CONCURRENTLY` qui fonctionne hors transaction et **échoue dans un `BEGIN`**.

**Non appliquée au laboratoire** (l'atelier demande une décision). Pour l'appliquer :
```bash
docker exec -i api-postgres-1 psql -U cours -d shopflow -v ON_ERROR_STOP=1 < atelier4/migration/002_idx_file_attente_up.sql
```
Les index GIN et GiST ne sont pas migrés : GIN est rejeté pour le catalogue actuel, et GiST concerne une table qui n'existe pas dans ShopFlow.

---

## 10. Reproduire et fichiers

```bash
docker compose up -d --wait          # dans 01_server/api
python3 atelier4/benchmark.py        # environ 5 minutes
```
Le script crée et supprime ses propres index et tables de travail, vérifie que le laboratoire retrouve son état initial (et nettoie en cas d'erreur), et écrit `resultats/resultats.json` et les plans dans `resultats/plans/`.

| Chemin | Contenu |
|---|---|
| `atelier4/benchmark.py` | Le protocole complet, reproductible |
| `atelier4/resultats/resultats.json` | Toutes les mesures brutes (chaque durée de chaque série, WAL, buffers, empreintes, usage) |
| `atelier4/resultats/plans/` | 56 plans `EXPLAIN (ANALYZE, BUFFERS)` + 1 observation (Parallel Seq Scan) |
| `atelier4/migration/` | Migration 002 : laboratoire, déploiement, vérification, retour arrière |
