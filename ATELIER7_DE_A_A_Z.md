# Atelier 7 de A à Z : ce que j'ai fait, et surtout à quoi ça sert

Ce guide est fait pour que tu **comprennes l'intérêt** de l'atelier, pas seulement les chiffres. Chaque partie suit le même schéma : **le problème** (une image de la vie courante), **ce que j'ai fait**, **ce que j'ai obtenu**, **ce que ça prouve**. Tous les chiffres viennent de `atelier7/resultats/` (exécutions du 07/10/2026).

---

## 0. L'atelier en une minute

Une API (le programme qui répond quand une appli demande « donne-moi mes commandes ») peut être lente pour **trois raisons différentes**, et l'atelier en traite trois :

| Problème | Image | Correction | Résultat mesuré |
|---|---|---|---|
| **N+1** : trop de petites requêtes | aller au magasin **20 fois** pour 20 courses, au lieu d'y aller une fois avec la liste | charger toutes les lignes d'un coup | **21 requêtes → 2**, même réponse |
| **OFFSET** : on relit tout ce qu'on saute | pour ouvrir un livre à la page 500, **tourner les 499 pages** une à une au lieu de poser un marque-page | **curseur** (un marque-page : « je me suis arrêté à telle commande ») | à 1 000 000 de commandes : **944 ms → 0,18 ms**, même page |
| **Trop de connexions** à la base | 40 clients qui veulent chacun **leur propre caisse** | **PgBouncer** : 5 caisses partagées | connexions **40 → 5**, mais **pas plus rapide** |

Le point le plus important à retenir : **ces trois problèmes sont différents, donc on les corrige séparément**, et **un gain ne se prouve pas par une théorie, il se mesure** (on va voir que la dernière correction n'accélère rien).

---

## 1. Les outils (ce qu'il y avait déjà, et ce que j'ai ajouté)

**Fournis par le cours (kit Jour 4) :**
- l'**API ShopFlow** (`01_server/api`), déjà écrite : elle sait paginer par OFFSET ou par curseur, charger les lignes en mode « N+1 » ou « groupé » ;
- une **aide de mesure** (`jour4_http.mjs`, la fonction `sf`) : elle appelle l'API, note la durée, le **nombre de requêtes SQL** (l'API l'écrit dans l'en-tête `X-SQL-Count`) et un identifiant de trace ;
- deux **scripts SQL** pour l'étape des dates identiques ;
- un **laboratoire PgBouncer** séparé (Docker) avec un outil de charge (`pgbench`).

