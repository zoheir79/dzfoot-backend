import os
import asyncio
import subprocess
import uuid
import json
from typing import Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis.asyncio as aioredis
import httpx
from livekit.api import LiveKitAPI, CreateRoomRequest, AccessToken, VideoGrants
try:
    from livekit.api import SendDataRequest
except ImportError:
    SendDataRequest = None
    print("[Session] WARNING: SendDataRequest not available in livekit.api", flush=True)
try:
    from livekit.rtc import Room, DataPacketKind
except ImportError as e:
    print(f"[Session] WARNING: livekit.rtc import failed: {e}", flush=True)
    Room = None
    class _DataPacketKind:
        KIND_LOSSY = 0
        KIND_RELIABLE = 1
    DataPacketKind = _DataPacketKind()

app = FastAPI(title="DZFoot Session Service")

LK_URL = os.getenv("LIVEKIT_URL", "")
LK_KEY = os.getenv("LIVEKIT_API_KEY", "")
LK_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
GF_BINARY_PATH = os.getenv("GF_BINARY_PATH", "/usr/local/bin/gf_server")
STATS_SERVICE_URL = os.getenv("STATS_SERVICE_URL", "")
GF_SPAWN_TIMEOUT = int(os.getenv("GF_SPAWN_TIMEOUT", "30"))  # seconds to wait for GF ready
GF_MATCH_TIMEOUT = int(os.getenv("GF_MATCH_TIMEOUT", "900"))  # max match duration + buffer
CATALOG_URL = os.getenv("CATALOG_URL", "http://catalog:8000")
CONFIG_DIR = os.getenv("GF_CONFIG_DIR", "/tmp/gf_configs")

os.makedirs(CONFIG_DIR, exist_ok=True)

redis: Optional[aioredis.Redis] = None
lkapi: Optional[LiveKitAPI] = None
active_matches: dict = {}
room_publishers: dict = {}   # room_id -> livekit.rtc.Room (for data publishing)
_background_tasks: list = []  # Strong references to prevent GC


@app.on_event("startup")
async def startup():
    global redis, lkapi
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    lkapi = LiveKitAPI(url=LK_URL, api_key=LK_KEY, api_secret=LK_SECRET)
    # Start background listeners (each with dedicated Redis connection)
    # Store strong references so Python 3.12+ doesn't garbage-collect them
    _background_tasks.append(asyncio.create_task(_pubsub_listener("gf.ready", _handle_gf_ready)))
    _background_tasks.append(asyncio.create_task(_pubsub_listener("gf.crashed", _handle_gf_crashed)))
    _background_tasks.append(asyncio.create_task(_pubsub_listener("gf.finished", _handle_gf_finished)))
    # Start GF -> LiveKit relay (binary pubsub for gamestate/event/setup)
    _background_tasks.append(asyncio.create_task(_binary_pubsub_relay("gf.gamestate", "gs", DataPacketKind.KIND_LOSSY)))
    _background_tasks.append(asyncio.create_task(_binary_pubsub_relay("gf.tactical", "tac", DataPacketKind.KIND_LOSSY)))
    _background_tasks.append(asyncio.create_task(_binary_pubsub_relay("gf.event", "ev", DataPacketKind.KIND_RELIABLE)))
    _background_tasks.append(asyncio.create_task(_binary_pubsub_relay("gf.setup", "setup", DataPacketKind.KIND_RELIABLE)))
    # Start LiveKit -> GF input relay (bot joins rooms, forwards inputs to Redis)
    _background_tasks.append(asyncio.create_task(_input_relay_bot()))
    _background_tasks.append(asyncio.create_task(check_worker_health()))
    _background_tasks.append(asyncio.create_task(check_match_timeouts()))
    print(f"[Session] Started {len(_background_tasks)} background tasks", flush=True)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "session"}


@app.on_event("shutdown")
async def shutdown():
    if redis:
        await redis.close()


async def _pubsub_listener(channel: str, handler):
    """Dedicated Redis pubsub connection per listener."""
    ps = await aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = ps.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await handler(message["data"])
    finally:
        await ps.close()


