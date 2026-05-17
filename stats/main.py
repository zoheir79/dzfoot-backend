import os
import json
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import redis.asyncio as aioredis

app = FastAPI(title="DZFoot Stats Service")

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
redis: Optional[aioredis.Redis] = None


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
    return {"status": "ok", "service": "stats"}


class MatchResult(BaseModel):
    player_a: str
    player_b: str
    team_a: Optional[str]
    team_b: Optional[str]
    stadium: Optional[str]
    score_a: int
    score_b: int
    duration_s: int
    room_id: str
    stats: list


@app.post("/internal/match-result")
async def receive_match_result(result: MatchResult):
    from sqlalchemy import text
    async with async_session() as session:
        match_id = await session.execute(
            text("""
                INSERT INTO matches(player_a_id, player_b_id, team_a_id, team_b_id,
                                    stadium_id, score_a, score_b, duration_s, livekit_room, played_at)
                VALUES(:pa, :pb, :ta, :tb, :st, :sa, :sb, :dur, :room, NOW()) RETURNING id
            """),
            {
                "pa": result.player_a, "pb": result.player_b,
                "ta": result.team_a, "tb": result.team_b, "st": result.stadium,
                "sa": result.score_a, "sb": result.score_b,
                "dur": result.duration_s, "room": result.room_id,
            },
        )
        mid = match_id.scalar()

        for i, pid in enumerate([result.player_a, result.player_b]):
            s = result.stats[i]
            await session.execute(
                text("""
                    INSERT INTO match_stats(match_id, player_id, goals, shots, passes,
                        tackles, yellow_cards, possession_pct, distance_m)
                    VALUES(:mid, :pid, :goals, :shots, :passes, :tackles, :yc, :pos, :dist)
                """),
                {
                    "mid": mid, "pid": pid,
                    "goals": s.get("goals", 0), "shots": s.get("shots", 0),
                    "passes": s.get("passes", 0), "tackles": s.get("tackles", 0),
                    "yc": s.get("yellow_cards", 0), "pos": s.get("possession_pct", 0.0),
                    "dist": s.get("distance_m", 0.0),
                },
            )
        await session.commit()

    await redis.delete("leaderboard:global")
    return {"match_id": str(mid)}


@app.get("/leaderboard")
async def leaderboard(limit: int = 20):
    cached = await redis.get("leaderboard:global")
    if cached:
        return json.loads(cached)

    from sqlalchemy import text
    async with async_session() as session:
        rows = await session.execute(
            text("""
                SELECT u.pseudo, u.elo, u.avatar_url,
                       COUNT(m.id) as matches,
                       SUM(CASE WHEN (m.player_a_id=u.id AND m.score_a>m.score_b)
                                 OR (m.player_b_id=u.id AND m.score_b>m.score_a)
                            THEN 1 ELSE 0 END) as wins
                FROM users u
                LEFT JOIN matches m ON m.player_a_id=u.id OR m.player_b_id=u.id
                GROUP BY u.id ORDER BY u.elo DESC LIMIT :lim
            """),
            {"lim": limit},
        )
        result = [dict(r._mapping) for r in rows]
    await redis.setex("leaderboard:global", 300, json.dumps(result))
    return result


@app.get("/stats/player/{player_id}")
async def player_stats(player_id: str):
    from sqlalchemy import text
    async with async_session() as session:
        row = await session.execute(
            text("""
                SELECT SUM(goals) as total_goals, SUM(shots) as total_shots,
                       AVG(possession_pct) as avg_possession,
                       SUM(distance_m) as total_distance,
                       COUNT(*) as matches_played
                FROM match_stats WHERE player_id=:pid
            """),
            {"pid": player_id},
        )
        return dict(row.mappings().first() or {})
