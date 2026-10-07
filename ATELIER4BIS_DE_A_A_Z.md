# Atelier 4 bis de A à Z : tout ce qui a été fait, et pourquoi

Ce document est écrit pour que **tu comprennes** l'atelier et que **tu puisses l'expliquer** à l'oral, sans lire le code. Tous les chiffres viennent de `atelier4bis/resultats/` (exécution du 07/10/2026, PostgreSQL 18.6 dans Docker).

---

## 0. En une minute

**La question de l'atelier :** comment ajouter une colonne `newsletter_ok` (non nulle, défaut `false`) à la table `clients`, **pendant que l'application tourne**, sans la casser et sans bloquer les utilisateurs ?

**La réponse :** on ne fait pas tout d'un coup. On découpe en petites étapes, chacune avec un verrou court ou léger :

```
1. ADD COLUMN newsletter_ok boolean            -> colonne vide (NULL), instantané
2. SET DEFAULT false                            -> les NOUVELLES lignes recevront false
3. UPDATE par lots de 200 (jusqu'à 0)           -> on remplit les ANCIENNES lignes
4. CHECK (...) NOT VALID                        -> règle appliquée aux nouvelles écritures
5. VALIDATE CONSTRAINT                          -> on vérifie les anciennes lignes (verrou léger)
6. SET NOT NULL                                 -> la colonne devient obligatoire, sans relire la table
```

**Ce que j'ai prouvé** : chaque étape donne le résultat attendu, aucune donnée historique n'est abîmée (0 écart), le retour arrière fonctionne, et la méthode bloque les autres utilisateurs **beaucoup moins longtemps** qu'une migration directe (mesuré sur 3 000 000 de lignes).

**Ce que ce n'est pas** : un gain de vitesse de requête. Le cours le dit lui-même (`LIRE_EN_PREMIER.txt`) : *« L'ajout de cette colonne ne démontre pas un gain de performance. »*

---

## 1. Ce que le cours demandait (et la slide 43)

Les slides 33 à 43 demandent de faire six choses sur une **copie** de `shopflow.clients` : ajouter la colonne, simuler l'ancien et le nouveau code, remplir les anciennes lignes, renforcer la contrainte, tester un verrou avec deux sessions, faire le retour arrière.

**Objectif de fin (slide 33) :** champs historiques identiques, aucune valeur NULL, retour arrière fonctionnel.

**La slide 43 est celle des « preuves de migration à rendre ».** Quand j'ai écrit « le livrable de la page 43 », je parlais de cette liste de six traces à conserver. La voici, avec l'endroit où chacune se trouve dans mes résultats :

| # | Trace demandée | Où c'est dans mes résultats |
|---|---|---|
| 01 | SQL d'ajout, défaut, lots et contrainte | les fichiers `Atelier_4bis/01` à `09` (rejoués tels quels), annexe 8.2 du PDF, `transcript.txt` |
| 02 | Volumes et NULL avant, pendant, après ; nombre et durée de chaque lot | annexe 8.3 du PDF, `resultats.json` (`04_lots`) |
| 03 | Compatibilité des lecteurs, défaut, rejet de NULL, comparaison historique à 0 écart | annexe 8.4 |
| 04 | État de la contrainte avant et après validation | annexe 8.5 |
| 05 | Verrou : erreur de B, COMMIT de A, réussite de B, avec la chronologie | annexe 8.6 |
| 06 | SQL de retour arrière et contrôles ; limites et précautions | annexe 8.7, section « Limites » ci-dessous |

Tu as précisé que **le temps de 60 minutes n'est pas à respecter** : c'est juste la forme. Mon script rejoue tout en environ 30 secondes.

---

## 2. Le vocabulaire (à connaître pour expliquer)