async def _binary_pubsub_relay(redis_channel: str, lk_topic: str, kind):
    """Relay binary data from Redis pubsub to LiveKit room via send_data.
    Message format: first 36 bytes = room_id (padded), rest = binary payload."""
    while True:
        try:
            print(f"[Session] Starting relay {redis_channel} -> {lk_topic}...", flush=True)
            ps = await aioredis.from_url(REDIS_URL, decode_responses=False)
            pubsub = ps.pubsub()
            await pubsub.subscribe(redis_channel)
            print(f"[Session] Relay started: Redis:{redis_channel} -> LiveKit:{lk_topic}", flush=True)
            try:
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    data = message["data"]
                    if len(data) < 37:
                        continue
                    room_id = data[:36].decode("utf-8", errors="replace").rstrip("\x00")
                    payload = data[36:]
                    # GF server truncates to 36 bytes but real room_id is 42 chars
                    # ("match-" + 36-char UUID). Look up full room_id by prefix in active_matches.
                    if room_id not in active_matches:
                        full_room_id = None
                        for known_room in active_matches.keys():
                            if known_room.startswith(room_id):
                                full_room_id = known_room
                                break
                        if full_room_id:
                            room_id = full_room_id
                        else:
                            # Orphan match (not in active_matches) — skip silently
                            continue
                    try:
                        pub_room = room_publishers.get(room_id)
                        if pub_room is None:
                            print(f"[Relay {redis_channel}] No Room publisher for {room_id}, skipping", flush=True)
                            continue
                        await pub_room.local_participant.publish_data(
                            payload,
                            reliable=(kind == DataPacketKind.KIND_RELIABLE),
                            topic=lk_topic,
                        )
                    except Exception as e:
                        print(f"[Relay {redis_channel}] publish_data error for room {room_id}: {e}", flush=True)
            finally:
                await ps.close()
        except Exception as e:
            import traceback
            print(f"[Relay {redis_channel}] FATAL error: {e}\n{traceback.format_exc()}", flush=True)
            await asyncio.sleep(5)  # retry after 5 seconds


async def _input_relay_bot():
    """Join rooms as a bot to relay player inputs from LiveKit to Redis.
    Listens for new rooms via Redis keyspace notifications or polls active_matches."""
    # Track which rooms we've already joined
    joined_rooms = set()
    while True:
        await asyncio.sleep(2)
        for room_id in list(active_matches.keys()):
            if room_id in joined_rooms:
                continue
            joined_rooms.add(room_id)
            asyncio.create_task(_bot_relay_for_room(room_id))


async def _bot_relay_for_room(room_id: str):
    """Join a LiveKit room as a bot to relay player inputs to Redis gf.input channel."""
    # Generate a bot token for this room
    bot_token = (
        AccessToken(LK_KEY, LK_SECRET)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_id,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_identity(f"bot-{room_id}")
        .to_jwt()
    )

    room = Room()
    try:
        @room.on("data_received")
        def on_data(data_packet):
            try:
                payload = getattr(data_packet, "data", None) or getattr(data_packet, "payload", None)
                topic = getattr(data_packet, "topic", "")
                if topic == "in" and payload is not None:
                    # Forward input to Redis as binary
                    asyncio.create_task(_forward_input_to_redis(room_id, bytes(payload)))
            except Exception as e:
                print(f"[Bot {room_id}] data_received error: {e}", flush=True)

        @room.on("participant_disconnected")
        def on_participant_disconnected(participant):
            try:
                identity = getattr(participant, "identity", "")
                # Ignore disconnects from gf-server, relay bots, and AI player "bot"
                if identity.startswith("bot-") or identity == "gf-server" or identity == "bot":
                    return
                print(f"[Bot {room_id}] Real participant '{identity}' disconnected — cleaning up match", flush=True)
                asyncio.create_task(_cleanup_orphan_match(room_id))
            except Exception as e:
                print(f"[Bot {room_id}] participant_disconnected error: {e}", flush=True)

        await room.connect(LK_URL, bot_token)
        room_publishers[room_id] = room
        print(f"[Bot {room_id}] Connected to room for input relay + data publishing")

        # Keep the bot alive until the room is gone
        while room_id in active_matches:
            await asyncio.sleep(5)
    except Exception as e:
        print(f"[Bot {room_id}] Error: {e}", flush=True)
    finally:
        room_publishers.pop(room_id, None)
        await room.disconnect()
        print(f"[Bot {room_id}] Disconnected")


