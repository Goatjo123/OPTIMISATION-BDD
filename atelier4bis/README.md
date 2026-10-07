# Atelier 4 bis : migration de schéma compatible

Jour 2, slides 33 à 43. ShopFlow ajoute `newsletter_ok` aux clients. Sur une **copie** de `shopflow.clients`, on ajoute la colonne, on simule l'ancienne et la nouvelle version du code, on remplit les anciennes lignes par lots, on renforce la contrainte, on teste l'attente de verrou avec deux sessions, puis on exécute le retour arrière.

Explication complète, pas à pas et pensée pour l'oral : **[`../ATELIER4BIS_DE_A_A_Z.md`](../ATELIER4BIS_DE_A_A_Z.md)**.

Les fichiers du cours (`../Atelier_4bis/01` à `09` et `LIRE_EN_PREMIER.txt`) ne sont pas modifiés : les scripts ci-dessous les **relisent tels quels**.

---

## Situation

L'application (ancienne version) lit et écrit `id`, `email`, `nom`. La nouvelle version lira aussi `newsletter_ok`. Pendant le déploiement les deux versions tournent ensemble, et la table `clients` ne doit pas devenir indisponible : un `ALTER TABLE` demande le verrou `ACCESS EXCLUSIVE` qui bloque même les simples lectures (slides 30 et 31).

## Solution et pourquoi

Migration progressive en quatre temps (slide 27) :

1. colonne **nullable** (instantané, l'ancienne version continue de fonctionner) ;
2. `DEFAULT false` pour les écritures suivantes ;
3. remplissage des anciennes lignes par **lots de 200**, chacun validé seul (autocommit) ;
4. `CHECK (newsletter_ok IS NOT NULL) NOT VALID`, puis `VALIDATE CONSTRAINT`, puis `SET NOT NULL`.

Pourquoi : chaque étape garde un verrou court ou léger. Un `SET NOT NULL` direct relit toute la table sous `ACCESS EXCLUSIVE` ; avec un CHECK déjà validé, PostgreSQL **saute** ce scan. `lock_timeout = 2 s` fait échouer la migration au lieu de bloquer la file.

## Est-ce que ça fonctionne ?

Oui. Tous les résultats attendus par `LIRE_EN_PREMIER.txt` sont obtenus (exécution du 07/10/2026, PostgreSQL 18.6) :

| Étape | Attendu | Obtenu |
|---|---|---|
| 01 | copie et référence, 1 000 clients | 1 000 / 1 000 |
| 02 | colonne nullable, 1 000 NULL | 1 000 NULL, la table `clients` d'origine n'a pas la colonne |
| 03 | ancien lecteur OK, nouveau lecteur gère NULL, insertions ancienne et nouvelle, tests annulés ; après le défaut : toujours 1 000 NULL | 1001 → NULL, 1002 → false ; 0 ligne de test restante ; 1 000 NULL |
| 04 | 200, 200, 200, 200, 200, puis 0 ; NULL restants 800, 600, 400, 200, 0 | exactement cela ; relancé après 0 : 0 ligne |
| 05 | CHECK présent, `convalidated = false` | `false` ; une insertion avec NULL est déjà refusée (23514) |
| 06 | CHECK validé, colonne NOT NULL, défaut false | `true`, `NO`, `false` ; message DEBUG1 : pas de second scan |
| 07 | défaut false ; NULL refusé (23502) ; 1 000 / 0 / 1 000 ; 0 écart | exactement cela ; md5 de `id|email|nom` identique à la table d'origine |
| 08 | délai de verrou dépassé (55P03), puis réussite après COMMIT de A | B échoue après 2,005 s ; après le COMMIT, le même ALTER réussit |
| 09 | colonne retirée, champs historiques identiques | colonne absente, 0 écart |

**Ce que ce n'est pas.** L'ajout de cette colonne ne démontre pas un gain de performance (dit dans `LIRE_EN_PREMIER.txt`). Le gain mesuré plus bas concerne le **blocage** des autres utilisateurs.

---

## Ce que j'ai ajouté au cours (signalé comme tel)

| Ajout | Pourquoi | Résultat |
|---|---|---|
| Une valeur explicite survit au remplissage (annulé par ROLLBACK) | prouver que le filtre `IS NULL` protège les valeurs déjà renseignées | l'id 7 mis à `true` reste `true`, le dernier lot traite 199 lignes |
| Le `CHECK NOT VALID` refuse déjà un NULL | prouver « s'applique aux nouvelles écritures avant validation » | erreur 23514 |
| `client_min_messages = debug1` pendant `SET NOT NULL` | prouver le « pas de second scan » au lieu de l'affirmer | message « existing constraints … are sufficient to prove that it does not contain nulls » |
| Instantané `pg_stat_activity` / `pg_locks` pendant l'attente de B | voir qui détient et qui attend | A : `AccessShareLock` accordé ; B : `AccessExclusiveLock` non accordé |
| Scénario « C derrière B » (slide 31) | vérifier qu'une simple lecture attend derrière un `ALTER` en attente | C bloquée 3,005 s alors que A ne détient qu'un verrou de lecture |
| Rejeu de 02 et de 01 après le retour arrière | vérifier la consigne « reprendre à 02, ne pas relancer 01 » | 02 réussit, 01 échoue (42P07 : la table existe) |
| Mesure ancienne → nouvelle à 3 000 000 lignes | l'atelier à 1 000 lignes ne montre aucun écart ; voir ce que change la méthode à volume réaliste | voir ci-dessous |

## Ancienne version → nouvelle version à 3 000 000 lignes

Table de travail jetable (hors laboratoire), même résultat final (md5 `b227f2377b62` dans les deux cas : 3 000 000 lignes à `false`, `NOT NULL`, défaut `false`).

| Ce qui bloque les autres | Ancienne (naïve) | Nouvelle (atelier 4 bis) |
|---|---|---|
| Temps sous verrou `ACCESS EXCLUSIVE` pour poser NOT NULL | **3 324 ms** (`SET NOT NULL` relit toute la table) | **46,3 ms** (`CHECK NOT VALID` 7,9 + `SET NOT NULL` sans scan 38,4) |
| Lecture la plus longue bloquée pendant cette étape | 3 323 ms | 38,9 ms (pendant `VALIDATE`, verrou léger) |
| Écriture la plus longue bloquée pendant le remplissage | 30 989 ms (un seul UPDATE) | 416 ms (lots de 50 000) |
| **Coût de la méthode** : durée totale du remplissage | 57 043 ms | 156 265 ms (≈ ×2,7 plus long) |

La nouvelle méthode n'est **pas plus rapide au total** : elle remplit plus lentement, avec plus de WAL (1,99 contre 1,63 Go), mais elle **ne bloque presque personne**. Une première exécution du même script avait donné 3 343 → 14,8 ms (×226) pour le verrou exclusif : le mode d'emploi est l'ordre de grandeur, pas la valeur exacte. Résultat dans `resultats/volume.json` (la première exécution n'a pas été conservée).

