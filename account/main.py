import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
import asyncpg
import redis.asyncio as aioredis
from livekit.api import AccessToken, VideoGrants

app = FastAPI(title="DZFoot Account Service")
pwd_ctx = CryptContext(schemes=["bcrypt"])
security = HTTPBearer()

# Config
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
LK_URL = os.getenv("LIVEKIT_URL", "")
LK_KEY = os.getenv("LIVEKIT_API_KEY", "")
LK_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Connections
pool: Optional[asyncpg.Pool] = None
redis: Optional[aioredis.Redis] = None


@app.on_event("startup")
async def startup():
    global pool, redis
    pool = await asyncpg.create_pool(DATABASE_URL)
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)


@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()
    if redis:
        await redis.close()


class RegisterRequest(BaseModel):
    pseudo: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def create_app_jwt(user_id: str) -> str:
    exp = datetime.utcnow() + timedelta(days=7)
    return jwt.encode({"sub": user_id, "exp": exp}, SECRET_KEY, algorithm="HS256")


def decode_app_jwt(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["sub"]
    except JWTError:
        raise HTTPException(401, "Invalid token")


async def get_current_user(cred: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    user_id = decode_app_jwt(cred.credentials)
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE id=$1", user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return dict(user)


@app.post("/auth/register")
async def register(body: RegisterRequest):
    hashed = pwd_ctx.hash(body.password)
    async with pool.acquire() as conn:
        try:
            user_id = await conn.fetchval(
                "INSERT INTO users(pseudo, email, password_hash, elo) VALUES($1,$2,$3,1000) RETURNING id",
                body.pseudo, body.email, hashed
            )
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(409, "Pseudo or email already exists")
    return {"user_id": str(user_id)}


@app.post("/auth/login")
async def login(body: LoginRequest):
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE email=$1", body.email)
    if not user or not pwd_ctx.verify(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_app_jwt(str(user["id"]))
    await redis.setex(f"session:{user['id']}", 86400 * 7, token)
    return {"token": token, "user_id": str(user["id"])}


@app.post("/auth/token/livekit")
async def livekit_token(user: dict = Depends(get_current_user)):
    # Get active match from Redis
    match = await redis.get(f"match:{user['id']}")
    if not match:
        raise HTTPException(404, "No active match")
    import json
    info = json.loads(match)
    room_id = info["room_id"]
    token = (
        AccessToken(LK_KEY, LK_SECRET)
        .with_grants(VideoGrants(room_join=True, room=room_id))
        .with_identity(str(user["id"]))
        .to_jwt()
    )
    return {"token": token, "room_id": room_id, "livekit_url": LK_URL}


@app.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    return {
        "id": str(user["id"]),
        "pseudo": user["pseudo"],
        "email": user["email"],
        "elo": user["elo"],
        "avatar_url": user["avatar_url"],
        "created_at": user["created_at"].isoformat() if user["created_at"] else None,
    }


@app.get("/friends")
async def list_friends(user: dict = Depends(get_current_user)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT friend_id, status FROM friendships WHERE user_id=$1 AND status='accepted'",
            user["id"]
        )
    return [{"friend_id": str(r["friend_id"]), "status": r["status"]} for r in rows]


@app.post("/friends/invite/{friend_id}")
async def invite_friend(friend_id: str, user: dict = Depends(get_current_user)):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO friendships(user_id, friend_id, status) VALUES($1, $2, 'pending')",
            user["id"], friend_id
        )
    return {"status": "invited"}
