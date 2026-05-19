#!/usr/bin/env python3
"""GF Simulator — simule physique + IA football, envoie GameState via LiveKit"""

import os
import sys
import math
import time
import struct
import asyncio
import random

import redis.asyncio as aioredis
from livekit import rtc

ROOM_ID = os.getenv("ROOM_ID", "mock-room")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
GF_TOKEN = os.getenv("GF_TOKEN", "")
DURATION = int(os.getenv("DURATION", "300"))  # 5 min default
TICK_RATE = 30  # Hz (30Hz = envoi toutes les 33ms)

# --- Struct formats (must match C++ GameBridge.h exactly) ---
PLAYER_FMT = "<3f3ffBB2x"      # 32 bytes
BALL_FMT = "<3f3f"              # 24 bytes
GAME_FMT = "<" + 22 * PLAYER_FMT[1:] + BALL_FMT[1:] + "2ifB3xI"  # 748 bytes
EVENT_FMT = "<3B1x3fI2i"        # 28 bytes

# Pitch bounds (half-size)
PITCH_X = 5.5   # -5.5 to +5.5
PITCH_Z = 2.5   # -2.5 to +2.5
GOAL_X = 5.5    # goal line x positions

# Team A formation 4-4-2 (left side, attacking right)
TEAM_A_FORMATION = [
    (-4.5, 0, 0),      # GK
    (-3.5, 0, -1.5), (-3.5, 0, -0.5), (-3.5, 0, 0.5), (-3.5, 0, 1.5),  # DEF
    (-2.0, 0, -1.5), (-2.0, 0, -0.5), (-2.0, 0, 0.5), (-2.0, 0, 1.5),  # MID
    (-0.8, 0, -0.8), (-0.8, 0, 0.8),   # FWD
]

# Team B formation 4-4-2 (right side, attacking left)
TEAM_B_FORMATION = [
    (4.5, 0, 0),
    (3.5, 0, -1.5), (3.5, 0, -0.5), (3.5, 0, 0.5), (3.5, 0, 1.5),
    (2.0, 0, -1.5), (2.0, 0, -0.5), (2.0, 0, 0.5), (2.0, 0, 1.5),
    (0.8, 0, -0.8), (0.8, 0, 0.8),
]