Preuve de verrouillage (déterministe, chaque `ALTER` maintenu dans une transaction ouverte) :

| Transaction maintenue ouverte | Verrou détenu | Lecture | UPDATE | INSERT |
|---|---|---|---|---|
| `VALIDATE CONSTRAINT` | `ShareUpdateExclusiveLock` | passe | passe | passe |
| `SET NOT NULL` | `AccessExclusiveLock` | **bloquée** (55P03 après 500 ms) | n/a | n/a |

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `run_atelier.py` | rejoue `01` à `09` du dossier `Atelier_4bis` sur le laboratoire, avec quatre vraies connexions (M, A, B, C), contrôle chaque résultat attendu (le script s'arrête si un contrôle échoue), supprime les deux tables de travail et vérifie que le laboratoire retrouve son état initial |
| `bench_volume.py` | mesure ancienne → nouvelle version sur une table de travail de N lignes (3 000 000 par défaut, environ 6 minutes) |
| `resultats/resultats.json` | toutes les valeurs de l'exécution de l'atelier |
| `resultats/transcript.txt` | sortie brute de psql, commande par commande, avec `\timing` et les codes d'erreur |
| `resultats/volume.json` | mesures à 3 000 000 lignes |

Rejouer : `python3 atelier4bis/run_atelier.py` (conteneur `api-postgres-1` démarré, environ 30 secondes). Le script refuse de démarrer si les tables de migration existent déjà.

## Deux défauts trouvés et corrigés dans mon propre script

1. Une erreur de psql (écrite sur la sortie d'erreur) pouvait arriver **après** la sortie de la commande suivante dans le tube, donc être attribuée à la mauvaise commande ou perdue (constaté sur le rejeu de `01`, où l'erreur `42P07` a disparu une fois). Correction : une sentinelle sur chaque flux, on lit jusqu'à les avoir vues toutes les deux. Vérifié sur 30 commandes en erreur d'affilée : 0 anomalie. Les deux scripts ont été relancés entièrement après la correction.
2. Une requête de contrôle utilisait `contype || ':'` sur un type `"char"` (PostgreSQL refuse l'opérateur ambigu) : cast explicite ajouté.

## Limites

Copie de 1 000 lignes, une seule base, pas de trafic réel concurrent. La mesure à 3 000 000 lignes est **une seule exécution** sur une table de travail ; le WAL est lu sur tout le serveur et inclut l'activité de fond ; les lots font 50 000 lignes (200 dans l'atelier). Le remplissage utilise `WHERE newsletter_ok IS NULL ORDER BY id LIMIT n` tel que dans le cours. Les lots de 50 000 lignes durent environ 2,3 s chacun (médiane), ce qui explique que le total soit plus long que l'UPDATE unique ; je n'ai pas analysé le plan de ces lots (hypothèse non vérifiée : relecture des lignes déjà traitées avant d'atteindre les suivantes).
