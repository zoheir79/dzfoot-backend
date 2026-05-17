import os
import asyncio
import json
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
import redis.asyncio as aioredis
import httpx

app = FastAPI(title="DZFoot Matchmaking Service")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SESSION_URL = os.getenv("SESSION_URL", "http://localhost:8002")
ACCOUNT_URL = os.getenv("ACCOUNT_URL", "http://localhost:8001")

redis: Optional[aioredis.Redis] = None


@app.on_event("startup")
async def startup():
    global redis
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)


@app.on_event("shutdown")
async def shutdown():
    if redis:
        await redis.close()


class QueueRequest(BaseModel):
    stadium_pref: Optional[str] = None


async def get_current_user_id(token: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{ACCOUNT_URL}/profile", headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise HTTPException(401, "Invalid token")
    return resp.json()["id"]


@app.post("/queue/join")
async def join_queue(req: QueueRequest, authorization: str = Header(...)):
    user_id = await get_current_user_id(authorization.replace("Bearer ", ""))
    async with httpx.AsyncClient() as client:
        profile = await client.get(f"{ACCOUNT_URL}/profile", headers={"Authorization": authorization})
    elo = profile.json()["elo"]

    # Add to Redis sorted set with ELO as score
    member = f"{user_id}:{req.stadium_pref or 'any'}"
    await redis.zadd("queue:global", {member: elo})

    asyncio.create_task(try_match(user_id, elo, authorization, req.stadium_pref or 'any'))
    return {"status": "waiting"}


async def try_match(player_id: str, elo: int, auth_header: str, stadium_pref: str):
    await asyncio.sleep(3)
    candidates = await redis.zrangebyscore("queue:global", elo - 200, elo + 200)
    candidates = [c for c in candidates if not c.startswith(player_id)]
    if not candidates:
        return

    opponent_entry = candidates[0]
    opponent_id = opponent_entry.split(":")[0]

    # Remove both from queue (exact members, not wildcards)
    await redis.zrem("queue:global", opponent_entry)
    await redis.zrem("queue:global", f"{player_id}:{stadium_pref}")

    # Create match via Session Service
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SESSION_URL}/internal/create-match",
            json={"player_a": player_id, "player_b": opponent_id},
        )
    match_info = resp.json()

    # Notify both players via Redis
    await redis.setex(f"match:{player_id}", 120, json.dumps(match_info))
    await redis.setex(f"match:{opponent_id}", 120, json.dumps(match_info))


@app.get("/queue/status")
async def queue_status(authorization: str = Header(...)):
    user_id = await get_current_user_id(authorization.replace("Bearer ", ""))
    match = await redis.get(f"match:{user_id}")
    if match:
        return {"status": "matched", **json.loads(match)}
    in_queue = await redis.zscore("queue:global", f"{user_id}:*")
    if in_queue is not None:
        return {"status": "waiting"}
    return {"status": "idle"}

