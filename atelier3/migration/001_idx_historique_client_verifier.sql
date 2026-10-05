-- Contrôles après la migration 001 (lecture seule).
SET search_path TO shopflow, public;

-- 1. L'index existe-t-il et est-il VALIDE ? (indisvalid doit valoir t)
SELECT c.relname AS index, i.indisvalid AS valide, i.indisready AS pret,
       pg_size_pretty(pg_relation_size(c.oid)) AS taille
FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
WHERE c.relname = 'idx_hist_client';

-- 2. Y a-t-il un index invalide dans le schéma ? (doit renvoyer 0 ligne)
SELECT c.relname AS index_invalide
FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'shopflow' AND NOT i.indisvalid;

-- 3. Le plan utilise-t-il l'index, sans Sort ? (requête exacte de l'API, qualificatif commandes. inclus)
EXPLAIN (ANALYZE, BUFFERS)
SELECT id::text AS id,
       to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS created_at,
       statut, total::text AS total
FROM shopflow.commandes AS commandes
WHERE client_id = 42
ORDER BY commandes.created_at DESC, commandes.id DESC
LIMIT 21;
