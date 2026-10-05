# Atelier 3 : l'historique client

Jour 2, slide 12 : comparer la base initiale, un index simple sur `client_id`, l'index composé et sa variante couvrante, sur plusieurs clients dont le 42, puis comparer les écritures et produire **un tableau de décision**.

---

## 1. Résumé et décision

| Variante | Lecture (requête de l'API, client 42) | Écriture (20 000 insertions) | Taille de l'index | Décision |
|---|---|---|---|---|
| Initiale | 0,690 ms, 96 buffers, avec `Sort` | référence | index unique existant : 1 864 kB | point de départ |
| Index simple `(client_id)` | 0,729 ms, 96 buffers, avec `Sort` | WAL +28,2 % | 688 kB | **Rejeté : aucun gain** |
| **Composé** `(client_id, created_at DESC, id DESC)` | **0,274 ms (×2,5)**, 27 buffers, sans `Sort` | WAL +35,0 % | 3 984 kB | **Retenu** |
| Couvrant `INCLUDE (statut, total)` | 0,199 ms (×3,5), 7 buffers | WAL +42,1 % | 5 792 kB | Option si l'endpoint est critique et rarement modifié |
| Couvrant `INCLUDE (total)` | 0,267 ms (×2,6), 27 buffers | WAL +38,4 % | 4 864 kB | **Rejeté : ne couvre pas la requête de l'API** |

**Décision : migration 001 = l'index composé** (`atelier3/migration/`). C'est lui qui supprime le tri et rend le coût de l'historique **indépendant du nombre de commandes du client** : un client très actif (20 100 commandes) passe de **23,3 ms à 0,26 ms** (×91).

Le résultat fonctionnel est **identique** dans toutes les variantes, pour tous les clients testés (empreinte md5 du résultat complet).

Cette décision dépend de la charge réelle (fréquence de lecture de l'historique par rapport aux créations de commandes), que nous ne connaissons pas ; les conditions de remise en cause sont en section 9.

---

## 2. Contexte et environnement

| Élément | Valeur |
|---|---|
| Version | PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2), conteneur Docker `api-postgres-1`, WSL2 |
| Base | `shopflow`, schéma `shopflow` |
| Table | `commandes` : 100 000 lignes, 1 674 pages, 13 392 kB |
| Répartition | 1 000 clients, **exactement 100 commandes chacun** |
| Paramètres | `work_mem` = 4 MB, `shared_buffers` = 128 MB |
| Visibilité | 1 674 pages sur 1 674 « toutes visibles » (autovacuum passé avant l'atelier) |
| Date des mesures | 05/10/2026 |

**État de départ et d'arrivée du laboratoire :** 6 index (clés primaires, `UNIQUE(email)`, `UNIQUE(client_id, cle_idempotence)`), aucune statistique étendue. Le script le vérifie avant et après ; il a retrouvé **exactement cet état** (`labo_restaure: true`). Les variantes ont été créées puis supprimées une par une.

---

## 3. Protocole

1. **Mesures du cours (vraie table)** : pour chaque variante, chaque requête et chaque client (1, 42, 250, 500, 1000) : 3 exécutions d'échauffement, puis 5 mesures `EXPLAIN (ANALYZE, BUFFERS)`, médiane. **75 combinaisons**, toutes avec résultat identique et plan identique sur les 5 mesures.
2. **Mesure renforcée** : les durées sont inférieures à la milliseconde et **bruitées** (la même requête sur le même plan a donné 0,23 ms à l'Atelier 1 et environ 0,55 ms aujourd'hui). Les variantes sont donc aussi mesurées **en alternance** (un tour de chaque variante, ordre tournant, **51 tours**), sur des tables de travail identiques, une par variante, pour que la dérive de la machine touche toutes les variantes de la même façon. On donne la médiane et le p95 (rang le plus proche, 49e valeur sur 51).
3. **Écriture** : lot de 20 000 insertions dans une transaction annulée (`ROLLBACK`), 15 tours en alternance, avec le volume de **WAL** (déterministe, contrairement au temps).
4. **Visibilité** (`Heap Fetches`) : table jetable séparée.
5. **Client très actif** : un client porté à 20 100 commandes sur des tables de travail neuves.

Les tables de travail (schéma `a3_tmp`, supprimé à la fin) contiennent les mêmes lignes que la vraie table. Contrôle : la requête initiale lit 96 buffers sur la table de travail et 99 sur la vraie, donc elles se comportent de la même façon.

**Ce qui est fiable :** les buffers, les plans, le volume de WAL, les tailles, les résultats. **Ce qui est bruité :** les durées absolues ; on ne compare que des durées prises dans la même mesure alternée.

---

## 4. Les requêtes testées

Slide 13 : « la compatibilité se teste avec le SQL réellement émis par l'application ». On teste donc trois requêtes.

**`slide`** (le cours) :
```sql
SELECT id, created_at, total FROM shopflow.commandes
WHERE client_id = 42 ORDER BY created_at DESC, id DESC LIMIT 20;
```

**`api`** (exactement `01_server/api/commandes.mjs`, première page, `limit + 1 = 21` lignes) :
```sql
SELECT id::text AS id,
       to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS created_at,
       statut, total::text AS total
FROM shopflow.commandes AS commandes
WHERE client_id = 42
ORDER BY commandes.created_at DESC, commandes.id DESC
LIMIT 21;
```

**`curseur`** : la même, page suivante, avec `AND (created_at, id) < ('<date de la 20e ligne>'::timestamptz, <id>::bigint)`.

> **Piège découvert pendant l'atelier.** Les colonnes de sortie de l'API s'appellent aussi `id` et `created_at` (des textes formatés). Dans `ORDER BY`, un nom sans qualificatif désigne d'abord la colonne de **sortie** : `ORDER BY created_at DESC, id DESC` trierait donc sur les **textes**, et aucun index ne peut fournir cet ordre. C'est pour cela que l'API écrit `commandes.created_at` et `commandes.id`. Cette variante fautive (`api_alias`) est mesurée en 6.4.

---

## 5. Les variantes

```sql
-- simple
CREATE INDEX a3_idx_simple ON shopflow.commandes (client_id);
-- composé
CREATE INDEX a3_idx_compose ON shopflow.commandes (client_id, created_at DESC, id DESC);
-- couvrant (slide 9)
CREATE INDEX a3_idx_couvrant ON shopflow.commandes (client_id, created_at DESC, id DESC) INCLUDE (statut, total);
-- couvrant limité à la projection de la requête du cours
CREATE INDEX a3_idx_couvrant_total ON shopflow.commandes (client_id, created_at DESC, id DESC) INCLUDE (total);
```

| Variante | Taille | Part de la table (13 392 kB) |
|---|---|---|
| Index unique existant `(client_id, cle_idempotence)` | 1 864 kB | 13,9 % |
| Simple | 688 kB | 5,1 % |
| Composé | 3 984 kB | 29,7 % |
| Couvrant `(statut, total)` | 5 792 kB (×1,45 le composé) | 43,2 % |
| Couvrant `(total)` | 4 864 kB (×1,22 le composé) | 36,3 % |

---

## 6. Résultats

### 6.1 Lecture, client 42, 51 tours en alternance (médiane, p95)

| Variante | `slide` | `api` | `curseur` | Buffers (`api`) | Nœuds du plan (`api`) |
|---|---|---|---|---|---|
| Initiale | 0,546 / 0,845 | 0,690 / 1,117 | 0,690 / 1,249 | 96 | Bitmap Heap Scan + **Sort** |
| Simple | 0,548 / 0,860 | 0,729 / 1,414 | 0,707 / 1,169 | 96 | Bitmap Heap Scan + **Sort** |
| Composé | 0,161 / 0,339 | 0,274 / 0,485 | 0,342 / 0,562 | 27 | Index Scan, **sans Sort** |
| Couvrant `(statut,total)` | 0,094 / 0,186 | 0,199 / 0,366 | 0,201 / 0,403 | 7 | Index Only Scan, 0 Heap Fetches |
| Couvrant `(total)` | 0,086 / 0,182 | 0,267 / 0,515 | 0,303 / 0,580 | 27 | Index Scan (revient à la table pour `statut`) |

Durées en ms ; médiane / p95. Gains sur la médiane de `api` : composé ×2,5, couvrant ×3,5, couvrant `(total)` ×2,6, simple ×0,95 (écart dans le bruit : pas de gain).

### 6.2 Lecture sur 5 clients (protocole du cours, 5 mesures, requête `api`, médiane en ms)

| Variante | Client 1 | Client 42 | Client 250 | Client 500 | Client 1000 | Buffers |
|---|---|---|---|---|---|---|
| Initiale | 0,799 | 0,786 | 0,803 | 0,884 | 0,771 | 99 à 109 |
| Simple | 0,766 | 0,847 | 0,701 | 0,771 | 0,769 | 99 à 109 |
| Composé | 0,256 | 0,321 | 0,281 | 0,358 | 0,273 | 27 |
| Couvrant `(statut,total)` | 0,160 | 0,161 | 0,172 | 0,168 | 0,203 | 7 |
| Couvrant `(total)` | 0,297 | 0,257 | 0,309 | 0,276 | 0,269 | 27 |

Les 75 combinaisons (5 variantes × 3 requêtes × 5 clients) donnent le **même résultat** que l'initiale. Les clients ayant tous 100 commandes dans le jeu fourni, les variations entre clients sont dues au bruit : le jeu ne contient **aucun client très actif**, d'où 6.3.

### 6.3 Client très actif (client 7 porté à 20 100 commandes)

| Variante | `api` : médiane | Buffers | Gain |
|---|---|---|---|
| Initiale | 23,311 ms | 287 | |
| Simple | 23,325 ms | 287 | ×1,0 |
| Composé | 0,256 ms | 27 | **×91** |
| Couvrant `(statut,total)` | 0,189 ms | 7 | ×123 |
| Couvrant `(total)` | 0,276 ms | 27 | ×84 |

Sans index adapté, le coût **croît avec le nombre de commandes du client** (96 buffers pour 100 commandes, 287 pour 20 100, 23 ms) parce que PostgreSQL lit toutes les commandes du client avant de trier. Avec l'index composé, il lit toujours 21 entrées : le coût **ne dépend plus du volume**.

### 6.4 Le piège de l'alias (client 42, `api_alias` : `ORDER BY created_at, id` sans qualificatif)

| Variante | Médiane | Buffers | Plan |
|---|---|---|---|
| Initiale | 0,877 ms | 93 | Sort |
| Composé | **0,783 ms** | 93 | **Sort, l'index composé n'est pas utilisé** (le plan retombe sur l'index unique) |
| Couvrant `(statut,total)` | 0,382 ms | 11 | Index Only Scan **puis Sort** |

Le résultat est identique à la version qualifiée, mais l'index composé ne sert à rien. La qualification `commandes.created_at` dans l'API est donc **indispensable** à l'optimisation.

### 6.5 Écriture : 20 000 insertions dans une transaction annulée (15 tours)

| Variante | Index sur la table | WAL | Écart WAL | Enregistrements WAL | Durée médiane |
|---|---|---|---|---|---|
| Initiale | 2 | 4 623 674 octets | référence | 60 322 | 126,8 ms |
| Simple | 3 | 5 927 578 | **+28,2 %** | 80 327 | 180,9 ms (+43 %) |
| Composé | 3 | 6 240 760 | **+35,0 %** | 80 322 | 194,0 ms (+53 %) |
| Couvrant `(statut,total)` | 3 | 6 570 048 | **+42,1 %** | 80 322 | 219,0 ms (+73 %) |
| Couvrant `(total)` | 3 | 6 400 760 | **+38,4 %** | 80 323 | 187,8 ms (+48 %) |

- **Le WAL est la mesure fiable.** Chaque index ajouté ajoute **environ 20 000 enregistrements** (un par ligne insérée, à quelques unités près) : 60 322 = 3 × 20 000 + 322 avec la table, la clé primaire et l'index unique ; 80 322 à 80 327 avec un index de plus. Le volume en octets dépend ensuite de la largeur de l'index.
- **Les durées sont très bruitées** (p95 jusqu'à 593 ms contre une médiane de 194 ms). Sur trois exécutions complètes du même protocole, la surcharge de l'index composé a varié de **+23 % à +62 %** (seule la dernière est conservée dans `resultats.json`). L'ordre entre composé et couvrant `(total)` n'est pas établi.
- Conclusion : tout index ajoute du travail à **chaque** insertion, de l'ordre de **+30 à +40 % de WAL** ici, et plus l'index est large, plus le coût augmente.

### 6.6 Visibilité et `Heap Fetches` (slide 9, table jetable séparée)

| Étape | Plan | Heap Fetches | Buffers |
|---|---|---|---|
| Après `VACUUM` | Index Only Scan | 0 | 4 |
| Après un `UPDATE` des 100 commandes du client 42, sans `VACUUM` | Index Only Scan | **40** | 48 |
| Après un nouveau `VACUUM` | Index Only Scan | 0 | 8 |

`INCLUDE` ne garantit pas l'absence d'accès à la table : dès que des lignes sont modifiées, il faut visiter la table jusqu'au prochain `VACUUM`. Les 40 visites pour 20 lignes renvoyées s'expliquent probablement par les anciennes versions des lignes encore présentes dans l'index (**hypothèse**, non vérifiée directement).

Sur la vraie table, `Heap Fetches` vaut 0 parce que la table était entièrement « visible » avant l'atelier.

---

## 7. Tableau de décision (livrable)

| Critère | Simple | Composé | Couvrant `(statut,total)` | Couvrant `(total)` |
|---|---|---|---|---|
| Supprime le `Sort` | non | **oui** | oui | oui (slide), non (API : reste un Index Scan) |
| Gain sur l'API (médiane) | aucun | ×2,5 | ×3,5 | ×2,6 |
| Gain avec un client de 20 100 commandes | aucun | ×91 | ×123 | ×84 |
| Résultat identique | oui | oui | oui | oui |
| Taille | 688 kB | 3 984 kB | 5 792 kB | 4 864 kB |
| Surcoût d'écriture (WAL) | +28 % | +35 % | +42 % | +38 % |
| Dépend de la visibilité (`VACUUM`) | non | non | **oui** | oui |
| **Décision** | **Rejeté** | **Retenu** | **Option** | **Rejeté** |

**Pourquoi le composé et pas le couvrant ?** Le couvrant gagne encore 0,075 ms par appel (0,274 → 0,199 ms), soit moins que le gain du composé lui-même (0,416 ms). En échange il est 45 % plus gros, coûte plus en écriture, et son avantage disparaît partiellement quand la table est modifiée (`Heap Fetches`, 6.6). Il devient intéressant si l'endpoint est un point chaud, si la table est rarement modifiée et si les lectures dominent nettement.

---

## 8. Explications

- **Simple : absence de gain.** La base a déjà un index qui commence par `client_id` : l'index unique `(client_id, cle_idempotence)`. PostgreSQL utilise le nouvel index simple (plus petit, 688 kB contre 1 864 kB) mais **le plan est le même** : Bitmap Heap Scan puis `Sort`, 96 buffers. Il retrouve les commandes du client sans pouvoir les fournir dans l'ordre : il doit donc toujours lire les 100 commandes et les trier pour en garder 20.
- **Composé : gain.** L'égalité sur `client_id` borne le groupe, puis `created_at DESC, id DESC` donne déjà l'ordre demandé : PostgreSQL lit 21 entrées et s'arrête. Plus de `Sort`. Il lit encore la table pour `statut` et `total` ; les 26 à 27 buffers correspondent vraisemblablement à une page de table par commande (les commandes d'un client sont dispersées) et quelques pages d'index (interprétation).
- **Couvrant `(statut,total)` : gain supplémentaire.** Toutes les colonnes de la requête sont dans l'index : Index Only Scan, 7 buffers, aucune lecture de table.
- **Couvrant `(total)` : pas de gain pour l'API.** Il ne contient pas `statut`, que l'API renvoie : PostgreSQL retourne à la table, comme pour le composé. Il n'aide que la requête du cours, qui ne lit pas `statut`. C'est un exemple de variante bonne sur le papier et inutile pour le SQL réellement émis.
- **Le curseur** : `(created_at, id) < (…)` utilise aussi l'index composé (Index Scan, 27 buffers, ×2,0). Sans index adapté, le coût est le même que la première page.

---

## 9. Limites et conditions de remise en cause

- Durées sub-milliseconde et bruitées : seules les comparaisons au sein d'une mesure alternée sont fiables ; on ne généralise pas un pourcentage (slide 29).
- Jeu synthétique : 100 commandes par client. Le cas du client très actif est **simulé** sur une table de travail.
- Les écritures mesurées sont des insertions. Les mises à jour de `statut` ne sont pas mesurées. **Hypothèse non testée :** une colonne dans `INCLUDE` compte comme colonne indexée, donc modifier `statut` empêcherait une mise à jour « HOT » et coûterait davantage avec l'index couvrant `(statut, total)`.
- La charge réelle (fréquence des lectures de l'historique, rythme des créations de commandes) est inconnue. **Remettre en cause la décision** si les créations de commandes dominent nettement, ou si l'endpoint devient un point chaud (alors envisager le couvrant).
- La construction sur une très grande table (volume de production) n'est pas prouvée par un essai sur 100 000 lignes (slide 24) ; d'où la variante `CONCURRENTLY`.

---

## 10. Migration

Dossier `atelier3/migration/` :

| Fichier | Rôle |
|---|---|
| `001_idx_historique_client_up.sql` | Crée `idx_hist_client` (laboratoire, `CREATE INDEX` ordinaire, `lock_timeout` de 5 s) |
| `001_idx_historique_client_prod_up.sql` | Même index avec `CREATE INDEX CONCURRENTLY` (déploiement, hors transaction) |
| `001_idx_historique_client_verifier.sql` | Contrôles : index valide, aucun index invalide, plan sans `Sort` |
| `001_idx_historique_client_down.sql` | Retour arrière : supprime uniquement `idx_hist_client` |

**Testé sur une base jetable** (copie de `shopflow`, supprimée ensuite) :
- la montée crée l'index (valide, 3 984 kB) et peut être **rejouée sans erreur** (`IF NOT EXISTS`) ;
- le plan de la requête de l'API devient `Index Scan using idx_hist_client`, sans `Sort` ;
- le retour arrière supprime l'index et laisse l'index unique `commandes_client_id_cle_idempotence_key` intact ;
- la variante `CONCURRENTLY` fonctionne hors transaction et **échoue dans un bloc `BEGIN`** (`cannot run inside a transaction block`), comme l'annonce la slide 25.

**La migration n'a pas été appliquée au laboratoire** : l'Atelier 3 demande une décision, et le laboratoire sert encore aux ateliers suivants. Pour l'appliquer :
```bash
docker exec -i api-postgres-1 psql -U cours -d shopflow -v ON_ERROR_STOP=1 < atelier3/migration/001_idx_historique_client_up.sql
```
En production : lancer la variante `prod_up`, puis `verifier`, surveiller les sessions et les verrous, et conserver le `down` comme plan de retour.

---

## 11. Reproduire

```bash
docker compose up -d --wait          # dans 01_server/api
python3 atelier3/benchmark.py        # environ 7 minutes
```
Le script crée et supprime ses propres index et tables de travail, vérifie que le laboratoire retrouve son état initial, et écrit `atelier3/resultats/resultats.json` et les plans dans `atelier3/resultats/plans/`. Les durées absolues changeront d'une exécution à l'autre ; les buffers, plans, volumes de WAL, tailles et résultats fonctionnels doivent rester identiques.

## 12. Fichiers

| Chemin | Contenu |
|---|---|
| `atelier3/benchmark.py` | Le protocole complet, reproductible |
| `atelier3/resultats/resultats.json` | Toutes les mesures brutes (chaque durée, buffers, plans résumés, empreintes) |
| `atelier3/resultats/plans/` | 75 plans `EXPLAIN (ANALYZE, BUFFERS)` complets (variante × requête × client, mesure n°5) |
| `atelier3/migration/` | Migration 001, version laboratoire, déploiement, vérification, retour arrière |
