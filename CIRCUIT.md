# DZFoot GF Circuit — Architecture complète avec timeouts, crash recovery, VM health

## Circuit Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SESSION SERVICE (Python)                           │
│                                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐ │
│  │ listen_gf_   │   │ listen_gf_   │   │ check_worker │   │ check_match_ │ │
│  │ ready()      │   │ crashed()    │   │ _health()    │   │ timeouts()   │ │
│  └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘ │
│         ▲                  ▲                  ▲                  ▲          │
└─────────┼──────────────────┼──────────────────┼──────────────────┼────────┘
          │                  │                  │                  │
          │ Redis PUB        │ Redis PUB        │ Redis HGET       │ Memory scan
          │ "gf.ready"       │ "gf.crashed"     │ "gf.workers"     │ active_matches
          │                  │                  │                  │
┌─────────┼──────────────────┼──────────────────┼──────────────────┼────────┐
│         │                  │                  │                  │         │
│  ┌──────┴──────────────────┴──────────────────┴──────────────────┴──────┐ │
│  │                         REDIS                                          │ │
│  │  Queues: gf.spawn (list)     Hashes: gf.active, gf.worker_map          │ │
│  │  PubSub: gf.ready, gf.crashed, gf.finished, match.crashed             │ │
│  │  Heartbeat: gf.workers, gf.heartbeat                                  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│         │                  │                  │                  │          │
└─────────┼──────────────────┼──────────────────┼──────────────────┼────────┘
          │ BRPOP            │ LPUSH/HSET       │                  │
          │ "gf.spawn"       │ PUBLISH          │                  │
          │                  │                  │                  │
┌─────────┼──────────────────┼──────────────────┼──────────────────┼────────┐
│         │                  │                  │                  │         │
│  ┌──────▼──────────────────▼──────────────────▼──────────────────▼──────┐ │
│  │                    GF WORKER (VM-01, VM-02, ...)                       │ │
│  │                                                                        │ │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐   │ │
│  │  │ Heartbeat loop  │    │ Poll loop       │    │ Watchdog loop   │   │ │
│  │  │ HSET gf.workers │    │ BRPOP gf.spawn  │    │ Monitor PID     │   │ │
│  │  │ every 10s       │    │ → Spawn GF      │    │ → Detect crash  │   │ │
│  │  └─────────────────┘    └─────────────────┘    └─────────────────┘   │ │
│  │         │                      │                      │               │ │
│  │         ▼                      ▼                      ▼               │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │ │
│  │  │ GF PROCESS (C++ GameServer)                                     │   │ │
│  │  │                                                                 │   │ │
│  │  │  run() ──► PUBLISH gf.ready (confirm ready)                   │   │ │
│  │  │         ──► HSET gf.heartbeat (every 1s)                      │   │ │
│  │  │         ──► LiveKit.connect() ──► Room "match-abc"             │   │ │
│  │  │         ──► Broadcast GameState 60 tick/s                     │   │ │
│  │  │         ──► Normal exit ──► PUBLISH gf.finished               │   │ │
│  │  │         ──► Crash ──► Watchdog PUBLISH gf.crashed           │   │ │
│  │  └─────────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  LiveKit Room "match-abc"                                                    │
│  ├──► Client Android #1 (data channel "gs", "ev")                            │
│  ├──► Client Android #2 (data channel "gs", "ev")                            │
│  └──► GF Server bot (data channel "gs", "ev", "in")                          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## States du match dans Session Service

```
CREATED ──► WAITING_GF ──► RUNNING ──► FINISHED
    │            │            │            │
    │            │            │            ▼
    │            │            │         [Cleanup]
    │            │            │
    │            │            ▼
    │            │        [Post result]
    │            │
    │            ▼
    │       [Timeout 30s]
    │       ──► CRASHED
    │
    ▼
[Timeout 30s]
──► CRASHED
```

## Messages Redis

