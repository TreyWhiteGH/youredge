# YourEdge Engine

Deterministic core: ingestion, game-script simulation, SGP pricing, correlation. FastAPI service serving `/api/football/*`.

The LLM layer talks to this service; it never computes odds itself.

## Run

    docker compose up engine        # from repo root
    curl localhost:8000/api/football/health

## Ingestion

    docker compose run --rm ingest python -m youredge.ingest.nfl_pbp --seasons 2023 2024 2025
    docker compose run --rm ingest python -m youredge.ingest.cfbd_pbp --seasons 2023 2024 2025
    docker compose run --rm ingest python -m youredge.ingest.odds_poller --once
