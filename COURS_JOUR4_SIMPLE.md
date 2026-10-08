# Jour 4 expliqué simplement : tout ce qui précède l'Atelier 7

Slides 1 à 12 du cours « Optimiser les API et le cache » (Jour 4). L'Atelier 7 commence à la slide 13 : tout ce qui est ici est ce qu'il faut avoir compris **avant** de le faire.

---

## L'idée de la journée (slides 1 et 2)

Jusqu'ici on a optimisé **la base** (requêtes, index, migrations). Le Jour 4 optimise **le chemin complet** : l'API qui appelle la base.

```
Client  ->  API  ->  (pool de connexions)  ->  PostgreSQL
                \->  (cache Redis)
```

Trois objectifs :
1. **limiter les requêtes inutiles** (le problème N+1) ;
2. **construire une pagination stable** (curseur plutôt qu'OFFSET) ;
3. **ajouter un cache** dont on comprend la fraîcheur (c'est la suite du cours, après l'atelier 7).

**La preuve à rendre (« B4C8 »)** contient : une **trace d'API**, un **comptage SQL**, un **contrat de pagination** et un **scénario d'invalidation** du cache. Et il faut **séparer** deux choses : ce qui vient de la **réduction du travail SQL** et ce qui vient du **cache**. Sinon on ne sait pas ce qui a produit le gain.

Phrase à retenir : *le cache intervient après l'examen des requêtes et des garanties métier.* On optimise d'abord les requêtes, on met un cache ensuite, pas l'inverse.

---

## Une page peut coûter cher en SQL : deux problèmes distincts (slide 3)

Exemple de la slide : une API affiche **3 livres avec le nom de leur auteur**.

| Problème | De quoi il s'agit | Ce qui coûte |
|---|---|---|
| **OFFSET** | pour la page 2, la requête **saute** 3 livres et renvoie les 3 suivants | le nombre de **lignes parcourues** |
| **N+1** | 1 requête pour les 3 livres, puis **1 requête par auteur** : 1 + 3 = **4 requêtes** | le nombre de **requêtes** |

**Le lien :** c'est la même page, mais **deux problèmes différents**. OFFSET concerne les lignes parcourues, N+1 concerne le nombre de requêtes. **On les corrige séparément** : une pagination adaptée d'un côté, un chargement groupé de l'autre. Corriger l'un ne corrige pas l'autre.

---

## OFFSET : comment ça marche (slide 4)

```sql
SELECT id, titre
FROM livres
ORDER BY id
LIMIT 3 OFFSET 3;
```

Avec les livres 1 Atlas, 2 Boréal, 3 Cosmos, 4 Delta, 5 Écho, 6 Flora : `OFFSET 3` **ignore** les livres 1 à 3, `LIMIT 3` renvoie les livres **4 à 6** (la page 2).

- `LIMIT n` : combien de lignes on veut.
- `OFFSET k` : combien de lignes on **saute** avant.
- Page `p` avec des pages de `n` lignes : `OFFSET (p - 1) × n`.

---

## OFFSET : le travail croît avec la page (slide 5)

Pour renvoyer la page 5 001, PostgreSQL doit **parcourir (et écarter) toutes les lignes d'avant**, même si la page n'en contient que 20.

Calcul de la slide (pages de 20, travail minimal = OFFSET + LIMIT) :

| Page | OFFSET | Entrées à parcourir au moins |
|---|---|---|
| 1 | 0 | 20 |
| 101 | 2 000 | 2 020 |
| 5 001 | 100 000 | **100 020** |

**Attention :** c'est un **calcul illustratif** (un travail théorique), **pas une durée mesurée**. Le cours le précise lui-même.

Deux autres défauts d'OFFSET :
- **les positions bougent** : si une ligne est insérée ou supprimée entre deux appels, les pages se décalent (une ligne peut être vue deux fois, ou jamais) ;
- mais OFFSET **reste pratique** pour un **accès direct à une page numérotée** sur un ensemble **raisonnable et stable**. La décision dépend du besoin de navigation.

---

## La pagination par curseur (slide 6)

Un **curseur** n'est pas un numéro de page : c'est un **repère** = la paire **(date, id)** de la **dernière commande affichée**.

```sql
SELECT id, created_at, total
FROM commandes
WHERE client_id = $1
  AND (created_at, id) < ($2, $3)
ORDER BY created_at DESC, id DESC
LIMIT 21;
```

Comment ça se lit :
- `$1` : le client ; `$2` et `$3` : la date et l'id du **repère**.
- `(created_at, id) < ($2, $3)` : « les commandes **plus anciennes** que ce repère » (comparaison de deux valeurs à la fois, d'abord la date, puis l'id si les dates sont égales).
- **L'id départage deux dates identiques** : sans lui, deux commandes avec la même date pourraient être sautées ou répétées.
- **Page 1 :** on omet simplement la ligne `AND …`.

**Pourquoi `LIMIT 21` pour une page de 20 ?** On demande **une ligne de trop** :
- si une **21e ligne** arrive : il y a une page suivante → `hasNextPage = vrai`. On affiche 20 lignes et on garde la **20e** comme prochain curseur ;
- sinon : `hasNextPage = faux`, on désactive le bouton « Page suivante ».
C'est moins cher que de faire un `COUNT(*)` pour savoir s'il reste des résultats.

**Pourquoi c'est plus rapide ?** `OFFSET 1 000` écarte d'abord 1 000 lignes. Le curseur, avec un **index adapté** (c'est l'index composé `(client_id, created_at DESC, id DESC)` de l'Atelier 3), **reprend directement au repère**.

**Limite :** le curseur est adapté à « **suivant** » (et « précédent »), **pas** à l'accès direct à « la page 37 ».

---

## La stabilité d'une pagination (slide 7)

- **Un ordre unique** : `ORDER BY created_at DESC, id DESC` (l'id rend l'ordre déterministe). Sans ordre unique, la sélection est **ambiguë** quand des lignes partagent la même date.
- Le curseur transporte : **la paire de valeurs**, **la version du format** et **les filtres nécessaires** pour reprendre la recherche (sinon un curseur d'un filtre pourrait être rejoué avec un autre).
- **Les modifications entre deux appels restent possibles.** Un curseur sur un champ **modifiable** peut **sauter** une ligne ou la **revoir**. Pour une exportation complète **cohérente**, il faut un protocole d'**instantané** ou un autre mécanisme explicite.
- **Sécurité :** un curseur **opaque** (illisible pour le client) n'est **pas une autorisation**. Le serveur **vérifie toujours** que l'appelant a le droit d'accéder au client demandé.

---

## Le comptage total (slide 8)

Une page courte peut être très rapide, alors qu'un `COUNT(*)` **exact** sur tout l'ensemble reste **coûteux** (il doit compter toutes les lignes qui correspondent). Ajouter un `totalCount` à **chaque** réponse peut donc **annuler le bénéfice** de la pagination.

Les options :
1. se contenter de **`hasNextPage`** (gratuit grâce au `LIMIT 21`) ;
2. demander le comptage **séparément** (seulement quand l'écran en a besoin) ;
3. donner une **estimation**, à condition de l'**afficher comme une estimation** (« environ 12 000 »).

L'API doit préciser **le coût et la fraîcheur** de cette information. Le besoin d'un total exact doit venir de **l'usage**, pas d'un **automatisme de l'ORM**.

---

## Le problème N+1 (slide 9)

Un accès **charge une liste**, puis un accès supplémentaire **charge une relation pour chaque élément**.

- 50 commandes → **1** requête pour la liste + **50** requêtes (une par commande pour ses lignes) = **51**.

Calcul théorique de la slide (pattern 1 + N) :

| N (commandes dans la page) | Requêtes SQL |
|---|---|
| 5 | 6 |
| 20 | 21 |
| 50 | 51 |

Pourquoi c'est un problème : **chaque aller-retour** ajoute du travail et une **attente possible de connexion**. Sur une base **locale**, ça peut paraître discret (chaque requête est très rapide). **Sous charge** et avec un **réseau réel**, ça peut **dominer** la latence de l'API. Le nombre de requêtes **croît avec N**.

---

## La correction : le chargement groupé (slide 10)

On charge la page de commandes, puis **toutes les lignes en une seule requête**, sur les identifiants de la page :

```sql
SELECT commande_id, produit_id, qte, prix_unitaire
FROM lignes
WHERE commande_id = ANY($1::bigint[])
ORDER BY commande_id, produit_id;
```

- `$1` est un **tableau** contenant les ids des commandes de la page (par exemple 50 ids).
- `= ANY(tableau)` veut dire « l'id est l'un de ceux du tableau » (équivalent de `IN (…)`).
- Ensuite, **l'API regroupe les lignes par commande en mémoire** pour construire la réponse.

**Résultat : 2 requêtes**, quel que soit N (la page + les lignes). Le nombre de requêtes **ne dépend plus de N**.

Deux précisions du cours :
- **La taille du tableau doit rester bornée** par la taille maximale de page (sinon on retombe dans un autre problème).
- Une **jointure unique** est une autre option, mais elle peut **multiplier les lignes** (une ligne par ligne de commande) et **interagir avec `LIMIT`** (le `LIMIT` compterait des lignes de jointure, pas des commandes). **On vérifie le contenu de la page** avant de conclure.

---

## L'ORM et le SQL réellement émis (slide 11)

Un **ORM** traduit des accès « objets » (`commande.lignes`) en SQL. Le code ne montre **pas toujours** combien de requêtes sont envoyées, quelles colonnes sont chargées, ni quelles jointures. **Les traces SQL** donnent cette visibilité : c'est pour ça qu'on compte les requêtes **réellement émises**.

- **Chargement paresseux (lazy)** : la relation est chargée **quand on y accède** → peut créer du **N+1**.
- **Chargement « eager » excessif** : on charge **trop de relations** d'avance → on transfère des données inutiles.
- Souvent mieux pour un **écran précis** : une **projection ciblée** (seulement les colonnes utiles) et un **chargement groupé**.
- **Les relations utiles au détail ne sont pas toutes nécessaires à la liste.**

---

## API REST : détecter et corriger N+1 (slide 12)

La méthode, qui est celle de l'Atelier 7 :

1. Appeler la liste des commandes avec **5** résultats, puis **50**, et **relever les requêtes SQL** de chaque appel.
2. Si la lecture des lignes déclenche **une requête par commande**, le total **croît avec N** : c'est le N+1.
3. Corriger : charger la page, puis **toutes ses lignes en une requête** sur les ids. **Refaire le test** : le nombre de requêtes doit rester **stable**.

Chiffres **théoriques** de la slide (à remplacer par des mesures réelles) :

| Appel | Avant | Après |
|---|---|---|
| `GET /commandes?limit=5` | 6 SQL | 2 SQL |
| `GET /commandes?limit=50` | 51 SQL | 2 SQL |

**Preuve attendue dans le TP :**
- **conserver les traces** avant/après (les vraies requêtes SQL comptées) ;
- **vérifier que la réponse REST contient toujours les mêmes commandes et leurs lignes** (même résultat, comme pour toute optimisation) ;
- **les chiffres de la slide sont théoriques** : il faut compter les requêtes réelles.

---

## Ce qu'il faut avoir compris avant l'Atelier 7

1. **OFFSET et N+1 sont deux problèmes différents** (lignes parcourues contre nombre de requêtes) : deux corrections séparées.
2. **OFFSET coûte de plus en plus cher** avec la page (il écarte d'abord toutes les lignes d'avant) ; il reste correct pour un accès direct à une page numérotée sur un ensemble stable.
3. **Le curseur** = la paire **(date, id)** de la dernière ligne ; l'**id** départage les dates identiques ; il est adapté à « suivant », pas à « page 37 ».
4. **`LIMIT 21` pour 20 lignes** donne `hasNextPage` sans `COUNT(*)`.
5. **Un `COUNT(*)` exact à chaque réponse** peut annuler le gain de la pagination.
6. **Un curseur n'est pas une autorisation** : le serveur vérifie toujours les droits.
7. **N+1 = 1 + N requêtes** ; il se reconnaît dans une trace par un nombre de requêtes qui **croît avec N**.
8. **Le chargement groupé** (`WHERE commande_id = ANY($1)`) ramène à **2 requêtes** quel que soit N ; le tableau d'ids reste borné.
9. **On prouve** par des traces avant/après **et** par un résultat identique, avec de **vrais** comptages (pas les chiffres théoriques du cours).

## Questions pièges

**Pourquoi le curseur contient-il une date et un id ?** La date donne l'ordre ; l'id départage les commandes qui ont la même date, pour ne ni sauter ni répéter de ligne.

**Pourquoi ne pas utiliser OFFSET partout ?** Parce qu'il écarte toutes les lignes d'avant à chaque appel, donc le coût grandit avec la page, et que les insertions entre deux appels décalent les pages.

**Quand garder OFFSET ?** Pour aller directement à une page numérotée, sur un ensemble raisonnable et stable.

**Pourquoi 2 requêtes et pas une jointure ?** La jointure peut multiplier les lignes et fausser le `LIMIT` : on charge d'abord la page, puis ses lignes.

**Les chiffres 6/51 → 2 de la slide 12 sont-ils des mesures ?** Non, ils sont théoriques : la preuve du TP, ce sont les requêtes réellement comptées dans les traces.

## Vocabulaire

| Mot | Sens |
|---|---|
| **API REST** | service web qui répond à des appels HTTP (`GET /commandes?limit=50`) |
| **ORM** | couche qui traduit des objets du code en requêtes SQL |
| **Aller-retour** | un envoi de requête à la base et sa réponse |
| **Curseur** | repère (date, id) de la dernière ligne affichée, pour reprendre au bon endroit |
| **`hasNextPage`** | indicateur « il y a une page suivante » |
| **Chargement groupé (batching)** | charger les relations de toute une page en une requête |
| **Projection** | ne sélectionner que les colonnes utiles |
| **Trace SQL** | journal des requêtes réellement envoyées à la base |
| **Contrat de pagination** | description de ce que renvoie l'API (taille, ordre, curseur, `hasNextPage`) et de ses règles |

---
---

# Partie 2 : ce qu'il y a entre l'Atelier 7 et l'Atelier 8 (slides 14 à 33)

Ces slides préparent l'**Atelier 8** (slide 34). Elles couvrent trois sujets : **le pool de connexions** (slides 14 à 19), **deux protections de l'API** (slides 21 et 22) et **le cache Redis** (slides 23 à 33). La slide 20 est la fiche de l'Atelier 7 (déjà faite).

---

## A. Le pool de connexions et PgBouncer (slides 14 à 19)

*(Déjà vu en pratique à l'Atelier 7, partie B.)*

### Le pool de connexions (slide 14)
Ouvrir une connexion à PostgreSQL **coûte des ressources**. Un **pool** garde un ensemble de connexions **déjà ouvertes** et les **prête** aux requêtes qui en ont besoin. Quand toutes sont prises, les demandes suivantes **attendent**.

- **Pool trop petit** : les requêtes font la queue (de l'attente).
- **Pool trop grand** : on peut **saturer la base**.
- La taille se raisonne pour **toutes les instances de l'API ensemble**, avec une réserve pour l'exploitation. Exemple de la slide : **4 instances × 30 connexions = 120 connexions demandées**, avant même les autres utilisateurs.

### PgBouncer (slide 15)
Si chaque instance de l'API a son propre pool, le total grossit vite. **PgBouncer** est un **processus à part** placé **entre l'API et PostgreSQL**. Il accepte beaucoup de connexions clientes et n'en réutilise qu'un **nombre borné** côté PostgreSQL. Une demande peut **attendre** qu'une connexion se libère.

**Il limite les connexions. Il ne rend aucune requête plus rapide** et ne remplace ni l'optimisation SQL ni la maîtrise de la charge.

### Le mode transaction (slide 16)
Deux API (A et B) gardent chacune une connexion avec PgBouncer. Quand A **démarre une transaction**, PgBouncer lui **prête** une connexion serveur S **jusqu'au `COMMIT` ou `ROLLBACK`**. Une fois S libre, B peut l'emprunter. Si toutes les connexions serveur sont prises, B **attend dans PgBouncer**.

### Les trois modes (slide 17)
| Mode | Quand la connexion serveur est rendue | Conséquence |
|---|---|---|
| **Session** | à la **déconnexion** du client | l'état de session (LISTEN, tables temporaires) est conservé ; peu de mutualisation |
| **Transaction** | à la fin de la **transaction** | le serveur **peut changer** entre deux transactions : ne pas supposer que l'état de session persiste |
| **Instruction** (statement) | après **chaque requête** | une transaction sur plusieurs instructions est **interdite** |

Notre API utilise le **mode transaction** : il faut vérifier `LISTEN`, les `SET` de session, les tables temporaires et les requêtes préparées.

### La configuration (slide 18)
```ini
pool_mode = transaction
default_pool_size = 20     # connexions serveur par couple base/utilisateur
max_client_conn = 120      # connexions clientes acceptées
```
L'API se connecte au **port 6432** (PgBouncer), pas au 5432 (PostgreSQL). On observe avec `SHOW POOLS` (clients actifs/en attente, serveurs actifs/libres). Ce sont des **valeurs d'illustration**, pas universelles.

### Temps d'attente et délais (slide 19)
- Un appel peut **consommer son budget de temps avant même d'exécuter le SQL**, en attendant une connexion. On sépare donc trois mesures : **acquisition** (attendre une connexion), **exécution** (le SQL) et **réponse**.
- Le **délai maximal global** doit rester cohérent avec les délais de chaque couche.
- Une requête **abandonnée par le client peut continuer sur le serveur** si l'annulation ne se propage pas.
- **Un timeout limite l'attente. Il ne prouve pas que l'écriture n'a jamais été validée.** (Si une écriture « expire », elle a peut-être quand même réussi.)

---

## B. Deux protections de l'API (slides 21 et 22)

### Le rate limiting et l'erreur 429 (slide 21)
Le **rate limiting** fixe un **quota** de requêtes **par client** (utilisateur ou clé API) sur une durée. Exemple : **10 appels par minute et par clé**. Au-delà, l'API **refuse** pour protéger ses ressources. Un quota **global** seul pénaliserait des clients qui n'ont rien à voir entre eux.

- **HTTP 429 « Too Many Requests »** = quota dépassé, l'appel est refusé.
- L'en-tête **`Retry-After`** (s'il est fourni) dit **combien attendre** avant de réessayer. Il faut **éviter les relances immédiates**.
- **Fenêtre fixe** : le quota est remis à zéro **à chaque minute pile**. Si un client envoie **10 appels à 12:00:59** puis **10 à 12:01:00**, **les 20 sont acceptés en environ 2 secondes** : chaque lot tombe dans une minute différente. C'est la **« rafale à la frontière »**.
- **Token bucket** (seau de jetons) : on a un seau qui contient un nombre limité de jetons, **rechargé progressivement**. Chaque appel consomme un jeton. Cela **borne la rafale**.

### La compression (slide 22)
La réponse JSON se **compresse côté API (ou proxy), pas en SQL**. Le client annonce `Accept-Encoding: gzip, br` ; le serveur répond avec `Content-Encoding` indiquant le format. Ça **réduit les octets transférés**, au prix de **calcul CPU**. À ne pas confondre avec **TOAST** de PostgreSQL (compression des valeurs **stockées**), qui ne compresse **pas** le JSON envoyé en HTTP. À mesurer : octets, latence, CPU.

---

## C. Le cache Redis (slides 23 à 33)

C'est **le sujet de l'Atelier 8**. Un **cache** garde une **copie** d'un résultat pour **éviter de refaire le travail**. L'idée est simple ; tout le sujet est de **garder la copie correcte** (« la fraîcheur »).

### Le cache et la source de vérité (slide 23)
**PostgreSQL reste la source de vérité.** Le cache peut **perdre une valeur** ou fournir une **ancienne valeur** selon sa politique. La décision précise : les **clés**, la **portée**, la **durée de validité**, l'**invalidation** et le **comportement en cas de panne**.

Dans notre cas : **une fiche catalogue peut tolérer un court retard** (un prix affiché quelques secondes périmé n'est pas grave), mais **la confirmation de stock garde son contrôle transactionnel** dans la base.

### Cache-aside (slide 24) : celui qu'on utilise
C'est **l'application** qui gère le cache :
1. elle demande la fiche à **Redis** ;
2. **hit** (la copie est là) → elle la renvoie, **sans toucher PostgreSQL** ;
3. **miss** (la copie n'est pas là) → elle lit **PostgreSQL**, **range une copie dans Redis avec une durée de vie (TTL)**, puis répond.

Le pattern **n'apporte pas tout seul la cohérence** entre Redis et PostgreSQL : c'est à l'écriture de **mettre à jour ou supprimer** la copie. Et **une erreur Redis ne doit pas transformer une valeur de base valide en réponse inventée**.

### Read-through (slide 25)
Une **couche de cache** sait **charger elle-même** la donnée depuis la source quand elle manque ; l'API ne gère pas le détail du miss. Attention : **`GET` Redis seul ne lit pas PostgreSQL**, un composant doit implémenter le chargement. La différence avec cache-aside, c'est **qui porte la responsabilité**, pas une commande Redis magique.

### Les clés de cache (slide 26)
Une clé décrit **la ressource et sa représentation** : `produit:v1:42` = la fiche publique du produit 42, **format v1**. Une réponse qui dépend du **client, de la langue ou des droits** doit avoir **un périmètre correspondant**, sinon on risque de **servir à un utilisateur la réponse d'un autre**. La **version de format** (`v1`) permet de faire évoluer les valeurs sans mélanger.

### Le TTL (slide 27)
Le **TTL** (Time To Live) = combien de temps une clé peut vivre avant **d'expirer**.
```
SET produit:v1:42 '{"id":42,"prix":19.90}' EX 60   # EX = secondes
GET produit:v1:42
TTL produit:v1:42     # temps restant
DEL produit:v1:42     # suppression
```
- **TTL court** : moins de vieilles copies, mais **plus de miss** et plus de charge sur la base.
- La **validité métier** peut être plus stricte que le TTL : après un changement de prix, l'application peut **invalider tout de suite**.
- Une clé peut disparaître **avant** son TTL (éviction).

### Expiration contre éviction (slide 28)
| Mécanisme | Déclencheur |
|---|---|
| **Expiration** | le TTL est atteint |
| **Éviction** | la **limite de mémoire** est atteinte (Redis retire des clés selon une politique) |
| **Invalidation métier** | la source a changé |
| **Suppression manuelle** | action explicite (`DEL`) |

Les politiques d'éviction : `allkeys-lru` (favorise les clés récemment utilisées), `allkeys-lfu` (tient compte d'une fréquence approximative), `noeviction` (refuse certaines écritures quand la limite est atteinte). Les deux mécanismes provoquent un **miss**, mais **pour des raisons différentes**.

### L'invalidation après une écriture (slide 29)
Stratégie simple : **1.** valider l'écriture dans PostgreSQL, **2.** **supprimer** la copie Redis, **3.** la prochaine lecture **reconstruit** la fiche.

**Risque :** si la suppression Redis **échoue**, une **ancienne copie reste jusqu'au TTL**. Et l'opération touche **deux systèmes sans transaction commune** (pas atomique). Un événement durable ou une **outbox** peut aider à rejouer l'invalidation. Le prix **affiché** peut être temporairement ancien ; le prix **validé pour une commande** est contrôlé dans la source.

### La course entre lecture et invalidation (slide 30)
C'est **la slide citée par l'Atelier 8**. Le scénario :

| Instant | Lecture A | Écriture B |
|---|---|---|
| t1 | **lit l'ancienne valeur** (miss) | |
| t2 | | **valide la nouvelle valeur** dans PostgreSQL |
| t3 | | **supprime** la clé Redis |
| t4 | **remet l'ancienne valeur** dans Redis | |

Résultat : Redis contient **l'ancien prix** alors que la base a le nouveau, **jusqu'à expiration du TTL**. **Supprimer la clé après l'écriture ne règle donc pas toutes les courses.** Pistes : des **versions** (n'écrire dans le cache que si la version est plus récente), un **protocole de chargement**, une **invalidation rejouée**. On choisit selon la **fraîcheur exigée** et la **complexité acceptable**. Le laboratoire ne simule que le cas simple, mais **le scénario doit apparaître dans l'analyse**.

### Le cache stampede (slide 31)
Quand **beaucoup de requêtes** trouvent **la même clé absente en même temps** (par exemple une valeur populaire qui vient d'expirer), **toutes** relancent le calcul ou le SQL : une **rafale** sur la base. Parades : **un seul chargement par clé** (les autres attendent), un **TTL avec une petite variation aléatoire** (les expirations ne tombent pas toutes ensemble), un **rafraîchissement anticipé**. Un verrou distribué demande un **propriétaire**, une **libération sûre**, une **attente bornée** et un **chemin d'échec**. Un TTL avec variation **ne résout pas à lui seul** tous les miss simultanés.

### La panne du cache et le repli (slide 32)
Quand **Redis tombe**, le service peut **relire PostgreSQL**, avec un **timeout court** pour ne pas bloquer tous les appels. Mais ce **repli augmente la charge sur la base** et peut créer **une seconde panne** (tous les hits deviennent des lectures SQL). Protections : **limites de concurrence**, **priorités**, **capacité réservée**, **circuit breaker** (couper temporairement les tentatives vers un composant en panne). Et : **une valeur absente ou une erreur de cache ne signifie pas que le produit n'existe pas.**

### Le taux de hit (slide 33)
Le **taux de hit** = accès servis par le cache ÷ accès au cache. Un taux élevé peut cacher un **mauvais endpoint** (réponse trop grosse, misses très lents). On suit aussi : durées hit et miss, évictions, mémoire, erreurs, charge SQL.

**Durée moyenne (modèle simple) :** **90 % × 5 ms + 10 % × 105 ms = 15 ms** (calcul **fictif** du cours). Ce modèle donne une **moyenne**, pas un **p95**.

---

## Ce que tu dois faire à l'Atelier 8 (slide 34 et fiche étudiant, 1 h 15)

**Objectif :** vérifier le **cache-aside** d'une fiche catalogue (le **produit 42**, clé `shopflow:produit:v1:42`), sa **fraîcheur après modification**, et le **repli** quand Redis est indisponible. **L'API contient déjà le cache et l'invalidation** (`produits.mjs`) : ton travail est de **prouver leur comportement** avec les valeurs, le comptage SQL, les durées et les traces.

| Étape | Ce qu'on fait | Résultat attendu |
|---|---|---|
| **1 Préparation** | `CACHE_TTL_SECONDS=60` dans `.env`, redémarrer l'API, noter le **prix initial** | TTL affiché = 60 |
| **2 Miss et hit** | vider la clé, 2 lectures de suite ; puis **5 paires** miss/hit | **miss = 1 SELECT**, **hit = 0 SQL**, même contenu |
| **3 UPDATE direct en SQL** | modifier le prix **directement dans PostgreSQL**, relire | l'API renvoie **l'ancien prix** (hit, 0 SQL) : la copie est **périmée** ; après un `DEL` → nouveau prix (miss) |
| **4 PATCH par l'API** | modifier le prix **via l'API** | réponse `invalidation=ok` ; 1er GET = nouveau prix (miss) ; 2e GET = hit |
| **5 Expiration et panne** | attendre 61 s ; puis **arrêter Redis** | miss après expiration (TTL = -2) ; Redis arrêté : l'API répond quand même (`Cache=indisponible`, 1 SELECT) |
| **6 Restauration et dossier** | remettre le **prix initial** (via le CSV si besoin), redémarrer Redis | « Prix restauré », `invalidation=ok` |

**Les points à comprendre derrière chaque étape :**
- **Étape 2** : un **hit évite le SELECT**. Une clé absente ne veut pas dire que le produit n'existe pas.
- **Étape 3** : c'est **la preuve que le cache peut mentir** : une écriture qui **ne passe pas par l'API** ne supprime pas la copie. Le **TTL ne l'actualise pas immédiatement**. Il faut **déclarer la fraîcheur tolérée** pour le catalogue (de quelques secondes à une minute) et rappeler que **la validation d'un achat exige un contrôle dans la source**.
- **Étape 4** : l'API fait l'`UPDATE` **puis** le `DEL`. `invalidation=echouee` voudrait dire que **le prix est enregistré mais que la copie reste ancienne** : une erreur d'invalidation ne prouve **pas** que l'écriture a été annulée.
- **Étape 5** : le **repli** protège la disponibilité mais **augmente les lectures PostgreSQL** : **risque sous forte charge** (slide 32).

**À rendre (dossier `Atelier08_Nom`) :** le **pattern et la clé justifiés**, le prix initial, le CSV, les valeurs avant/après, les sorties SQL et les traces liées par TraceId ; les durées **expliquées en distinguant hit, miss et panne**.

**Une analyse écrite à ajouter (sans simulation) : la course de reconstruction** (slide 30). Décrire : A lit un ancien prix sur un miss ; B valide un nouveau prix ; B supprime la clé ; A remet l'ancien prix dans Redis. Expliquer **pourquoi `DEL` après l'écriture ne supprime pas ce risque** et **proposer une piste** (version, protocole de chargement, invalidation rejouée).

**Critères de réussite :** miss à 1 SELECT, hit à 0 SQL ; copie ancienne **prouvée** après un UPDATE direct ; nouvelle valeur après invalidation ; expiration et repli **testés** ; **prix initial restauré** ; fraîcheur acceptée **déclarée**.

**Attention comme à l'Atelier 7 :** l'atelier **modifie temporairement le prix du produit 42** dans la vraie base. Il faut **restaurer le prix initial** (et vérifier), puis **remettre le TTL de départ** dans `.env` si demandé.
