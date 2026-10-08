# Kit oral de demain : présentation de 5 minutes

Dossier ShopFlow, Optimisation BDD (SUP DE VINCI M2), PostgreSQL 18. Tous les chiffres viennent des fichiers de mesures (atelier7/resultats, atelier8/resultats, atelier9/resultats).

## Problématique (fil rouge)
Une page de 20 commandes paraît simple, mais devient lente quand plusieurs clients arrivent. D'où vient ce coût, comment le supprimer sans changer le résultat, et à quel prix ?

## Les 3 phrases de conclusion
1. J'ai observé 21 requêtes par page et un débit plafonné.
2. En les ramenant à 2, le débit est multiplié par 4,2 sans erreur.
3. C'est valable sur cette machine, ce jeu (100 000 commandes) et 1 à 20 clients, pas encore démontré en production.

## Chiffres à connaître par cœur
- 21 → 2 requêtes par page de 20 commandes
- Débit à 20 clients : 246,9 → 1032,1 req/s (×4,2) ; p95 : 98,0 → 26,8 ms (−73 %) ; 0 erreur
- 3 essais : N+1 238 à 253 ; groupé 978 à 1082 (intervalles disjoints)
- Requête de lignes : 0,018 ms vu par PostgreSQL, 0,68 ms vu par l'API (×38)
- Pool 5 : 15 requêtes en attente à 20 clients ; pool 20 : ≈ 287 req/s (2 essais, indicatif)
- PgBouncer : 40 → 5 connexions, 261 → 94 transactions/s
- Cache : miss 2,7 ms (1 SELECT), hit 0,99 ms (0 SQL), TTL 60 s ; copie périmée 57,50 alors que la base dit 19,90
- Protocole : 1/5/10/20 clients, 3 s d'échauffement + 10 s par essai, 3 essais alternés, médiane (la fiche cite 10 s + 30 s en exemple)

## Version 1 : structure de la fiche

### Besoin et problème initial (0:00 – 0:45)
Bonjour. Mon cas, c'est ShopFlow, une boutique en ligne : une base PostgreSQL 18 avec 100 000 commandes et 300 000 lignes de commande. Je m'intéresse à un endpoint très simple, GET /commandes, qui renvoie une page de 20 commandes avec leurs lignes. Sur le schéma : le client appelle l'API, l'API passe par un pool de 5 connexions, puis interroge PostgreSQL. Le problème observé : pour construire une seule page, l'API envoie **21 requêtes SQL**, une pour la liste puis une par commande. Ma mesure de départ, avec 20 clients simultanés : le débit plafonne à environ **247 requêtes par seconde** dès 5 clients, le p95 est de **98 millisecondes**, et jusqu'à 15 requêtes attendent une connexion. Zéro erreur, mais le service est saturé.

### Mécanisme et intervention (0:45 – 1:45)
Première question : où est le coût ? J'ai regardé pg_stat_statements. La requête de lignes apparaît avec 20 000 appels de 0,018 milliseconde : 369 millisecondes cumulées, elle passe inaperçue, et elle ne figure pas non plus dans le journal des requêtes lentes. Mais l'API, elle, mesure 14,2 millisecondes de SQL par page : environ 0,68 milliseconde par requête, soit **38 fois plus** que ce que voit PostgreSQL. Donc le coût n'est pas dans la requête, il est dans les **allers-retours**. Mon hypothèse causale : si je charge toutes les lignes de la page en une seule requête, avec ANY et la liste des identifiants, je passe de 21 à 2 requêtes. C'est **la seule chose que je change**, comme on le voit sur le code à gauche.

### Mesures avant / après (1:45 – 3:00)
Pour mesurer, je garde les mêmes conditions : même machine, même jeu de données, 1, 5, 10 et 20 clients, trois essais alternés. Sur la courbe de gauche, le débit du N+1 reste plat autour de 250 dès 5 clients : ajouter des clients n'ajoute que de l'attente. Le groupé monte et se stabilise bien plus haut. À 20 clients, le débit passe de 247 à **1032 requêtes par seconde**, soit fois 4,2. Sur la courbe de droite, le p95 passe de 98 à **26,8 millisecondes**, moins 73 pour cent. Zéro erreur. Les trois essais ne se chevauchent pas : c'est reproductible. Et le processeur reste à 50 pour cent dans les deux cas : le gain vient du travail évité, pas d'une ressource en plus.