class GFSimulator:
    def __init__(self):
        self.tick = 0
        self.score = [0, 0]
        self.timer = DURATION
        self.ball_pos = [0.0, 0.25, 0.0]
        self.ball_vel = [0.0, 0.0, 0.0]
        self.players = []  # list of dicts: {pos, vel, team}
        self.room = None

        # Init players
        for i, pos in enumerate(TEAM_A_FORMATION):
            self.players.append({"pos": list(pos), "vel": [0.0, 0.0, 0.0], "team": 0, "idx": i})
        for i, pos in enumerate(TEAM_B_FORMATION):
            self.players.append({"pos": list(pos), "vel": [0.0, 0.0, 0.0], "team": 1, "idx": i + 11})

    def update(self, dt):
        """Simple physics: players chase ball, ball moves toward random target"""
        self.tick += 1
        self.timer = max(0, self.timer - dt)

        # Update ball physics
        # Dampen velocity
        self.ball_vel[0] *= 0.98
        self.ball_vel[2] *= 0.98

        # Move ball
        self.ball_pos[0] += self.ball_vel[0] * dt
        self.ball_pos[2] += self.ball_vel[2] * dt

        # Ball bounds bounce
        if abs(self.ball_pos[0]) > PITCH_X:
            self.ball_vel[0] *= -0.7
            self.ball_pos[0] = math.copysign(PITCH_X, self.ball_pos[0])
        if abs(self.ball_pos[2]) > PITCH_Z:
            self.ball_vel[2] *= -0.7
            self.ball_pos[2] = math.copysign(PITCH_Z, self.ball_pos[2])

        # Players chase ball
        for p in self.players:
            dx = self.ball_pos[0] - p["pos"][0]
            dz = self.ball_pos[2] - p["pos"][2]
            dist = math.sqrt(dx*dx + dz*dz) + 0.001

            # Speed depends on team and distance
            max_speed = 2.0 if dist > 1.0 else 0.5
            speed = min(max_speed, dist) * 0.5

            p["vel"][0] = (dx / dist) * speed
            p["vel"][2] = (dz / dist) * speed

            # Move toward ball
            p["pos"][0] += p["vel"][0] * dt
            p["pos"][2] += p["vel"][2] * dt

            # Keep in formation area loosely
            if p["team"] == 0:
                p["pos"][0] = max(-5.0, min(2.0, p["pos"][0]))
            else:
                p["pos"][0] = max(-2.0, min(5.0, p["pos"][0]))
            p["pos"][2] = max(-PITCH_Z, min(PITCH_Z, p["pos"][2]))

        # Random kick toward goal
        if self.tick % 120 == 0:  # every ~4 seconds
            team = random.randint(0, 1)
            target_x = -GOAL_X if team == 1 else GOAL_X
            target_z = random.uniform(-0.5, 0.5)
            dx = target_x - self.ball_pos[0]
            dz = target_z - self.ball_pos[2]
            dist = math.sqrt(dx*dx + dz*dz) + 0.001
            kick_force = random.uniform(1.5, 3.0)
            self.ball_vel[0] = (dx / dist) * kick_force
            self.ball_vel[2] = (dz / dist) * kick_force

        # Check goal
        event = None
        if self.ball_pos[0] > GOAL_X and abs(self.ball_pos[2]) < 0.5:
            self.score[0] += 1
            event = {"type": 1, "team": 0, "pos": list(self.ball_pos)}
            self._reset_ball()
        elif self.ball_pos[0] < -GOAL_X and abs(self.ball_pos[2]) < 0.5:
            self.score[1] += 1
            event = {"type": 1, "team": 1, "pos": list(self.ball_pos)}
            self._reset_ball()

        return event

    def _reset_ball(self):
        self.ball_pos = [0.0, 0.25, 0.0]
        self.ball_vel = [0.0, 0.0, 0.0]

    def pack_game_state(self):
        """Pack GameState into 748 bytes matching C++ struct"""
        data = bytearray()

        # 22 players
        for p in self.players:
            data += struct.pack(PLAYER_FMT,
                p["pos"][0], p["pos"][1], p["pos"][2],
                p["vel"][0], p["vel"][1], p["vel"][2],
                0.0,  # rot
                0,    # anim_id
                p["team"])

        # Ball
        data += struct.pack(BALL_FMT,
            self.ball_pos[0], self.ball_pos[1], self.ball_pos[2],
            self.ball_vel[0], self.ball_vel[1], self.ball_vel[2])

        # Score, timer, game_mode, tick
        data += struct.pack("<2ifB3xI",
            self.score[0], self.score[1],
            self.timer,
            0,  # game_mode
            self.tick)

        assert len(data) == 748, f"GameState size mismatch: {len(data)} != 748"
        return bytes(data)

    def pack_event(self, event):
        """Pack MatchEvent into 28 bytes"""
        return struct.pack(EVENT_FMT,
            event["type"],
            event["team"],
            0,  # player_idx
            event["pos"][0], event["pos"][1], event["pos"][2],
            self.tick,
            self.score[0], self.score[1])


async def run_simulator():
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)

    # 1. Signal ready on Redis
    await redis.publish("gf.ready", ROOM_ID)
    print(f"[GFSim] Room {ROOM_ID} ready")

    # 2. Connect to LiveKit
    sim = GFSimulator()
    room = rtc.Room()
    await room.connect(LIVEKIT_URL, GF_TOKEN)
    print(f"[GFSim] Connected to LiveKit room {ROOM_ID}")

    # 3. Heartbeat + game loop
    start_time = time.time()
    tick_interval = 1.0 / TICK_RATE
    next_tick = time.time()

    try:
        while time.time() - start_time < DURATION and sim.timer > 0:
            now = time.time()
            if now >= next_tick:
                # Update physics
                event = sim.update(tick_interval)

                # Send game state
                gs_bytes = sim.pack_game_state()
                await room.local_participant.publish_data(
                    data=gs_bytes,
                    topic="gs",
                    reliable=False
                )

                # Send event if goal
                if event:
                    ev_bytes = sim.pack_event(event)
                    await room.local_participant.publish_data(
                        data=ev_bytes,
                        topic="ev",
                        reliable=True
                    )
                    print(f"[GFSim] GOAL! Team {event['team']} | Score {sim.score[0]}-{sim.score[1]}")

                # Heartbeat
                if sim.tick % 300 == 0:  # every 10s
                    await redis.hset("gf.heartbeat", ROOM_ID, str(int(time.time())))

                next_tick += tick_interval

            await asyncio.sleep(0.001)

    except asyncio.CancelledError:
        pass
    finally:
        # Match finished
        await redis.publish("gf.finished", ROOM_ID)
        await redis.hdel("gf.heartbeat", ROOM_ID)
        await redis.close()
        await room.disconnect()
        print(f"[GFSim] Match finished. Final score {sim.score[0]}-{sim.score[1]}")


if __name__ == "__main__":
    asyncio.run(run_simulator())
