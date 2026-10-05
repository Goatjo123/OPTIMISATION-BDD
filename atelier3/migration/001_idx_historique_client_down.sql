-- Migration 001 (DOWN) : retour arrière. Supprime uniquement l'index ajouté par la migration 001.
-- Ne touche à aucun index de contrainte (en particulier l'index unique (client_id, cle_idempotence)).
-- En production, remplacer par DROP INDEX CONCURRENTLY IF EXISTS shopflow.idx_hist_client;
SET lock_timeout = '5s';
DROP INDEX IF EXISTS shopflow.idx_hist_client;
