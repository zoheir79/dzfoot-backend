import os
import asyncio
import uuid
import json
from typing import Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis.asyncio as aioredis
from livekit.api import LiveKitAPI, CreateRoomRequest, AccessToken, VideoGrants

app = FastAPI(title="DZFoot Session Service")

LK_URL = os.getenv("LIVEKIT_URL", "")
LK_KEY = os.getenv("LIVEKIT_API_KEY", "")
LK_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
GF_BINARY_PATH = os.getenv("GF_BINARY_PATH", "/usr/local/bin/gf_server")
STATS_SERVICE_URL = os.getenv("STATS_SERVICE_URL", "")
GF_SPAWN_TIMEOUT = int(os.getenv("GF_SPAWN_TIMEOUT", "30"))  # seconds to wait for GF ready
GF_MATCH_TIMEOUT = int(os.getenv("GF_MATCH_TIMEOUT", "900"))  # max match duration + buffer

redis: Optional[aioredis.Redis] = None
lkapi: Optional[LiveKitAPI] = None
active_matches: dict = {}


@app.on_event("startup")
async def startup():
    global redis, lkapi
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    lkapi = LiveKitAPI(url=LK_URL, api_key=LK_KEY, api_secret=LK_SECRET)
    # Start background listeners
    asyncio.create_task(listen_gf_ready())
    asyncio.create_task(listen_gf_crashed())
    asyncio.create_task(listen_gf_finished())
    asyncio.create_task(check_worker_health())
    asyncio.create_task(check_match_timeouts())


@app.on_event("shutdown")
async def shutdown():
    if redis:
        await redis.close()


# === Circuit: Listen for GF ready signal ===
async def listen_gf_ready():
    """Listen for GF servers announcing they are ready to handle a match."""
    pubsub = redis.pubsub()
    await pubsub.subscribe("gf.ready")
    async for message in pubsub.listen():
        if message["type"] == "message":
            room_id = message["data"]
            if room_id in active_matches:
                active_matches[room_id]["status"] = "running"
                active_matches[room_id]["gf_ready_at"] = datetime.utcnow().isoformat()
                print(f"[Session] GF ready for room {room_id}")


# === Circuit: Listen for GF crashes ===
async def listen_gf_crashed():
    """Listen for GF server crashes and handle recovery."""
    pubsub = redis.pubsub()
    await pubsub.subscribe("gf.crashed")
    async for message in pubsub.listen():
        if message["type"] == "message":
            room_id = message["data"]
            print(f"[Session] GF crashed for room {room_id}")
            if room_id in active_matches:
                active_matches[room_id]["status"] = "crashed"
                active_matches[room_id]["crashed_at"] = datetime.utcnow().isoformat()
                # Option: requeue for respawn or notify players
                await redis.publish("match.crashed", room_id)
                # Cleanup after notification
                await asyncio.sleep(60)  # Give clients time to handle
                active_matches.pop(room_id, None)
                await redis.delete(f"room:{room_id}")


# === Circuit: Listen for GF match finished ===
async def listen_gf_finished():
    """Listen for GF servers finishing matches normally."""
    pubsub = redis.pubsub()
    await pubsub.subscribe("gf.finished")
    async for message in pubsub.listen():
        if message["type"] == "message":
            room_id = message["data"]
            print(f"[Session] GF finished for room {room_id}")
            if room_id in active_matches:
                active_matches[room_id]["status"] = "finished"
                active_matches[room_id]["finished_at"] = datetime.utcnow().isoformat()
                await redis.publish("match.finished", room_id)
                active_matches.pop(room_id, None)
                await redis.delete(f"room:{room_id}")


# === Circuit: Check worker health (detect dead VMs) ===
async def check_worker_health():
    """Periodically check if GF workers are still alive via heartbeat."""
    while True:
        await asyncio.sleep(30)
        now = datetime.utcnow().timestamp()
        workers = await redis.hgetall("gf.workers")
        for worker_id, last_seen in workers.items():
            if now - int(last_seen) > 60:  # No heartbeat for 60s
                print(f"[Session] Worker {worker_id} appears dead")
                # Find matches assigned to this worker
                worker_map = await redis.hgetall("gf.worker_map")
                for room_id, w_id in worker_map.items():
                    if w_id == worker_id:
                        print(f"[Session] Room {room_id} may be orphaned")
                        await redis.publish("gf.crashed", room_id)
                await redis.hdel("gf.workers", worker_id)


