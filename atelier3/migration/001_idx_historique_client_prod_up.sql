-- Migration 001 (UP, variante DÉPLOIEMENT) : même index, construit sans bloquer les écritures.
-- CREATE INDEX CONCURRENTLY ne s'exécute PAS dans un bloc BEGIN/COMMIT (slide 25) :
-- ne pas l'enrober dans une transaction, et lancer psql sans l'option --single-transaction.
--
-- Une construction interrompue peut laisser un index INVALIDE : on le vérifie et on le supprime
-- avant de réessayer (voir 001_idx_historique_client_verifier.sql).
SET search_path TO shopflow, public;
SET lock_timeout = '5s';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hist_client
    ON commandes (client_id, created_at DESC, id DESC);
