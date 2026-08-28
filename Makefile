.PHONY: up down logs psql redis-cli health ingest-nfl reset-db migrate

# Apply every migration the database has not seen yet (initdb only runs once,
# so an existing volume drifts behind the repo). Idempotent; safe to re-run.
migrate:
	./db/migrate.sh

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

# One sweep: featured markets for every game, plus the per-event tier (props,
# period lines, alternates, team totals) for games whose tier says they are stale.
poll-odds:
	docker compose run --rm ingest python -m youredge.ingest.odds_poller --once

# Featured markets only — no per-event spend. Use when checking the pipeline.
poll-odds-core:
	docker compose run --rm ingest python -m youredge.ingest.odds_poller --once --core-only

# Detached polling loop (interval: ODDS_POLL_INTERVAL_SECONDS).
poll-odds-loop:
	docker compose --profile poller up -d poller

poll-odds-stop:
	docker compose --profile poller stop poller

poll-odds-logs:
	docker compose --profile poller logs -f poller

# NFL play-by-play back to 2016, aligning the NFL window with NCAAF's. 2016 is
# the floor because NGS and air yards start there, so every enriched column the
# 2023+ rows carry exists across the whole range.
backfill-nfl:
	docker compose run --rm ingest python -m youredge.ingest.nfl_pbp --seasons 2016 2017 2018 2019 2020 2021 2022

devig:
	docker compose run --rm ingest python -m youredge.pricing.devig

# Nukes the DB volume and re-runs migrations on next `make up`
reset-db:
	docker compose down -v

ingest-pff:
	docker compose run --rm ingest python -m youredge.ingest.pff

ingest-cfbd-context:
	docker compose run --rm ingest python -m youredge.ingest.cfbd_context --seasons 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 2026

ingest-fcs-coaches:
	docker compose run --rm ingest python -m youredge.ingest.fcs_coaches

ingest-cfbd-history:
	docker compose run --rm ingest python -m youredge.ingest.cfbd_history --seasons 2016 2017 2018 2019 2020 2021 2022

ingest-cfbd-roster:
	docker compose run --rm ingest python -m youredge.ingest.cfbd_roster --seasons 2023 2024 2025 2026

ingest-cfbd-player-stats:
	docker compose run --rm ingest python -m youredge.ingest.cfbd_player_stats --seasons 2023 2024 2025

ingest-venues:
	docker compose run --rm ingest python -m youredge.ingest.venues --seasons 2023 2024 2025 2026

features-ncaaf:
	docker compose run --rm ingest python -m youredge.modeling.features --league ncaaf --seasons 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025

features-nfl:
	docker compose run --rm ingest python -m youredge.modeling.features --league nfl --seasons 2023 2024 2025

# Derive drives from plays (the simulator, script labelling and the leg ledger
# all read this). NFL only; NCAAF is refused until college scoring is derivable.
drives:
	docker compose run --rm ingest python -m youredge.modeling.drives --league nfl

# NCAAF drives come from CFBD /drives (one call per season) — college plays
# cannot express a scoring drive. See ingest/cfbd_drives.py.
drives-ncaaf:
	docker compose run --rm ingest python -m youredge.ingest.cfbd_drives --seasons 2023 2024 2025
