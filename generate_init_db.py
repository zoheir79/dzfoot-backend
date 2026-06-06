import json
import os
import hashlib

def generate_avatar_config(name: str) -> dict:
    """Deterministic avatar attributes from player name hash."""
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    def _b(idx, mod):
        return int(h[idx:idx+2], 16) % mod
    return {
        "config_id": h[:8],
        "skin_color": _b(0, 7),      # 0..6  (7 teintes)
        "hair_style": _b(2, 5),      # 0..4  (short, long, mohawk, curly, bald)
        "hair_color": _b(4, 8),      # 0..7  (black, brown, blonde, red, gray, white, dark_brown, auburn)
        "body_type":  _b(6, 4),      # 0..3  (thin, average, muscular, heavy)
        "beard_style": _b(8, 4),     # 0..3  (none, stubble, short, full)
        "eye_color":  _b(10, 4),     # 0..3  (brown, blue, green, hazel)
    }

def generate_seed():
    json_path = r"d:\DZFoot\ligue1DZ\clubs.json"
    output_path = r"d:\DZFoot\repos\dzfoot-backend\init_db.sql"
    
    if not os.path.exists(json_path):
        print(f"Error: {json_path} does not exist!")
        return
        
    with open(json_path, "r", encoding="utf-8") as f:
        clubs = json.load(f)
        
    # Standard 16 team colors mapping
    team_meta = {
        "ASO Chlef": {"short_name": "ASO", "color_primary": "#FF8C00", "color_secondary": "#000000", "color_rgb1": "255,140,0", "color_rgb2": "0,0,0", "kit_texture": "asochlef_dzfoot"},
        "CR Belouizdad": {"short_name": "CRB", "color_primary": "#DC0000", "color_secondary": "#FFFFFF", "color_rgb1": "220,0,0", "color_rgb2": "255,255,255", "kit_texture": "crbelouizdad_dzfoot"},
        "JS Kabylie": {"short_name": "JSK", "color_primary": "#FFD700", "color_secondary": "#008000", "color_rgb1": "255,215,0", "color_rgb2": "0,128,0", "kit_texture": "jskabylie_dzfoot"},
        "MC Alger": {"short_name": "MCA", "color_primary": "#DC0000", "color_secondary": "#008000", "color_rgb1": "220,0,0", "color_rgb2": "0,128,0", "kit_texture": "mcalger_dzfoot"},
        "USM Alger": {"short_name": "USM", "color_primary": "#000000", "color_secondary": "#DC0000", "color_rgb1": "0,0,0", "color_rgb2": "220,0,0", "kit_texture": "usmalger_dzfoot"},
        "ES Sétif": {"short_name": "ESS", "color_primary": "#000000", "color_secondary": "#FFFFFF", "color_rgb1": "0,0,0", "color_rgb2": "255,255,255", "kit_texture": "essetif_dzfoot"},
        "CS Constantine": {"short_name": "CSC", "color_primary": "#DC0000", "color_secondary": "#008000", "color_rgb1": "220,0,0", "color_rgb2": "0,128,0", "kit_texture": "csconstantine_dzfoot"},
        "Paradou AC": {"short_name": "PAC", "color_primary": "#FFD700", "color_secondary": "#0000C8", "color_rgb1": "255,215,0", "color_rgb2": "0,0,200", "kit_texture": "paradouac_dzfoot"},
        "MC Oran": {"short_name": "MCO", "color_primary": "#DC0000", "color_secondary": "#FFFFFF", "color_rgb1": "220,0,0", "color_rgb2": "255,255,255", "kit_texture": "mcoran_dzfoot"},
        "ES Ben Aknoun": {"short_name": "ESB", "color_primary": "#FFFFFF", "color_secondary": "#000000", "color_rgb1": "255,255,255", "color_rgb2": "0,0,0", "kit_texture": "esbenaknoun_dzfoot"},
        "ES Mostaganem": {"short_name": "ESM", "color_primary": "#000080", "color_secondary": "#FFFFFF", "color_rgb1": "0,0,128", "color_rgb2": "255,255,255", "kit_texture": "esmostaganem_dzfoot"},
        "JS Saoura": {"short_name": "JSS", "color_primary": "#008000", "color_secondary": "#FFD700", "color_rgb1": "0,128,0", "color_rgb2": "255,215,0", "kit_texture": "jssaoura_dzfoot"},
        "MB Rouissat": {"short_name": "MBR", "color_primary": "#0000FF", "color_secondary": "#FFFFFF", "color_rgb1": "0,0,255", "color_rgb2": "255,255,255", "kit_texture": "mbrouissat_dzfoot"},
        "MC El Bayadh": {"short_name": "MCE", "color_primary": "#008000", "color_secondary": "#FFFFFF", "color_rgb1": "0,128,0", "color_rgb2": "255,255,255", "kit_texture": "mcelbayadh_dzfoot"},
        "O Akbou": {"short_name": "OAK", "color_primary": "#FF0000", "color_secondary": "#000000", "color_rgb1": "255,0,0", "color_rgb2": "0,0,0", "kit_texture": "oakbou_dzfoot"},
        "USM Khenchela": {"short_name": "USK", "color_primary": "#000000", "color_secondary": "#FFD700", "color_rgb1": "0,0,0", "color_rgb2": "255,215,0", "kit_texture": "usmkhenchela_dzfoot"}
    }

    sql = []
    sql.append("-- Seed data for DZFoot — Algerian Ligue 1 Mobilis (Deterministic from clubs.json)\n")
    
    # 1. Insert Stadiums
    sql.append("-- 1. Insert Stadiums")
    sql.append("INSERT INTO stadiums (name, city, capacity, ar_marker_ref, pitch_texture) VALUES")
    stadiums = [
        ("Stade 5 Juillet 1962", "Algiers", 80000, "marker_5juillet", "grass_sunny"),
        ("Stade 20 Aout 1955", "Algiers", 15000, "marker_20aout", "grass_sunny"),
        ("Stade du 1er Novembre", "Tizi Ouzou", 25000, "marker_tiziouzou", "grass_sunny"),
        ("Stade Miloud Hadefi", "Oran", 40000, "marker_oran", "grass_overcast"),
        ("Stade Mustapha Tchaker", "Blida", 35000, "marker_blida", "grass_sunny"),
        ("Stade 8 Mai 1945", "Setif", 25000, "marker_setif", "grass_night"),
        ("Stade Mohamed Hamlaoui", "Constantine", 30000, "marker_constantine", "grass_sunny"),
        ("Stade 24 Fevrier 1956", "Sidi Bel Abbes", 20000, "marker_sba", "grass_overcast")
    ]
    stadium_rows = []
    for s in stadiums:
        stadium_rows.append(f"('{s[0]}', '{s[1]}', {s[2]}, '{s[3]}', '{s[4]}')")
    sql.append(",\n".join(stadium_rows) + ";\n")
    
    # 2. Insert Teams
    sql.append("-- 2. Insert Teams with real names, logos, colors")
    sql.append("INSERT INTO teams (name, country, logo_url, kit_texture_url, short_name, color_primary, color_secondary, color_rgb1, color_rgb2, league, formation) VALUES")
    
    team_rows = []
    for club in clubs:
        name = club["short_name"]
        full_name = club["full_name"]
        full_name_sql = full_name.replace("'", "''")
        logo_url = club["logo_url"]
        
        # Fallback to defaults if color not found
        meta = team_meta.get(name, team_meta.get(name.replace("Sétif", "Setif"), {
            "short_name": name[:3].upper(),
            "color_primary": "#FFFFFF",
            "color_secondary": "#000000",
            "color_rgb1": "255,255,255",
            "color_rgb2": "0,0,0",
            "kit_texture": "default"
        }))
        
        logo_local = f"images_teams/logos/{club['id']}.png"
        kit_tex_url = f"images_teams/ligue1dz/{meta['kit_texture']}"
        
        team_rows.append(f"('{full_name_sql}', 'Algeria', '{logo_url}', '{kit_tex_url}', '{meta['short_name']}', '{meta['color_primary']}', '{meta['color_secondary']}', '{meta['color_rgb1']}', '{meta['color_rgb2']}', 'Ligue 1 Mobilis', '4-3-3')")
    
    sql.append(",\n".join(team_rows) + ";\n")
    
    # 3. Insert Players
    sql.append("-- 3. Insert Players for each Team")
    for club in clubs:
        full_name = club["full_name"]
        full_name_sql = full_name.replace("'", "''")
        players = club["players"]
        
        sql.append(f"-- Players for {full_name}")
        sql.append(f"WITH t AS (SELECT id FROM teams WHERE name='{full_name_sql}')")
        sql.append("INSERT INTO players (")
        sql.append("  team_id, name, position, number,")
        sql.append("  speed, shooting, passing, defense, stamina,")
        sql.append("  physical_balance, physical_reaction, physical_acceleration, physical_velocity, physical_stamina,")
        sql.append("  physical_agility, physical_shotpower,")
        sql.append("  technical_standingtackle, technical_slidingtackle, technical_ballcontrol, technical_dribble,")
        sql.append("  technical_shortpass, technical_highpass, technical_header, technical_shot, technical_volley,")
        sql.append("  mental_calmness, mental_workrate, mental_resilience,")
        sql.append("  mental_defensivepositioning, mental_offensivepositioning, mental_vision,")
        sql.append("  photo_url, photo_local, avatar_config_id,")
        sql.append("  skin_color, hair_style, hair_color, body_type, beard_style, eye_color")
        sql.append(") SELECT t.id, name, position, number,")
        sql.append("  speed, shooting, passing, defense, stamina,")
        sql.append("  pb, pr, pa, pv, ps, pag, psp,")
        sql.append("  tst, tsl, tbc, td, tsp, thp, th, tsh, tv,")
        sql.append("  mc, mw, mr, mdp, mop, mv,")
        sql.append("  photo_url, photo_local, avatar_config_id,")
        sql.append("  skin_color, hair_style, hair_color, body_type, beard_style, eye_color")
        sql.append("FROM t, (VALUES")
        
        player_values = []
        for i, p in enumerate(players):
            pname = p["name"].replace("'", "''")
            pnum = int(p["number"]) if p["number"] and p["number"].isdigit() else (i + 1)
            raw_pos = p["position"].lower()
            
            # Avatar config deterministic from name
            av = generate_avatar_config(p["name"])
            photo_url = p.get("photo_url", "")
            photo_local = p.get("photo_local", "")
            # Escape single quotes for SQL
            photo_url_sql = photo_url.replace("'", "''") if photo_url else ""
            photo_local_sql = photo_local.replace("'", "''") if photo_local else ""
            
            # Formations positions: mapping Real LFP position names to GF roles (GK, CB, LB, RB, CM, LM, RM, CF, etc.)
            # Deterministic mapping depending on index inside the club
            if "goalkeeper" in raw_pos:
                role = "GK"
                # Goalkeeper skillset
                speed, shooting, passing, defense, stamina = 0.70, 0.40, 0.60, 0.85, 0.82
                pb, pr, pa, pv, ps, pag, psp = 0.75, 0.82, 0.72, 0.70, 0.82, 0.70, 0.60
                tst, tsl, tbc, td, tsp, thp, th, tsh, tv = 0.85, 0.60, 0.55, 0.45, 0.60, 0.55, 0.50, 0.40, 0.30
                mc, mw, mr, mdp, mop, mv = 0.85, 0.80, 0.88, 0.90, 0.20, 0.70
            elif "defender" in raw_pos:
                role = "CB"
                if i % 3 == 0: role = "LB"
                elif i % 3 == 1: role = "RB"
                # Defender skillset
                speed, shooting, passing, defense, stamina = 0.74, 0.50, 0.65, 0.82, 0.80
                pb, pr, pa, pv, ps, pag, psp = 0.80, 0.76, 0.70, 0.74, 0.80, 0.68, 0.70
                tst, tsl, tbc, td, tsp, thp, th, tsh, tv = 0.82, 0.78, 0.65, 0.52, 0.68, 0.62, 0.72, 0.50, 0.40
                mc, mw, mr, mdp, mop, mv = 0.76, 0.80, 0.82, 0.85, 0.50, 0.70
            elif "midfielder" in raw_pos:
                role = "CM"
                if i % 3 == 0: role = "LM"
                elif i % 3 == 1: role = "RM"
                # Midfielder skillset
                speed, shooting, passing, defense, stamina = 0.78, 0.68, 0.82, 0.68, 0.84
                pb, pr, pa, pv, ps, pag, psp = 0.75, 0.80, 0.76, 0.78, 0.84, 0.76, 0.70
                tst, tsl, tbc, td, tsp, thp, th, tsh, tv = 0.70, 0.65, 0.82, 0.72, 0.84, 0.78, 0.64, 0.68, 0.52
                mc, mw, mr, mdp, mop, mv = 0.82, 0.84, 0.80, 0.72, 0.70, 0.84
            else: # attacker
                role = "CF"
                if i % 3 == 0: role = "LW"
                elif i % 3 == 1: role = "RW"
                # Attacker skillset
                speed, shooting, passing, defense, stamina = 0.86, 0.84, 0.74, 0.44, 0.75
                pb, pr, pa, pv, ps, pag, psp = 0.72, 0.84, 0.86, 0.86, 0.75, 0.88, 0.80
                tst, tsl, tbc, td, tsp, thp, th, tsh, tv = 0.44, 0.40, 0.82, 0.84, 0.74, 0.68, 0.75, 0.82, 0.68
                mc, mw, mr, mdp, mop, mv = 0.78, 0.78, 0.76, 0.48, 0.84, 0.78
                
            player_values.append(f"  ('{pname}', '{role}', {pnum}, {speed}, {shooting}, {passing}, {defense}, {stamina}, {pb}, {pr}, {pa}, {pv}, {ps}, {pag}, {psp}, {tst}, {tsl}, {tbc}, {td}, {tsp}, {thp}, {th}, {tsh}, {tv}, {mc}, {mw}, {mr}, {mdp}, {mop}, {mv}, '{photo_url_sql}', '{photo_local_sql}', '{av['config_id']}', {av['skin_color']}, {av['hair_style']}, {av['hair_color']}, {av['body_type']}, {av['beard_style']}, {av['eye_color']})")
            
        sql.append(",\n".join(player_values))
        sql.append(") AS tmp(name, position, number, speed, shooting, passing, defense, stamina, pb, pr, pa, pv, ps, pag, psp, tst, tsl, tbc, td, tsp, thp, th, tsh, tv, mc, mw, mr, mdp, mop, mv, photo_url, photo_local, avatar_config_id, skin_color, hair_style, hair_color, body_type, beard_style, eye_color);\n")

    # Write out to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sql))
        
    print(f"Successfully generated seed file: {output_path} with {len(clubs)} teams and players!")

if __name__ == "__main__":
    generate_seed()
