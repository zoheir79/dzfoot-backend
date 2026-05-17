# DZFoot Scaling — Summary

## Two deployment modes

### Mode 1: Single Node (default) — `GF_SPAWN_MODE=local`

Everything runs on one machine. GF server spawned as local subprocess.

```bash
cp .env.example .env
# GF_SPAWN_MODE=local (already default)
docker-compose up --build -d
```

Services: 1× each (account, session, matchmaking, stats, catalog, postgres, redis, nginx)
GF: spawned locally by Session Service via `asyncio.subprocess`

**Capacity**: ~20 concurrent matches on a 4 vCPU VM.

### Mode 2: Distributed — `GF_SPAWN_MODE=queue`

Backend services in Docker. GF servers on dedicated bare-metal/cloud VMs.

```bash
# Backend
cp .env.example .env
# Edit: GF_SPAWN_MODE=queue
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up \
  --scale account=3 --scale session=3 \
  --scale matchmaking=2 --scale stats=2 --scale catalog=2 \
  -d

# GF Workers (on separate VMs)
# See GF_WORKER.md for setup
```

**Backend services**: scaled via Docker Compose (`--scale service=N`)
**GF servers**: scaled by adding/removing VMs with `gf-worker.sh`

## Scripts provided

| Script | Purpose | Repo |
|---|---|---|
| `scale.sh` | Scale Docker services on demand | `dzfoot-backend/` |
| `scripts/healthcheck.sh` | Check all services health | `dzfoot-backend/scripts/` |
| `scripts/gf-worker.sh` | Poll Redis queue and spawn GF (per VM) | `dzfoot-gf-server/scripts/` |

## Scaling commands

### Scale backend services

```bash
# Scale to 3 account + 3 session
./scale.sh account=3 session=3

# Scale all at once
./scale.sh account=3 session=3 matchmaking=2 stats=2 catalog=2
```

### Scale GF workers (VMs)

```bash
# On each new VM:
sudo systemctl start gf-worker

# Or cloud auto-scale:
hcloud server create --type cpx31 --name gf-worker-N
```

## Monitoring

```bash
# Docker services
docker-compose ps
docker stats

# GF workers (on VM)
pgrep -c gf_server
redis-cli LLEN gf.spawn

# Full health check
./scripts/healthcheck.sh
```
