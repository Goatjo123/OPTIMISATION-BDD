# Atelier 8 de A à Z : le cache Redis, à quoi ça sert, et ce qu'il peut faire mentir

Ce guide suit la même idée que celui de l'Atelier 7 : pour chaque partie, **le problème** (une image), **ce que j'ai fait**, **ce que j'ai obtenu**, **ce que ça prouve**. Tous les chiffres viennent de `atelier8/resultats/` (exécutions du 08/10/2026).

---

## 0. L'atelier en une minute

**L'idée :** la fiche d'un produit est lue **très souvent** et change **rarement**. Chaque lecture oblige l'API à interroger PostgreSQL. Un **cache** garde une **copie** de la fiche dans une mémoire très rapide (**Redis**), pour **éviter de refaire le travail**.

**L'image :** tu cherches souvent le numéro de téléphone d'un ami. Plutôt que d'ouvrir l'annuaire (PostgreSQL) à chaque fois, tu le **notes sur un post-it** (Redis). C'est plus rapide. **Mais** si ton ami change de numéro, **ton post-it devient faux** tant que tu ne le jettes pas. Tout l'atelier tourne autour de cette question : **comment garder le post-it correct ?**

| Ce qu'on prouve | Résultat |
|---|---|
| Le cache évite le SQL | 1ʳᵉ lecture (**miss**) : **1 SELECT** ; lectures suivantes (**hit**) : **0 SQL** |
| Il va plus vite | 2,7 ms → **0,99 ms** (×2,7), un gain **petit** sur ma machine |
| **Il peut mentir** | après une modification **directement dans la base**, l'API continue de servir **57,50 alors que la base dit 19,90** |
| Le chemin prévu invalide la copie | modification **via l'API** : la copie est supprimée, la lecture suivante est juste |
| Si Redis tombe | l'API **répond quand même** (elle relit PostgreSQL), mais **chaque lecture redevient un SELECT** |

**À retenir :** un cache est une optimisation qui **peut changer ce que voit l'utilisateur**. Il faut mesurer le gain, **dire combien de temps une copie peut être périmée**, et **ne jamais s'y fier pour ce qui engage** (acheter, vérifier le stock).

---

## 1. Les mots à connaître (en une phrase chacun)

| Mot | Ce que ça veut dire |
|---|---|
| **Cache** | une copie d'un résultat, gardée pour ne pas refaire le calcul |
| **Redis** | le programme qui garde ces copies en mémoire (très rapide) |
| **Source de vérité** | la vraie donnée, celle qui fait foi : ici **PostgreSQL** |
| **Clé** | l'étiquette de la copie. Ici `shopflow:produit:v1:42` = « la fiche du produit 42, format v1 » |
| **Hit** | la copie est dans Redis → on la renvoie, **sans toucher PostgreSQL** |
| **Miss** | la copie n'est pas dans Redis → on lit PostgreSQL et on **range une copie** |
| **TTL** | la durée de vie de la copie (ici **60 secondes**), après quoi elle disparaît |
| **Cache-aside** | c'est **l'application** qui gère le cache : elle regarde Redis, sinon elle lit PostgreSQL et range une copie |
| **Invalidation** | supprimer la copie quand la donnée change, pour que la lecture suivante recharge la bonne valeur |
| **Fraîcheur** | à quel point la copie est à jour. « Fraîcheur acceptée de 60 s » = on tolère une copie vieille de 60 s au plus |

---

## 2. Comment le cache fonctionne ici (le code de `produits.mjs`)

**Lire une fiche (cache-aside) :**
1. L'API demande la clé à **Redis**.
2. **Hit** → elle renvoie la copie. **0 requête SQL.**
3. **Miss** → elle fait **1 SELECT** sur PostgreSQL, **range une copie dans Redis avec un TTL de 60 s**, puis répond.