### Correction et fraîcheur (3:00 – 4:00)
Je ne regarde pas que la vitesse : un résultat plus rapide mais faux ne sert à rien. Le JSON complet, commandes et lignes, est **identique** en N+1 et en groupé, pour 5, 20, 50 et 100 commandes, et les droits sont conservés : 401 sans jeton, 400 si on injecte un client dans l'URL. Ensuite, la fraîcheur, avec le cache Redis sur la fiche produit : un hit ne fait aucune requête SQL, un miss en fait une. Mais regardez : après une modification faite directement dans la base, l'API a continué de servir **57.50 alors que la base disait 19.90**. Le TTL de 60 secondes borne la copie périmée, il ne la corrige pas. Quand on passe par l'API avec un PATCH, la copie est invalidée et la valeur redevient juste. Et l'achat ne passe jamais par le cache.

### Décision, variante rejetée, risque (4:00 – 5:00)
Ma décision : je retiens le chargement groupé. Une variante rejetée : agrandir le pool de 5 à 20 connexions. Cela supprime l'attente, mais n'atteint que 287 requêtes par seconde, contre 1032 avec le groupé, sur deux essais seulement, donc à titre indicatif. J'ai aussi testé PgBouncer : il fait passer les connexions de 40 à 5, mais le débit tombe de 261 à 94 transactions par seconde. Il limite les connexions, il n'accélère rien. Risque restant : la copie du cache peut être périmée jusqu'à 60 secondes, et il existe une course entre une lecture lente et une invalidation, que j'ai reproduite à la main. Pour conclure en trois phrases : j'ai observé 21 requêtes par page et un débit plafonné ; en les ramenant à 2, le débit est multiplié par 4,2 sans erreur ; c'est valable sur cette machine, ce jeu et 1 à 20 clients, et pas encore démontré en production.

## Version 2 : l'histoire en 5 actes

### Pourquoi ça plafonne ? (0:00 – 0:45, acte : Le symptôme)
Bonjour. Je vais vous raconter une enquête, avec une seule question : **pourquoi une page de 20 commandes devient-elle lente quand les clients arrivent ?** Imaginez une boutique en ligne : pour afficher une page de 20 commandes, le serveur fait **21 allers-retours** vers la base, un pour la liste, puis un par commande. Ça marche, mais sous charge ça coince : avec 20 clients, le débit plafonne à environ **247 requêtes par seconde** dès 5 clients, le p95 monte à **98 millisecondes**, et 15 requêtes attendent une connexion. Aucune erreur : le service est simplement saturé. Le symptôme est clair. Reste à trouver d'où vient ce coût, et c'est l'objet de l'enquête.

*Transition :* → Le symptôme est clair. Mais où se cache le coût ?

### Où est le coupable ? (0:45 – 1:30, acte : L'enquête)
Premier suspect : la requête elle-même. Elle est **innocente** : PostgreSQL la voit à 0,018 milliseconde, elle ne ressort pas en tête de pg_stat_statements, et elle n'apparaît pas dans le journal des requêtes lentes. Deuxième suspect : le pool de connexions. Sa file d'attente est une **conséquence**, pas la cause : même avec un pool de 20, on n'atteint que 287 requêtes par seconde. Le vrai coupable, ce sont **les allers-retours** : côté API, chaque requête coûte 0,68 milliseconde, soit **38 fois plus** que ce que voit PostgreSQL. Multipliez ce prix par 21 pour chaque page, et vous obtenez le plafond.

*Transition :* → Si le coût est dans les allers-retours, je n'ai besoin de changer qu'une seule chose.

### Peut-on le supprimer sans rien casser ? (1:30 – 2:15, acte : Le remède)
Le remède tient en une idée : au lieu d'une requête par commande, **une seule requête pour toutes les lignes de la page**, avec ANY et la liste des identifiants. On passe de 21 à **2 requêtes**, quelle que soit la taille de la page. C'est un seul changement : je ne touche ni à l'index, ni au pool, ni à la base. Mais un remède qui casse le résultat ne vaut rien. Je vérifie donc : le JSON complet, commandes et lignes, est **identique** avec 5, 20, 50 et 100 commandes, et les droits sont conservés : 401 sans jeton, 400 si on injecte un client dans l'URL. Même résultat, moins de travail.

