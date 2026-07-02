# Deployment Bootstrap

Minimal fallback files used to bootstrap the GitHub Pages research build.

At build time, `mlbmodel.sources.sync_mlbma` replaces the slate, team profiles, starting
pitcher profiles, and pitch-mix data with the current MLBMA sources. The committed files
remain available for local/offline development only.

Production refreshes continue to use `MLBMA_DATA_DIR`; this directory is not a replacement
for the MLBMA pipeline or historical warehouse.
