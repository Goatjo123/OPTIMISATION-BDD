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