**Ce que j'ai écrit :**
- `atelier7/run_partie_a.py` : rejoue **toute la fiche** de la partie A (il utilise les outils du kit, il ne les remplace pas) et **vérifie chaque résultat attendu** : s'il y a un écart, il s'arrête ;
- `atelier7/bench_offset_curseur.py` : la mesure « OFFSET contre curseur » sur beaucoup de données (j'explique pourquoi plus loin) ;
- les documents (PDF, résumé, ce guide).

**Une règle du cours que j'ai respectée partout :** *les durées doivent venir de mes appels* et *une baisse du nombre de requêtes ne prouve pas à elle seule un gain de temps.* Donc je mesure les deux séparément.

---

## 2. Partie A, étape 1 : démarrer et vérifier le point de départ

**Ce que j'ai fait :** démarrer l'API, puis vérifier que le client 42 a bien **100 commandes** (5 pages de 20) et que chaque commande a **3 lignes**.

**Pourquoi :** toutes les comparaisons qui suivent supposent le même point de départ. Si le jeu de données est différent, on ne peut plus comparer.

**Résultat :** 100 commandes, 3 lignes chacune. ✔

---

## 3. Étape 2 : le problème N+1 (aller au magasin 20 fois)

### Le problème, en image
Tu veux afficher 20 commandes **avec leurs lignes** (les produits de chaque commande).
- **Méthode N+1 :** une requête pour la liste des 20 commandes, **puis une requête par commande** pour ses lignes → 1 + 20 = **21 requêtes**.
- **Méthode groupée :** une requête pour les 20 commandes, **puis une seule requête** pour *toutes* leurs lignes → **2 requêtes**.

La seconde a fait la même chose avec bien moins d'allers-retours vers la base.

### Où c'est dans le code (`commandes.mjs`)
```js
// N+1 : une requête par commande
for (const row of rows) row.lignes = (await query(lineSql + ' WHERE commande_id=$1 ...', [row.id])).rows;

// Groupé : une seule requête pour tous les ids de la page
const lines = (await query(lineSql + ' WHERE commande_id=ANY($1::bigint[]) ...', [rows.map(r => r.id)])).rows;
```
`ANY($1::bigint[])` veut dire : « l'identifiant est l'un de ceux de cette liste ». Ensuite le code **range les lignes dans leur commande, en mémoire**.

### Ce que j'ai mesuré
| Taille de page | Requêtes (N+1) | Requêtes (groupé) |
|---|---|---|
| 5 commandes | 6 | 2 |
| 20 | 21 | 2 |
| 50 | 51 | 2 |
| 100 | 101 | 2 |
| page vide | 1 | 1 |

**Même réponse ?** Oui : j'ai comparé le résultat JSON **complet** (commandes et lignes, champ par champ) à chaque taille de page : identique. C'est la règle de base de tout le cours : *on n'optimise pas si le résultat change.*

### Et le temps ? (30 tours alternés, après 5 échauffements)
| Page de | HttpMs N+1 | HttpMs groupé | sqlMs N+1 | sqlMs groupé |
|---|---|---|---|---|
| 20 | 55,3 ms | 43,9 ms | 14,2 ms | 2,2 ms |
| 50 | 68,5 ms | 44,2 ms | 29,0 ms | 2,6 ms |

- **HttpMs** = le temps vu par celui qui appelle l'API (il comprend l'appel HTTP lui-même). **sqlMs** = le temps passé seulement dans les requêtes SQL (lu dans le journal de l'API).
- Le gain existe mais est **modeste** (11 ms pour 20 commandes) parce que **la base est sur ma machine** : chaque aller-retour coûte presque rien. Sur un vrai réseau, chaque requête supprimée pèserait plus. **Je ne l'ai pas mesuré**, donc je le dis comme une attente, pas comme un fait.

### Ce que ça prouve
> Le N+1 se **reconnaît** au nombre de requêtes qui **grandit avec N** (6, 21, 51, 101). Le chargement groupé le **fixe à 2**, sans changer la réponse.

---

## 4. Étape 3 : OFFSET contre curseur

### Le problème, en image
Un **OFFSET** : « saute les 20 premières commandes et donne-moi les 20 suivantes ». C'est comme chercher la page 500 d'un livre **en tournant les 499 pages une à une**. Plus la page est loin, plus ça coûte.

Un **curseur** : un **marque-page**. Au lieu de « saute 20 », tu dis « donne-moi celles **après** la commande X ». PostgreSQL va **directement** à X grâce à l'index, sans relire ce qui est avant.

Concrètement, le curseur est la paire **(date, id)** de la dernière commande affichée :
```sql
WHERE client_id = 42 AND (created_at, id) < ($date, $id)
ORDER BY created_at DESC, id DESC
LIMIT 21
```

### L'astuce `LIMIT 21`
Pour une page de 20, on demande **21** lignes. Si la 21e existe, on sait qu'il y a **une page suivante** (`hasNextPage = vrai`) et on garde la 20e comme curseur ; sinon, c'est la dernière page. Pas besoin d'un `COUNT(*)` coûteux.

### Ce que j'ai fait et obtenu
- Page 2 par curseur **et** par OFFSET : **réponses identiques**, 2 requêtes chacune. ✔
- **Contrat de l'API** (ce que renvoie l'endpoint), vérifié : `data` / `hasNextPage` / `nextCursor` ; **20 lignes par défaut, 100 au maximum** (101 ou 0 → erreur 400) ; ordre `created_at DESC` puis `id DESC` (vérifié sur les 100 lignes) ; les `id` et les montants sont des chaînes ; les dates ont 6 chiffres de microsecondes.

### Pourquoi j'ai ajouté une mesure à grande échelle
La fiche du cours dit : *« Les 100 commandes du client permettent surtout de vérifier le contrat. Ne pas annoncer un gain sur de grands décalages à partir d'un OFFSET qui dépasse le nombre de résultats. »*

Autrement dit : avec **seulement 100 commandes**, on ne peut **rien conclure** sur la vitesse. Pour voir ce que change vraiment le curseur, j'ai construit une **table de travail jetable** de **1 000 000 de commandes** (un client, des dates en double, le même index que l'atelier 3) et j'ai comparé **la même page** à plusieurs profondeurs. Le laboratoire ShopFlow n'est pas touché.