**Modifier un prix (PATCH) :**
1. L'API fait l'**UPDATE** dans PostgreSQL.
2. **Puis** elle **supprime** la clé dans Redis (l'invalidation).
3. La prochaine lecture sera un miss et rechargera le bon prix.

Pourquoi ce choix pour une **fiche catalogue** : elle est publique, a une clé simple, et **un prix un peu en retard n'est pas grave**. Ce ne serait pas adapté à la **confirmation de stock** (elle doit être exacte : elle se contrôle dans PostgreSQL, dans la transaction de l'achat).

---

## 3. Ce que j'ai fait, étape par étape

Le script `atelier8/run_atelier8.py` rejoue la **fiche du cours** sur le **produit 42**, avec les outils du kit. À chaque étape, il **vérifie le résultat attendu** (et s'arrête s'il y a un écart). Le prix de départ est **57,50**.

### Étape 1 : préparation
J'ai mis le TTL à **60 secondes** et vérifié qu'il est bien pris en compte : après le chargement, Redis donne un TTL de **60** (et non 5, qui était la valeur du fichier `.env`).

> Un détail : la fiche dit de modifier `.env`. J'ai préféré **passer le TTL par une variable d'environnement** au démarrage de l'API : même résultat, et **ton `.env` reste intact** (je l'ai vérifié par une empreinte avant et après).

### Étape 2 : miss et hit
Je vide la clé, puis je lis deux fois de suite.

| Lecture | Cache | Requêtes SQL |
|---|---|---|
| 1ʳᵉ (après avoir vidé la clé) | **miss** | **1 SELECT** |
| 2ᵉ | **hit** | **0** |

