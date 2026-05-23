#!/usr/bin/env python3
"""DZFoot GF Worker - Docker mode via docker-py"""
import os, sys, json, time, signal

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STATS_URL = os.getenv("STATS_URL", "http://stats:8000")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
GF_IMAGE = os.getenv("GF_IMAGE", "dzfoot-gf-server:prod")
GF_NETWORK = os.getenv("GF_NETWORK", "dzfoot-backend_default")
WORKER_ID = os.getenv("HOSTNAME", "worker-docker")

print(f"[GF Docker Worker {WORKER_ID}] Starting. Redis: {REDIS_URL}")

import redis
import docker

r = redis.from_url(REDIS_URL)

try:
    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    client.ping()
    print(f"[GF Docker Worker {WORKER_ID}] Docker OK")
except Exception as e:
    print(f"ERROR: Cannot access Docker: {e}")
    sys.exit(1)

running = True

def shutdown(sig, frame):
    global running
    running = False

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

while running:
    try:
        result = r.brpop("gf.spawn", timeout=10)
        if result is None:
            continue
        _, payload_bytes = result
        payload = json.loads(payload_bytes)
        room_id = payload.get("room_id", "")
        token = payload.get("token", "")
        if not room_id or not token:
            continue
        team_a = payload.get("team_a", "default-a")
        team_b = payload.get("team_b", "default-b")
        stadium = payload.get("stadium_id", "default-stadium")
        duration = payload.get("duration", 600)
        mode = payload.get("mode", "vs_ai")
        player_a = payload.get("player_a", "")
        player_b = payload.get("player_b", "")
        match_config = payload.get("match_config", "")
        print(f"[GF Docker Worker {WORKER_ID}] Spawning {room_id} ({team_a} vs {team_b}, {duration}s)")
        cmd = [
            f"--room-id={room_id}", f"--team-a={team_a}", f"--team-b={team_b}",
            f"--stadium={stadium}", f"--duration={duration}", f"--mode={mode}",
            "--broadcast-hz=20", f"--livekit-url={LIVEKIT_URL}",
            f"--livekit-token={token}", f"--stats-url={STATS_URL}",
            f"--redis-url={REDIS_URL}",
        ]
        if player_a: cmd.append(f"--player-a={player_a}")
        if player_b: cmd.append(f"--player-b={player_b}")
        volumes = []
        if match_config and match_config not in ("", "null", None):
            config_path = f"/tmp/gf_{room_id}.json"
            with open(config_path, "w") as f:
                f.write(match_config if isinstance(match_config, str) else json.dumps(match_config))
            volumes.append(f"{config_path}:/tmp/match_config.json:ro")
            cmd.append("--config-file=/tmp/match_config.json")
        env = {"LIVEKIT_URL": LIVEKIT_URL, "LIVEKIT_TOKEN": token,
               "REDIS_URL": REDIS_URL, "STATS_URL": STATS_URL}
        container = client.containers.run(
            image=GF_IMAGE, command=cmd, name=f"gf-{room_id}",
            network=GF_NETWORK, environment=env, volumes=volumes,
            detach=True, remove=True)
        print(f"[GF Docker Worker {WORKER_ID}] Container {container.id[:12]} launched")
        r.publish("gf.ready", room_id)
    except redis.exceptions.ConnectionError as e:
        print(f"[GF Docker Worker {WORKER_ID}] Redis error: {e}")
        time.sleep(5)
        try: r = redis.from_url(REDIS_URL)
        except: pass
    except Exception as e:
        print(f"[GF Docker Worker {WORKER_ID}] Error: {e}")
        time.sleep(1)
