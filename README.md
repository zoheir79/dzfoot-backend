# dzfoot-backend

Backend services for DZFoot — 5 microservices + PostgreSQL + Redis.

## Quick Start

```bash
cp .env.example .env
# Edit .env with your LiveKit credentials
docker-compose up --build
```

## Services

| Service | Port | Role |
|---|---|---|
| Account | 8001 | Auth, JWT, profiles, friends |
| Session | 8002 | Spawn GF server, LiveKit rooms |
| Matchmaking | 8003 | ELO queue, match pairing |
| Stats | 8004 | Match history, leaderboard, ELO |
| Catalog | 8005 | Teams, players, stadiums |

## Architecture

```
Client/Android  ──REST/JWT──►  Account
       │                          │
       │                    Matchmaking
       │                          │
       └──LiveKit◄────Session────┘
                          │
                     Spawn GF Server
                          │
                     Stats (POST result)
```

## Database

PostgreSQL 16 schema in `schema.sql`. Seed data in `init_db.sql`.

Tables: `users`, `teams`, `players`, `stadiums`, `matches`, `match_stats`, `friendships`.

## License
MIT