| Décalage (page de 20) | OFFSET | pages lues | Curseur | pages lues |
|---|---|---|---|---|
| 0 | 0,171 ms | 24 | 0,154 ms | 24 |
| 20 | 0,180 ms | 44 | 0,177 ms | 24 |
| 1 000 | 1,2 ms | 1 029 | 0,174 ms | 25 |
| 20 000 | 21,8 ms | 20 122 | 0,167 ms | 24 |
| 100 000 | 99,7 ms | 100 516 | 0,168 ms | 24 |
| 500 000 | 466 ms | 502 487 | 0,195 ms | 24 |
| 900 000 | 832 ms | 904 457 | 0,164 ms | 24 |
| 999 000 | **944 ms** | **1 003 945** | **0,177 ms** | **24** |

**Lecture :**
- **Même page à chaque profondeur** (je compare une empreinte md5 des deux résultats).
- **OFFSET lit environ une page par ligne sautée** : 1 million de lignes sautées → environ 1 million de pages lues. Le curseur en lit **24, toujours**.
- **À petite profondeur, aucune différence** (0,17 ms des deux côtés). Le curseur n'apporte quelque chose que **quand le décalage est grand**.

### Ce que ça prouve
> Le curseur change **l'ordre de grandeur** quand on pagine loin ; quand on reste près du début, OFFSET reste correct (et plus simple). Et le curseur n'est adapté qu'à « suivant », **pas** à « aller directement à la page 37 ».

---

## 5. Étape 4 : les dates identiques (pourquoi le curseur a deux valeurs)

### Le problème, en image
Imagine deux marque-pages qui disent la même chose : « arrêté le 13 septembre à 23 h 54 ». Si trois commandes ont **exactement la même date**, un marque-page « date » seul **ne sait pas laquelle des trois** tu viens de lire.

### Ce que j'ai fait
Le kit fournit un script qui donne **la même date** aux commandes **2042, 1042 et 42** du client 42 (après avoir sauvegardé leurs vraies dates). Puis j'ai pris des pages de **2** commandes, de façon que l'égalité **tombe juste à la frontière** entre deux pages :
- page 1 : **2042, 1042**
- page 2 : **42**, puis une autre commande (86042)

**Les trois commandes apparaissent une seule fois.** ✔

### La démonstration du défaut
Si la page suivante utilisait **seulement la date** (`created_at < date`), elle renverrait `86042, 83042` : **la commande 42 est perdue**. Avec la **paire** `(created_at, id) < (date, 1042)`, elle renvoie `42, 86042` : **42 est bien là**.

