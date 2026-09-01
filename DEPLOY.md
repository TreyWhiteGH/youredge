# Deploying YourEdge

A single VPS running the engine and the two workers, with the database somewhere
else. That split is the only architectural decision here worth defending: the
box is disposable and the database is not, because `odds_snapshots` records line
movement that cannot be re-fetched at any price and `user_bets` holds quotes
collected by hand from sportsbooks.

Hetzner CPX31 in Ashburn for the compute, Neon for Postgres. Roughly 45 minutes
end to end, most of it waiting for a restore.

Running cost is about **$19-25/mo** for the box, **~$19/mo** for a 10 GB Neon
tier and **~$12/yr** for the domain. Once the reasoning layer is in, the
Anthropic bill will make all three a rounding error -- which is the real reason
not to spend long optimising this part.

---

## 1. Database first

Create a Postgres 16 instance at **Neon**, region **AWS us-east**, to sit near
the Ashburn box. You need about 10 GB: the dump is 126 MB but restores to ~3 GB
and grows with every poll.

Neon over Hetzner's own managed Postgres deliberately. IONOS and most hosts keep
write-ahead logs for seven days, and the failure this data actually faces is not
a dead disk -- it is a bad migration or a `--rebuild` against the wrong URL,
which you might not notice in a week. Neon also branches, so a migration can be
tested against a copy of production before it touches production.

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

**Hetzner Cloud, CPX31, Ashburn (us-east)** — 4 vCPU, 8 GB, 160 GB NVMe, 3 TB
traffic, IPv4 included. Around $19-25/mo after the 2026 price rise; check the
figure at checkout rather than trusting this file. It is more machine than this
needs today and leaves room for the mining jobs.

Ubuntu 24.04. In the Hetzner console, add an SSH key at creation — password
login on a fresh public IP is found by scanners within minutes.

Attach a **cloud firewall** (free, and applied outside the machine so a
misconfigured host cannot undo it):

| Direction | Port | Source |
|---|---|---|
| inbound | 22 | your IP only |
| inbound | 80, 443 | anywhere |

Nothing else. Postgres is not on this box and nothing here listens on 5432 —
if you ever find yourself opening that port, something has gone wrong.

```bash
ssh root@YOUR_IP
apt update && apt install -y docker.io docker-compose-plugin git
git clone https://github.com/TreyWhiteGH/youredge.git && cd youredge
```

Hetzner's Ashburn region and Neon's `aws-us-east-2` are both US East, which
keeps the engine a few milliseconds from its database. Putting the box in
Europe and the database in Virginia would add a transatlantic round trip to
every query, and this engine issues a lot of small ones.

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
