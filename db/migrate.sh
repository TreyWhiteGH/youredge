#!/usr/bin/env bash
# Apply every migration that has not been applied yet, in filename order.
#
# Postgres runs /docker-entrypoint-initdb.d once, on an empty volume. Migrations
# added afterwards never run on an existing volume, so a long-lived dev database
# silently drifts behind the repo. This is the catch-up path.
#
# Migrations are not written to be idempotent (001_init.sql opens with a bare
# CREATE TABLE), so replaying blindly is not an option — we track what has run.
# An existing database is baselined: it got 001..021 from initdb, so those are
# recorded as applied rather than re-executed.
set -euo pipefail

cd "$(dirname "$0")/.."

DB_USER="${POSTGRES_USER:-youredge}"
DB_NAME="${POSTGRES_DB:-youredge}"
BASELINE="021_career_links.sql"   # last migration that shipped before the tracker

# Two databases to reach, and only one of them is a container.
#
# Development runs Postgres in compose as `db`. Production does not: the whole point
# of docker-compose.prod.yml is that the data lives at a managed provider, so there is
# no `db` service to exec into and every psql here failed with "no such service" --
# which meant DEPLOY.md's instruction to run this against the managed URL, both on
# first deploy and on every schema change after, could not work as written.
#
# So: if a URL is given, talk to it through a throwaway psql container; otherwise fall
# back to the compose service. MIGRATE_DATABASE_URL wins over DATABASE_URL so that
# pointing a migration at a Neon branch is a one-off env var rather than an edit.
#
# The engine's DATABASE_URL carries SQLAlchemy's `+asyncpg` driver tag and libpq has
# never heard of it, so it is stripped here rather than requiring a second spelling of
# the same secret in .env.prod.
RAW_URL="${MIGRATE_DATABASE_URL:-${DATABASE_URL:-}}"

# Nothing in this deployment exports DATABASE_URL into a shell -- the services get it
# through compose's `env_file: .env.prod`, so an operator running this by hand has an
# empty environment and silently fell through to the compose path, which then failed
# looking for a `.env` that does not exist. Read the file the services read.
#
# Grepped rather than sourced, deliberately. `.env.prod` holds a bcrypt hash full of
# `$`, and sourcing it would have the shell expand `$2a`, `$14` and whatever follows
# into nothing -- the same class of mangling that commit 3027872 documented for
# Compose, arriving by a different route.
ENV_FILE="${ENV_FILE:-$(dirname "$0")/../.env.prod}"
if [ -z "$RAW_URL" ] && [ -f "$ENV_FILE" ]; then
    RAW_URL=$(sed -n 's/^DATABASE_URL=//p' "$ENV_FILE" | head -1)
    [ -n "$RAW_URL" ] && echo "==> read DATABASE_URL from $(basename "$ENV_FILE")"
fi

DB_URL="${RAW_URL/+asyncpg/}"

# Schema changes go to the direct endpoint, not the pooler.
#
# The engine's DATABASE_URL points at Neon's `-pooler` host, which is right for an
# application making many short queries and wrong for DDL: the pooler multiplexes
# transactions across backends and cannot promise the session semantics a migration
# assumes. .env.prod already records the same distinction for pg_dump, where
# BACKUP_DATABASE_URL exists precisely because "backups need a real session and the
# pooler cannot give one" -- a migration needs one for the same reason.
#
# Neon's own convention is that the direct host is the pooled host without the suffix
# (ep-name-pooler.region -> ep-name.region), which is exactly how the two URLs in
# .env.prod differ. Set MIGRATE_DATABASE_URL to override if that ever stops holding.
if [ -z "${MIGRATE_DATABASE_URL:-}" ] && [[ "$DB_URL" == *-pooler.* ]]; then
    DB_URL="${DB_URL/-pooler./.}"
    echo "==> using the direct (unpooled) endpoint for DDL"
fi

# Pinned to the major version production runs (DEPLOY.md step 1). A newer client is
# fine against an older server, but pinning means the tool that applies a migration is
# never a surprise.
PSQL_IMAGE="${PSQL_IMAGE:-postgres:18-alpine}"

if [ -n "$DB_URL" ]; then
    echo "==> target: managed database (from ${MIGRATE_DATABASE_URL:+MIGRATE_}DATABASE_URL)"
    psql_raw() { docker run --rm -i -e PGCONNECT_TIMEOUT=15 "$PSQL_IMAGE" \
                     psql "$DB_URL" -v ON_ERROR_STOP=1 "$@"; }
else
    echo "==> target: local compose service 'db'"
    psql_raw() { docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" \
                     -v ON_ERROR_STOP=1 "$@"; }
fi

psql() { psql_raw "$@"; }

psql -q -c "CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);"

# Baseline: if the tracker is empty but the schema is populated, this database
# was built by initdb. Record everything up to the baseline without running it.
tracked=$(psql -tAc "SELECT count(*) FROM schema_migrations;")
has_schema=$(psql -tAc "SELECT to_regclass('public.games') IS NOT NULL;")

if [ "$tracked" = "0" ] && [ "$has_schema" = "t" ]; then
    echo "==> existing database detected; baselining through $BASELINE"
    for f in $(ls db/migrations/*.sql | sort); do
        name=$(basename "$f")
        psql -q -c "INSERT INTO schema_migrations (filename) VALUES ('$name')
                    ON CONFLICT DO NOTHING;"
        [ "$name" = "$BASELINE" ] && break
    done
fi

applied=0
for f in $(ls db/migrations/*.sql | sort); do
    name=$(basename "$f")
    seen=$(psql -tAc "SELECT 1 FROM schema_migrations WHERE filename = '$name';")
    [ -n "$seen" ] && continue

    echo "==> applying $name"
    # Fed over stdin rather than read from the container's initdb mount: that
    # mount is fixed when the container starts and points at whichever checkout
    # launched it, which is the wrong file set inside a git worktree.
    #
    # One transaction per migration, with the tracker row appended to the same
    # stream: a failure leaves no half-applied file and no tracker row, so a
    # re-run retries it cleanly.
    { cat "$f"; printf "\nINSERT INTO schema_migrations (filename) VALUES ('%s');\n" "$name"; } \
        | psql_raw --single-transaction -q -f -
    applied=$((applied + 1))
done

if [ "$applied" = "0" ]; then
    echo "==> up to date; nothing to apply"
else
    echo "==> applied $applied migration(s)"
fi
