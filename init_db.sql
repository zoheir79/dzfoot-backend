-- Seed data for DZFoot — Full player profiles with all 22 GF skills
INSERT INTO teams (name, country, color_primary, color_secondary, formation) VALUES
('Algeria FC', 'Algeria', '#009639', '#FFFFFF', '4-3-3'),
('Casablanca United', 'Morocco', '#E31937', '#006341', '4-4-2'),
('Tunis Eagles', 'Tunisia', '#FFFFFF', '#E31937', '4-3-3'),
('Cairo Pharaohs', 'Egypt', '#C8102E', '#FFFFFF', '3-5-2');

INSERT INTO stadiums (name, city, capacity, ar_marker_ref, pitch_texture) VALUES
('Stade 5 Juillet', 'Algiers', 80000, 'marker_algiers', 'grass_sunny'),
('Mohamed V', 'Casablanca', 67000, 'marker_casablanca', 'grass_overcast'),
('Radès Stadium', 'Tunis', 60000, 'marker_tunis', 'grass_night'),
('Cairo International', 'Cairo', 75000, 'marker_cairo', 'grass_sunny');

-- Helper: full player insert with all 22 skills (avoids giant column list each row)
-- Algeria FC 4-3-3 (11 players)
WITH t AS (SELECT id FROM teams WHERE name='Algeria FC')
INSERT INTO players (
  team_id, name, position, number,
  speed, shooting, passing, defense, stamina,
  physical_balance, physical_reaction, physical_acceleration, physical_velocity, physical_stamina,
  physical_agility, physical_shotpower,
  technical_standingtackle, technical_slidingtackle, technical_ballcontrol, technical_dribble,
  technical_shortpass, technical_highpass, technical_header, technical_shot, technical_volley,
  mental_calmness, mental_workrate, mental_resilience,
  mental_defensivepositioning, mental_offensivepositioning, mental_vision
)
SELECT t.id, 'Mbolhi',    'GK', 23,
  0.70, 0.40, 0.60, 0.88, 0.82,  -- legacy
  0.75, 0.82, 0.72, 0.70, 0.82, 0.70, 0.60,  -- physical
  0.88, 0.65, 0.55, 0.45, 0.60, 0.55, 0.50, 0.40, 0.30,  -- technical
  0.85, 0.80, 0.88, 0.92, 0.20, 0.70 FROM t  -- mental
UNION ALL SELECT t.id, 'Mandi',     'CB', 2,
  0.72, 0.55, 0.68, 0.85, 0.82,
  0.82, 0.78, 0.68, 0.72, 0.82, 0.65, 0.72,
  0.85, 0.80, 0.68, 0.55, 0.72, 0.65, 0.78, 0.55, 0.45,
  0.78, 0.82, 0.85, 0.88, 0.55, 0.72 FROM t
UNION ALL SELECT t.id, 'Bensebaini','CB', 5,
  0.74, 0.50, 0.65, 0.82, 0.80,
  0.80, 0.76, 0.70, 0.74, 0.80, 0.68, 0.70,
  0.82, 0.78, 0.65, 0.52, 0.68, 0.62, 0.72, 0.50, 0.40,
  0.76, 0.80, 0.82, 0.85, 0.50, 0.70 FROM t
UNION ALL SELECT t.id, 'Atal',      'LB', 20,
  0.88, 0.60, 0.72, 0.70, 0.78,
  0.75, 0.82, 0.88, 0.88, 0.78, 0.90, 0.72,
  0.70, 0.65, 0.72, 0.75, 0.75, 0.70, 0.68, 0.60, 0.45,
  0.74, 0.88, 0.78, 0.72, 0.70, 0.75 FROM t
UNION ALL SELECT t.id, 'Zedadka',   'RB', 21,
  0.82, 0.55, 0.68, 0.72, 0.78,
  0.76, 0.78, 0.80, 0.82, 0.78, 0.82, 0.68,
  0.72, 0.68, 0.68, 0.65, 0.70, 0.65, 0.68, 0.55, 0.40,
  0.72, 0.82, 0.76, 0.74, 0.68, 0.72 FROM t
UNION ALL SELECT t.id, 'Bennacer',  'CM', 4,
  0.78, 0.70, 0.90, 0.65, 0.85,
  0.75, 0.85, 0.76, 0.78, 0.85, 0.78, 0.68,
  0.72, 0.68, 0.85, 0.72, 0.90, 0.82, 0.72, 0.70, 0.50,
  0.88, 0.86, 0.82, 0.70, 0.75, 0.88 FROM t
UNION ALL SELECT t.id, 'Zerrouki',  'CM', 6,
  0.76, 0.62, 0.82, 0.70, 0.84,
  0.78, 0.80, 0.74, 0.76, 0.84, 0.74, 0.70,
  0.75, 0.70, 0.80, 0.68, 0.85, 0.78, 0.68, 0.62, 0.48,
  0.82, 0.84, 0.80, 0.72, 0.72, 0.82 FROM t
UNION ALL SELECT t.id, 'Feghouli',  'CM', 10,
  0.76, 0.68, 0.78, 0.58, 0.76,
  0.72, 0.78, 0.76, 0.76, 0.76, 0.78, 0.72,
  0.58, 0.55, 0.78, 0.72, 0.80, 0.72, 0.74, 0.68, 0.55,
  0.80, 0.82, 0.78, 0.62, 0.72, 0.82 FROM t
UNION ALL SELECT t.id, 'Benrahma',  'LW', 7,
  0.88, 0.82, 0.78, 0.45, 0.72,
  0.68, 0.82, 0.88, 0.88, 0.72, 0.90, 0.78,
  0.42, 0.40, 0.85, 0.88, 0.78, 0.72, 0.70, 0.82, 0.65,
  0.76, 0.78, 0.74, 0.48, 0.82, 0.80 FROM t
UNION ALL SELECT t.id, 'Mahrez',    'RW', 26,
  0.85, 0.86, 0.84, 0.40, 0.75,
  0.70, 0.86, 0.82, 0.85, 0.75, 0.88, 0.82,
  0.40, 0.38, 0.90, 0.88, 0.82, 0.75, 0.85, 0.86, 0.72,
  0.82, 0.80, 0.78, 0.45, 0.88, 0.85 FROM t
UNION ALL SELECT t.id, 'Bounedjah', 'CF', 9,
  0.74, 0.88, 0.60, 0.42, 0.78,
  0.82, 0.78, 0.72, 0.74, 0.78, 0.68, 0.85,
  0.42, 0.40, 0.72, 0.60, 0.60, 0.78, 0.88, 0.78, 0.75,
  0.78, 0.76, 0.80, 0.45, 0.88, 0.72 FROM t;