| Mot | Ce que ça veut dire, simplement |
|---|---|
| **Migration** | modifier la structure de la base (ajouter une colonne, une contrainte…) |
| **DDL** | « langage de définition des données » : les commandes qui changent la structure (`ALTER TABLE`, `CREATE INDEX`) |
| **Nullable** | une colonne qui accepte la valeur `NULL` (« pas de valeur »). Une colonne ajoutée est nullable au départ : les anciennes lignes ont `NULL` |
| **DEFAULT** | la valeur donnée aux **nouvelles** lignes quand on n'écrit pas la colonne. **Il ne remplit pas les anciennes lignes** (c'est le piège de l'étape 03) |
| **Lot (batch)** | un petit paquet de lignes traité en une fois (ici 200). Chaque lot est validé seul, donc les verrous de ligne sont libérés vite |
| **Autocommit** | chaque commande est validée toute seule, sans `BEGIN … COMMIT` autour. Indispensable pour que chaque lot soit réellement validé avant le suivant |
| **CHECK … NOT VALID** | une règle (ici « la colonne n'est pas NULL ») qui s'applique tout de suite aux **nouvelles** écritures, mais dont la vérification des **anciennes** lignes est repoussée |
| **VALIDATE CONSTRAINT** | vérifie les anciennes lignes. Pose un verrou léger : lectures et écritures continuent |
| **SET NOT NULL** | rend la colonne obligatoire. Pose le verrou le plus fort (`ACCESS EXCLUSIVE`) ; normalement relit toute la table pour vérifier |
| **Verrou ACCESS SHARE** | verrou de lecture pris par un `SELECT`. Plusieurs lectures coexistent |
| **Verrou ACCESS EXCLUSIVE** | verrou exclusif de l'`ALTER TABLE`. **Bloque même les lectures** |
| **lock_timeout** | durée maximale d'**attente** d'un verrou. Passé ce délai : erreur `55P03` au lieu d'attendre indéfiniment. Il ne limite **pas** la durée du DDL une fois le verrou obtenu |
| **WAL** | journal d'écriture de PostgreSQL. Son volume est une mesure stable du travail d'écriture |
| **EXCEPT ALL** | différence entre deux résultats, en tenant compte des doublons. Dans les deux sens, 0 ligne = résultats identiques |
| **md5** | empreinte d'un résultat. Deux empreintes égales = résultats identiques |
| **Vacuum / ligne morte** | un `UPDATE` ne modifie pas la ligne : il en crée une nouvelle version, l'ancienne devient « morte » et sera nettoyée plus tard |

---

## 3. Pourquoi ne pas tout faire d'un coup ?

La version naïve tient en trois commandes :

```sql
ALTER TABLE clients ADD COLUMN newsletter_ok boolean;
UPDATE clients SET newsletter_ok = false;                 -- tout d'un coup
ALTER TABLE clients ALTER COLUMN newsletter_ok SET NOT NULL;
```

Elle marche, mais elle a **deux défauts** qu'on ne voit pas sur 1 000 lignes :

1. **Un seul gros `UPDATE`** : toutes les lignes sont verrouillées jusqu'à la fin. Quiconque veut modifier une de ces lignes **attend**.
2. **`SET NOT NULL` relit toute la table** pour vérifier qu'il n'y a aucun NULL, **en tenant le verrou `ACCESS EXCLUSIVE`** : pendant ce temps, **personne ne peut même lire** la table.

La slide 31 montre le pire : une lecture simple (C) arrivée **après** l'`ALTER` en attente reste coincée **derrière** lui, même si la lecture qui tient le verrou (A) est compatible avec elle. Une migration mal préparée peut donc bloquer toute l'application.

---

## 4. Déroulement, étape par étape

Le script `atelier4bis/run_atelier.py` envoie à PostgreSQL le **SQL des fichiers du cours, tel quel** (il ne le réécrit pas), commande par commande, comme quand on « sélectionne puis exécute » dans pgAdmin. Il utilise **quatre connexions distinctes** (M pour la migration, A, B et C pour les verrous). À chaque étape, il **vérifie le résultat attendu** et s'arrête s'il est différent.

### État avant de commencer

Le laboratoire a 4 tables, **6 index**, **0 statistique étendue**, 1 000 clients (ids 1 à 1000). J'ai enregistré une empreinte md5 de la table `clients` : `aec47d5bdba0`. À la fin, tout doit être identique.

### Étape 01 : préparation (`01_preparation.sql`)

- **Ce que ça fait :** crée `clients_migration_tp` (`LIKE clients INCLUDING ALL` : même clés, mêmes contraintes), la remplit, puis crée une table de **référence** `clients_migration_reference_tp` avec les valeurs d'origine.
- **Pourquoi deux tables :** on travaille sur la copie, et la référence sert à **comparer à la fin** que rien n'a changé.
- **Résultat :** 1 000 clients dans la copie et dans la référence. La clé primaire et l'`UNIQUE(email)` sont conservées.

### Étape 02 : ajout compatible (`02_ajout_colonne.sql`)

- **Ce que ça fait :** `SET lock_timeout = '2s'`, puis `ADD COLUMN newsletter_ok boolean` (nullable).
- **Pourquoi nullable :** ajouter une colonne nullable est instantané (aucune ligne n'est réécrite) et **l'ancienne version de l'application continue de fonctionner**, puisqu'elle ne connaît pas la colonne.
- **Résultat :** **1 000 NULL** (toutes les lignes existantes). `ALTER` en 6,3 ms. La vraie table `clients` n'a pas la colonne : on n'a touché que la copie.

### Étape 03 : compatibilité des deux versions (`03_compatibilite.sql`)

- **Ancien lecteur :** `SELECT id, email, nom …` : marche toujours.
- **Nouveau lecteur :** `COALESCE(newsletter_ok, false)` : traite `NULL` comme « pas d'autorisation » (règle métier de l'exercice).
- **Simulation d'écrivains** dans un `BEGIN … ROLLBACK` : l'**ancien** écrivain (qui ne connaît pas la colonne) insère la ligne 1001 : sa valeur est `NULL`. Le **nouvel** écrivain insère la ligne 1002 avec `false` : sa valeur est `false`. Puis `ROLLBACK` : les deux lignes disparaissent (0 ligne de test restante).
- **`SET DEFAULT false`** : à partir de maintenant, une insertion qui oublie la colonne reçoit `false`.
- **Le piège :** après le `SET DEFAULT`, on recompte les NULL : **toujours 1 000**. Le défaut s'applique aux **futures** lignes, il ne remplit pas les anciennes. C'est pour cela qu'il faut l'étape 04.

### Étape 03 bis (mon ajout) : une valeur explicite survit au remplissage

- **Question :** si un client a déjà `newsletter_ok = true`, le remplissage va-t-il l'écraser ?
- **Test :** dans un `BEGIN … ROLLBACK`, je mets l'id 7 à `true`, je lance les lots, je regarde l'id 7.
- **Résultat :** l'id 7 reste `true`, et le dernier lot ne traite que **199** lignes au lieu de 200. Le filtre `WHERE newsletter_ok IS NULL` protège les valeurs déjà renseignées. Tout est annulé ensuite.
- **Détail honnête :** ce test crée des lignes mortes (taille de la table : 80 kB → 152 kB avant les vrais lots). C'est sans conséquence, mais ça explique ce chiffre dans l'annexe.

### Étape 04 : remplissage par lots (`04_remplissage_lot.sql`)

Le bloc SQL du cours :

```sql
WITH lot AS (
  SELECT id FROM clients_migration_tp
  WHERE newsletter_ok IS NULL ORDER BY id LIMIT 200
), maj AS (
  UPDATE clients_migration_tp c SET newsletter_ok = false FROM lot
  WHERE c.id = lot.id AND c.newsletter_ok IS NULL
  RETURNING c.id
)
SELECT count(*) AS nb_mises_a_jour FROM maj;
```

- **Comment ça marche :** `lot` choisit au plus 200 lignes encore à NULL (les plus petits ids) ; `maj` les passe à `false` et renvoie leurs ids ; le `SELECT` final compte combien on en a modifié.
- **On le relance jusqu'à obtenir 0.** Chaque exécution est validée toute seule (autocommit), donc elle libère ses verrous avant la suivante. **Ne jamais mettre tous les lots dans un seul `BEGIN`** : ce serait un seul gros lot déguisé.
- **Résultat :** 200, 200, 200, 200, 200, puis **0**. NULL restants entre les lots : 800, 600, 400, 200, 0. Relancé encore après 0 : **0** (le script est rejouable sans danger).

| Lot | Lignes | Durée (ms) | WAL (octets) | NULL restants |
|---|---|---|---|---|
| 1 | 200 | 4,2 | 66 560 | 800 |
| 2 | 200 | 5,3 | 65 352 | 600 |
| 3 | 200 | 41,5 | 60 872 | 400 |
| 4 | 200 | 38,5 | 57 296 | 200 |
| 5 | 200 | 39,2 | 44 816 | 0 |
| 6 | 0 | 0,6 | 0 | 0 |

**À dire à l'oral :** les durées varient du simple au décuple pour des lots identiques (4 à 41 ms) : elles sont **bruitées**, donc je ne m'appuie pas dessus. Ce qui est fiable : le nombre de lignes, les NULL restants et le WAL (≈ 300 octets par ligne modifiée, soit environ 305 ko au total).

### Étape 05 : contrainte progressive (`05_contrainte_progressive.sql`)

- **Ce que ça fait :** après un contrôle à 0 NULL, `ADD CONSTRAINT … CHECK (newsletter_ok IS NOT NULL) NOT VALID`.
- **Pourquoi `NOT VALID` :** PostgreSQL **n'attend pas** de relire toutes les lignes (c'est donc très court), mais **applique tout de suite** la règle aux nouvelles écritures. La vérification des anciennes lignes est séparée en une étape à part.
- **Résultat :** `convalidated = false` (la contrainte existe mais n'est pas encore « validée »).
- **Mon ajout :** je tente d'insérer une ligne avec `newsletter_ok = NULL` : **refusée, erreur 23514** (violation du CHECK), alors que la contrainte n'est pas validée. Ça prouve que la règle protège déjà les nouvelles écritures.

### Étape 06 : validation (`06_validation.sql`)

1. `VALIDATE CONSTRAINT` : relit les anciennes lignes pour vérifier qu'aucune n'est NULL. Verrou **léger** : lectures et écritures continuent. Résultat : `convalidated = true`.
2. `SET NOT NULL` : la colonne devient obligatoire. Ce verrou est le plus fort, **mais** comme le CHECK validé prouve déjà qu'il n'y a aucun NULL, PostgreSQL **saute** la relecture de la table. Il faut pour cela **conserver le CHECK** pendant la commande (c'est ce que dit le cours).
- **Mon ajout, la preuve :** j'ai activé `client_min_messages = debug1` juste pour cette commande. PostgreSQL a écrit : *« existing constraints on column … are sufficient to prove that it does not contain nulls »*. C'est la preuve que la table n'est pas relue. Ce réglage n'a **pas changé** le comportement, seulement l'affichage.
- **Résultat :** `is_nullable = NO`, défaut `false`, CHECK validé.

### Étape 07 : contrôles finaux (`07_controles.sql`)

| Contrôle | Attendu | Obtenu |
|---|---|---|
| Insertion qui oublie la colonne (annulée) | `false` | `false` |
| `UPDATE … SET newsletter_ok = NULL` (hors transaction) | erreur 23502 | **23502** (violation de NOT NULL) |
| Comptage | 1 000 clients / 0 NULL / 1 000 false | exactement cela |
| Comparaison avec la référence (`EXCEPT ALL` dans les deux sens) | 0 écart | **0 écart** |

J'ai ajouté une empreinte md5 de `id|email|nom` : copie, référence et table `clients` d'origine donnent toutes `aec47d5bdba0`. **Pourquoi `EXCEPT ALL` et md5, et pas juste un comptage :** un comptage identique ne prouve pas que les valeurs sont identiques (on pourrait avoir 1 000 lignes toutes différentes).

### Étape 08 : verrous avec deux sessions (`08_verrous_session_A.sql` et `_B.sql`)

**Le scénario :**

| Temps | Session | Ce qui se passe |
|---|---|---|
| 0,000 s | **A** | `BEGIN; SELECT …` : détient `ACCESS SHARE`, **transaction laissée ouverte** |
| 0,004 s | **B** | `SET lock_timeout='2s'` puis `ALTER TABLE … ADD COLUMN test_verrou` : demande `ACCESS EXCLUSIVE`, **attend** |
| pendant l'attente | — | `pg_locks` : A détient `AccessShareLock` (accordé) ; B demande `AccessExclusiveLock` (**non accordé**) |
| ≈ 2,0 s | **B** | **erreur 55P03** « canceling statement due to lock timeout » (le serveur mesure 2 001,8 ms) |
| ≈ 2,2 s | **A** | `COMMIT` : le verrou est libéré |
| juste après | **B** | **même `ALTER` relancé : réussi** (2,3 ms) ; puis `DROP COLUMN test_verrou` et `RESET lock_timeout` (nettoyage) |

**Ce que ça démontre :** une migration peut **attendre** derrière une simple lecture laissée ouverte. `lock_timeout` la fait **échouer proprement** au lieu de rester coincée ; on relance quand le bloqueur est parti. Pour que le test soit vrai, il faut **deux connexions indépendantes** (deux onglets qui partagent une connexion ne suffisent pas, dit `LIRE_EN_PREMIER.txt`). Mon script ouvre bien deux processus `psql` séparés.

**Mon ajout, la file de la slide 31 :** je relance le scénario avec B qui attend 4 s et une lecture simple **C** lancée 1 s plus tard. **C est restée bloquée 3,005 s**, alors que A ne détient qu'un verrou de lecture compatible avec C : c'est **la file d'attente de B qui la retient**. Dès que B abandonne (55P03 à 4 s), C passe. Un `pg_stat_activity` pris pendant l'attente le montre : B et C attendent un verrou, A non. **C'est le vrai danger d'un `ALTER TABLE` sur une table très lue**, et la raison d'être de `lock_timeout`.

### Étape 09 : retour arrière (`09_retour_arriere.sql`)

1. Dans une transaction : retirer le CHECK, puis `DROP NOT NULL` et `DROP DEFAULT`. **La colonne et ses valeurs existent encore** (vérifié : colonne présente, 1 000 valeurs à `false`, 0 contrainte restante, `is_nullable = YES`, plus de défaut).
2. `DROP COLUMN newsletter_ok` : termine le TP **et détruit les valeurs**.
3. Contrôles : colonne restante = 0 ; écarts historiques = **0** ; md5 identique à l'original.
- **Limite importante :** le retour de **structure** ne reconstitue pas les valeurs supprimées. On compare donc seulement `id`, `email`, `nom`. En production, on devrait **conserver** les nouvelles valeurs et organiser le retour de la version applicative.
- **Rejouabilité (mon ajout) :** je relance 02 sur la copie conservée : réussi. Je relance 01 : **erreur 42P07** « la table existe déjà ». C'est exactement ce que dit `LIRE_EN_PREMIER.txt` : rejouer à partir de 02, ne pas relancer 01.

### Nettoyage et état final

À la fin, le script **supprime** `clients_migration_tp` et `clients_migration_reference_tp`, puis compare le laboratoire à son état initial : mêmes 4 tables, mêmes 6 index, 0 statistique étendue, mêmes nombres de lignes, même empreinte de `clients`. Résultat : **identique**. Pour rejouer l'atelier, il suffit de relancer `01`.

---

## 5. La mesure à grande échelle : ancienne version → nouvelle version

### Pourquoi la faire

Sur 1 000 lignes, tout est instantané : **on ne voit aucune différence** entre la méthode directe et la méthode en étapes. Or tout l'intérêt de la méthode est ce qui se passe sur une grosse table. Le prof demande de montrer la **transformation d'une ancienne version en une nouvelle**, avec un même résultat et un gain. J'ai donc comparé les deux sur une table jetable de **3 000 000 lignes** (hors laboratoire, supprimée ensuite).

### Ce qui est comparé

| | Ancienne (naïve) | Nouvelle (atelier 4 bis) |
|---|---|---|
| Remplissage | un seul `UPDATE` de toutes les lignes | lots de 50 000 lignes validés un par un |
| Contrainte | `SET NOT NULL` direct | `CHECK NOT VALID`, `VALIDATE`, puis `SET NOT NULL` |

Pour mesurer le blocage, une « **sonde** » (connexion séparée) répète en boucle une lecture ou un verrouillage de ligne, et note **la plus longue attente** observée.

### Résultats (exécution du 07/10/2026)

**Résultat final identique** : md5 `b227f2377b62` dans les deux cas (3 000 000 lignes à `false`, `NOT NULL`, défaut `false`).

| Ce qui bloque les autres | Ancienne | Nouvelle |
|---|---|---|
| Temps sous verrou `ACCESS EXCLUSIVE` pour poser NOT NULL | **3 324 ms** | **46,3 ms** (×72) |
| Lecture la plus longue bloquée pendant cette étape | 3 323 ms | 38,9 ms |
| Écriture la plus longue bloquée pendant le remplissage | 30 989 ms | 416 ms (×74) |
| **Durée totale du remplissage (le coût de la méthode)** | 57 043 ms | 156 265 ms (≈ ×2,7 **plus long**) |

### Comment l'expliquer honnêtement

- **La nouvelle méthode est plus lente au total** (156 s contre 57 s) et produit plus de WAL (1,99 contre 1,63 Go). **Ce qu'elle gagne, c'est de ne presque jamais bloquer personne** : une lecture attend au plus 39 ms au lieu de 3,3 s, une écriture au plus 0,4 s au lieu de 31 s.
- **Optimiser une migration, c'est réduire le temps pendant lequel les autres attendent**, pas forcément la durée totale.
- **Une seule exécution.** Une première exécution du même script avait donné 3 343 → 14,8 ms (×226) pour le verrou exclusif ; la deuxième, 3 324 → 46,3 ms (×72). La différence vient du temps de `SET NOT NULL` « sans scan », qui varie de quelques à quelques dizaines de ms. **Ce qui compte, c'est l'ordre de grandeur** (des centaines de ms ou des secondes contre quelques dizaines de ms), pas la valeur exacte. Seul le résultat de la deuxième exécution est conservé dans `volume.json`.

### La preuve de verrouillage (déterministe)

Au lieu de compter sur le chrono, j'ai **maintenu chaque `ALTER` dans une transaction ouverte** et j'ai regardé si une connexion concurrente (avec `lock_timeout` de 500 ms) arrivait à lire ou écrire :

| Transaction maintenue ouverte | Verrou détenu | Lecture | UPDATE | INSERT |
|---|---|---|---|---|
| `VALIDATE CONSTRAINT` | `ShareUpdateExclusiveLock` | passe | passe | passe |
| `SET NOT NULL` | `AccessExclusiveLock` | **bloquée** (55P03 après 500 ms) | n/a | n/a |

C'est ce qui justifie toute la méthode : `VALIDATE` relit la table **sans bloquer personne**, alors que `SET NOT NULL` direct bloque les lectures.

---

## 6. Ce que j'ai dû corriger en route (à connaître : ça se vérifie)

Un travail se contrôle, y compris le mien. J'ai trouvé deux défauts dans mon propre script :

1. **Des erreurs de psql pouvaient être attribuées à la mauvaise commande.** psql écrit ses erreurs sur la sortie d'erreur, qui peut arriver **après** la sortie de la commande suivante. Je l'ai constaté sur le rejeu de `01` : l'erreur `42P07` a disparu une fois. Correction : une « sentinelle » sur chaque flux, et on lit jusqu'à les avoir vues toutes les deux. Vérifié sur 30 commandes en erreur d'affilée : 0 anomalie. J'ai ensuite **relancé les deux scripts en entier**.
2. **Une requête de contrôle plantait** (opérateur `||` ambigu sur un type `"char"`) : cast explicite.

---

## 7. Les limites (à dire, ça montre que tu as compris)

- **1 000 lignes** : le SQL qui réussit sur 1 000 lignes n'est pas une preuve pour la production (slide 27). D'où la mesure à 3 000 000 lignes.
- **Une seule base, aucun trafic réel concurrent** : les attentes mesurées viennent de sondes, pas d'utilisateurs.
- **La mesure à 3 000 000 lignes est une seule exécution**, les durées exactes varient.
- **Le WAL est lu sur tout le serveur** et inclut l'activité de fond (autovacuum) : c'est pour ça qu'il est élevé pour le `ADD COLUMN` de la nouvelle variante dans le fichier de mesures.
- **Les lots font 50 000 lignes** dans la mesure (200 dans l'atelier), pour garder 60 lots à cette taille.
- **Le retour arrière détruit les valeurs** de la colonne (`DROP COLUMN`). Le retour de structure n'est donc pas un retour de données.
- **`CREATE INDEX CONCURRENTLY`** (slide 29) n'est pas utilisé ici : cet atelier ne crée pas d'index.
- **Je n'ai pas analysé** pourquoi les lots de 50 000 lignes sont longs (≈ 2,3 s chacun) : hypothèse non vérifiée, relecture des lignes déjà traitées.

---

## 8. Comment l'expliquer en deux minutes à l'oral

> « L'atelier 4 bis, c'est ajouter une colonne `newsletter_ok` à la table clients **sans casser l'application et sans bloquer les utilisateurs**. Je ne fais pas tout d'un coup : j'ajoute la colonne vide, je pose un défaut pour les nouvelles lignes, je remplis les anciennes **par lots de 200**, puis je pose la contrainte en deux temps, `NOT VALID` puis `VALIDATE`, et enfin `SET NOT NULL`, qui ne relit plus la table parce que la contrainte validée prouve déjà qu'il n'y a pas de NULL. J'ai **prouvé** chaque étape : 1 000 NULL après l'ajout, les lots 200, 200, 200, 200, 200 puis 0, une écriture de NULL refusée, **0 écart** sur les champs historiques, et un retour arrière qui fonctionne. Avec deux sessions, j'ai vu qu'un `ALTER` qui attend un verrou est arrêté par `lock_timeout` après 2 secondes, et qu'une simple lecture arrivée après lui reste bloquée **derrière** lui. Enfin, pour voir l'intérêt à volume réel, j'ai comparé à 3 millions de lignes : la méthode directe tient la table **inaccessible 3,3 secondes**, la nouvelle seulement quelques dizaines de millisecondes. Elle est plus lente au total, mais elle ne bloque presque personne : optimiser une migration, c'est réduire l'attente des autres. »

---

## 9. Questions qu'on peut te poser

**Pourquoi ajouter la colonne nullable et pas directement `NOT NULL DEFAULT false` ?**
On pourrait, et PostgreSQL moderne le fait vite quand le défaut est constant. L'atelier suit la méthode progressive pour garder la compatibilité entre versions de l'application et pour montrer le principe général (remplissage, puis contrainte), qui reste nécessaire quand la valeur doit être calculée ou que le défaut n'est pas constant.

**Pourquoi le DEFAULT ne suffit-il pas ?**
Il ne s'applique qu'aux **nouvelles** lignes. Les 1 000 existantes restent NULL (vérifié). Il faut un remplissage.

**Pourquoi des lots plutôt qu'un seul UPDATE ?**
Un seul UPDATE tient les verrous de toutes les lignes jusqu'à la fin. Les lots libèrent leurs verrous à chaque validation. Mesuré : écriture bloquée au plus 0,4 s au lieu de 31 s.

**À quoi sert `NOT VALID` ?**
À poser la règle **sans relire** la table (donc un verrou très court) tout en protégeant déjà les nouvelles écritures (erreur 23514 vérifiée).

**Pourquoi garder le CHECK pendant `SET NOT NULL` ?**
Parce que le CHECK validé prouve l'absence de NULL : PostgreSQL saute alors la relecture de la table (message DEBUG1 relevé).

**Que fait `lock_timeout` ?**
Il limite l'**attente** d'un verrou (B échoue en 55P03 après 2 s). Il ne limite pas la durée du DDL une fois le verrou obtenu.

**Pourquoi une lecture simple peut-elle être bloquée ?**
Parce qu'elle fait la queue **derrière** l'`ALTER` en attente (mesuré : 3,005 s). C'est le risque réel d'une migration sur une table très lue.

**Le retour arrière est-il complet ?**
Non : `DROP COLUMN` détruit les valeurs. On retrouve la structure et les champs historiques, pas les nouvelles données.

**La nouvelle méthode est-elle plus rapide ?**
Non, elle est plus lente au total (≈ ×2,7 sur le remplissage). Elle est **moins bloquante**.

---

## 10. Fichiers produits

| Fichier | Contenu |
|---|---|
| `atelier4bis/run_atelier.py` | rejoue les fichiers 01 à 09 du cours, avec contrôles, quatre connexions, nettoyage et vérification du laboratoire |
| `atelier4bis/bench_volume.py` | mesure ancienne → nouvelle version sur 3 000 000 lignes |
| `atelier4bis/resultats/resultats.json` | toutes les valeurs de l'exécution de l'atelier |
| `atelier4bis/resultats/transcript.txt` | sortie brute de psql, commande par commande |
| `atelier4bis/resultats/volume.json` | mesures à 3 000 000 lignes |
| `atelier4bis/README.md` | résumé court : situation, solution, est-ce que ça fonctionne |
| `Atelier1_Diagnostic_compact.pdf` | **section Atelier 4 bis (pages 16 à 18)** et **annexe 8 (pages 42 à 46)** |
| `Optimisations.pdf` | **page 8** : « ancienne version → nouvelle version » de la migration, plus la ligne 7 du tableau d'ensemble |
| `Atelier_4bis/` | fichiers du cours, **non modifiés** |

**Rejouer :** `python3 atelier4bis/run_atelier.py` (le conteneur `api-postgres-1` doit tourner ; environ 30 secondes). Le script refuse de démarrer si les tables de migration existent déjà.
