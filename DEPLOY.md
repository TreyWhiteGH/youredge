# Deploying YourEdge

A single VPS running the engine and the two workers, with the database somewhere
else. That split is the only architectural decision here worth defending: the
box is disposable and the database is not, because `odds_snapshots` records line
movement that cannot be re-fetched at any price and `user_bets` holds quotes
collected by hand from sportsbooks.

Roughly 45 minutes end to end, most of it waiting for a restore.

---

## 1. Database first

Create a Postgres 16 instance at **Neon** or **Supabase**. Pick a US East
region — nflverse, CFBD and The Odds API are all US-hosted and the poller is
chatty. You need about 10 GB; the dump is 126 MB but restores to ~3 GB and
grows with every poll.

Restore your backup into it:

```bash
pg_restore --no-owner --no-acl -d "$MANAGED_URL" backups/youredge_full_YYYYMMDD.dump
bash db/migrate.sh                     # anything newer than the dump
```

`pg_restore` will print errors about extensions and roles it cannot create.
Those are expected on a managed instance and harmless — check the table counts
rather than the exit code:

```bash
psql "$MANAGED_URL" -c "SELECT count(*) FROM odds_snapshots;"   # ~358,000
psql "$MANAGED_URL" -c "SELECT count(*) FROM user_bets;"        # 141
```

**On PFF.** `pff_player_stats` is 1.6 GB of the 2.9 GB and is licensed data. If
you would rather not put it on a third party's infrastructure, exclude it —
five API routes will return empty and nothing else breaks:

```bash
pg_restore --no-owner --no-acl --exclude-table=pff_player_stats -d "$MANAGED_URL" backups/....dump
```

## 2. A domain

Register one (~$12/yr — Cloudflare and Namecheap are both fine). Point an **A
record** at the server's IP once you have it in step 3. DNS has to resolve
before Caddy can get a certificate, so do this early and let it propagate while
you work.

## 3. The box

Hetzner CPX31 (4 vCPU, 8 GB, 160 GB, Ashburn) is about €14/mo and is more
machine than this needs. DigitalOcean's equivalent is ~$48 in NYC.

```bash
ssh root@YOUR_IP
apt update && apt install -y docker.io docker-compose-plugin git
git clone https://github.com/TreyWhiteGH/youredge.git && cd youredge
```

Do not open Postgres ports; nothing here listens on 5432. Only 80 and 443 need
to be reachable.

## 4. Configure

```bash
cp .env.prod.example .env.prod
docker run --rm caddy caddy hash-password --plaintext 'the password you want'
```

Fill in `.env.prod`: the managed `DATABASE_URL` (change the scheme to
`postgresql+asyncpg://` and keep `?sslmode=require`), `SITE_ADDRESS` as
`https://yourdomain.com`, the basic-auth user and the **hash** from above, and
both API keys.

## 5. Up

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f caddy   # watch the certificate issue
```

Then check it end to end:

```bash
curl -u user:password https://yourdomain.com/api/football/health
docker compose -f docker-compose.prod.yml logs --tail 20 results
```

## 6. Backups, which are now yours to keep

Managed Postgres gives you point-in-time restore, which covers the disaster
case. It does not cover *you* — a bad migration replicates instantly. Keep an
independent nightly dump:

```bash
cat > /etc/cron.daily/youredge-backup <<'EOF'
#!/bin/sh
set -e
D=$(date +%Y%m%d)
pg_dump "$DATABASE_URL" --no-owner --no-acl -Fc -f /var/backups/youredge_$D.dump
find /var/backups -name 'youredge_*.dump' -mtime +14 -delete
EOF
chmod +x /etc/cron.daily/youredge-backup
```

Copy those off the box — object storage, or `rsync` to somewhere else. A backup
that lives only on the machine it protects is not a backup.

---

## Working on it while it runs

**The poller runs in exactly one place.** The Odds API budget is monthly and
shared by the key, not by the machine. A laptop polling alongside production
spends the same quota twice and neither will notice. When developing locally,
run `docker compose up -d db engine` only — no poller, no results.

**Develop against your own database.** Restore a dump locally rather than
pointing a dev engine at production. Every ingest in this repo writes, several
rebuild whole tables, and `--rebuild` on the wrong `DATABASE_URL` is a bad
afternoon.

**Deploying a change:**

```bash
git pull && docker compose -f docker-compose.prod.yml build && \
  docker compose -f docker-compose.prod.yml up -d
```

Migrations do not run automatically — `bash db/migrate.sh` against the managed
URL, deliberately, so a schema change is something you decide rather than
something a deploy does to you.

## What this does not have yet

- **No CI.** Deploys are a git pull on the box. `make test` is 15 invariants
  against a live database and would need a database in CI to run.
- **No staging.** One environment. A bad deploy is visible immediately, which
  is survivable at one user and will not stay that way.
- **One instance of everything.** Restarting the engine drops in-flight
  requests. Fine now; the fix is two engine replicas behind Caddy, which is a
  few lines when it matters.