*Transition :* → Le résultat est identique. Mais est-ce que ça tient quand la concurrence monte ?

### Le gain tient-il sous charge ? (2:15 – 3:30, acte : La preuve à la charge)
Pour le savoir, je mesure avec 1, 5, 10 et 20 clients, trois essais alternés, un seul changement. Regardez la courbe de gauche : le débit de l'ancienne version reste plat autour de 250 ; celui de la nouvelle monte et se stabilise bien plus haut. À 20 clients, on passe de 247 à **1032 requêtes par seconde**, fois 4,2. À droite, le p95 passe de 98 à **26,8 millisecondes**. Zéro erreur. Le processeur ne bouge pas, autour de 50 pour cent : le gain vient du **travail évité**, pas d'une machine plus puissante. Et les trois essais de chaque version ne se chevauchent pas : c'est reproductible, pas un hasard de mesure.

*Transition :* → Le gain est réel. Alors qu'est-ce qu'il me coûte, et qu'est-ce que je ne sais pas ?

### Quel est le prix, et quelles limites ? (3:30 – 5:00, acte : Le prix du remède)
Premier prix, la fraîcheur. Si je mets un cache Redis devant, un hit ne fait aucune requête, mais la copie peut **mentir** : après une modification faite directement dans la base, l'API a servi **57.50 alors que la base disait 19.90**. Je borne la copie à 60 secondes, je l'invalide à chaque écriture par l'API, et je ne cache jamais l'achat. Deuxième prix, ce que j'ai écarté : agrandir le pool n'atteint que 287 requêtes par seconde, sur deux essais, donc indicatif ; PgBouncer limite les connexions de 40 à 5 mais fait tomber le débit de 261 à 94. Il limite, il n'accélère pas. Risque restant : une lecture lente peut remettre une copie ancienne après l'invalidation. Réponse à ma question : le coût venait des allers-retours ; en les supprimant, le débit est multiplié par 4,2 sans erreur, mesuré sur cette machine, ce jeu et 1 à 20 clients, et pas encore en production.

*Transition :* Conclusion : mesuré ici ; à tester avant toute généralisation.

## Questions probables
- **Reproductibilité ?** Même base (01_schema.sql, 02_donnees.sql, md5 comparés), PostgreSQL 18, Node 22, pool de 5, charge fermée, 3 essais alternés ; `python3 atelier9/p2_charge.py` (≈ 16 min). On compare l'ordre de grandeur.
- **Conséquence pour l'API ?** Contrat inchangé (même JSON, mêmes droits), moins de connexions occupées, fraîcheur bornée à 60 s avec cache, repli sur PostgreSQL si Redis tombe.
- **Pourquoi pas un JOIN ?** Raisonnement, non mesuré : un JOIN répète la commande sur chaque ligne et complique la limite de 20 commandes. Je ne prétends pas qu'il soit plus lent.
- **Le gain est-il un hasard ?** Non : 3 essais alternés, intervalles disjoints, CPU ≈ 50 % dans les deux cas.
- **Au-delà de 20 clients / en production ?** Non testé ; portée : cette machine, ce jeu, 1 à 20 clients.
- **Pourquoi 3 s d'échauffement ?** Mon protocole ; l'écart (×4) dépasse largement la variation entre essais.
- **Risques du cache ?** Copie périmée ≤ 60 s, course entre lecture lente et invalidation (reproduite à la main), stampede (testé, atelier 8), panne Redis (repli PostgreSQL). Jamais de cache sur l'achat.

## Contexte pour une nouvelle session Claude
Projet dans /home/youssef/école (ou copie). Fichiers utiles : SYNTHESE.md, GUIDE_REDACTION_PDF.md, test_compact.pdf (dossier essentiel), Presentation_V1_structure.pdf, Presentation_V2_histoire.pdf, presentation/build_presentations.py (génère les deux PDF), atelier7/8/9 (scripts et résultats). Prochaine tâche demandée : PDF « le secondaire » (dossier complet Atelier 10 : sections A–F, fiche d'identité P-xx, auto-évaluation, checklist, deux réponses, formulation finale).
