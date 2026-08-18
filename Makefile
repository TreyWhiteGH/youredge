.PHONY: up down logs psql redis-cli health ingest-nfl reset-db migrate

# Apply migrations added after the volume was created (001 ran via initdb)
migrate:
	docker compose exec db psql -U youredge -d youredge -f /docker-entrypoint-initdb.d/002_markets_null_unique.sql
	docker compose exec db psql -U youredge -d youredge -f /docker-entrypoint-initdb.d/003_snapshot_nullable_price.sql

up:
	docker compose up -d db redis engine

down:
	docker compose down

logs:
	docker compose logs -f engine

psql:
	docker compose exec db psql -U youredge -d youredge

redis-cli:
	docker compose exec redis redis-cli

health:
	curl -s localhost:8000/api/football/health | python3 -m json.tool

ingest-nfl:
	docker compose run --rm ingest python -m youredge.ingest.nfl_pbp --seasons 2023 2024 2025

ingest-cfbd:
	docker compose run --rm ingest python -m youredge.ingest.cfbd_pbp --seasons 2023 2024 2025

ingest-all: ingest-nfl ingest-cfbd

# Current-season schedules (future games — required for odds event resolution)
schedules:
	docker compose run --rm ingest python -m youredge.ingest.schedules --season 2026

ingest-snaps:
	docker compose run --rm ingest python -m youredge.ingest.snaps_depth --seasons 2023 2024 2025 --depth-season 2026

ingest-players:
	docker compose run --rm ingest python -m youredge.ingest.players

poll-odds:
	docker compose run --rm ingest python -m youredge.ingest.odds_poller --once

devig:
	docker compose run --rm ingest python -m youredge.pricing.devig

# Nukes the DB volume and re-runs migrations on next `make up`
reset-db:
	docker compose down -v