### Ce que ça prouve
> Le curseur contient **la date ET l'id** : l'id départage les commandes qui ont la même date. Sans lui, on perd des lignes entre deux pages (je l'ai montré avec les vraies données).

---

## 6. Étape 5 : parcours complet, droits et remise en état

### Parcours
J'ai parcouru les **5 pages de 20** (alors que les dates identiques étaient en place) : **100 commandes, 100 uniques, dans le même ordre que PostgreSQL**. Aucune perdue, aucune en double. ✔
(Attention : un curseur **n'est pas un instantané** : si des commandes bougeaient entre deux appels, une page pourrait en sauter une. Ici, rien ne bouge.)

### Les droits (la sécurité)
| Test | Résultat attendu | Obtenu |
|---|---|---|
| Appel **sans jeton** | 401 (non autorisé) | **401** |
| `client_id=43` mis **dans l'URL** | 400 (refusé) | **400** |
| Curseur **falsifié** (ajout) | 400 | **400** |

**Pourquoi c'est important :** un curseur est **signé** (une signature cryptographique l'accompagne), donc on ne peut pas le modifier. Mais **ça ne remplace pas le contrôle d'accès** : le serveur détermine le client **lui-même** à partir de son contexte (le fichier `.env` : `LAB_CLIENT_ID=42`), **jamais** à partir de l'URL. Sinon n'importe qui pourrait demander les commandes d'un autre.

### Remettre les dates comme avant
J'ai exécuté le script de restauration : **3 dates restaurées**, puis j'ai vérifié par une **empreinte** que **toutes les dates de la table** sont **exactement** celles d'avant, et j'ai supprimé la table de sauvegarde créée par le script. Le laboratoire est identique à son état initial. ✔

---

## 7. Partie B : PgBouncer (le pool de connexions)

### Le problème, en image
Chaque connexion à PostgreSQL **coûte des ressources**. Si 40 clients se connectent, PostgreSQL ouvre 40 sessions. Avec 10 instances de l'API qui ont chacune un petit pool de 5, on peut vite arriver à 50, et PostgreSQL a une **limite** (ici 60).

**PgBouncer** se place entre l'API et PostgreSQL. Image : **un supermarché avec 5 caisses pour 40 clients**. Les clients **font la queue** et chaque caisse sert les clients à tour de rôle. Au lieu d'ouvrir 40 sessions, PostgreSQL n'en voit que 5.

**Mode transaction :** la caisse n'est « prêtée » à un client que **le temps de sa transaction** (de `BEGIN` à `COMMIT`). Entre deux transactions, elle sert quelqu'un d'autre.

### Ce que j'ai fait
Le cours fournit un laboratoire à part (base « pooling » de 1 000 produits, PostgreSQL 17.11, PgBouncer 1.18.0 avec **5 connexions serveur**, max 60 connexions PostgreSQL) et un test : chaque client fait une transaction qui **attend 50 ms** (pour simuler un traitement), puis **réfléchit 100 ms**. J'ai lancé les trois campagnes de la fiche (chacune avec **trois essais**, ordre alterné, échauffement à part).

### Résultat 1 : 40 clients connectés en permanence
| | Direct | Via PgBouncer |
|---|---|---|
| Connexions PostgreSQL (pic mesuré) | **40** | **5** |
| Transactions par seconde (médiane de 3) | 260,7 | **93,8** |
| Latence moyenne | 153 ms | **422 ms** |

**PgBouncer a bien limité les connexions (40 → 5), mais c'est plus lent !** Ce n'est pas une anomalie, ça se calcule :
- chaque transaction occupe une caisse **50 ms** ; 5 caisses → au plus 5 ÷ 0,05 s = **100 transactions par seconde** (mesuré : ≈ 94) ;
- 40 clients qui attendent leur tour → chacun attend environ 40 ÷ 94 ≈ **0,43 s** (mesuré : 422 ms).

Dans PgBouncer (`SHOW POOLS`), on voit les **clients qui attendent** : `cl_waiting` vaut **25 à 29** pendant la charge, avec `sv_active = 5` (jamais plus de 5 caisses ouvertes).

### Résultat 2 : 80 clients (au-delà de la limite de PostgreSQL)
- **En direct :** **refus**. PostgreSQL répond « *remaining connection slots are reserved…* » (plus de place) et l'essai s'arrête en 2,9 secondes. **Ses débits ne sont donc pas mesurables** (et pas « zéro »).
- **Avec PgBouncer :** **tous les clients sont servis**, avec de l'attente (`cl_waiting` de **66 à 69**, **5** connexions serveur), 90,7 transactions par seconde, latence 860 ms.

**Ce que ça montre :** PgBouncer **transforme un refus en attente**. Il ne crée pas de capacité, il organise la file.

### Résultat 3 : reconnexion à chaque transaction (option `-C`)
Je l'ai lancé **deux fois** parce que la première campagne était **bizarre** (le débit baissait d'un essai à l'autre, des deux côtés) :

| | Direct (médiane) | PgBouncer (médiane) |
|---|---|---|
| Campagne 1 | 22,6 transactions/s | 29,7 |
| Campagne 2 | 36,5 | 33,1 |

**L'ordre s'est inversé d'une campagne à l'autre** : on ne peut **pas conclure** que l'un est plus rapide. C'est un résultat honnête : *« test instable, aucune conclusion »*, plutôt que de choisir la campagne qui arrange.

### Ce que ça prouve
> PgBouncer **encadre les connexions** : moins de sessions, des refus remplacés par de l'attente. Il **ne rend pas une requête plus rapide** et il **ne corrige ni le N+1 ni les index**. Moins de connexions ne veut pas dire moins de latence.

---

## 8. Ce que j'ai dû corriger en route (à connaître)

1. **Un piège que j'avais déjà rencontré** (atelier 3) : dans ma mesure OFFSET/curseur, j'ai nommé les colonnes de sortie `id` et `created_at` (en texte, comme l'API). Le `ORDER BY created_at` s'est alors mis à trier sur **le texte** au lieu de la vraie colonne, l'index est devenu inutile, et PostgreSQL a lu toute la table (3 secondes !). **Il faut écrire `ORDER BY commandes.created_at`**, ce que fait l'API. Je l'ai corrigé et j'ai refait la mesure : tous les chiffres de ce guide viennent de la version corrigée.
2. **Une première version de la mesure ne lisait que `id` et `created_at`** : l'index suffisait à tout fournir et ça **sous-estimait** le coût d'OFFSET. L'API lit aussi `statut` et `total` : je les ai ajoutés pour que la mesure ressemble à la vraie requête.
3. **Un petit bug de langage** (Python 3.8 ne connaît pas l'opérateur `|` entre dictionnaires) : corrigé avant la vraie exécution.
4. **Le test des connexions répétées était instable** : je l'ai relancé et je le dis (voir plus haut).

---

## 9. Ce qu'il faut retenir (le tableau final)

| # | À retenir | Preuve dans l'atelier |
|---|---|---|
| 1 | **N+1** = 1 + N requêtes ; il se voit au nombre de requêtes qui **grandit avec N** | 6, 21, 51, 101 requêtes |
| 2 | Le **chargement groupé** ramène à **2** requêtes, **sans changer la réponse** | réponses identiques, 21 → 2 |
| 3 | Une baisse du **nombre de requêtes** n'est **pas** automatiquement un gain de **temps** : on mesure les deux | gain modeste en local (55,3 → 43,9 ms) |
| 4 | **OFFSET** relit ce qu'il saute : le coût **croît avec le décalage** | 944 ms au décalage 999 000 |
| 5 | Le **curseur** reste **constant**, mais **ne change rien à petite profondeur** et ne sert qu'à « suivant » | 0,17 ms partout ; pas de gain à 0 ou 20 |
| 6 | Le curseur contient **la date et l'id** (sinon on perd des lignes) | commande 42 perdue avec la date seule |
| 7 | Un curseur **signé** n'est **pas** une autorisation : le client vient du **contexte**, pas de l'URL | 401, 400, 400 |
| 8 | **PgBouncer limite les connexions** (40 → 5) mais **n'accélère pas** : il transforme un refus en attente | 261 → 94 transactions/s ; refus à 80 clients en direct |
| 9 | Un **test instable** se relance et se dit, il ne s'arrange pas | test `-C` : résultats inversés entre deux campagnes |

---

## 10. Les 5 questions de la fiche (réponses courtes)

1. **Quel accès supplémentaire N+1 fait-il ?** Une requête sur `lignes` **par commande** (la boucle `for (const row of rows)` du mode `n1` dans `commandes.mjs`).
2. **Pourquoi charger les lignes après les commandes ? Quel problème avec une jointure + `LIMIT` ?** On connaît d'abord les 20 commandes, puis on charge leurs lignes. Avec une jointure, le `LIMIT` compterait des **lignes de jointure** (3 par commande) : la page contiendrait environ 7 commandes au lieu de 20. *(Raisonnement du cours, non testé ici.)*
3. **Pourquoi date et id ?** Pour départager les commandes de même date. Avec la date seule, la commande **42** est perdue (mesuré : `86042, 83042` au lieu de `42, 86042`).
4. **Pourquoi un curseur signé ne remplace-t-il pas le contrôle d'accès ? D'où vient `client_id` ?** La signature empêche de **modifier** le curseur, pas de **demander les données d'un autre client**. Le `client_id` vient du **contexte autorisé** (`LAB_CLIENT_ID` dans `.env`), jamais de l'URL.
5. **Que montrent mes mesures ? Qu'est-ce qui demanderait un jeu plus gros ?** Gain modeste du groupé en local ; le gain du curseur n'apparaît qu'à grande profondeur (d'où ma table de 1 000 000) ; l'effet d'un réseau réel et d'une vraie charge ne sont pas mesurés.

**Partie B**
1. **`pg.Pool` contre PgBouncer ?** `pg.Pool` réutilise des connexions **à l'intérieur d'un processus** ; PgBouncer est un service **partagé** entre processus. Dix instances de l'API avec `POOL_MAX = 5` peuvent ouvrir **50** connexions (la limite est 60 dans le labo).
2. **Comment 80 clients sont-ils servis par 5 connexions ?** La connexion serveur n'est prêtée que **de `BEGIN` à `COMMIT`** ; pendant l'attente de 100 ms **hors transaction** (dans `charge.sql`), elle sert quelqu'un d'autre.
3. **Qu'est-ce qui prouve moins de connexions ? Une attente ? Un gain de temps ?** Le pic de sessions (40 → 5) prouve la baisse ; `cl_waiting` (25 à 69) prouve l'attente ; **rien de tout cela ne prouve un gain de temps** (le débit baisse).
4. **Pourquoi corriger encore N+1 et les index ? Quoi tester ensuite ?** Le pool n'accélère aucune requête. À tester : `default_pool_size`, en surveillant **`cl_waiting`** et **`maxwait`** pour ne pas déplacer le problème.

---

## 11. Les limites (à dire, ça montre que tu as compris)

- **Base locale** et **100 commandes** pour le client 42 : on valide le **contrat**, pas la vitesse à grande échelle.
- Les durées HTTP sont **bruitées** (30 tours) ; le gain du groupé est **modeste** ici.
- La mesure OFFSET/curseur est sur une **table de travail**, pas sur ShopFlow.
- PgBouncer : campagnes de **20 secondes** (une **démonstration**, pas une capacité de production) ; `pgbench` mesure un scénario avec des attentes artificielles, **pas** du temps HTTP de ShopFlow ; le **pic de connexions est échantillonné** (1 fois par seconde), pas exact ; le test `-C` est **instable**.
- Le curseur **n'est pas un instantané** : si des lignes bougent entre deux appels, une page peut en sauter une.

---

## 12. Comment l'expliquer en deux minutes

> « L'atelier 7 corrige trois problèmes différents d'une API. **Premier problème, le N+1** : pour afficher 20 commandes avec leurs lignes, l'API faisait 21 requêtes, une par commande. En chargeant toutes les lignes d'un coup, on tombe à **2 requêtes** avec exactement la même réponse. Sur ma machine le gain de temps est modeste, parce que la base est locale. **Deuxième problème, OFFSET** : pour aller loin dans une liste, il relit toutes les lignes sautées. Le **curseur** repart d'un repère, la paire date et id. À un million de commandes, la même page passe de **944 ms à 0,18 ms**, mais à petite profondeur il n'y a **aucune différence**. L'id est indispensable : avec la date seule, j'ai montré qu'une commande est perdue quand trois commandes ont la même date. **Troisième sujet, PgBouncer** : il limite les connexions à PostgreSQL, de 40 à 5, et il transforme un refus en attente quand on dépasse la limite. Mais il **n'accélère rien** : mon débit est passé de 261 à 94 transactions par seconde, ce qui se calcule avec 5 connexions de 50 ms. Je n'ai conclu sur aucun gain que je n'avais pas mesuré. »

---

## 13. Fichiers produits et comment rejouer

| Fichier | Contenu |
|---|---|
| `atelier7/run_partie_a.py` | rejoue la partie A de la fiche, vérifie chaque résultat, restaure les dates, contrôle le laboratoire |
| `atelier7/bench_offset_curseur.py` | mesure OFFSET contre curseur sur 1 000 000 de commandes (table jetable) |
| `atelier7/resultats/resultats_partie_a.json`, `mesures_partie_a.csv` | toutes les mesures de la partie A |
| `atelier7/resultats/api_journal.log`, `api_extraits_par_traceid.txt` | journal de l'API (une ligne par appel) et extraits rattachés par identifiant de trace |
| `atelier7/resultats/offset_curseur_volume.json`, `plan_*.txt` | mesures à grande échelle et plans d'exécution |
| `atelier7/resultats/pgbouncer/` | les 4 campagnes (synthèse, sorties `pgbench`, connexions, `SHOW POOLS`, configuration) |
| `Atelier1_Diagnostic_compact.pdf` | section **Atelier 7 (pages 19 à 21)** et **annexe 9 (pages 53 à 56)** |
| `Optimisations.pdf` | **pages 9 et 10** (N+1 → groupé, OFFSET → curseur) et deux lignes du tableau d'ensemble ; PgBouncer dans « transformations écartées » |

**Rejouer la partie A :** `python3 atelier7/run_partie_a.py` (conteneurs `api-postgres-1` et `api-redis-1` démarrés ; environ 2 minutes). **Mesure à grande échelle :** `python3 atelier7/bench_offset_curseur.py` (environ 1 minute). **PgBouncer :** depuis `Kit_Jour4_Windows_Linux/02_Laboratoire/Jour4/PgBouncer`, `node pooling.mjs up`, puis `compare`, `saturation`, et `down` pour arrêter.

**État du laboratoire :** à la fin, ShopFlow est identique à son état initial (6 index, aucune statistique, mêmes tables, **mêmes dates**, vérifié par empreinte). Le laboratoire PgBouncer est arrêté ; son volume de données reste disponible (`node pooling.mjs reset --confirm` l'efface).
