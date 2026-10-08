# Atelier 9 et Jour 5 : monitorer et prouver les gains

Produit : **`../test.pdf`** (71 pages) = le PDF principal (59 pages, identiques) + le chapitre « Jour 5 » (pages 60 à 67) + l'annexe 11 (pages 68 à 71). `Atelier1_Diagnostic_compact.pdf` n'est pas modifié.

Tous les tests lourds tournent sur une **copie jetable** (conteneur `a9-pg`, même image PostgreSQL 18.6, mêmes réglages, **mêmes données : empreintes md5 de `commandes` et `lignes` identiques**, `pg_stat_statements` actif), supprimée à la fin. Le laboratoire n'est modifié par aucun test (lectures seules et `EXPLAIN` annulés ; vérifié par empreinte).

| Script | Rôle | Durée |
|---|---|---|
| `p1_diagnostics.py` | `pg_stat_statements`, journal lent, `pg_stat_activity`, `work_mem`, `effective_cache_size`, VACUUM et transaction longue | ≈ 2 min |
| `p1b_workmem.py` | `work_mem` 4 MB contre 32 MB en tours alternés ; surcoût de `pg_stat_statements` | ≈ 1 min |
| `p1c_slowlog.py` | relit le journal du conteneur et classe les lignes « duration: » | secondes |
| `p2_charge.py` | courbe de charge 1/5/10/20 clients : A SQL (index), B HTTP (N+1 / groupé), C pool, D charge fermée / ouverte, E OLTP contre rapport | ≈ 16 min |
| `p3_export.py` | export de la slide 28 + contrôles du contrat + CSV (`export/commandes_journalieres.csv`) | secondes |
| `loadgen.mjs` | générateur de charge HTTP fermée ou ouverte (latence comptée depuis l'arrivée prévue) | — |
| `common.py` | sessions `psql`, médianes, percentiles, machine | — |

Résultats bruts : `resultats/*.json` (chaque essai, avec CPU, file du pool, sessions PostgreSQL). Les journaux de latence par transaction de `pgbench` ne sont pas conservés (volume).

## Résultats principaux (8 cœurs, 7,6 Go, WSL2 ; 10 s par essai, 3 essais alternés)

| Changement (un seul par série) | Avant → après à 20 clients |
|---|---|
| Index composé (SQL, pgbench) | 14 840 → 25 133 tps (×1,7) ; p95 2,8 → 1,5 ms |
| Chargement groupé (HTTP) | 246,9 → 1 032,1 req/s (×4,2) ; p95 98,0 → 26,8 ms ; 0 erreur |
| Pool de l'API 5 → 20 (N+1) | file du pool 15 → 0 ; débit 137–216 → 276–299 req/s (2 essais, **indicatif**) |
| Charge ouverte (N+1) à 90 % puis 130 % du débit fermé | instable puis effondrement (503) ; la charge fermée (0 erreur) **masque** la saturation |
| Rapports analytiques concurrents | p95 des commandes +64 %, p99 ×2,2 ; médiane inchangée |
| `work_mem` 4 → 32 MB | agrégation mensuelle 84,0 → 53,5 ms (tri disque 3 040 kB → mémoire) ; requête de la slide 13 : pas de débordement, aucun effet |
| `effective_cache_size` | aucun changement de plan (8 sélectivités × 4 valeurs) : réglage non justifié |
| VACUUM | bloqué par une transaction longue (0 supprimée, 200 000 mortes non supprimables) ; 200 000 supprimées après son COMMIT |

`pg_stat_statements` : le N+1 pèse 369 ms cumulés (20 000 appels de 0,018 ms) mais 14,2 ms de `sqlMs` par page côté API : son coût est dans les allers-retours, que PostgreSQL ne compte pas ; il est **absent** du journal des requêtes lentes.

## Limites

Une seule machine (PostgreSQL, API et générateur de charge ensemble), jeu synthétique de 100 000 commandes, essais de 10 s ; séries C (2 essais) et D (comportement bimodal) signalées instables ; clients très actifs non testés ; plusieurs instances d'API non testées ; Lakehouse et Data Mesh **conçus, non déployés** (non demandé) ; ingestion incrémentale non implémentée ; dates des données jusqu'au 2026-10-27 (la règle de « journée provisoire » n'est pas testable). L'Atelier 10 (restitution) n'est pas fait.
