# dzfoot-backend

Backend services for DZFoot — 5 microservices + PostgreSQL + Redis.

## Quick Start

```bash
cp .env.example .env
# Edit .env with your LiveKit credentials
docker-compose up --build
```

## Services

| Service | Port (dev) | Port (prod) | Role |
|---|---|---|---|
| Account | 8001 | internal only | Auth, JWT, profiles, friends |
| Session | 8002 | internal only | Spawn GF server, LiveKit rooms |
| Matchmaking | 8003 | internal only | ELO queue, match pairing |
| Stats | 8004 | internal only | Match history, leaderboard, ELO |
| Catalog | 8005 | internal only | Teams, players, stadiums |
| Nginx | 8080 | 80/443 | API Gateway (public entrypoint) |

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