# === Circuit: Check match timeouts (stuck matches) ===
async def check_match_timeouts():
    """Kill matches that exceed maximum duration + buffer."""
    while True:
        await asyncio.sleep(60)
        for room_id, match_info in list(active_matches.items()):
            started_at = match_info.get("started_at")
            duration = match_info.get("duration", 600)
            if started_at:
                elapsed = (datetime.utcnow() - datetime.fromisoformat(started_at)).total_seconds()
                if elapsed > duration + GF_MATCH_TIMEOUT:
                    print(f"[Session] Match {room_id} timed out")
                    await redis.publish("gf.crashed", room_id)
                    active_matches.pop(room_id, None)


class CreateMatchRequest(BaseModel):
    player_a: str
    player_b: str
    team_a: Optional[str] = None
    team_b: Optional[str] = None
    stadium_id: Optional[str] = None
    duration: int = 600  # seconds (default 10 min)


@app.post("/internal/create-match")
async def create_match(req: CreateMatchRequest):
    room_id = f"match-{uuid.uuid4()}"

    # 1. Create LiveKit room
    await lkapi.room.create_room(
        CreateRoomRequest(name=room_id, max_participants=10, empty_timeout=300)
    )

    # 2. Generate token for GF server (identity="gf-server")
    gf_token = (
        AccessToken(LK_KEY, LK_SECRET)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_id,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .with_identity("gf-server")
        .to_jwt()
    )

    # 3. Spawn GF — local subprocess (dev) OR Redis queue (prod VM pool)
    spawn_mode = os.getenv("GF_SPAWN_MODE", "local")  # "local" or "queue"
    
    if spawn_mode == "queue":
        # Publish to Redis queue for GF worker pool (VMs)
        spawn_request = {
            "room_id": room_id,
            "token": gf_token,
            "team_a": req.team_a or "default-a",
            "team_b": req.team_b or "default-b",
            "stadium_id": req.stadium_id or "default-stadium",
            "duration": req.duration,
        }
        await redis.lpush("gf.spawn", str(spawn_request))
        active_matches[room_id] = {"queued": True, "players": [req.player_a, req.player_b]}
    else:
        # Local subprocess (single-node dev)
        proc = await asyncio.create_subprocess_exec(
            GF_BINARY_PATH,
            f"--room-id={room_id}",
            f"--team-a={req.team_a or 'default-a'}",
            f"--team-b={req.team_b or 'default-b'}",
            f"--stadium={req.stadium_id or 'default-stadium'}",
            f"--duration={req.duration}",
            f"--livekit-url={LK_URL}",
            f"--livekit-token={gf_token}",
            f"--stats-url={STATS_SERVICE_URL}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        active_matches[room_id] = {"proc": proc, "pid": proc.pid, "players": [req.player_a, req.player_b]}
        asyncio.create_task(monitor_process(room_id, proc))

    # 4. Store match info in Redis (short TTL for matchmaking polling)
    match_info = {
        "room_id": room_id,
        "livekit_url": LK_URL,
        "players": [req.player_a, req.player_b],
    }
    await redis.setex(f"match:{req.player_a}", 120, str(match_info))
    await redis.setex(f"match:{req.player_b}", 120, str(match_info))
    await redis.setex(f"room:{room_id}", 3600, str(match_info))

    return {"room_id": room_id, "livekit_url": LK_URL}


async def monitor_process(room_id: str, proc: asyncio.subprocess.Process):
    await proc.wait()
    active_matches.pop(room_id, None)
    await redis.publish("match.finished", room_id)
    await redis.delete(f"room:{room_id}")


@app.get("/health")
async def health():
    return {"status": "ok", "active_matches": len(active_matches)}
