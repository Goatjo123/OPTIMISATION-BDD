-- Migration 001 (UP) : index de l'historique client                       [Atelier 3, Jour 2]
-- Décision : index composé (client_id, created_at DESC, id DESC), voir atelier3/README.md.
-- Version LABORATOIRE : CREATE INDEX ordinaire (slide 29 : le labo peut l'utiliser).
-- Pour un déploiement sans bloquer les écritures, utiliser 001_idx_historique_client_prod_up.sql.
--
-- Exécution : docker exec -i api-postgres-1 psql -U cours -d shopflow -v ON_ERROR_STOP=1 \
--               < atelier3/migration/001_idx_historique_client_up.sql
SET search_path TO shopflow, public;
SET lock_timeout = '5s';   -- slide 32 : limite d'attente d'un verrou, abandon plutôt que file d'attente

CREATE INDEX IF NOT EXISTS idx_hist_client
    ON commandes (client_id, created_at DESC, id DESC);