Les **données renvoyées sont identiques** (c'est la règle de base : un cache ne doit pas changer le résultat). J'ai répété **5 paires** : à chaque fois, miss = 1 SELECT, hit = 0.
Le TTL de la clé juste après : 60 s (on voit qu'elle expire bien).

### Étape 3 : modifier la base **directement** en SQL (la démonstration la plus importante)
1. Je charge la copie (prix **57,50**).
2. Je fais un `UPDATE` du prix à **19,90** **directement dans PostgreSQL** (sans passer par l'API).
3. Je relis la fiche **par l'API**.

**Résultat : l'API renvoie encore 57,50** (`hit`, 0 SQL), alors que PostgreSQL contient **19,90**.

C'est **le post-it périmé** : l'UPDATE direct **n'est pas passé par le code de l'API**, donc personne n'a supprimé la copie. Le TTL ne la rafraîchit pas tout de suite : il attend 60 secondes.

4. Je supprime la clé à la main (`DEL`) et je relis : l'API renvoie **19,90** (miss, 1 SELECT).

> **Ce que ça prouve :** le TTL **ne met pas la copie à jour après une écriture**, il **limite seulement la durée** pendant laquelle une copie périmée peut être servie.

### Étape 4 : modifier **par l'API** (le chemin prévu)
`PATCH /produits/42` avec `{"prix":"29.90"}`.

| Appel | Résultat |
|---|---|
| PATCH | prix 29,90, **`invalidation = ok`**, 1 UPDATE |
| 1ᵉʳ GET après | **29,90**, miss, 1 SELECT |
| 2ᵉ GET | **29,90**, hit, 0 SQL |

Ici l'API a **elle-même supprimé la copie** après l'UPDATE : pas de prix périmé. Voilà pourquoi les écritures doivent passer par le chemin qui invalide.

### Étape 5 : l'expiration et la panne de Redis
**Expiration :** je charge la clé, je lis son TTL (**60**), j'attends **61 secondes**, je relis le TTL : **−2** (= la clé n'existe plus). La lecture suivante est un **miss avec 1 SELECT**, prix 29,90.

**Panne :** j'**arrête Redis**. Puis je lis la fiche.
- Résultat : **réponse normale (200)**, prix 29,90, mais `Cache = indisponible` et **1 SELECT**.
- L'API **continue de fonctionner** : elle se replie sur PostgreSQL. Une panne de cache ne doit pas rendre le site indisponible.

### Étape 6 : tout remettre
Je remets le **prix initial (57,50)** via l'API, je vérifie (« Prix restauré »), `invalidation = ok`. À la fin, la table des produits est **exactement** celle d'avant (empreinte identique).

---

## 4. Ce que j'ai ajouté (hors fiche, signalé comme tel)

### 4.1. Mesurer le vrai gain du cache (et pourquoi le premier outil ne le voit pas)
Avec l'outil du kit, la durée vue est **43,0 ms (miss)** contre **42,0 ms (hit)** : **presque aucune différence**. Pourquoi ? Cet outil lance **un nouveau processus Node pour chaque appel**, ce qui coûte environ **40 ms** à chaque fois et **noie** la différence.

J'ai donc refait la mesure avec **une connexion persistante** (100 paires) :

| Mesure | Miss | Hit | Rapport |
|---|---|---|---|
| Durée de la requête | 2,709 ms | **0,988 ms** | **×2,7** |
| Temps dans l'API | 2,08 ms | 0,671 ms | ×3,1 |
| Temps SQL | 0,768 ms | 0 | — |

**Le gain existe mais il est petit** (≈ 1,7 ms) parce que la base est **sur ma machine** et que la requête est un simple accès par clé primaire. Pour une requête **coûteuse** ou une base **distante**, il serait plus grand (**je ne l'ai pas mesuré**). **Le vrai gain, c'est la charge évitée sur PostgreSQL : un hit ne fait aucune lecture SQL.**

### 4.2. Quand l'invalidation échoue
Je charge la copie (29,90), j'**arrête Redis**, puis je fais un `PATCH` à **34,90**.
- Réponse de l'API : **`invalidation = echouee`**. L'UPDATE a réussi (**PostgreSQL = 34,90**), mais l'API n'a pas pu supprimer la copie.
- Je redémarre Redis et je relis : **l'API sert encore 29,90** (hit).

> **Ce que ça prouve :** une erreur d'invalidation **ne signifie pas que l'écriture a été annulée**. Le prix **est** enregistré ; c'est la copie qui reste ancienne (jusqu'à l'expiration).
>
> *(La copie a survécu au redémarrage parce que Redis sauvegarde son contenu quand on l'arrête. Sans cela, elle aurait disparu et on n'aurait rien observé.)*

### 4.3. La course entre une lecture et une invalidation (slide 30)
C'est l'**analyse écrite** que demande la fiche. Je l'ai **reproduite à la main**, pour la voir pour de vrai :

| Instant | A (lecture lente) | B (écriture) |
|---|---|---|
| t1 | A lit l'ancien prix **34,90** dans PostgreSQL | |
| t2 | | B met le prix à **39,90** dans PostgreSQL |
| t3 | | B **supprime** la clé Redis |
| t4 | A **range sa copie ancienne** (34,90) dans Redis | |

**Résultat :** l'API sert **34,90** (hit) alors que PostgreSQL contient **39,90**.

**Pourquoi le `DEL` de B ne suffit pas :** il a eu lieu **avant** que A range sa copie, donc il ne pouvait pas l'annuler. A, plus lent, a **remis une ancienne valeur après coup**.

**Pistes de traitement :**
1. une **version** (numéro ou date de modification) stockée avec la copie : A n'écrit dans Redis **que si sa version est au moins aussi récente** ;
2. une **invalidation rejouée** après un court délai (ou via une *outbox*) : on supprime à nouveau, ce qui élimine une copie remise en retard ;
3. un **TTL court** si la fraîcheur exigée est forte.

### 4.4. La rafale (cache stampede, slide 31)
Quand **beaucoup de requêtes trouvent la même clé absente en même temps**, chacune **recharge** depuis PostgreSQL. J'ai lancé **20 lectures simultanées** sur une clé absente : **6 miss et 6 SELECT** au total (au lieu d'un seul). Avec la clé **présente**, les 20 lectures ont été des hit (**0 SQL**). *(Le nombre exact de miss varie d'une exécution à l'autre : ce qui compte, c'est que **plusieurs** requêtes rechargent la même chose.)* Pour l'éviter : un seul chargement par clé, ou un TTL avec une petite variation aléatoire.

---

## 5. La panne de Redis : le « repli » et son danger

Quand Redis tombe, l'API **relit PostgreSQL** : c'est ce qui la garde en vie. **Mais** :
- avec Redis, **la plupart des lectures** étaient des hit (**0 SQL**) ;
- sans Redis, **chaque lecture devient un SELECT** : j'ai mesuré **30 appels = 30 SELECT** (contre 0 avec le cache).

**Le danger (slide 32) :** sous **forte charge**, ce reflux de lectures peut **surcharger PostgreSQL** : la panne du cache provoque alors une **seconde panne**. On s'en protège par des limites de concurrence, des priorités et un *circuit breaker* (couper temporairement les tentatives quand ça va mal).

Et une règle : **une absence de valeur ou une erreur de cache ne veut pas dire que le produit n'existe pas** (on retourne lire la source).

---

## 6. La fraîcheur : combien de temps une copie périmée est acceptable

C'est la question que la fiche demande de **déclarer**.

- **Catalogue (fiche produit) :** une copie périmée de **quelques secondes à une minute** est **acceptable** (TTL de 60 s). Un prix affiché avec un retard court n'est pas grave.
- **Achat / stock :** **pas de cache.** Le prix et le stock sont **contrôlés dans PostgreSQL, dans la transaction de l'achat.** Un client ne doit jamais acheter à un prix périmé ni dépasser le stock.

---

## 7. À retenir (le tableau final)

| # | À retenir | Preuve |
|---|---|---|
| 1 | **Hit = 0 SQL, miss = 1 SELECT** puis une copie avec TTL | miss 1 SELECT, hit 0, 5 paires + 100 paires |
| 2 | Le gain de durée est **petit en local** ; le vrai gain est la **charge évitée sur la base** | 2,7 → 0,99 ms ; l'outil du kit ne le voit pas |
| 3 | **Un cache peut mentir** | l'API sert 57,50 alors que la base a 19,90 |
| 4 | Le **TTL n'actualise pas** la copie après une écriture, il borne sa durée | UPDATE direct : copie ancienne jusqu'au `DEL` |
| 5 | **Invalider = supprimer la clé après l'écriture** | PATCH : `invalidation = ok`, GET suivant correct |
| 6 | Une **invalidation échouée n'annule pas l'écriture** | `echouee` : PostgreSQL = 34,90, copie = 29,90 |
| 7 | **Redis en panne ≠ produit absent** : l'API se replie sur PostgreSQL, au prix de plus de SQL | 30 appels = 30 SELECT |
| 8 | **Supprimer la clé ne règle pas toutes les courses** | course reproduite : l'API sert l'ancien prix |
| 9 | Une clé absente peut déclencher **plusieurs rechargements simultanés** | 20 lectures : 6 miss, 6 SELECT |
| 10 | **Déclarer la fraîcheur** et **ne pas cacher ce qui engage** (achat, stock) | catalogue : ≤ 60 s ; achat : contrôle dans la source |

---

## 8. Les limites (à dire)

- **Un seul produit**, base et Redis **locaux**, un seul processus API, TTL de 60 s.
- Le gain de durée est **petit** et n'est mesuré que sur cette configuration (accès par clé primaire, base locale) ; **je n'ai pas mesuré** le cas d'une requête lourde ou d'un réseau réel.
- La **course est reproduite à la main**, pas sous charge réelle ; la **rafale** est **une mesure** dont le nombre exact varie.
- L'échec d'invalidation n'est observable que parce que **Redis a gardé la copie à son redémarrage** (sa sauvegarde à l'arrêt).
- L'outil de mesure du kit **noie** les petites différences : c'est pour cela que j'ai ajouté une mesure sur connexion persistante.

---

## 9. Comment l'expliquer en deux minutes

> « L'atelier 8 vérifie un cache Redis sur la fiche d'un produit. Le principe est le cache-aside : l'API regarde Redis ; si la copie est là, c'est un hit et **aucune requête SQL** ; sinon c'est un miss, elle lit PostgreSQL, range une copie avec une durée de vie de 60 secondes, et répond. J'ai prouvé que le miss fait **un SELECT** et le hit **zéro**, avec les mêmes données. Mesuré proprement, la requête passe de **2,7 à 0,99 milliseconde** : le gain est petit sur ma machine, le vrai bénéfice est la charge évitée sur la base. **Le point important, c'est qu'un cache peut mentir** : quand j'ai modifié le prix **directement dans PostgreSQL**, l'API a continué de servir **57,50** alors que la base disait **19,90**. Modifié par l'API, le prix est juste, parce qu'elle supprime la copie. J'ai aussi vu que si l'invalidation échoue, le prix est enregistré mais la copie reste ancienne, que si Redis tombe l'API répond quand même mais fait un SELECT à chaque lecture, et que supprimer la clé ne règle pas la course entre une lecture lente et une écriture. Donc je déclare la fraîcheur acceptée pour le catalogue, une minute, et je ne mets **aucun cache sur l'achat** : le prix et le stock se contrôlent dans la base. »

---

## 10. Questions qu'on peut te poser

**Pourquoi un hit évite-t-il le SELECT ?** L'API trouve la copie dans Redis et la renvoie sans interroger PostgreSQL.

**Un TTL garantit-il la fraîcheur après une écriture ?** Non : il **limite la durée** d'une copie périmée, il ne la met pas à jour. Après mon UPDATE direct, la copie est restée ancienne.

**Pourquoi supprimer la clé après l'écriture plutôt qu'avant ?** On supprime **après** que l'écriture est validée : si on supprimait avant, une lecture pourrait recharger l'ancienne valeur entre les deux. (Et même après, il reste la course.)

**Si l'invalidation échoue, l'écriture est-elle annulée ?** Non : PostgreSQL a déjà enregistré le prix ; seule la copie reste ancienne.

**Pourquoi une panne de Redis peut-elle saturer PostgreSQL ?** Parce que toutes les lectures qui étaient des hit deviennent des SELECT : la charge de la base remonte brutalement.

**Pourquoi ne cache-t-on pas la confirmation de stock ?** Parce qu'elle doit être exacte : elle se contrôle dans PostgreSQL, dans la transaction.

**Redis GET suffit-il à faire du read-through ?** Non : il ne lit pas PostgreSQL ; il faut un composant qui charge la donnée quand elle manque.

---

## 11. Fichiers produits et comment rejouer

| Fichier | Contenu |
|---|---|
| `atelier8/run_atelier8.py` | rejoue la fiche avec l'aide du kit, vérifie chaque résultat, fait les ajouts, restaure le prix, contrôle le laboratoire |
| `atelier8/mesure_persistante.py` | miss contre hit sur connexion persistante (100 paires) |
| `atelier8/stampede.mjs` | 20 lectures simultanées |
| `atelier8/resultats/` | toutes les mesures, le journal de l'API, les traces par identifiant |
| `Atelier1_Diagnostic_compact.pdf` | section **Atelier 8 (pages 22 à 24)** et **annexe 10 (pages 57 à 59)** |
| `Optimisations.pdf` | **page 11** : « de la lecture SQL au cache Redis » (avec son coût de fraîcheur) |

**Rejouer :** `python3 atelier8/run_atelier8.py` (environ 3 minutes ; il **arrête puis redémarre** le conteneur Redis), puis `python3 atelier8/mesure_persistante.py` (environ 1 minute).

**État final :** prix du produit 42 **restauré à 57,50**, table des produits **identique** à l'état initial, Redis **démarré**, clé supprimée, API arrêtée, `.env` **inchangé**, laboratoire ShopFlow identique à son état initial.
