# Scaling DZFoot Backend — Docker Compose (No K8s)

## Quick Scale

```bash
# Start with 3 replicas of account/session, 2 of others
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up \
  --scale account=3 \
  --scale session=3 \
  --scale matchmaking=2 \
  --scale stats=2 \
  --scale catalog=2 \
  -d
```

## How it works

Docker Compose DNS automatically load-balances across all containers of the same service name. When you `--scale account=3`, Docker creates:
- `account_1`, `account_2`, `account_3`
- DNS `account` resolves to all 3 IPs (round-robin)

`nginx` upstream `account_backend` → `server account:8000;` gets all 3 IPs via Docker DNS.

## Resource limits per service (prod override)

| Service | CPU limit | RAM limit | Replicas |
|---|---|---|---|
| account | 0.5 | 256 MB | 3 |
| session | 0.5 | 256 MB | 3 |
| matchmaking | 0.5 | 256 MB | 2 |
| stats | 0.5 | 256 MB | 2 |
| catalog | 0.5 | 256 MB | 2 |
| postgres | 2.0 | 2 GB | 1 |
| redis | 1.0 | 512 MB | 1 |
| nginx | 0.5 | 128 MB | 1 |

## GF Server Pool (future)

Currently Session Service spawns GF via local subprocess. For true scaling:

1. **Session Service** publishes match request to Redis queue
2. **GF Workers** (separate VMs or containers) consume from queue and start GF processes
3. Workers report back match room_id via Redis

```
Session Service ──► Redis Queue "gf.spawn" ◄── GF Worker Pool (VMs with GF binary)
```

This keeps GF on bare metal / high-CPU VMs while backend services stay containerized.

## Horizontal scaling formula

| Players concurrent | Backend replicas | GF VMs |
|---|---|---|
| 100 (50 matches) | 2 each | 2 (4 vCPU each) |
| 1,000 (500 matches) | 5 each | 20 |
| 10,000 (5k matches) | 10 + PG replica | 200 |

## Monitoring

```bash
# Watch container stats
docker stats

# Check nginx upstream health
curl http://localhost:8080/health
```
