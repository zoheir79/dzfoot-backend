#!/bin/bash
# DZFoot GF Worker — Docker mode: spawns dedicated containers per match
set -e

REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
STATS_URL="${STATS_URL:-http://stats:8000}"
LIVEKIT_URL="${LIVEKIT_URL:-}"
GF_IMAGE="${GF_IMAGE:-dzfoot-gf-server:prod}"
GF_NETWORK="${GF_NETWORK:-dzfoot-backend_default}"
WORKER_ID="${HOSTNAME:-worker-docker}"

echo "[GF Docker Worker $WORKER_ID] Starting. Redis: $REDIS_URL"
echo "[GF Docker Worker $WORKER_ID] Image: $GF_IMAGE, Network: $GF_NETWORK"

# Check Docker access
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Cannot access Docker daemon. Mount /var/run/docker.sock."
    exit 1
fi

cleanup() {
    echo "[GF Docker Worker $WORKER_ID] Shutting down..."
    exit 0
}
trap cleanup SIGINT SIGTERM

while true; do
    RESULT=$(redis-cli -u "$REDIS_URL" BRPOP "gf.spawn" 10 2>/dev/null || true)
    
    if [ -z "$RESULT" ] || [ "$RESULT" = "nil" ]; then
        continue
    fi
    
    PAYLOAD=$(echo "$RESULT" | tail -n1)
    
    ROOM_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin)['room_id'])" 2>/dev/null || echo "")
    TOKEN=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")
    TEAM_A=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('team_a','default-a'))" 2>/dev/null || echo "default-a")
    TEAM_B=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('team_b','default-b'))" 2>/dev/null || echo "default-b")
    STADIUM=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stadium_id','default-stadium'))" 2>/dev/null || echo "default-stadium")
    DURATION=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('duration',600))" 2>/dev/null || echo "600")
    MODE=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('mode','vs_ai'))" 2>/dev/null || echo "vs_ai")
    PLAYER_A=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('player_a',''))" 2>/dev/null || echo "")
    PLAYER_B=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('player_b',''))" 2>/dev/null || echo "")

    # Extract match_config and write to temp file
    MATCH_CONFIG=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('match_config','')))" 2>/dev/null || echo "")
    CONFIG_VOLUME=""
    if [ -n "$MATCH_CONFIG" ] && [ "$MATCH_CONFIG" != "null" ] && [ "$MATCH_CONFIG" != "\"\"" ]; then
        CONFIG_TMP="/tmp/gf_${ROOM_ID}.json"
        echo "$MATCH_CONFIG" > "$CONFIG_TMP"
        CONFIG_VOLUME="-v ${CONFIG_TMP}:/tmp/match_config.json:ro"
    fi

    if [ -z "$ROOM_ID" ] || [ -z "$TOKEN" ]; then
        echo "[GF Docker Worker $WORKER_ID] Invalid payload, skipping"
        continue
    fi

    echo "[GF Docker Worker $WORKER_ID] Spawning container for room $ROOM_ID ($TEAM_A vs $TEAM_B, ${DURATION}s)"

    # Launch dedicated GF container
    docker run -d --rm \
        --name "gf-${ROOM_ID}" \
        --network "$GF_NETWORK" \
        -e LIVEKIT_URL="$LIVEKIT_URL" \
        -e LIVEKIT_TOKEN="$TOKEN" \
        -e REDIS_URL="$REDIS_URL" \
        -e STATS_URL="$STATS_URL" \
        $CONFIG_VOLUME \
        "$GF_IMAGE" \
        --room-id="$ROOM_ID" \
        --team-a="$TEAM_A" \
        --team-b="$TEAM_B" \
        --stadium="$STADIUM" \
        --duration="$DURATION" \
        --mode="$MODE" \
        --broadcast-hz=20 \
        --livekit-url="$LIVEKIT_URL" \
        --livekit-token="$TOKEN" \
        --stats-url="$STATS_URL" \
        --redis-url="$REDIS_URL" \
        ${PLAYER_A:+--player-a="$PLAYER_A"} \
        ${PLAYER_B:+--player-b="$PLAYER_B"} \
        ${CONFIG_TMP:+--config-file=/tmp/match_config.json} \
        2>&1

    # Signal ready to session service
    redis-cli -u "$REDIS_URL" PUBLISH "gf.ready" "$ROOM_ID" >/dev/null 2>&1 || true
    echo "[GF Docker Worker $WORKER_ID] Container gf-${ROOM_ID} launched"
done
