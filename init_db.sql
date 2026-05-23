-- Seed data for DZFoot — Algerian Ligue 1 Mobilis clubs (2024-25)
INSERT INTO teams (name, country, short_name, color_primary, color_secondary, color_rgb1, color_rgb2, league, formation, kit_texture_url) VALUES
('CR Belouizdad', 'Algeria', 'CRB', '#DC0000', '#FFFFFF', '220,0,0', '255,255,255', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/crbelouizdad_dzfoot'),
('JS Kabylie', 'Algeria', 'JSK', '#FFD700', '#008000', '255,215,0', '0,128,0', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/jskabylie_dzfoot'),
('MC Alger', 'Algeria', 'MCA', '#DC0000', '#008000', '220,0,0', '0,128,0', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/mcalger_dzfoot'),
('USM Alger', 'Algeria', 'USM', '#000000', '#DC0000', '0,0,0', '220,0,0', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/usmalger_dzfoot'),
('ES Setif', 'Algeria', 'ESS', '#000000', '#FFFFFF', '0,0,0', '255,255,255', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/essetif_dzfoot'),
('CS Constantine', 'Algeria', 'CSC', '#DC0000', '#008000', '220,0,0', '0,128,0', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/csconstantine_dzfoot'),
('Paradou AC', 'Algeria', 'PAC', '#FFD700', '#0000C8', '255,215,0', '0,0,200', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/paradouac_dzfoot'),
('ASO Chlef', 'Algeria', 'ASO', '#FF8C00', '#000000', '255,140,0', '0,0,0', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/asochlef_dzfoot'),
('MC Oran', 'Algeria', 'MCO', '#DC0000', '#FFFFFF', '220,0,0', '255,255,255', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/mcoran_dzfoot'),
('ES Ben Aknoun', 'Algeria', 'ESB', '#FFFFFF', '#000000', '255,255,255', '0,0,0', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/esbenaknoun_dzfoot'),
('ES Mostaganem', 'Algeria', 'ESM', '#000080', '#FFFFFF', '0,0,128', '255,255,255', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/esmostaganem_dzfoot'),
('JS Saoura', 'Algeria', 'JSS', '#008000', '#FFD700', '0,128,0', '255,215,0', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/jssaoura_dzfoot'),
('MB Rouissat', 'Algeria', 'MBR', '#0000FF', '#FFFFFF', '0,0,255', '255,255,255', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/mbrouissat_dzfoot'),
('MC El Bayadh', 'Algeria', 'MCE', '#008000', '#FFFFFF', '0,128,0', '255,255,255', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/mcelbayadh_dzfoot'),
('O Akbou', 'Algeria', 'OAK', '#FF0000', '#000000', '255,0,0', '0,0,0', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/oakbou_dzfoot'),
('USM Khenchela', 'Algeria', 'USK', '#000000', '#FFD700', '0,0,0', '255,215,0', 'Ligue 1 Mobilis', '4-3-3', 'images_teams/ligue1dz/usmkhenchela_dzfoot');

INSERT INTO stadiums (name, city, capacity, ar_marker_ref, pitch_texture) VALUES
('Stade 5 Juillet 1962', 'Algiers', 80000, 'marker_5juillet', 'grass_sunny'),
('Stade 20 Aout 1955', 'Algiers', 15000, 'marker_20aout', 'grass_sunny'),
('Stade du 1er Novembre', 'Tizi Ouzou', 25000, 'marker_tiziouzou', 'grass_sunny'),
('Stade Miloud Hadefi', 'Oran', 40000, 'marker_oran', 'grass_overcast'),
('Stade Mustapha Tchaker', 'Blida', 35000, 'marker_blida', 'grass_sunny'),
('Stade 8 Mai 1945', 'Setif', 25000, 'marker_setif', 'grass_night'),
('Stade Mohamed Hamlaoui', 'Constantine', 30000, 'marker_constantine', 'grass_sunny'),
('Stade 24 Fevrier 1956', 'Sidi Bel Abbes', 20000, 'marker_sba', 'grass_overcast');

-- Helper: full player insert with all 22 skills (avoids giant column list each row)
-- Algeria FC 4-3-3 (11 players)
WITH t AS (SELECT id FROM teams WHERE name='CR Belouizdad')
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

-- JS Kabylie 4-3-3 (11 players)
WITH t AS (SELECT id FROM teams WHERE name='JS Kabylie')
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
SELECT t.id, 'Saichi',    'GK', 1,
  0.72, 0.45, 0.68, 0.82, 0.82,
  0.78, 0.85, 0.72, 0.70, 0.82, 0.74, 0.65,
  0.82, 0.62, 0.62, 0.50, 0.68, 0.60, 0.58, 0.45, 0.35,
  0.82, 0.80, 0.85, 0.85, 0.28, 0.72 FROM t
UNION ALL SELECT t.id, 'Benlamri',  'CB', 4,
  0.72, 0.58, 0.75, 0.85, 0.82,
  0.82, 0.78, 0.70, 0.72, 0.82, 0.68, 0.70,
  0.85, 0.80, 0.70, 0.58, 0.75, 0.68, 0.80, 0.58, 0.48,
  0.80, 0.82, 0.85, 0.88, 0.58, 0.76 FROM t
UNION ALL SELECT t.id, 'Belkebla',  'CM', 5,
  0.76, 0.68, 0.80, 0.78, 0.85,
  0.78, 0.80, 0.74, 0.76, 0.85, 0.74, 0.72,
  0.78, 0.74, 0.80, 0.70, 0.80, 0.76, 0.72, 0.68, 0.55,
  0.82, 0.88, 0.82, 0.78, 0.68, 0.82 FROM t
UNION ALL SELECT t.id, 'Boudene',   'LW', 10,
  0.88, 0.82, 0.82, 0.42, 0.74,
  0.70, 0.85, 0.88, 0.88, 0.74, 0.90, 0.76,
  0.42, 0.38, 0.88, 0.86, 0.82, 0.76, 0.70, 0.82, 0.72,
  0.78, 0.82, 0.78, 0.48, 0.88, 0.86 FROM t
UNION ALL SELECT t.id, 'Hamroune',  'RW', 7,
  0.90, 0.80, 0.78, 0.40, 0.80,
  0.68, 0.82, 0.92, 0.90, 0.80, 0.92, 0.74,
  0.40, 0.36, 0.86, 0.88, 0.78, 0.70, 0.68, 0.80, 0.68,
  0.74, 0.86, 0.76, 0.46, 0.86, 0.84 FROM t
UNION ALL SELECT t.id, 'Banoune',   'CF', 9,
  0.78, 0.82, 0.68, 0.48, 0.80,
  0.80, 0.78, 0.76, 0.78, 0.80, 0.74, 0.80,
  0.48, 0.44, 0.76, 0.70, 0.68, 0.64, 0.82, 0.82, 0.74,
  0.78, 0.84, 0.80, 0.50, 0.86, 0.78 FROM t
UNION ALL SELECT t.id, 'Player7',   'CM', 8,
  0.70, 0.70, 0.70, 0.65, 0.70,
  0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70,
  0.65, 0.60, 0.70, 0.65, 0.70, 0.65, 0.60, 0.70, 0.55,
  0.70, 0.70, 0.70, 0.65, 0.65, 0.70 FROM t
UNION ALL SELECT t.id, 'Player8',   'CB', 3,
  0.70, 0.70, 0.70, 0.65, 0.70,
  0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70,
  0.65, 0.60, 0.70, 0.65, 0.70, 0.65, 0.60, 0.70, 0.55,
  0.70, 0.70, 0.70, 0.65, 0.65, 0.70 FROM t
UNION ALL SELECT t.id, 'Player9',   'LB', 6,
  0.70, 0.70, 0.70, 0.65, 0.70,
  0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70,
  0.65, 0.60, 0.70, 0.65, 0.70, 0.65, 0.60, 0.70, 0.55,
  0.70, 0.70, 0.70, 0.65, 0.65, 0.70 FROM t
UNION ALL SELECT t.id, 'Player10',  'RB', 2,
  0.70, 0.70, 0.70, 0.65, 0.70,
  0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70,
  0.65, 0.60, 0.70, 0.65, 0.70, 0.65, 0.60, 0.70, 0.55,
  0.70, 0.70, 0.70, 0.65, 0.65, 0.70 FROM t
UNION ALL SELECT t.id, 'Player11',  'RM', 11,
  0.70, 0.70, 0.70, 0.65, 0.70,
  0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70,
  0.65, 0.60, 0.70, 0.65, 0.70, 0.65, 0.60, 0.70, 0.55,
  0.70, 0.70, 0.70, 0.65, 0.65, 0.70 FROM t;