async def _cleanup_orphan_match(room_id: str):
    """Kill GF container for an orphan match where the player has disconnected."""
    await asyncio.sleep(10)  # Grace period for reconnect
    if room_id in active_matches:
        print(f"[Session] Cleaning up orphan match {room_id} (no player after 10s)", flush=True)
        await redis.publish("gf.crashed", room_id)
        active_matches.pop(room_id, None)
        room_publishers.pop(room_id, None)
        await redis.delete(f"room:{room_id}")


async def _forward_input_to_redis(room_id: str, payload: bytes):
    """Forward binary input data to Redis gf.input channel with room_id prefix."""
    try:
        # Prefix room_id (36 bytes padded) + binary payload
        room_prefix = room_id.encode("utf-8").ljust(36, b"\x00")[:36]
        await redis.publish("gf.input", room_prefix + payload)
    except Exception as e:
        print(f"[Session] Failed to forward input to Redis: {e}", flush=True)


async def _handle_gf_ready(room_id):
    if room_id in active_matches:
        active_matches[room_id]["status"] = "running"
        active_matches[room_id]["gf_ready_at"] = datetime.utcnow().isoformat()
        print(f"[Session] GF ready for room {room_id}")


async def _handle_gf_crashed(room_id):
    print(f"[Session] GF crashed for room {room_id}")
    if room_id in active_matches:
        active_matches[room_id]["status"] = "crashed"
        active_matches[room_id]["crashed_at"] = datetime.utcnow().isoformat()
        await redis.publish("match.crashed", room_id)
        # Async cleanup so listener stays responsive
        asyncio.create_task(_cleanup_after_crash(room_id))


async def _cleanup_after_crash(room_id):
    await asyncio.sleep(60)
    active_matches.pop(room_id, None)
    room_publishers.pop(room_id, None)
    await redis.delete(f"room:{room_id}")


async def _handle_gf_finished(room_id):
    print(f"[Session] GF finished for room {room_id}")
    if room_id in active_matches:
        active_matches[room_id]["status"] = "finished"
        active_matches[room_id]["finished_at"] = datetime.utcnow().isoformat()
        await redis.publish("match.finished", room_id)
        active_matches.pop(room_id, None)
        room_publishers.pop(room_id, None)
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
    player_b: Optional[str] = None  # not known yet for PvP waiting matches
    team_a: Optional[str] = None
    team_b: Optional[str] = None
    stadium_id: Optional[str] = None
    duration: int = 600  # seconds (default 10 min)
    mode: Optional[str] = "vs_ai"  # "1v1", "vs_ai", or "ai_vs_ai"


class JoinMatchRequest(BaseModel):
    room_id: str
    player_id: str


def _generate_procedural_avatar(name: str, index: int, team_id: int):
    """Generate a deterministic and realistic DZ-themed player avatar metadata based on player name."""
    import hashlib
    h = int(hashlib.md5(f"{name}_{index}_{team_id}".encode("utf-8")).hexdigest(), 16)
    
    # 1. Skin tone (0..6, mostly olive/brown since it's DZ Foot Algerian League)
    # 0=fair, 1=light, 2=medium, 3=olive, 4=dark olive, 5=brown, 6=black
    skin_color = h % 7
    if (h % 10) < 6: 
        skin_color = 3 # force more olive/brown tones for local Algerian players
    
    # 2. Hair styles matching the 6 GLB files recognized by GameServer
    # short=0, long=1, mohawk=2, curly=3, ponytail=4, bald=5
    hair_styles = ["short", "long", "mohawk", "curly", "ponytail", "bald"]
    hair_style = hair_styles[(h >> 2) % len(hair_styles)]
    
    # 3. Hair colors from the 8 options (dominant black/dark_brown)
    hair_colors = ["black", "dark_brown", "brown", "blonde", "grey", "chestnut", "auburn", "white"]
    if (h % 10) < 8:
        hair_color = "black" if (h % 2 == 0) else "dark_brown"
    else:
        hair_color = hair_colors[(h >> 4) % len(hair_colors)]
        
    # 4. Height (1.72m to 1.93m)
    is_gk = (index == 0)
    base_height = 1.86 if is_gk else 1.78
    height = round(base_height + ((h >> 6) % 15 - 7) * 0.015, 2)
    
    # 5. Body type (0=thin, 1=average, 2=muscular, 3=heavy)
    body_type = 1 # average dominant
    if (h % 10) == 0:
        body_type = 0 # thin
    elif (h % 10) in (8, 9):
        body_type = 2 # muscular
        
    # 6. Beard style (0=none, 1=stubble, 2=short, 3=full)
    beard_style = (h >> 8) % 4
    
    # 7. Eye color (0=brown, 1=blue, 2=green, 3=hazel, 4=grey)
    if (h % 10) < 8:
        eye_color = 0 # brown dominant
    else:
        eye_color = (h >> 10) % 5
        
    return {
        "skin_color": skin_color,
        "hair_style": hair_style,
        "hair_color": hair_color,
        "height": height,
        "body_type": body_type,
        "beard_style": beard_style,
        "eye_color": eye_color
    }


