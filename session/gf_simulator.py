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
# LiveKit Python SDK requires WebSocket scheme
if LIVEKIT_URL.startswith("https://"):
    LIVEKIT_URL = "wss://" + LIVEKIT_URL[len("https://"):]
elif LIVEKIT_URL.startswith("http://"):
    LIVEKIT_URL = "ws://" + LIVEKIT_URL[len("http://"):]
GF_TOKEN = os.getenv("GF_TOKEN", "")
DURATION = int(os.getenv("DURATION", "300"))  # 5 min default
TICK_RATE = 30  # Hz (30Hz = envoi toutes les 33ms)

# --- Struct formats (must match C++ DZFootProtocol.h exactly) ---
# NetworkPlayerState: pos[3] + vel[3] + dir[3] + rotY + anim + team + role + flags + tiredFactor = 48 bytes
PLAYER_FMT = "<3f3f3fBBBBf"
# NetworkBallState: pos[3] + vel[3] + rot[3] + ownedTeam(int8) + ownedPlayer(int8) + pad[2] = 40 bytes
BALL_FMT = "<3f3f3fbb2x"
# NetworkOfficialState: pos[3] + dir[3] + rotY + anim + team + role + flags = 32 bytes
OFFICIAL_FMT = "<3f3ffBBBB"
# GameStatePacket: header(12) + tick(4) + timestampUs(8) + gameMode(1) + gameFlags(1) + score[2](2) + timer(4) + ball(40) + 22*players(48*22)
# Header is packed separately in send() so GAME_FMT is just the body after header
BODY_FMT = "IQBB2Bf" + BALL_FMT[1:] + 22 * PLAYER_FMT[1:]
# MatchEventPacket: header(12) + eventType(1) + team(1) + playerIdx(1) + extra(1) + pos[3](12) + tick(4) + score[2](2) + pad[2]
EVENT_FMT = "<IHHHH" + "BBBB" + "3f" + "I" + "2B" + "2x"

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
        self.players = []  # list of dicts: {pos, vel, team, has_ball}
        self.room = None
        # Default controlled player = player 0 (team A GK)
        # TODO: map participant identity to player index
        self.controlled_idx = 0
        # Input buffer from clients
        self._pending_input = {"dir_x": 0.0, "dir_z": 0.0, "kick": False, "pass": False, "shot": False, "dribble": False}

        # Init players
        for i, pos in enumerate(TEAM_A_FORMATION):
            self.players.append({"pos": list(pos), "vel": [0.0, 0.0, 0.0], "team": 0, "idx": i, "has_ball": False})
        for i, pos in enumerate(TEAM_B_FORMATION):
            self.players.append({"pos": list(pos), "vel": [0.0, 0.0, 0.0], "team": 1, "idx": i + 11, "has_ball": False})

    _input_log_count = 0
    def handle_input(self, payload: bytes):
        """Parse PlayerInput struct from C++ (32 bytes: 8 floats)"""
        if len(payload) < 32:
            print(f"[GFSim] handle_input: short payload {len(payload)}", flush=True)
            return
        vals = struct.unpack("<8f", payload[:32])
        self._pending_input["dir_x"] = vals[0]
        self._pending_input["dir_z"] = vals[1]
        self._pending_input["kick"]  = vals[2] > 0.5
        self._pending_input["pass"]  = vals[3] > 0.5
        self._pending_input["shot"]  = vals[4] > 0.5
        self._pending_input["dribble"] = vals[5] > 0.5
        # Log first 5 inputs + any with actions
        any_action = any([vals[2] > 0.5, vals[3] > 0.5, vals[4] > 0.5, vals[5] > 0.5])
        if self._input_log_count < 5 or any_action:
            print(f"[GFSim] Input rx: dx={vals[0]:.2f} dz={vals[1]:.2f} kick={vals[2]:.1f} pass={vals[3]:.1f} shot={vals[4]:.1f} dribble={vals[5]:.1f}", flush=True)
            self._input_log_count += 1

    def _ball_nearest_player(self):
        """Return index of player closest to ball"""
        best = -1
        best_d = float('inf')
        for i, p in enumerate(self.players):
            d2 = (p["pos"][0]-self.ball_pos[0])**2 + (p["pos"][2]-self.ball_pos[2])**2
            if d2 < best_d:
                best_d, best = d2, i
        return best

    def update(self, dt):
        """Simple physics: players chase ball, ball moves, handle player input"""
        self.tick += 1
        self.timer = max(0, self.timer - dt)

        # --- Handle controlled player input ---
        ctrl = self.players[self.controlled_idx]
        inp = self._pending_input
        move_speed = 2.5
        if abs(inp["dir_x"]) > 0.01 or abs(inp["dir_z"]) > 0.01:
            ctrl["pos"][0] += inp["dir_x"] * move_speed * dt
            ctrl["pos"][2] += -inp["dir_z"] * move_speed * dt  # screen Y down = -Z forward

        # Clamp controlled player in bounds
        if ctrl["team"] == 0:
            ctrl["pos"][0] = max(-5.0, min(5.0, ctrl["pos"][0]))
        else:
            ctrl["pos"][0] = max(-5.0, min(5.0, ctrl["pos"][0]))
        ctrl["pos"][2] = max(-PITCH_Z, min(PITCH_Z, ctrl["pos"][2]))

        # Determine who has the ball (closest within 0.5m)
        ball_carrier = self._ball_nearest_player()
        ball_dist = math.sqrt((self.players[ball_carrier]["pos"][0]-self.ball_pos[0])**2 +
                              (self.players[ball_carrier]["pos"][2]-self.ball_pos[2])**2) if ball_carrier >= 0 else 999
        for p in self.players:
            p["has_ball"] = False
        if ball_dist < 0.5:
            self.players[ball_carrier]["has_ball"] = True
            # Dribble: ball sticks to carrier
            if ball_carrier == self.controlled_idx and inp["dribble"]:
                self.ball_pos[0] = ctrl["pos"][0] + inp["dir_x"] * 0.3
                self.ball_pos[2] = ctrl["pos"][2] - inp["dir_z"] * 0.3

        # Kick / Shot / Pass actions from controlled player
        if ball_carrier == self.controlled_idx and ball_dist < 0.5:
            target_x = GOAL_X if ctrl["team"] == 0 else -GOAL_X
            target_z = 0.0

            if inp["shot"]:
                dx = target_x - self.ball_pos[0]
                dz = target_z - self.ball_pos[2]
                dist = math.sqrt(dx*dx+dz*dz) + 0.001
                force = 4.0
                self.ball_vel[0] = (dx/dist) * force
                self.ball_vel[2] = (dz/dist) * force
                inp["shot"] = False  # consume action
                print(f"[GFSim] SHOT by player {ball_carrier}!")

            elif inp["pass"]:
                # Pass to nearest teammate in front
                team_mates = [p for p in self.players if p["team"] == ctrl["team"] and p["idx"] != ctrl["idx"]]
                if team_mates:
                    best_mate = min(team_mates, key=lambda p: (p["pos"][0]-ctrl["pos"][0])**2 + (p["pos"][2]-ctrl["pos"][2])**2)
                    dx = best_mate["pos"][0] - self.ball_pos[0]
                    dz = best_mate["pos"][2] - self.ball_pos[2]
                    dist = math.sqrt(dx*dx+dz*dz) + 0.001
                    force = 3.0
                    self.ball_vel[0] = (dx/dist) * force
                    self.ball_vel[2] = (dz/dist) * force
                    inp["pass"] = False
                    print(f"[GFSim] PASS to player {best_mate['idx']}!")

            elif inp["kick"]:
                # Simple kick forward in facing direction
                dx = inp["dir_x"] if abs(inp["dir_x"]) > 0.1 else (1.0 if ctrl["team"] == 0 else -1.0)
                dz = -inp["dir_z"] if abs(inp["dir_z"]) > 0.1 else 0.0
                dist = math.sqrt(dx*dx+dz*dz) + 0.001
                force = 2.5
                self.ball_vel[0] = (dx/dist) * force
                self.ball_vel[2] = (dz/dist) * force
                inp["kick"] = False
                print(f"[GFSim] KICK by player {ball_carrier}!")

        # Update ball physics
        self.ball_vel[0] *= 0.98
        self.ball_vel[2] *= 0.98
        self.ball_pos[0] += self.ball_vel[0] * dt
        self.ball_pos[2] += self.ball_vel[2] * dt

        # Ball bounds bounce
        if abs(self.ball_pos[0]) > PITCH_X:
            self.ball_vel[0] *= -0.7
            self.ball_pos[0] = math.copysign(PITCH_X, self.ball_pos[0])
        if abs(self.ball_pos[2]) > PITCH_Z:
            self.ball_vel[2] *= -0.7
            self.ball_pos[2] = math.copysign(PITCH_Z, self.ball_pos[2])

        # Realistic AI: only closest player per team pursues ball, others return to formation
        # Controlled player is NOT driven by AI (manual override)
        # Find closest player per team
        closest_per_team = [None, None]
        closest_dist = [float('inf'), float('inf')]
        for p in self.players:
            if p["idx"] == self.controlled_idx:
                continue
            dx = self.ball_pos[0] - p["pos"][0]
            dz = self.ball_pos[2] - p["pos"][2]
            d2 = dx*dx + dz*dz
            t = p["team"]
            if d2 < closest_dist[t]:
                closest_dist[t] = d2
                closest_per_team[t] = p["idx"]

        # Move each player
        for i, p in enumerate(self.players):
            if p["idx"] == self.controlled_idx:
                continue  # Skip AI for controlled player
            home_x, home_y, home_z = (TEAM_A_FORMATION[i] if p["team"] == 0
                                       else TEAM_B_FORMATION[i - 11])
            is_chaser = (p["idx"] == closest_per_team[p["team"]])

            if is_chaser:
                # Chase the ball at high speed
                target_x, target_z = self.ball_pos[0], self.ball_pos[2]
                max_speed = 3.0
            else:
                # Return to formation home position with slight ball-side bias (for support)
                bias = 0.3
                target_x = home_x + (self.ball_pos[0] - home_x) * bias
                target_z = home_z + (self.ball_pos[2] - home_z) * bias
                max_speed = 1.5

            dx = target_x - p["pos"][0]
            dz = target_z - p["pos"][2]
            dist = math.sqrt(dx*dx + dz*dz) + 0.001
            speed = min(max_speed, dist * 2.0)

            p["vel"][0] = (dx / dist) * speed
            p["vel"][2] = (dz / dist) * speed
            p["pos"][0] += p["vel"][0] * dt
            p["pos"][2] += p["vel"][2] * dt

            # Keep in own half-ish (with overlap for attacking)
            if p["team"] == 0:
                p["pos"][0] = max(-5.0, min(3.0, p["pos"][0]))
            else:
                p["pos"][0] = max(-3.0, min(5.0, p["pos"][0]))
            p["pos"][2] = max(-PITCH_Z, min(PITCH_Z, p["pos"][2]))

        # AI auto-kick when a non-controlled player gets the ball (every ~2s)
        if ball_carrier >= 0 and ball_carrier != self.controlled_idx and ball_dist < 0.5:
            if self.tick % 60 == 0 and random.random() < 0.3:
                team = self.players[ball_carrier]["team"]
                target_x = GOAL_X if team == 0 else -GOAL_X
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
        """Pack GameState into 1224 bytes matching C++ DZFootProtocol.h"""
        data = bytearray()

        # Packet header: magic=0x54465A44 'DZFT', version=1, type=1 (GAME_STATE), size=1224, flags=0
        data += struct.pack("<IHHHH", 0x54465A44, 1, 1, 1224, 0)

        # tick + timestampUs + gameMode + gameFlags + score + timer
        data += struct.pack("<IQBB2Bf",
            self.tick,
            int(time.time() * 1_000_000),  # timestampUs
            0,  # gameMode
            0,  # gameFlags
            self.score[0], self.score[1],
            self.timer)

        # Ball: pos[3] + vel[3] + rot[3] + ownedTeam + ownedPlayer + pad[2]
        data += struct.pack(BALL_FMT,
            self.ball_pos[0], self.ball_pos[1], self.ball_pos[2],
            self.ball_vel[0], self.ball_vel[1], self.ball_vel[2],
            0.0, 0.0, 0.0,  # rot
            -1, -1)  # ownedTeam, ownedPlayer

        # 22 players: pos[3] + vel[3] + dir[3] + rotY + anim + team + role + flags + tiredFactor
        for p in self.players:
            speed = math.sqrt(p["vel"][0]**2 + p["vel"][1]**2 + p["vel"][2]**2)
            anim = 0 if speed < 0.1 else (1 if speed < 0.5 else 2)
            role = 0 if p["idx"] % 11 == 0 else 1  # GK=0, field=1
            data += struct.pack(PLAYER_FMT,
                p["pos"][0], p["pos"][1], p["pos"][2],
                p["vel"][0], p["vel"][1], p["vel"][2],
                0.0, 0.0, 1.0,  # dir (default facing +Y)
                0.0,  # rotY
                anim,
                p["team"],
                role,
                1,  # flags: active
                0.0)  # tiredFactor

        # 3 officials: referee, linesmanNorth, linesmanSouth
        officials_def = [
            ([0.0, 0.0, 0.0], [0.0, 1.0, 0.0], 0), # referee central
            ([0.0, -2.5, 0.0], [1.0, 0.0, 0.0], 1), # linesman North
            ([0.0, 2.5, 0.0], [-1.0, 0.0, 0.0], 2) # linesman South
        ]
        for opos, odir, orole in officials_def:
            data += struct.pack(OFFICIAL_FMT,
                opos[0], opos[1], opos[2],
                odir[0], odir[1], odir[2],
                0.0, # rotY
                0,   # anim: IDLE
                2,   # team: officials
                orole,
                1)   # flags: active

        assert len(data) == 1224, f"GameState size mismatch: {len(data)} != 1224"
        return bytes(data)

    def pack_event(self, event):
        """Pack MatchEvent into 36 bytes matching C++ DZFootProtocol.h"""
        return struct.pack(EVENT_FMT,
            0x54465A44, 1, 2, 36, 0,  # header: magic, version, type=EVENT, size=36, flags
            event["type"],
            event["team"],
            0,  # player_idx
            0,  # extra
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

    @room.on("data_received")
    def on_data(data_packet):
        # data_packet.data is bytes (livekit-rtc 0.x API)
        try:
            payload = getattr(data_packet, "data", None) or getattr(data_packet, "payload", None)
            topic = getattr(data_packet, "topic", "")
            if topic == "in" and payload is not None:
                sim.handle_input(bytes(payload))
        except Exception as e:
            print(f"[GFSim] data_received error: {e}", flush=True)

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
                    payload=gs_bytes,
                    topic="gs",
                    reliable=False
                )

                # Send event if goal
                if event:
                    ev_bytes = sim.pack_event(event)
                    await room.local_participant.publish_data(
                        payload=ev_bytes,
                        topic="ev",
                        reliable=True
                    )
                    print(f"[GFSim] GOAL! Team {event['team']} | Score {sim.score[0]}-{sim.score[1]}")

                # Heartbeat
                if sim.tick % 300 == 0:  # every 10s
                    await redis.hset("gf.heartbeat", ROOM_ID, str(int(time.time())))

                # Log every second (30 ticks at 30Hz) so we can verify the loop is running
                if sim.tick % 30 == 0:
                    num_remote = len(room.remote_participants)
                    print(f"[GFSim] tick={sim.tick} t={int(time.time()-start_time)}s score={sim.score[0]}-{sim.score[1]} remotes={num_remote}", flush=True)

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
