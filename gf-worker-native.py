#!/usr/bin/env python3
"""DZFoot GF Worker — Native binary mode for dedicated GF VM.

Runs on VM 102.220.31.37 (or any VM with the compiled gf_server binary).
Connects to Redis on the backend VM (102.220.31.70:6379), consumes gf.spawn
queue, launches the GF binary natively, and reports status back via Redis pubsub.

Usage on the GF VM:
    export REDIS_URL=redis://102.220.31.70:6379
    export GF_BINARY_PATH=/usr/local/bin/gf_server
    export STATS_URL=http://102.220.31.70:8004
    python3 gf-worker-native.py
"""

import os
import sys
import json
import time
import signal
import threading
import subprocess

REDIS_URL = os.getenv("REDIS_URL", "redis://192.168.199.134:6379")
STATS_URL = os.getenv("STATS_URL", "http://192.168.199.134:8004")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "https://orch.adexgenie.ai")
GF_BINARY = os.getenv("GF_BINARY_PATH", "/usr/local/bin/gf_server")
WORKER_ID = os.getenv("HOSTNAME", "worker-native")

print(f"[GF Native Worker {WORKER_ID}] Starting. Redis: {REDIS_URL}")

import redis

r = redis.from_url(REDIS_URL)

running = True
processes = {}  # room_id -> subprocess.Popen


def shutdown(sig, frame):
    global running
    running = False
    for proc in processes.values():
        proc.terminate()


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def cleanup_listener():
    """Listen to gf.crashed / gf.finished and kill matching native processes."""
    cleanup_r = redis.from_url(REDIS_URL)
    pubsub = cleanup_r.pubsub()
    pubsub.subscribe("gf.crashed", "gf.finished")
    print(f"[GF Native Worker {WORKER_ID}] Cleanup listener started", flush=True)
    for message in pubsub.listen():
        if not running:
            break
        if message["type"] != "message":
            continue
        try:
            raw = message["data"]
            room_id = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if room_id in processes:
                proc = processes[room_id]
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                print(
                    f"[GF Native Worker {WORKER_ID}] Terminated/Killed process for {room_id}",
                    flush=True,
                )
                del processes[room_id]
        except Exception as e:
            print(f"[GF Native Worker {WORKER_ID}] Cleanup error: {e}", flush=True)


threading.Thread(target=cleanup_listener, daemon=True).start()


def monitor_process(proc: subprocess.Popen, room_id: str, log_file):
    """Wait for process exit and publish status to Redis."""
    try:
        exit_code = proc.wait()
        print(
            f"[GF Native Worker {WORKER_ID}] {room_id} exited (code {exit_code})",
            flush=True,
        )
        processes.pop(room_id, None)
        try:
            log_file.close()
        except Exception:
            pass
        if exit_code != 0:
            try:
                crash_log_path = os.path.join("/var/log/dzfoot/gf", f"gf_{room_id}.log")
                with open(crash_log_path, "r", encoding="utf-8", errors="replace") as f:
                    logs = f.read(2000)
                print(
                    f"[GF Native Worker {WORKER_ID}] {room_id} logs:\n{logs}",
                    flush=True,
                )
            except Exception:
                pass
            r.publish("gf.crashed", room_id)
        else:
            r.publish("gf.finished", room_id)
    except Exception as e:
        print(f"[GF Native Worker {WORKER_ID}] Monitor error: {e}", flush=True)


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

        # Write match config to disk if provided
        match_config = payload.get("match_config", "")
        config_path = None
        if match_config:
            config_path = f"/tmp/gf_{room_id}.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(match_config, f)

        cmd = [
            GF_BINARY,
            f"--room-id={room_id}",
            f"--team-a={payload.get('team_a', 'default-a')}",
            f"--team-b={payload.get('team_b', 'default-b')}",
            f"--stadium={payload.get('stadium_id', 'default-stadium')}",
            f"--duration={payload.get('duration', 600)}",
            f"--mode={payload.get('mode', 'vs_ai')}",
            "--broadcast-hz=20",
            f"--livekit-url={LIVEKIT_URL}",
            f"--livekit-token={token}",
            f"--stats-url={STATS_URL}",
            f"--redis-url={REDIS_URL}",
        ]
        if payload.get("player_a"):
            cmd.append(f"--player-a={payload['player_a']}")
        if payload.get("player_b"):
            cmd.append(f"--player-b={payload['player_b']}")
        if config_path:
            cmd.append(f"--config-file={config_path}")

        env = os.environ.copy()
        env["LIVEKIT_URL"] = LIVEKIT_URL
        env["LIVEKIT_TOKEN"] = token
        env["REDIS_URL"] = REDIS_URL
        env["STATS_URL"] = STATS_URL

        print(
            f"[GF Native Worker {WORKER_ID}] Spawning {room_id}",
            flush=True,
        )
        log_dir = "/var/log/dzfoot/gf"
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"gf_{room_id}.log")
        try:
            log_file = open(log_path, "w")
        except OSError as e:
            print(
                f"[GF Native Worker {WORKER_ID}] FAILED to open log {log_path}: {e}",
                flush=True,
            )
            raise
        print(
            f"[GF Native Worker {WORKER_ID}] Log file: {log_path}",
            flush=True,
        )
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
        )
        processes[room_id] = proc

        # Quick health-check after 5 seconds
        time.sleep(5)
        if proc.poll() is not None:
            try:
                log_file.close()
            except Exception:
                pass
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    logs = f.read(4000)
                print(
                    f"[GF Native Worker {WORKER_ID}] CRASH for {room_id}!\n{logs}",
                    flush=True,
                )
            except Exception:
                pass
            r.publish("gf.crashed", room_id)
            processes.pop(room_id, None)
            continue

        r.publish("gf.ready", room_id)
        print(
            f"[GF Native Worker {WORKER_ID}] {room_id} ready (PID {proc.pid})",
            flush=True,
        )

        # Monitor exit in background
        threading.Thread(
            target=monitor_process,
            args=(proc, room_id, log_file),
            daemon=True,
        ).start()

    except redis.exceptions.ConnectionError as e:
        print(f"[GF Native Worker {WORKER_ID}] Redis error: {e}")
        time.sleep(5)
        try:
            r = redis.from_url(REDIS_URL)
        except Exception:
            pass
    except Exception as e:
        print(f"[GF Native Worker {WORKER_ID}] Error: {e}")
        time.sleep(1)
