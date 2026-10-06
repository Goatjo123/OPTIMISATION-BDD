-- Migration 002 (UP) : index partiel de la file des commandes en attente        [Atelier 4, Jour 2]
-- Décision : index partiel (created_at, id) WHERE statut = 'en_attente', voir atelier4/README.md.
-- Version LABORATOIRE : CREATE INDEX ordinaire (slide 29 : le labo peut l'utiliser).
-- Pour un déploiement sans bloquer les écritures, utiliser 002_idx_file_attente_prod_up.sql.
--
-- ATTENTION : l'index ne sert que si la requête contient la condition  statut = 'en_attente'  en LITTÉRAL.
-- Une requête préparée avec un paramètre (statut = $1) peut recevoir un plan générique qui ne le reconnaît pas.
--
-- Exécution : docker exec -i api-postgres-1 psql -U cours -d shopflow -v ON_ERROR_STOP=1 \
--               < atelier4/migration/002_idx_file_attente_up.sql
SET search_path TO shopflow, public;
SET lock_timeout = '5s';   -- slide 32 : limite d'attente d'un verrou, abandon plutôt que file d'attente

CREATE INDEX IF NOT EXISTS idx_attente
    ON commandes (created_at, id)
    WHERE statut = 'en_attente';