| Channel | Direction | Payload | Trigger |
|---|---|---|---|
| `gf.spawn` | Session → Workers | JSON room config | Create match |
| `gf.ready` | Worker → Session | room_id | GF process started, LiveKit connected |
| `gf.crashed` | Worker/Watchdog → Session | room_id | GF exit code ≠ 0, or VM dead |
| `gf.finished` | Worker/Watchdog → Session | room_id | GF exit code 0 (normal end) |
| `match.crashed` | Session → Clients | room_id | Notify clients of crash |
| `match.finished` | Session → Stats | room_id | Trigger stats persistence |

## Redis Keys

| Key | Type | Purpose |
|---|---|---|
| `gf.spawn` | List | Queue of pending match spawn requests |
| `gf.active` | Hash | room_id → PID mapping |
| `gf.worker_map` | Hash | room_id → worker_id mapping |
| `gf.workers` | Hash | worker_id → last_heartbeat_timestamp |
| `gf.heartbeat` | Hash | room_id → last_heartbeat_timestamp |
| `room:{room_id}` | String | Match metadata (TTL 1h) |
| `match:{player_id}` | String | Player → match mapping (TTL 2min) |

## Timeouts configurables

| Variable | Défaut | Description |
|---|---|---|
| `GF_SPAWN_TIMEOUT` | 30s | Max attente pour `gf.ready` après spawn |
| `GF_MATCH_TIMEOUT` | 900s | Durée max match + buffer avant kill forcé |
| `WORKER_HEARTBEAT_INTERVAL` | 10s | Fréquence heartbeat worker |
| `WORKER_DEATH_THRESHOLD` | 60s | Sans heartbeat → worker considéré mort |

## Crash Recovery Scenarios

### 1. GF crash immédiat (< 5s)
- Watchdog détecte `kill -0` échoue
- Publie `gf.crashed`
- Session Service notifie clients

### 2. GF crash en cours de match
- Watchdog détecte process mort
- Publie `gf.crashed`
- Session Service marque match comme `crashed`
- Clients affichent "Connexion perdue"

### 3. VM entière down (worker mort)
- `check_worker_health()` détecte heartbeat absent > 60s
- Trouve les rooms assignées via `gf.worker_map`
- Publie `gf.crashed` pour chaque room
- Nettoie `gf.workers`

### 4. Match bloqué (infinite loop GF)
- `check_match_timeouts()` détecte elapsed > duration + buffer
- Publie `gf.crashed` pour forcer cleanup

## LiveKit Integration

### GF Server
```cpp
// In GameServer::run()
// 1. Connect to LiveKit as bot
lkBridge.connect(livekitUrl, livekitToken);
// 2. Publish GameState 60 tick/s → topic "gs"
// 3. Publish events → topic "ev"
// 4. Subscribe to topic "in" for player inputs
```

### Client Android
```kotlin
// In LiveKitManager
room.events.collect { event ->
    is RoomEvent.DataReceived -> {
        when (event.topic) {
            "gs" -> jniBridge.nativeOnGameStateReceived(event.data)
            "ev" -> jniBridge.nativeOnGameEvent(event.data)
        }
    }
    is RoomEvent.ParticipantDisconnected -> {
        // GF bot left = match ended or crashed
    }
}
```

## Startup Sequence

```
1. Session Service crée LiveKit room
2. Session Service publie dans Redis queue gf.spawn
3. Worker VM consomme message (BRPOP)
4. Worker spawn process GF
5. GF se connecte à LiveKit room
6. GF PUBLISH gf.ready
7. Session Service met match à RUNNING
8. Clients reçoivent tokens et rejoignent la room
9. GF broadcast GameState 60/s
10. Match se termine → GF PUBLISH gf.finished
11. Session Service cleanup
```

## Shutdown Sequence (VM down)

```
1. VM reçoit SIGTERM
2. Trap cleanup() dans gf-worker.sh
3. Kill tous les process GF actifs
4. HDEL gf.active, PUBLISH gf.crashed pour chaque room
5. HDEL gf.workers
6. Clients perdent connexion LiveKit → affichent "Serveur déconnecté"
```
