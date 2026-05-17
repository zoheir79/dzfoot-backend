#!/usr/bin/env python3
"""Mock GF Server pour PoC V1 — simule le circuit Redis + LiveKit sans C++"""

import os
import sys
import json
import time
import asyncio
import random
import redis.asyncio as aioredis

ROOM_ID = os.getenv("ROOM_ID", "mock-room")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DURATION = int(os.getenv("DURATION", "60"))  # 60 secondes pour test

async def run_mock_match():
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)

    print(f"[MockGF] Room {ROOM_ID} demarre ({DURATION}s)")

    # 1. Signal ready
    await redis.hset("gf.heartbeat", ROOM_ID, str(int(time.time())))
    await redis.publish("gf.ready", json.dumps({"room_id": ROOM_ID, "pid": 9999}))
    print(f"[MockGF] gf.ready publie")

    # 2. Heartbeat toutes les 10s
    start = time.time()
    tick = 0
    try:
        while time.time() - start < DURATION:
            await redis.hset("gf.heartbeat", ROOM_ID, str(int(time.time())))

            # Simuler un score change
            if tick % 6 == 0:  # chaque ~60s (10s * 6)
                score_a = random.randint(0, 3)
                score_b = random.randint(0, 3)
                print(f"[MockGF] Score: {score_a}-{score_b}")

            tick += 1
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        pass

    # 3. Match finished
    print(f"[MockGF] Match termine, envoi gf.finished")
    await redis.publish("gf.finished", json.dumps({
        "room_id": ROOM_ID,
        "score_a": random.randint(0, 3),
        "score_b": random.randint(0, 3),
        "duration_s": int(time.time() - start)
    }))
    await redis.hdel("gf.heartbeat", ROOM_ID)
    await redis.close()
    print(f"[MockGF] Termine")

if __name__ == "__main__":
    asyncio.run(run_mock_match())
