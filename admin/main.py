import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import create_engine, Column, Integer, String, Boolean, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker as async_sessionmaker

import bcrypt

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL", "")
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8080"))
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "dzfoot-admin-secret-change-me")
COOKIE_NAME = "dzfoot_admin_session"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

# ---------------------------------------------------------------------------
# SQLite – Auth Admin
# ---------------------------------------------------------------------------
SQLITE_PATH = os.path.join(BASE_DIR, "data", "admin.db")
sqlite_engine = create_engine(
    f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False}
)
AdminBase = declarative_base()
AdminSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sqlite_engine)


class AdminUser(AdminBase):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String(20), default="admin")          # admin | moderator
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class AdminSession(AdminBase):
    __tablename__ = "admin_sessions"
    id = Column(Integer, primary_key=True)
    token = Column(String(128), unique=True, index=True)
    user_id = Column(Integer)
    expires_at = Column(String)


AdminBase.metadata.create_all(bind=sqlite_engine)

# ---------------------------------------------------------------------------
# PostgreSQL – Game data
# ---------------------------------------------------------------------------
pg_engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(title="DZFoot Admin Panel")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.middleware("http")
async def auth_redirect_middleware(request: Request, call_next):
    """Redirect web browsers to /login on 403, leave API responses untouched."""
    response = await call_next(request)
    if response.status_code == 403 and request.url.path != "/login":
        accept = request.headers.get("accept", "")
        if "text/html" in accept or "*/*" in accept:
            return RedirectResponse(url="/login", status_code=302)
    return response


# ---------------------------------------------------------------------------
# Init default admin
# ---------------------------------------------------------------------------
def init_admin() -> None:
    db = AdminSessionLocal()
    count = db.query(AdminUser).count()
    if count == 0:
        import secrets
        temp_pass = secrets.token_urlsafe(12)
        user = AdminUser(
            username="admin",
            email="admin@dzfoot.local",
            hashed_password=hash_password(temp_pass),
            role="admin",
        )
        db.add(user)
        db.commit()
        print(f"[DZFoot Admin] Default account created -> admin / {temp_pass}")
        print("[DZFoot Admin] IMPORTANT: Change this password after first login!")
    db.close()


init_admin()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def create_session_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db = AdminSessionLocal()
    expires = (datetime.utcnow() + timedelta(hours=8)).isoformat()
    sess = AdminSession(token=token, user_id=user_id, expires_at=expires)
    db.add(sess)
    db.commit()
    db.close()
    return token


def get_current_user_from_cookie(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    db = AdminSessionLocal()
    try:
        sess = db.query(AdminSession).filter(AdminSession.token == token).first()
        if not sess:
            return None
        expires = datetime.fromisoformat(sess.expires_at)
        if datetime.utcnow() > expires:
            db.delete(sess)
            db.commit()
            return None
        user = db.query(AdminUser).filter(AdminUser.id == sess.user_id).first()
        if not user or not user.is_active:
            return None
        return {"id": user.id, "username": user.username, "role": user.role}
    finally:
        db.close()


async def require_admin(request: Request) -> Dict[str, Any]:
    user = get_current_user_from_cookie(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication required",
        )
    return user


# ---------------------------------------------------------------------------
# Routes – Auth
# ---------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user_from_cookie(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_post(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    db = AdminSessionLocal()
    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    db.close()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Nom d'utilisateur ou mot de passe invalide"},
            status_code=401,
        )

    token = create_session_token(user.id)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=28800,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db = AdminSessionLocal()
        sess = db.query(AdminSession).filter(AdminSession.token == token).first()
        if sess:
            db.delete(sess)
            db.commit()
        db.close()
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: Dict[str, Any] = Depends(require_admin)):
    stats: Dict[str, int] = {}
    recent_matches: List[Dict[str, Any]] = []

    async with AsyncSessionLocal() as pg:
        r = await pg.execute(text("SELECT COUNT(*) FROM users"))
        stats["users"] = r.scalar() or 0
        r = await pg.execute(text("SELECT COUNT(*) FROM teams"))
        stats["teams"] = r.scalar() or 0
        r = await pg.execute(text("SELECT COUNT(*) FROM players"))
        stats["players"] = r.scalar() or 0
        r = await pg.execute(text("SELECT COUNT(*) FROM matches"))
        stats["matches"] = r.scalar() or 0

        r = await pg.execute(
            text(
                """
                SELECT m.id, u1.pseudo as p1, u2.pseudo as p2,
                       m.score_a, m.score_b, m.played_at
                FROM matches m
                JOIN users u1 ON m.player_a_id = u1.id
                JOIN users u2 ON m.player_b_id = u2.id
                ORDER BY m.played_at DESC LIMIT 6
                """
            )
        )
        recent_matches = [dict(row._mapping) for row in r]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "recent_matches": recent_matches,
        },
    )