async def _build_match_config(room_id: str, team_a_id: Optional[str], team_b_id: Optional[str], duration: int, mode: str, stadium_id: Optional[str] = None) -> dict:
    """Fetch formations + full player rosters with 22 skills from Catalog."""
    left_team = {"name": "Team A", "formation": [], "players": []}
    right_team = {"name": "Team B", "formation": [], "players": []}

    async with httpx.AsyncClient(timeout=10.0) as client:
        if team_a_id:
            try:
                resp = await client.get(f"{CATALOG_URL}/teams/{team_a_id}/formation")
                if resp.status_code == 200:
                    data = resp.json()
                    left_team["name"] = data.get("team_name", "Team A")
                    left_team["formation"] = data.get("formation", [])
                    left_team["players"] = data.get("players", [])
                    left_team["short_name"] = data.get("short_name")
                    left_team["color_primary"] = data.get("color_primary")
                    left_team["color_secondary"] = data.get("color_secondary")
                    left_team["color_rgb1"] = data.get("color_rgb1")
                    left_team["color_rgb2"] = data.get("color_rgb2")
                    left_team["kit_texture_url"] = data.get("kit_texture_url")
                    left_team["league"] = data.get("league")
            except Exception as e:
                print(f"[Session] Catalog fetch failed for team_a: {e}")
        if team_b_id:
            try:
                resp = await client.get(f"{CATALOG_URL}/teams/{team_b_id}/formation")
                if resp.status_code == 200:
                    data = resp.json()
                    right_team["name"] = data.get("team_name", "Team B")
                    right_team["formation"] = data.get("formation", [])
                    right_team["players"] = data.get("players", [])
                    right_team["short_name"] = data.get("short_name")
                    right_team["color_primary"] = data.get("color_primary")
                    right_team["color_secondary"] = data.get("color_secondary")
                    right_team["color_rgb1"] = data.get("color_rgb1")
                    right_team["color_rgb2"] = data.get("color_rgb2")
                    right_team["kit_texture_url"] = data.get("kit_texture_url")
                    right_team["league"] = data.get("league")
            except Exception as e:
                print(f"[Session] Catalog fetch failed for team_b: {e}")

    # Fallback formation: default 4-3-3 (GameplayFootball native)
    if not left_team["formation"]:
        left_team["formation"] = [
            {"role": "GK", "x": -1.0, "y": 0.0, "controllable": True},
            {"role": "LB", "x": -0.7, "y": 0.75, "controllable": False},
            {"role": "CB", "x": -1.0, "y": 0.25, "controllable": False},
            {"role": "CB", "x": -1.0, "y": -0.25, "controllable": False},
            {"role": "RB", "x": -0.7, "y": -0.75, "controllable": False},
            {"role": "CM", "x": 0.0, "y": 0.5, "controllable": True},
            {"role": "CM", "x": -0.2, "y": 0.0, "controllable": True},
            {"role": "CM", "x": 0.0, "y": -0.5, "controllable": True},
            {"role": "LM", "x": 0.6, "y": 0.75, "controllable": True},
            {"role": "CF", "x": 1.0, "y": 0.0, "controllable": True},
            {"role": "RM", "x": 0.6, "y": -0.75, "controllable": True},
        ]
    if not right_team["formation"]:
        mirrored = []
        for entry in left_team["formation"]:
            mirrored.append({
                "role": entry["role"],
                "x": -entry["x"],
                "y": entry["y"],
                "controllable": entry.get("controllable", False),
            })
        right_team["formation"] = mirrored

    # Fallback players: if catalog has formation but no players, generate generic profiles
    if not left_team["players"] and left_team["formation"]:
        left_team["players"] = _generic_players(left_team["formation"])
    if not right_team["players"] and right_team["formation"]:
        right_team["players"] = _generic_players(right_team["formation"])

    # Enrich both teams with procedural avatar metadata.
    # If catalog already has values (e.g. from DB), keep them. Otherwise generate.
    for i, p in enumerate(left_team["players"]):
        avatar = _generate_procedural_avatar(p["name"], i, 0)
        for key, val in avatar.items():
            if key not in p or p[key] is None:
                p[key] = val
    for i, p in enumerate(right_team["players"]):
        avatar = _generate_procedural_avatar(p["name"], i, 1)
        for key, val in avatar.items():
            if key not in p or p[key] is None:
                p[key] = val

    # Ensure no null values are sent to C++ GF server (nlohmann::json .value()
    # throws type_error.302 when key exists but value is null)
    for team in (left_team, right_team):
        for key in ("short_name", "color_primary", "color_secondary",
                    "color_rgb1", "color_rgb2", "kit_texture_url", "league"):
            if team.get(key) is None:
                team[key] = ""

    return {
        "duration_seconds": duration,
        "mode": mode,
        "stadium_id": stadium_id or "",
        "left_team": left_team,
        "right_team": right_team,
    }


