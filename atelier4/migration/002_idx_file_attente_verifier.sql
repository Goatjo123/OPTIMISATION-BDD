-- Contrôles après la migration 002 (lecture seule).
SET search_path TO shopflow, public;

-- 1. L'index existe-t-il, est-il VALIDE, et que vaut son prédicat ? (indisvalid doit valoir t)
SELECT c.relname AS index, i.indisvalid AS valide, i.indisready AS pret,
       pg_size_pretty(pg_relation_size(c.oid)) AS taille,
       pg_get_expr(i.indpred, i.indrelid) AS predicat
FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
WHERE c.relname = 'idx_attente';

-- 2. Y a-t-il un index invalide dans le schéma ? (doit renvoyer 0 ligne)
SELECT c.relname AS index_invalide
FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'shopflow' AND NOT i.indisvalid;

-- 3. Requête avec le statut en LITTÉRAL : doit utiliser idx_attente (Index Only Scan, sans Sort).
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM shopflow.commandes
WHERE statut = 'en_attente'
ORDER BY created_at, id
LIMIT 100;

-- 4. Même requête PARAMÉTRÉE avec un plan générique forcé : l'index partiel n'est PAS utilisé (Seq Scan).
--    C'est le piège de la slide 13 : l'application doit émettre le littéral, ou garder un plan spécifique.
SET plan_cache_mode = force_generic_plan;
PREPARE q_attente(text) AS
  SELECT id FROM shopflow.commandes WHERE statut = $1 ORDER BY created_at, id LIMIT 100;
\echo '--- requête paramétrée, plan générique forcé ---'
EXPLAIN (ANALYZE, BUFFERS) EXECUTE q_attente('en_attente');
DEALLOCATE q_attente;
RESET plan_cache_mode;
