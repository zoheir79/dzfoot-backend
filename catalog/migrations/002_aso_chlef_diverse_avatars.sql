-- Gives ASO Chlef a roster covering every avatar variant:
-- skin 0..6, hair style 0..5 (short,long,mohawk,curly,ponytail,bald),
-- hair color 0..7, beard 0..3, body type 0..3, heights 1.70..1.92m (GK 1.86..1.90m).
-- Idempotent: safe to run several times.

ALTER TABLE players ADD COLUMN IF NOT EXISTS height REAL;

WITH ranked AS (
  SELECT p.id, p.position,
         (ROW_NUMBER() OVER (ORDER BY p.number, p.id) - 1)::int AS i
  FROM players p
  JOIN teams t ON t.id = p.team_id
  WHERE t.name = 'Association sportive olympique de Chlef'
)
UPDATE players pl SET
  skin_color  = r.i % 7,
  hair_style  = r.i % 6,
  hair_color  = (r.i * 3) % 8,
  beard_style = (r.i / 2) % 4,
  body_type   = (r.i / 3) % 4,
  eye_color   = r.i % 4,
  height      = CASE WHEN r.position = 'GK'
                     THEN 1.86 + (r.i % 3) * 0.02
                     ELSE 1.70 + ((r.i * 7) % 12) * 0.02 END
FROM ranked r
WHERE pl.id = r.id;
