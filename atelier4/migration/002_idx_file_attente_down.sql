-- Migration 002 (DOWN) : retour arrière. Supprime uniquement l'index ajouté par la migration 002.
-- Ne touche à aucun index de contrainte ni à l'index idx_hist_client de la migration 001.
-- En production, remplacer par DROP INDEX CONCURRENTLY IF EXISTS shopflow.idx_attente;
SET lock_timeout = '5s';
DROP INDEX IF EXISTS shopflow.idx_attente;