# ---------------------------------------------------------------------------
# TEAMS CRUD
# ---------------------------------------------------------------------------
@app.get("/teams", response_class=HTMLResponse)
async def teams_list(
    request: Request,
    user: Dict[str, Any] = Depends(require_admin),
    q: Optional[str] = Query(None),
):
    async with AsyncSessionLocal() as pg:
        if q:
            r = await pg.execute(
                text(
                    "SELECT * FROM teams WHERE name ILIKE :q OR short_name ILIKE :q ORDER BY name"
                ),
                {"q": f"%{q}%"},
            )
        else:
            r = await pg.execute(text("SELECT * FROM teams ORDER BY name"))
        teams = [dict(row._mapping) for row in r]
    return templates.TemplateResponse(
        "teams.html", {"request": request, "user": user, "teams": teams, "q": q}
    )


@app.get("/teams/new", response_class=HTMLResponse)
async def team_new_form(request: Request, user: Dict[str, Any] = Depends(require_admin)):
    return templates.TemplateResponse(
        "team_form.html", {"request": request, "user": user, "team": None}
    )


@app.post("/teams/new")
async def team_create(
    request: Request,
    user: Dict[str, Any] = Depends(require_admin),
    name: str = Form(...),
    country: str = Form(""),
    logo_url: str = Form(""),
    kit_texture_url: str = Form(""),
    short_name: str = Form(""),
    color_primary: str = Form("#ffffff"),
    color_secondary: str = Form("#000000"),
    color_rgb1: str = Form(""),
    color_rgb2: str = Form(""),
    league: str = Form("Ligue 1 Mobilis"),
    formation: str = Form("4-3-3"),
):
    async with AsyncSessionLocal() as pg:
        await pg.execute(
            text(
                """
                INSERT INTO teams (name, country, logo_url, kit_texture_url, short_name,
                    color_primary, color_secondary, color_rgb1, color_rgb2, league, formation)
                VALUES (:name, :country, :logo_url, :kit_texture_url, :short_name,
                    :color_primary, :color_secondary, :color_rgb1, :color_rgb2, :league, :formation)
                """
            ),
            {
                "name": name,
                "country": country,
                "logo_url": logo_url,
                "kit_texture_url": kit_texture_url,
                "short_name": short_name,
                "color_primary": color_primary,
                "color_secondary": color_secondary,
                "color_rgb1": color_rgb1,
                "color_rgb2": color_rgb2,
                "league": league,
                "formation": formation,
            },
        )
        await pg.commit()
    return RedirectResponse(url="/teams", status_code=302)