def _generic_players(formation):
    """Generate 11 generic player profiles with balanced skills when DB has none."""
    generic_skills = {
        "physical_balance": 0.70, "physical_reaction": 0.70, "physical_acceleration": 0.70,
        "physical_velocity": 0.70, "physical_stamina": 0.70, "physical_agility": 0.70,
        "physical_shotpower": 0.70,
        "technical_standingtackle": 0.65, "technical_slidingtackle": 0.60,
        "technical_ballcontrol": 0.70, "technical_dribble": 0.65,
        "technical_shortpass": 0.70, "technical_highpass": 0.65, "technical_header": 0.60,
        "technical_shot": 0.70, "technical_volley": 0.55,
        "mental_calmness": 0.70, "mental_workrate": 0.70, "mental_resilience": 0.70,
        "mental_defensivepositioning": 0.65, "mental_offensivepositioning": 0.65,
        "mental_vision": 0.70,
    }
    players = []
    for i, entry in enumerate(formation):
        players.append({
            "name": f"Player {i+1}",
            "position": entry["role"],
            "number": i + 1,
            "skills": generic_skills.copy(),
        })
    return players


def _write_config_to_disk(room_id: str, match_config: dict) -> str:
    """Write match config dict to disk, return file path."""
    config_path = os.path.join(CONFIG_DIR, f"{room_id}.json")
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(match_config, f, indent=2)
    print(f"[Session] Match config written to {config_path}")
    return config_path


