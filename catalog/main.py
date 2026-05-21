import os
import json
from typing import Optional

from fastapi import FastAPI, HTTPException
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


# Load predefined formations from JSON file (inspired by GameplayFootball defaults)
_formations_cache = None

def _load_formations():
    global _formations_cache
    if _formations_cache is None:
        path = os.path.join(os.path.dirname(__file__), "formations.json")
        with open(path, "r", encoding="utf-8") as f:
            _formations_cache = json.load(f)
    return _formations_cache


SKILL_COLS = [
    "physical_balance", "physical_reaction", "physical_acceleration", "physical_velocity",
    "physical_stamina", "physical_agility", "physical_shotpower",
    "technical_standingtackle", "technical_slidingtackle", "technical_ballcontrol",
    "technical_dribble", "technical_shortpass", "technical_highpass", "technical_header",
    "technical_shot", "technical_volley",
    "mental_calmness", "mental_workrate", "mental_resilience",
    "mental_defensivepositioning", "mental_offensivepositioning", "mental_vision"
]


@app.get("/teams/{team_id}/formation")
async def team_formation(team_id: str):
    """Return formation + full player roster with 22 GF skills for a team."""
    key = f"team:{team_id}:formation"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    formations = _load_formations()
    async with async_session() as session:
        row = await session.execute(
            text("SELECT name, formation FROM teams WHERE id=:tid"),
            {"tid": team_id},
        )
        r = row.mappings().first()
        if not r:
            raise HTTPException(status_code=404, detail="Team not found")
        formation_key = r["formation"] or "default"
        team_name = r["name"]

        # Fetch all 11 players with full skill profiles
        cols = ", ".join(SKILL_COLS)
        prow = await session.execute(
            text(f"SELECT id, name, position, number, {cols} FROM players WHERE team_id=:tid ORDER BY number"),
            {"tid": team_id},
        )
        players = []
        for p in prow.mappings().all():
            pd = dict(p)
            players.append({
                "id": str(pd["id"]),
                "name": pd["name"],
                "position": pd["position"],
                "number": pd["number"],
                "skills": {c: float(pd[c]) for c in SKILL_COLS},
            })

    data = formations.get(formation_key, formations["default"]).copy()
    data["team_name"] = team_name
    data["team_id"] = team_id
    data["players"] = players
    await redis.setex(key, CACHE_TTL, json.dumps(data))
    return data


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
