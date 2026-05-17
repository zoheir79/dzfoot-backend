-- DZFoot Database Schema
-- PostgreSQL 15+

-- users
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pseudo        VARCHAR(30) UNIQUE NOT NULL,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    avatar_url    TEXT,
    elo           INTEGER DEFAULT 1000,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- teams
CREATE TABLE teams (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(100) NOT NULL,
    country          VARCHAR(100),
    logo_url         TEXT,
    color_primary    VARCHAR(7),
    color_secondary  VARCHAR(7),
    formation        VARCHAR(20) DEFAULT '4-3-3'
);

-- players
CREATE TABLE players (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     UUID REFERENCES teams(id),
    name        VARCHAR(100) NOT NULL,
    position    VARCHAR(5),
    number      INTEGER,
    speed       FLOAT DEFAULT 0.75,
    shooting    FLOAT DEFAULT 0.70,
    passing     FLOAT DEFAULT 0.72,
    defense     FLOAT DEFAULT 0.65,
    stamina     FLOAT DEFAULT 0.80,
    model_ref   TEXT
);

-- stadiums
CREATE TABLE stadiums (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR(200) NOT NULL,
    city           VARCHAR(100),
    capacity       INTEGER,
    model_3d_url   TEXT,
    ar_marker_ref  TEXT,
    pitch_texture  TEXT
);

-- matches
CREATE TABLE matches (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_a_id  UUID REFERENCES users(id),
    player_b_id  UUID REFERENCES users(id),
    team_a_id    UUID REFERENCES teams(id),
    team_b_id    UUID REFERENCES teams(id),
    stadium_id   UUID REFERENCES stadiums(id),
    score_a      INTEGER DEFAULT 0,
    score_b      INTEGER DEFAULT 0,
    duration_s   INTEGER,
    livekit_room TEXT,
    played_at    TIMESTAMPTZ DEFAULT NOW()
);

-- match_stats
CREATE TABLE match_stats (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id        UUID REFERENCES matches(id),
    player_id       UUID REFERENCES users(id),
    goals           INTEGER DEFAULT 0,
    shots           INTEGER DEFAULT 0,
    shots_on_target INTEGER DEFAULT 0,
    passes          INTEGER DEFAULT 0,
    passes_success  INTEGER DEFAULT 0,
    tackles         INTEGER DEFAULT 0,
    yellow_cards    INTEGER DEFAULT 0,
    red_cards       INTEGER DEFAULT 0,
    possession_pct  FLOAT DEFAULT 0.0,
    distance_m      FLOAT DEFAULT 0.0
);

-- friendships
CREATE TABLE friendships (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    friend_id   UUID REFERENCES users(id),
    status      VARCHAR(20) DEFAULT 'pending',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, friend_id)
);

-- Index
CREATE INDEX idx_matches_player_a ON matches(player_a_id);
CREATE INDEX idx_matches_player_b ON matches(player_b_id);
CREATE INDEX idx_matches_played_at ON matches(played_at DESC);
CREATE INDEX idx_match_stats_player ON match_stats(player_id);
CREATE INDEX idx_match_stats_match ON match_stats(match_id);
CREATE INDEX idx_users_elo ON users(elo DESC);
