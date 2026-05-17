# GF Server Worker Pool — VM Scaling Guide

## Architecture

```
Session Service ──► Redis Queue "gf.spawn" ◄── GF Worker Pool (Bare Metal / Cloud VMs)
                      │
                      └── GF Worker #1 (VM-01, 4 vCPU)
                      └── GF Worker #2 (VM-02, 4 vCPU)
                      └── GF Worker #N (VM-N, 4 vCPU)
```

## Why VMs for GF?

- **GF is CPU-intensive**: Physics 60 tick/s for 22 players + ball
- **No container overhead**: Native Linux binary, zero Docker latency
- **Predictable performance**: Dedicated cores, no noisy neighbors
- **Easy to add**: New VM = new worker. No cluster config.

## Worker Setup (per VM)

### 1. Prerequisites

```bash
# Ubuntu 22.04 VM
sudo apt update
sudo apt install -y build-essential cmake libenet-dev libcurl4-openssl-dev
```

### 2. Deploy GF binary

```bash
# Copy from your build machine
scp gf-server-binary user@vm-N:/usr/local/bin/gf_server

# Or clone repo and build
git clone https://github.com/YOUR_ORG/dzfoot-gf-server.git
cd dzfoot-gf-server
mkdir build && cd build
cmake .. && make
sudo cp gf_server /usr/local/bin/
```

### 3. Install worker script

```bash
curl -o /usr/local/bin/gf-worker.sh https://raw.githubusercontent.com/YOUR_ORG/dzfoot-gf-server/main/scripts/gf-worker.sh
chmod +x /usr/local/bin/gf-worker.sh
```

### 4. Systemd service (auto-restart)

```bash
sudo tee /etc/systemd/system/gf-worker.service << 'EOF'
[Unit]
Description=DZFoot GF Worker
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/gf-worker.sh
Restart=always
RestartSec=5
User=ubuntu
Environment="REDIS_URL=redis://YOUR_REDIS_HOST:6379"
Environment="LIVEKIT_URL=wss://your-livekit.com"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gf-worker
sudo systemctl start gf-worker
```

## Worker Script (gf-worker.sh)

```bash
#!/bin/bash
# Polls Redis queue for match spawn requests
# Runs continuously on each GF VM

REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
GF_BINARY="/usr/local/bin/gf_server"

while true; do
    # Block until a spawn request arrives
    REQUEST=$(redis-cli -u "$REDIS_URL" BRPOP "gf.spawn" 10)
    if [ -z "$REQUEST" ]; then
        continue
    fi
    
    # Parse request JSON (simplified)
    ROOM_ID=$(echo "$REQUEST" | jq -r '.room_id')
    TOKEN=$(echo "$REQUEST" | jq -r '.token')
    TEAM_A=$(echo "$REQUEST" | jq -r '.team_a')
    TEAM_B=$(echo "$REQUEST" | jq -r '.team_b')
    DURATION=$(echo "$REQUEST" | jq -r '.duration')
    
    # Spawn GF process
    $GF_BINARY \
        --room-id="$ROOM_ID" \
        --team-a="$TEAM_A" \
        --team-b="$TEAM_B" \
        --duration="$DURATION" \
        --livekit-url="$LIVEKIT_URL" \
        --livekit-token="$TOKEN" \
        --stats-url="http://stats:8000" \
        &
    
    echo "Spawned GF for room $ROOM_ID (PID $!)"
done
```

## Scaling Formula

| Matchs simultanés | VMs GF | vCPU/VM | Total vCPU |
|---|---|---|---|
| 10 | 1 | 4 | 4 |
| 50 | 2 | 8 | 16 |
| 100 | 4 | 8 | 32 |
| 500 | 20 | 8 | 160 |
| 1000 | 40 | 8 | 320 |

**1 VM GF ≈ 20–25 matchs simultanés** (estimation conservatrice).

## Auto-scaling (Cloud)

### Hetzner Cloud example

```bash
# Create new GF worker VM
hcloud server create \
  --type cpx31 \
  --image ubuntu-22.04 \
  --name gf-worker-$(date +%s) \
  --user-data-from-file cloud-init-gf.yml
```

### AWS / Azure / GCP

Use **managed instance groups** or **VM scale sets**:
- Metric: queue depth of `gf.spawn` in Redis
- Scale out: >5 pending requests → +1 VM
- Scale in: <2 pending requests → -1 VM

## Monitoring

```bash
# Check running GF processes per VM
pgrep -c gf_server

# Check Redis queue depth
redis-cli LLEN gf.spawn

# Check VM load
uptime
```
