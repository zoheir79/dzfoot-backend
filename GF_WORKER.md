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
Environment="STATS_URL=http://stats:8000"
Environment="GF_BINARY=/usr/local/bin/gf_server"
Environment="LOG_DIR=/var/log/dzfoot"
Environment="HEARTBEAT_INTERVAL=10"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gf-worker
sudo systemctl start gf-worker
```

## Worker Script

The actual `gf-worker.sh` is maintained in the `dzfoot-gf-server` repo and includes heartbeat, crash detection, and proper process monitoring. **Do not copy the old snippet below — use the real file:**

```bash
# Copy from dzfoot-gf-server repo
curl -o /usr/local/bin/gf-worker.sh \
  https://raw.githubusercontent.com/zoheir79/dzfoot-gf-server/main/scripts/gf-worker.sh
chmod +x /usr/local/bin/gf-worker.sh
```

Features of the real script:
- Heartbeat loop (`gf.workers` hash in Redis)
- `BRPOP` queue polling with 10s timeout
- `nohup` + subshell structured spawn
- Watchdog with `wait "$PID"` for real exit codes
- Publishes `gf.ready`, `gf.crashed`, `gf.finished`
- Cleanup on SIGTERM (kill all active GF processes)

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
