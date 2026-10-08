# Atelier 8 : cache Redis et fraîcheur

Jour 4, slides 23 à 35 et fiche étudiant du kit (`Kit_Jour4_Windows_Linux/02_Laboratoire/Jour4/Atelier_08_Fiche_etudiant_Linux.pdf`). Vérifier le cache-aside de la fiche du **produit 42** (clé `shopflow:produit:v1:42`), sa fraîcheur après modification et le repli quand Redis est indisponible. PostgreSQL reste la source de vérité.

Explication pas à pas, pensée pour comprendre l'intérêt : **[`../ATELIER8_DE_A_A_Z.md`](../ATELIER8_DE_A_A_Z.md)**.

L'API (`01_server/api`) et le kit ne sont **pas modifiés**, et `.env` reste intact : le TTL de 60 s est passé à l'API par une variable d'environnement au lieu de modifier `.env` (écart volontaire avec la fiche ; empreinte de `.env` vérifiée avant et après).

---

## Situation

La fiche d'un produit est lue très souvent et change rarement. Chaque lecture envoie un SELECT à PostgreSQL. On veut éviter ce travail **sans que le catalogue affiche durablement un prix faux** et sans que la validation d'un achat dépende d'une copie.

## Solution et pourquoi

**Cache-aside avec Redis** (slide 24) : l'API lit Redis ; sur *miss* elle lit PostgreSQL puis range une copie avec un **TTL de 60 s** ; le PATCH fait l'UPDATE puis supprime la clé. Pourquoi : fiche publique, clé unique, tolère un court retard (slide 35). Pas read-through : il demanderait une couche de chargement en plus pour un seul endpoint (slide 25). L'historique privé d'un client changerait trop souvent ; la confirmation de stock garde son contrôle dans la source.

## Est-ce que ça fonctionne ?

| Étape | Attendu | Obtenu |
|---|---|---|
| 1 Préparation | TTL 60 s | TTL de la clé après chargement : **60** ; prix initial **57,50** |
| 2 Miss / hit (+ 5 paires) | miss : 1 SELECT ; hit : 0 SQL ; data identiques | **identiques, 1 et 0** (5 paires vérifiées) |
| 3 UPDATE SQL direct | l'API renvoie l'ancien prix (hit, 0 SQL) ; après DEL : le nouveau | **57,50 (hit, 0 SQL)** alors que PostgreSQL a 19,90 ; après DEL : **19,90 (miss)** |
| 4 PATCH 29.90 | `invalidation=ok`, GET : miss puis hit | **ok**, 29,90 miss, 29,90 hit |
| 5 Expiration | TTL positif puis −2 ; miss, 1 SELECT | **60 → −2** ; miss, 1 SELECT, prix 29,90 |
| 5 Panne de Redis | 200, `indisponible`, 1 SELECT | **200, indisponible, 1 SELECT, prix 29,90** |
| 6 Restauration | prix initial, `invalidation=ok` | **57,50, ok** ; table `produits` identique (md5) |

### Miss contre hit : ce que le cache gagne vraiment

| Mesure | Miss (médiane) | Hit (médiane) | Rapport |
|---|---|---|---|
| Durée de la requête, **connexion persistante**, 100 paires | 2,709 ms | **0,988 ms** | ×2,7 |
| Temps dans l'API (`durationMs` du journal) | 2,08 ms | 0,671 ms | ×3,1 |
| SQL | 1 SELECT (0,768 ms) | 0 | — |
| Durée vue par l'**aide du kit** (un processus Node par appel), 30 paires | 43,0 ms | 42,0 ms | ×1,03 (non significatif) |

L'aide du kit lance un processus Node par appel : son coût fixe (≈ 40 ms) **noie** la différence. J'ai donc ajouté une mesure sur connexion persistante. Le gain absolu reste **petit** (≈ 1,7 ms) : base locale, accès par clé primaire. Le vrai gain est la **charge évitée sur PostgreSQL**.

### Ce que le cache peut faire mentir

| Situation | Résultat |
|---|---|
| UPDATE direct dans PostgreSQL | l'API sert **57,50** (hit, 0 SQL) alors que la base a **19,90** |
| PATCH par l'API | `invalidation=ok`, le GET suivant donne le nouveau prix |
| PATCH pendant que Redis est arrêté (ajout) | `invalidation=echouee`, PostgreSQL = **34,90** ; après le retour de Redis l'API sert encore **29,90** (la clé a survécu au redémarrage : Redis sauvegarde à l'arrêt) |
| Course de la slide 30, reproduite à la main (ajout) | A lit 34,90 ; B écrit 39,90 et supprime la clé ; A remet 34,90 : l'API sert **34,90** (hit), PostgreSQL a **39,90** |

**Fraîcheur acceptée pour le catalogue :** de quelques secondes à une minute (TTL 60 s). **La validation d'un achat n'utilise pas le cache** : prix et stock sont contrôlés dans PostgreSQL.

### Panne et rafale

Redis arrêté : l'API répond (200, prix de PostgreSQL), mais **chaque lecture devient un SELECT** (30 appels : 30 SELECT contre 0) : risque de surcharge de la base sous forte charge. **Rafale (slide 31) :** 20 lectures simultanées, clé absente : **6 miss et 6 SELECT** au lieu d'un seul ; clé présente : 20 hit, 0 SQL (une mesure, le nombre exact n'est pas reproductible).

## Analyse de la course (slide 30)

A lit l'ancien prix dans PostgreSQL (miss) ; B valide le nouveau prix puis supprime la clé ; A, plus lent, range sa copie ancienne dans Redis. Le `DEL` de B a eu lieu **avant** le `SET` de A : il ne pouvait pas l'annuler. Pistes : une **version** stockée avec la copie (écriture conditionnelle : A n'écrit que si sa version est au moins aussi récente) ; une **invalidation rejouée** après un court délai (ou via une outbox) ; un TTL court si la fraîcheur exigée est forte.

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `run_atelier8.py` | rejoue la fiche (aide du kit `jour4_http.mjs`), vérifie chaque résultat, fait les ajouts, restaure le prix, contrôle le laboratoire |
| `mesure_persistante.py` | miss contre hit sur une connexion HTTP persistante (100 paires) |
| `stampede.mjs` | 20 lectures simultanées (clé absente / présente) |
| `resultats/resultats_atelier8.json`, `mesure_persistante.json`, `mesures_atelier8.csv` | mesures |
| `resultats/api_journal.log`, `api_extraits_par_traceid.txt` | journal de l'API et extraits par TraceId |

Rejouer : `python3 atelier8/run_atelier8.py` (environ 3 minutes ; arrête puis redémarre `api-redis-1`), `python3 atelier8/mesure_persistante.py` (environ 1 minute).

## Limites

Un seul produit, base et Redis locaux, un seul processus API, TTL de 60 s ; la course est reproduite à la main, pas sous charge ; la rafale n'est pas chronométrée finement (une mesure) ; le gain d'une requête plus lourde ou d'une base distante n'est pas mesuré ; le redémarrage de Redis a gardé la copie grâce à sa sauvegarde à l'arrêt (sans elle, l'échec d'invalidation n'aurait pas été observable).