@app.get("/teams/{team_id}/edit", response_class=HTMLResponse)
async def team_edit_form(
    request: Request, team_id: str, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        r = await pg.execute(text("SELECT * FROM teams WHERE id = :id"), {"id": team_id})
        row = r.mappings().first()
        team = dict(row) if row else None
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return templates.TemplateResponse(
        "team_form.html", {"request": request, "user": user, "team": team}
    )


@app.post("/teams/{team_id}/edit")
async def team_update(
    request: Request,
    team_id: str,
    user: Dict[str, Any] = Depends(require_admin),
    name: str = Form(...),
    country: str = Form(""),
    logo_url: str = Form(""),
    kit_texture_url: str = Form(""),
    short_name: str = Form(""),
    color_primary: str = Form("#ffffff"),
    color_secondary: str = Form("#000000"),
    color_rgb1: str = Form(""),
    color_rgb2: str = Form(""),
    league: str = Form("Ligue 1 Mobilis"),
    formation: str = Form("4-3-3"),
):
    async with AsyncSessionLocal() as pg:
        await pg.execute(
            text(
                """
                UPDATE teams SET name=:name, country=:country, logo_url=:logo_url,
                    kit_texture_url=:kit_texture_url, short_name=:short_name,
                    color_primary=:color_primary, color_secondary=:color_secondary,
                    color_rgb1=:color_rgb1, color_rgb2=:color_rgb2, league=:league, formation=:formation
                WHERE id=:id
                """
            ),
            {
                "id": team_id,
                "name": name,
                "country": country,
                "logo_url": logo_url,
                "kit_texture_url": kit_texture_url,
                "short_name": short_name,
                "color_primary": color_primary,
                "color_secondary": color_secondary,
                "color_rgb1": color_rgb1,
                "color_rgb2": color_rgb2,
                "league": league,
                "formation": formation,
            },
        )
        await pg.commit()
    return RedirectResponse(url="/teams", status_code=302)


@app.post("/teams/{team_id}/delete")
async def team_delete(
    request: Request, team_id: str, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        await pg.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
        await pg.commit()
    return RedirectResponse(url="/teams", status_code=302)


# ---------------------------------------------------------------------------
# PLAYERS CRUD
# ---------------------------------------------------------------------------
@app.get("/players", response_class=HTMLResponse)
async def players_list(
    request: Request,
    user: Dict[str, Any] = Depends(require_admin),
    q: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
):
    async with AsyncSessionLocal() as pg:
        sql = "SELECT p.*, t.name as team_name FROM players p LEFT JOIN teams t ON p.team_id = t.id WHERE 1=1"
        params: Dict[str, Any] = {}
        if q:
            sql += " AND p.name ILIKE :q"
            params["q"] = f"%{q}%"
        if team_id:
            sql += " AND p.team_id = :team_id"
            params["team_id"] = team_id
        sql += " ORDER BY p.name"
        r = await pg.execute(text(sql), params)
        players = [dict(row._mapping) for row in r]
        r2 = await pg.execute(text("SELECT id, name FROM teams ORDER BY name"))
        teams = [dict(row._mapping) for row in r2]
    return templates.TemplateResponse(
        "players.html",
        {
            "request": request,
            "user": user,
            "players": players,
            "teams": teams,
            "q": q,
            "team_id": team_id,
        },
    )


@app.get("/players/new", response_class=HTMLResponse)
async def player_new_form(
    request: Request, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        r = await pg.execute(text("SELECT id, name FROM teams ORDER BY name"))
        teams = [dict(row._mapping) for row in r]
    return templates.TemplateResponse(
        "player_form.html",
        {"request": request, "user": user, "player": None, "teams": teams},
    )


@app.post("/players/new")
async def player_create(
    request: Request,
    user: Dict[str, Any] = Depends(require_admin),
    name: str = Form(...),
    team_id: str = Form(""),
    position: str = Form(""),
    number: int = Form(0),
    speed: float = Form(0.75),
    shooting: float = Form(0.70),
    passing: float = Form(0.72),
    defense: float = Form(0.65),
    stamina: float = Form(0.80),
):
    tid = team_id if team_id else None
    async with AsyncSessionLocal() as pg:
        await pg.execute(
            text(
                """
                INSERT INTO players (name, team_id, position, number, speed, shooting, passing, defense, stamina)
                VALUES (:name, :team_id, :position, :number, :speed, :shooting, :passing, :defense, :stamina)
                """
            ),
            {
                "name": name,
                "team_id": tid,
                "position": position,
                "number": number,
                "speed": speed,
                "shooting": shooting,
                "passing": passing,
                "defense": defense,
                "stamina": stamina,
            },
        )
        await pg.commit()
    return RedirectResponse(url="/players", status_code=302)


@app.get("/players/{player_id}/edit", response_class=HTMLResponse)
async def player_edit_form(
    request: Request, player_id: str, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        r = await pg.execute(text("SELECT * FROM players WHERE id = :id"), {"id": player_id})
        row = r.mappings().first()
        player = dict(row) if row else None
        r2 = await pg.execute(text("SELECT id, name FROM teams ORDER BY name"))
        teams = [dict(row._mapping) for row in r2]
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return templates.TemplateResponse(
        "player_form.html",
        {"request": request, "user": user, "player": player, "teams": teams},
    )


@app.post("/players/{player_id}/edit")
async def player_update(
    request: Request,
    player_id: str,
    user: Dict[str, Any] = Depends(require_admin),
    name: str = Form(...),
    team_id: str = Form(""),
    position: str = Form(""),
    number: int = Form(0),
    speed: float = Form(0.75),
    shooting: float = Form(0.70),
    passing: float = Form(0.72),
    defense: float = Form(0.65),
    stamina: float = Form(0.80),
):
    tid = team_id if team_id else None
    async with AsyncSessionLocal() as pg:
        await pg.execute(
            text(
                """
                UPDATE players SET name=:name, team_id=:team_id, position=:position, number=:number,
                    speed=:speed, shooting=:shooting, passing=:passing, defense=:defense, stamina=:stamina
                WHERE id=:id
                """
            ),
            {
                "id": player_id,
                "name": name,
                "team_id": tid,
                "position": position,
                "number": number,
                "speed": speed,
                "shooting": shooting,
                "passing": passing,
                "defense": defense,
                "stamina": stamina,
            },
        )
        await pg.commit()
    return RedirectResponse(url="/players", status_code=302)


@app.post("/players/{player_id}/delete")
async def player_delete(
    request: Request, player_id: str, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        await pg.execute(text("DELETE FROM players WHERE id = :id"), {"id": player_id})
        await pg.commit()
    return RedirectResponse(url="/players", status_code=302)


# ---------------------------------------------------------------------------
# MATCHES CRUD
# ---------------------------------------------------------------------------
@app.get("/matches", response_class=HTMLResponse)
async def matches_list(
    request: Request, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        r = await pg.execute(
            text(
                """
                SELECT m.*, u1.pseudo as player_a_name, u2.pseudo as player_b_name,
                       t1.name as team_a_name, t2.name as team_b_name
                FROM matches m
                LEFT JOIN users u1 ON m.player_a_id = u1.id
                LEFT JOIN users u2 ON m.player_b_id = u2.id
                LEFT JOIN teams t1 ON m.team_a_id = t1.id
                LEFT JOIN teams t2 ON m.team_b_id = t2.id
                ORDER BY m.played_at DESC
                """
            )
        )
        matches = [dict(row._mapping) for row in r]
    return templates.TemplateResponse(
        "matches.html", {"request": request, "user": user, "matches": matches}
    )


@app.post("/matches/{match_id}/delete")
async def match_delete(
    request: Request, match_id: str, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        await pg.execute(text("DELETE FROM match_stats WHERE match_id = :id"), {"id": match_id})
        await pg.execute(text("DELETE FROM matches WHERE id = :id"), {"id": match_id})
        await pg.commit()
    return RedirectResponse(url="/matches", status_code=302)


# ---------------------------------------------------------------------------
# USERS CRUD
# ---------------------------------------------------------------------------
@app.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    user: Dict[str, Any] = Depends(require_admin),
    q: Optional[str] = Query(None),
):
    async with AsyncSessionLocal() as pg:
        if q:
            r = await pg.execute(
                text(
                    "SELECT * FROM users WHERE pseudo ILIKE :q OR email ILIKE :q ORDER BY created_at DESC"
                ),
                {"q": f"%{q}%"},
            )
        else:
            r = await pg.execute(text("SELECT * FROM users ORDER BY created_at DESC"))
        users = [dict(row._mapping) for row in r]
    return templates.TemplateResponse(
        "users.html", {"request": request, "user": user, "users": users, "q": q}
    )


@app.post("/users/{user_id}/delete")
async def user_delete(
    request: Request, user_id: str, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        await pg.execute(
            text("DELETE FROM match_stats WHERE player_id = :id"), {"id": user_id}
        )
        await pg.execute(
            text("DELETE FROM friendships WHERE user_id = :id OR friend_id = :id"),
            {"id": user_id},
        )
        await pg.execute(
            text("DELETE FROM matches WHERE player_a_id = :id OR player_b_id = :id"),
            {"id": user_id},
        )
        await pg.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await pg.commit()
    return RedirectResponse(url="/users", status_code=302)


# ---------------------------------------------------------------------------
# STADIUMS CRUD
# ---------------------------------------------------------------------------
@app.get("/stadiums", response_class=HTMLResponse)
async def stadiums_list(
    request: Request, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        r = await pg.execute(text("SELECT * FROM stadiums ORDER BY name"))
        stadiums = [dict(row._mapping) for row in r]
    return templates.TemplateResponse(
        "stadiums.html", {"request": request, "user": user, "stadiums": stadiums}
    )


@app.get("/stadiums/new", response_class=HTMLResponse)
async def stadium_new_form(
    request: Request, user: Dict[str, Any] = Depends(require_admin)
):
    return templates.TemplateResponse(
        "stadium_form.html", {"request": request, "user": user, "stadium": None}
    )


@app.post("/stadiums/new")
async def stadium_create(
    request: Request,
    user: Dict[str, Any] = Depends(require_admin),
    name: str = Form(...),
    city: str = Form(""),
    capacity: int = Form(0),
    model_3d_url: str = Form(""),
    ar_marker_ref: str = Form(""),
    pitch_texture: str = Form(""),
):
    async with AsyncSessionLocal() as pg:
        await pg.execute(
            text(
                """
                INSERT INTO stadiums (name, city, capacity, model_3d_url, ar_marker_ref, pitch_texture)
                VALUES (:name, :city, :capacity, :model_3d_url, :ar_marker_ref, :pitch_texture)
                """
            ),
            {
                "name": name,
                "city": city,
                "capacity": capacity,
                "model_3d_url": model_3d_url,
                "ar_marker_ref": ar_marker_ref,
                "pitch_texture": pitch_texture,
            },
        )
        await pg.commit()
    return RedirectResponse(url="/stadiums", status_code=302)


@app.get("/stadiums/{stadium_id}/edit", response_class=HTMLResponse)
async def stadium_edit_form(
    request: Request, stadium_id: str, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        r = await pg.execute(text("SELECT * FROM stadiums WHERE id = :id"), {"id": stadium_id})
        row = r.mappings().first()
        stadium = dict(row) if row else None
    if not stadium:
        raise HTTPException(status_code=404, detail="Stadium not found")
    return templates.TemplateResponse(
        "stadium_form.html", {"request": request, "user": user, "stadium": stadium}
    )


@app.post("/stadiums/{stadium_id}/edit")
async def stadium_update(
    request: Request,
    stadium_id: str,
    user: Dict[str, Any] = Depends(require_admin),
    name: str = Form(...),
    city: str = Form(""),
    capacity: int = Form(0),
    model_3d_url: str = Form(""),
    ar_marker_ref: str = Form(""),
    pitch_texture: str = Form(""),
):
    async with AsyncSessionLocal() as pg:
        await pg.execute(
            text(
                """
                UPDATE stadiums SET name=:name, city=:city, capacity=:capacity,
                    model_3d_url=:model_3d_url, ar_marker_ref=:ar_marker_ref, pitch_texture=:pitch_texture
                WHERE id=:id
                """
            ),
            {
                "id": stadium_id,
                "name": name,
                "city": city,
                "capacity": capacity,
                "model_3d_url": model_3d_url,
                "ar_marker_ref": ar_marker_ref,
                "pitch_texture": pitch_texture,
            },
        )
        await pg.commit()
    return RedirectResponse(url="/stadiums", status_code=302)


@app.post("/stadiums/{stadium_id}/delete")
async def stadium_delete(
    request: Request, stadium_id: str, user: Dict[str, Any] = Depends(require_admin)
):
    async with AsyncSessionLocal() as pg:
        await pg.execute(text("DELETE FROM stadiums WHERE id = :id"), {"id": stadium_id})
        await pg.commit()
    return RedirectResponse(url="/stadiums", status_code=302)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=ADMIN_PORT)
