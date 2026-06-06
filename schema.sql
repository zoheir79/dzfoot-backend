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

-- teams
CREATE TABLE teams (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(100) NOT NULL,
    country          VARCHAR(100),
    logo_url         TEXT,
    kit_texture_url  TEXT,
    short_name       VARCHAR(10),
    color_primary    VARCHAR(7),
    color_secondary  VARCHAR(7),
    color_rgb1       VARCHAR(20),   -- e.g. "220,0,0" for GF Vector3
    color_rgb2       VARCHAR(20),
    league           VARCHAR(50) DEFAULT 'Ligue 1 Mobilis',
    formation        VARCHAR(20) DEFAULT '4-3-3',
    stadium_id       UUID REFERENCES stadiums(id)
);

-- players (all 22 skills match GameplayFootball PlayerStat enum)
CREATE TABLE players (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     UUID REFERENCES teams(id),
    name        VARCHAR(100) NOT NULL,
    position    VARCHAR(5),
    number      INTEGER,
    -- Legacy shortcuts (mapped to GF native stats)
    speed       FLOAT DEFAULT 0.75,   -- physical_velocity
    shooting    FLOAT DEFAULT 0.70,   -- technical_shot
    passing     FLOAT DEFAULT 0.72,   -- technical_shortpass
    defense     FLOAT DEFAULT 0.65,   -- technical_standingtackle
    stamina     FLOAT DEFAULT 0.80,   -- physical_stamina
    -- Full GF PlayerStat skillset (0.0 .. 1.0)
    physical_balance            FLOAT DEFAULT 0.70,
    physical_reaction           FLOAT DEFAULT 0.70,
    physical_acceleration       FLOAT DEFAULT 0.70,
    physical_velocity           FLOAT DEFAULT 0.75,
    physical_stamina            FLOAT DEFAULT 0.80,
    physical_agility            FLOAT DEFAULT 0.70,
    physical_shotpower          FLOAT DEFAULT 0.70,
    technical_standingtackle    FLOAT DEFAULT 0.65,
    technical_slidingtackle     FLOAT DEFAULT 0.60,
    technical_ballcontrol       FLOAT DEFAULT 0.72,
    technical_dribble           FLOAT DEFAULT 0.68,
    technical_shortpass         FLOAT DEFAULT 0.72,
    technical_highpass          FLOAT DEFAULT 0.65,
    technical_header            FLOAT DEFAULT 0.60,
    technical_shot              FLOAT DEFAULT 0.70,
    technical_volley            FLOAT DEFAULT 0.55,
    mental_calmness             FLOAT DEFAULT 0.70,
    mental_workrate             FLOAT DEFAULT 0.70,
    mental_resilience           FLOAT DEFAULT 0.70,
    mental_defensivepositioning FLOAT DEFAULT 0.65,
    mental_offensivepositioning FLOAT DEFAULT 0.65,
    mental_vision               FLOAT DEFAULT 0.70,
    model_ref   TEXT,
    -- Avatar & Photo (deterministic from player name hash)
    photo_url           TEXT,
    photo_local         TEXT,
    avatar_config_id    VARCHAR(16),  -- deterministic hex hash (e.g. '4b2f9c1a')
    skin_color          INT DEFAULT 3,   -- 0..6 (7 teintes)
    hair_style          INT DEFAULT 0,   -- 0..4 (short, long, mohawk, curly, bald)
    hair_color          INT DEFAULT 0,   -- 0..7 (black, brown, blonde, red, gray, white, dark_brown, auburn)
    body_type           INT DEFAULT 1,   -- 0..3 (thin, average, muscular, heavy)
    beard_style         INT DEFAULT 0,   -- 0..3 (none, stubble, short, full)
    eye_color           INT DEFAULT 0    -- 0..3 (brown, blue, green, hazel)
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