async def _spawn_gf_server(
    room_id: str,
    match_config: dict,
    mode: str,
    player_a: str,
    player_b: Optional[str],
    team_a: Optional[str],
    team_b: Optional[str],
    stadium_id: Optional[str],
    duration: int,
    gf_token: str,
):
    """Spawn the GF server process (local, queue, or mock)."""
    spawn_mode = os.getenv("GF_SPAWN_MODE", "local")
    players = [p for p in [player_a, player_b] if p]

    if spawn_mode == "queue":
        spawn_request = {
            "room_id": room_id,
            "token": gf_token,
            "team_a": team_a or "default-a",
            "team_b": team_b or "default-b",
            "stadium_id": stadium_id or "default-stadium",
            "duration": duration,
            "mode": mode,
            "player_a": player_a,
            "player_b": player_b,
            "match_config": match_config,
        }
        await redis.lpush("gf.spawn", json.dumps(spawn_request))
        active_matches[room_id] = {"queued": True, "players": players, "started_at": datetime.utcnow().isoformat(), "duration": duration}
    elif spawn_mode == "mock":
        env = os.environ.copy()
        env["ROOM_ID"] = room_id
        env["REDIS_URL"] = REDIS_URL
        env["LIVEKIT_URL"] = LK_URL
        env["GF_TOKEN"] = gf_token
        env["DURATION"] = str(duration)
        if not env.get("PATH"):
            env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        print(f"[Session] Spawning GF simulator for room {room_id}")
        try:
            proc = subprocess.Popen(
                ["python3", "-u", "/app/gf_simulator.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
            )
            print(f"[Session] GF simulator started with PID {proc.pid}")
            active_matches[room_id] = {"proc": proc, "pid": proc.pid, "players": players, "started_at": datetime.utcnow().isoformat(), "duration": duration}
            asyncio.create_task(monitor_process(room_id, proc))
        except Exception as e:
            print(f"[Session] Failed to spawn GF simulator: {e}")
    else:
        config_path = _write_config_to_disk(room_id, match_config)
        proc = await asyncio.create_subprocess_exec(
            GF_BINARY_PATH,
            f"--room-id={room_id}",
            f"--team-a={team_a or 'default-a'}",
            f"--team-b={team_b or 'default-b'}",
            f"--stadium={stadium_id or 'default-stadium'}",
            f"--player-a={player_a}",
            f"--player-b={player_b or 'bot'}",
            f"--duration={duration}",
            f"--mode={mode}",
            f"--stats-url={STATS_SERVICE_URL}",
            f"--redis-url={REDIS_URL}",
            f"--config-file={config_path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        active_matches[room_id] = {"proc": proc, "pid": proc.pid, "players": players, "started_at": datetime.utcnow().isoformat(), "duration": duration}
        asyncio.create_task(monitor_process(room_id, proc))


@app.post("/internal/create-match")
async def create_match(req: CreateMatchRequest):
    room_id = f"match-{uuid.uuid4()}"

    mode = req.mode if req.mode in ("1v1", "vs_ai", "ai_vs_ai") else "vs_ai"
    if req.mode == "ai_vs_ai":
        print(f"[Session] ai_vs_ai mode requested — bot vs bot, no human player")

    match_config = await _build_match_config(room_id, req.team_a, req.team_b, req.duration, mode, req.stadium_id)

    # 1. Create LiveKit room
    await lkapi.room.create_room(
        CreateRoomRequest(name=room_id, max_participants=10, empty_timeout=300)
    )

    # 2. Generate token for GF server
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

    # 2b. Generate token for creator (player A)
    client_token = (
        AccessToken(LK_KEY, LK_SECRET)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_id,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_identity(req.player_a)
        .to_jwt()
    )

    if mode == "1v1":
        # PvP waiting mode: do NOT spawn GF yet, wait for player B to join
        match_info = {
            "room_id": room_id,
            "livekit_url": LK_URL,
            "players": [req.player_a],
            "status": "waiting",
            "mode": mode,
            "team_a": req.team_a,
            "team_b": req.team_b,
            "stadium_id": req.stadium_id,
            "duration": req.duration,
            "match_config": match_config,
            "gf_token": gf_token,
        }
        match_json = json.dumps(match_info)
        await redis.setex(f"match:{req.player_a}", 120, match_json)
        await redis.setex(f"room:{room_id}", 3600, match_json)
        print(f"[Session] Created waiting PvP match {room_id} for player {req.player_a}")
        return {"room_id": room_id, "livekit_url": LK_URL, "token": client_token, "status": "waiting"}

    # Immediate spawn for vs_ai / ai_vs_ai
    await _spawn_gf_server(
        room_id, match_config, mode, req.player_a, req.player_b,
        req.team_a, req.team_b, req.stadium_id, req.duration, gf_token,
    )

    match_info = {
        "room_id": room_id,
        "livekit_url": LK_URL,
        "players": [req.player_a, req.player_b or "bot"],
        "status": "running",
    }
    match_json = json.dumps(match_info)
    await redis.setex(f"match:{req.player_a}", 120, match_json)
    if req.player_b:
        await redis.setex(f"match:{req.player_b}", 120, match_json)
    await redis.setex(f"room:{room_id}", 3600, match_json)

    return {"room_id": room_id, "livekit_url": LK_URL, "token": client_token, "status": "running"}


@app.get("/internal/waiting-matches")
async def waiting_matches():
    """Return all PvP matches currently waiting for a second player."""
    matches = []
    try:
        keys = await redis.keys("room:match-*")
        for key in keys:
            data = await redis.get(key)
            if not data:
                continue
            try:
                info = json.loads(data)
                if info.get("status") == "waiting":
                    matches.append({
                        "room_id": info["room_id"],
                        "player_a": info["players"][0] if info.get("players") else None,
                        "team_a": info.get("team_a"),
                        "team_b": info.get("team_b"),
                        "duration": info.get("duration"),
                    })
            except json.JSONDecodeError:
                continue
    except Exception as e:
        print(f"[Session] waiting-matches error: {e}", flush=True)
    return {"matches": matches}


@app.post("/internal/join-match")
async def join_match(req: JoinMatchRequest):
    """Player B joins a waiting PvP match and the GF server is spawned."""
    room_id = req.room_id
    data = await redis.get(f"room:{room_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Match not found")

    try:
        info = json.loads(data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Corrupted match data")

    if info.get("status") != "waiting":
        raise HTTPException(status_code=400, detail="Match is not waiting for players")

    if req.player_id in info.get("players", []):
        raise HTTPException(status_code=400, detail="Player already in match")

    # Update match info
    info["players"].append(req.player_id)
    info["status"] = "running"
    info["player_b"] = req.player_id

    # Spawn GF server now that both players are present
    await _spawn_gf_server(
        room_id,
        info.get("match_config", {}),
        info.get("mode", "1v1"),
        info["players"][0],
        req.player_id,
        info.get("team_a"),
        info.get("team_b"),
        info.get("stadium_id"),
        info.get("duration", 600),
        info.get("gf_token", ""),
    )

    # Generate token for joining player (Player B)
    player_b_token = (
        AccessToken(LK_KEY, LK_SECRET)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_id,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_identity(req.player_id)
        .to_jwt()
    )

    # Persist updated info
    await redis.setex(f"match:{req.player_id}", 120, json.dumps(info))
    await redis.setex(f"room:{room_id}", 3600, json.dumps(info))

    print(f"[Session] Player {req.player_id} joined match {room_id}. GF spawned. Match running.")
    return {"room_id": room_id, "livekit_url": LK_URL, "token": player_b_token, "status": "running"}


def _stream_output(proc: subprocess.Popen, room_id: str):
    """Read stdout/stderr line by line and print in real-time (blocking, run in thread)."""
    import threading
    def reader(stream, label):
        try:
            for line in iter(stream.readline, b""):
                if not line:
                    break
                print(f"[GF {room_id}] {label}: {line.decode(errors='replace').rstrip()}", flush=True)
        except Exception as e:
            print(f"[GF {room_id}] {label} reader error: {e}", flush=True)
    t_out = threading.Thread(target=reader, args=(proc.stdout, "stdout"), daemon=True)
    t_err = threading.Thread(target=reader, args=(proc.stderr, "stderr"), daemon=True)
    t_out.start()
    t_err.start()
    proc.wait()
    t_out.join(timeout=2)
    t_err.join(timeout=2)


async def monitor_process(room_id: str, proc: subprocess.Popen):
    await asyncio.to_thread(_stream_output, proc, room_id)
    exit_code = proc.returncode
    print(f"[GF {room_id}] process exited with code {exit_code}", flush=True)
    active_matches.pop(room_id, None)
    if exit_code != 0:
        await redis.publish("gf.crashed", room_id)
    else:
        await redis.publish("gf.finished", room_id)
    await redis.delete(f"room:{room_id}")


@app.get("/health")
async def health():
    return {"status": "ok", "active_matches": len(active_matches)}
