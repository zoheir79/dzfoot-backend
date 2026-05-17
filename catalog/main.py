import os
import json
from typing import Optional

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import redis.asyncio as aioredis

app = FastAPI(title="DZFoot Catalog Service")

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
redis: Optional[aioredis.Redis] = None

CACHE_TTL = 3600


@app.on_event("startup")
async def startup():
    global redis
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)


@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
    if redis:
        await redis.close()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "catalog"}


@app.get("/teams")
async def list_teams():
    cached = await redis.get("teams:all")
    if cached:
        return json.loads(cached)
    async with async_session() as session:
        rows = await session.execute(text("SELECT * FROM teams ORDER BY name"))
        result = [dict(r._mapping) for r in rows]
    await redis.setex("teams:all", CACHE_TTL, json.dumps(result))
    return result


@app.get("/teams/{team_id}/players")
async def team_players(team_id: str):
    key = f"team:{team_id}:players"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    async with async_session() as session:
        rows = await session.execute(
            text("SELECT * FROM players WHERE team_id=:tid ORDER BY number"),
            {"tid": team_id},
        )
        result = [dict(r._mapping) for r in rows]
    await redis.setex(key, CACHE_TTL, json.dumps(result))
    return result


@app.get("/stadiums")
async def list_stadiums():
    cached = await redis.get("stadiums:all")
    if cached:
        return json.loads(cached)
    async with async_session() as session:
        rows = await session.execute(text("SELECT * FROM stadiums"))
        result = [dict(r._mapping) for r in rows]
    await redis.setex("stadiums:all", CACHE_TTL, json.dumps(result))
    return result
