-- Seed data for DZFoot
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

-- Example players for Algeria FC
WITH t AS (SELECT id FROM teams WHERE name='Algeria FC')
INSERT INTO players (team_id, name, position, number, speed, shooting, passing, defense)
SELECT t.id, 'Benrahma', 'LW', 7, 0.88, 0.82, 0.78, 0.45 FROM t
UNION ALL SELECT t.id, 'Mahrez', 'RW', 26, 0.85, 0.86, 0.84, 0.40 FROM t
UNION ALL SELECT t.id, 'Bennacer', 'CM', 4, 0.78, 0.70, 0.90, 0.65 FROM t
UNION ALL SELECT t.id, 'Mandi', 'CB', 2, 0.72, 0.55, 0.68, 0.85 FROM t
UNION ALL SELECT t.id, 'Mbolhi', 'GK', 23, 0.70, 0.40, 0.60, 0.88 FROM t;
