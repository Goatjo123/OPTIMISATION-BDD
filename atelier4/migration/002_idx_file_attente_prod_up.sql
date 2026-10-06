-- Migration 002 (UP, variante DÉPLOIEMENT) : même index, construit sans bloquer les écritures.
-- CREATE INDEX CONCURRENTLY ne s'exécute PAS dans un bloc BEGIN/COMMIT (slide 29) :
-- ne pas l'enrober dans une transaction, et lancer psql sans l'option --single-transaction.
--
-- Une construction interrompue peut laisser un index INVALIDE : on le vérifie et on le supprime
-- avant de réessayer (voir 002_idx_file_attente_verifier.sql).
SET search_path TO shopflow, public;
SET lock_timeout = '5s';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_attente
    ON commandes (created_at, id)
    WHERE statut = 'en_attente';
