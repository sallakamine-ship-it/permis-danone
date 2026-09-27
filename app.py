"""
Permis de travail de chantier — Danone
Backend FastAPI + SQLite.

Sécurité :
- Mots de passe hachés avec bcrypt (jamais stockés ni transmis en clair après création).
- Sessions signées côté serveur (cookie httpOnly, signé avec itsdangerous) —
  le contenu de la session ne peut pas être falsifié par le navigateur.
- Les routes de sous-traitant (lookup par numéro de permis + entreprise) sont
  PUBLIQUES et ne nécessitent aucun compte, par design (exigence #3).
- Les routes admin/donneur exigent une session valide.
"""
import os
import io
import json
import re
import time
import uuid
import secrets
from collections import defaultdict, deque
from datetime import datetime, date
from typing import Optional

import bcrypt
import qrcode
from fastapi import FastAPI, Request, Response, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from database import init_db, db, row_to_dict

BASE_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Clé de signature des sessions. En production : variable d'environnement,
# jamais codée en dur. Générée une fois ici pour que la démo fonctionne
# sans configuration.
SECRET_KEY_PATH = os.path.join(BASE_DIR, ".secret_key")
if os.path.exists(SECRET_KEY_PATH):
    SECRET_KEY = open(SECRET_KEY_PATH).read().strip()
else:
    SECRET_KEY = secrets.token_hex(32)
    with open(SECRET_KEY_PATH, "w") as f:
        f.write(SECRET_KEY)

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="session")
SESSION_COOKIE = "danone_session"
SESSION_MAX_AGE = 60 * 60 * 12  # 12h

app = FastAPI(title="Permis de travail de chantier — Danone")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

init_db()


# ---------------------------------------------------------------------------
# Comptes par défaut au premier démarrage (mots de passe hachés dès la création)
# ---------------------------------------------------------------------------
def seed_default_admin():
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        if count == 0:
            defaults = [
                ("admin", "Danone2026!", "Administrateur SST", "admin"),
                ("coordinateur", "Sst2026!", "Coordinateur SST", "donneur"),
            ]
            for username, password, full_name, role in defaults:
                h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                conn.execute(
                    "INSERT INTO users (username, password_hash, full_name, role) VALUES (?,?,?,?)",
                    (username, h, full_name, role),
                )


seed_default_admin()


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def create_session_cookie(user_id: int, username: str, role: str, full_name: str) -> str:
    return serializer.dumps({"uid": user_id, "username": username, "role": role, "full_name": full_name})


def read_session(request: Request) -> Optional[dict]:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        return serializer.loads(raw, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def is_https_request(request: Request) -> bool:
    """Détecte si la requête arrive en HTTPS, y compris derrière un proxy
    inverse (Render, etc.) qui termine le TLS et transmet en HTTP interne
    avec l'en-tête X-Forwarded-Proto."""
    if request.url.scheme == "https":
        return True
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    return forwarded_proto.split(",")[0].strip().lower() == "https"


def normalize_company_name(s: Optional[str]) -> str:
    """Normalise un nom d'entreprise pour une comparaison exacte insensible
    à la casse et aux espaces (début/fin + espaces multiples internes)."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ---------------------------------------------------------------------------
# Limitation du taux de requêtes (anti-bruteforce) — compteur en mémoire par
# IP et par point d'accès. Suffisant pour un déploiement mono-processus
# (l'app utilise SQLite, donc un seul worker de toute façon) ; à remplacer
# par un stockage partagé (Redis, etc.) si l'app est un jour répartie sur
# plusieurs instances.
# ---------------------------------------------------------------------------
RATE_LIMIT_WINDOW_SECONDS = 15 * 60  # 15 minutes
RATE_LIMIT_MAX_ATTEMPTS = 5
_rate_limit_buckets: dict = defaultdict(deque)


def get_client_ip(request: Request) -> str:
    """Adresse IP du visiteur, en tenant compte d'un proxy inverse en amont
    (Render, etc.) qui transmet l'IP réelle via X-Forwarded-For — sinon
    request.client.host renverrait l'IP interne du proxy pour tout le monde,
    et la limitation de débit s'appliquerait à tort à l'ensemble des
    visiteurs comme une seule et même IP."""
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, bucket_name: str) -> None:
    client_ip = get_client_ip(request)
    key = (bucket_name, client_ip)
    now = time.monotonic()
    attempts = _rate_limit_buckets[key]
    while attempts and now - attempts[0] > RATE_LIMIT_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        retry_after = max(1, int(RATE_LIMIT_WINDOW_SECONDS - (now - attempts[0])))
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives. Réessayez dans quelques minutes.",
            headers={"Retry-After": str(retry_after)},
        )
    attempts.append(now)


def require_session(request: Request) -> dict:
    session = read_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return session


def require_admin(request: Request) -> dict:
    session = require_session(request)
    if session["role"] != "admin":
        raise HTTPException(status_code=403, detail="Accès admin requis")
    return session


# ---------------------------------------------------------------------------
# Numérotation des permis
# ---------------------------------------------------------------------------
def next_permit_num(conn) -> str:
    row = conn.execute("SELECT num FROM permits ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return "00525"
    try:
        n = int(row["num"])
    except ValueError:
        n = 524
    return str(n + 1).zfill(5)


def add_status_history(conn, permit_id: int, statut: str, par: str, note: str = None):
    conn.execute(
        "INSERT INTO status_history (permit_id, statut, par, note) VALUES (?,?,?,?)",
        (permit_id, statut, par, note),
    )


def auto_close_if_expired(conn, permit_row) -> dict:
    """Ferme automatiquement un permis Actif dont la date de fin est dépassée.
    Évalué à la lecture (pas de tâche planifiée réelle sans serveur cron dédié —
    limite documentée : la fermeture se déclenche au prochain accès au permis)."""
    p = row_to_dict(permit_row)
    if p["statut"] == "Actif" and p["date_fin"]:
        try:
            fin = datetime.strptime(p["date_fin"], "%Y-%m-%d").date()
        except ValueError:
            return p
        if fin < date.today():
            ferme_le = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE permits SET statut='Fermé', ferme_le=?, updated_at=datetime('now') WHERE id=?",
                (ferme_le, p["id"]),
            )
            add_status_history(conn, p["id"], "Fermé", "Système", "Fermeture automatique — date de fin dépassée")
            p["statut"] = "Fermé"
            p["ferme_le"] = ferme_le
    return p


# ===========================================================================
# AUTHENTIFICATION
# ===========================================================================
@app.post("/api/auth/login")
async def login(request: Request, response: Response):
    enforce_rate_limit(request, "auth_login")
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Nom d'utilisateur ou mot de passe incorrect")
    cookie_val = create_session_cookie(user["id"], user["username"], user["role"], user["full_name"])
    resp = JSONResponse({"ok": True, "username": user["username"], "role": user["role"], "full_name": user["full_name"]})
    resp.set_cookie(
        SESSION_COOKIE, cookie_val, max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
        secure=is_https_request(request),
    )
    return resp


@app.post("/api/auth/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/api/auth/me")
async def me(request: Request):
    session = read_session(request)
    if not session:
        return JSONResponse({"authenticated": False})
    return JSONResponse({"authenticated": True, **session})


# ===========================================================================
# UTILISATEURS (admin uniquement)
# ===========================================================================
@app.get("/api/users")
async def list_users(session=Depends(require_admin)):
    with db() as conn:
        rows = conn.execute("SELECT id, username, full_name, role, created_at FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/users")
async def create_user(request: Request, session=Depends(require_admin)):
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    full_name = (body.get("full_name") or "").strip()
    role = body.get("role")
    if not username or not password or not full_name or role not in ("admin", "donneur"):
        raise HTTPException(status_code=400, detail="Champs manquants ou rôle invalide")
    h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?,?,?,?)",
                (username, h, full_name, role),
            )
    except Exception:
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà")
    return {"ok": True}


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, session=Depends(require_admin)):
    if user_id == session["uid"]:
        raise HTTPException(status_code=400, detail="Impossible de supprimer votre propre compte")
    with db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"ok": True}


# ===========================================================================
# SECTEURS + QR CODES (admin/donneur)
# ===========================================================================
def slugify(name: str) -> str:
    import re, unicodedata
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or uuid.uuid4().hex[:8]


@app.get("/api/sectors")
async def list_sectors(session=Depends(require_session)):
    with db() as conn:
        rows = conn.execute("SELECT * FROM sectors ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/sectors")
async def create_sector(request: Request, session=Depends(require_session)):
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de secteur requis")
    slug = slugify(name)
    try:
        with db() as conn:
            conn.execute("INSERT INTO sectors (name, slug) VALUES (?,?)", (name, slug))
    except Exception:
        raise HTTPException(status_code=409, detail="Ce secteur existe déjà")
    return {"ok": True, "slug": slug}


@app.delete("/api/sectors/{sector_id}")
async def delete_sector(sector_id: int, session=Depends(require_admin)):
    with db() as conn:
        conn.execute("UPDATE permits SET sector_id = NULL WHERE sector_id = ?", (sector_id,))
        conn.execute("DELETE FROM sectors WHERE id = ?", (sector_id,))
    return {"ok": True}


@app.get("/api/sectors/{slug}/qrcode.png")
async def sector_qrcode(slug: str, request: Request):
    with db() as conn:
        sector = conn.execute("SELECT * FROM sectors WHERE slug = ?", (slug,)).fetchone()
    if not sector:
        raise HTTPException(status_code=404, detail="Secteur introuvable")
    base_url = str(request.base_url).rstrip("/")
    target_url = f"{base_url}/secteur/{slug}"
    img = qrcode.make(target_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


# ===========================================================================
# PERMIS — création / liste / détail / modification (admin, donneur)
# ===========================================================================
REQUIRED_BASE = ["donneur", "executant", "description", "lieux"]


def validate_permit_payload(body: dict):
    missing = [f for f in REQUIRED_BASE if not (body.get(f) or "").strip()]
    if body.get("height_work") or body.get("roof_work"):
        if not (body.get("height_vigie") or body.get("roof_vigie")):
            missing.append("vigie (obligatoire si travail en hauteur ou au toit)")
        if body.get("height_work") and not body.get("height_sauvetage"):
            missing.append("plan de sauvetage (obligatoire si travail en hauteur)")
    if body.get("hot_work") and not body.get("hot_surv"):
        missing.append("surveillance incendie (obligatoire si travail à chaud)")
    if missing:
        raise HTTPException(status_code=400, detail="Champs obligatoires manquants : " + ", ".join(missing))


@app.post("/api/permits")
async def create_permit(request: Request, session=Depends(require_session)):
    body = await request.json()
    validate_permit_payload(body)
    with db() as conn:
        num = next_permit_num(conn)
        cur = conn.execute(
            """INSERT INTO permits (
                num, sector_id, donneur, donneur_tel, entreprise, executant, executant_tel,
                description, lieux, zone, date_debut, date_fin,
                risques_a, risques_b, risques_c, zone_conforme, zone_comm,
                height_work, risques_hauteur, height_acces, height_m, height_sauvetage, height_vigie,
                bonbonne_work, risques_bonbonne, bonbonne_type, bonbonne_nombre, bonbonne_levage,
                roof_work, risques_toit, roof_type, roof_resistance, roof_perimetre, roof_vigie,
                hot_work, risques_hot, hot_nature, hot_debut, hot_fin, hot_surv, hot_ext,
                statut, cree_par
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                num, body.get("sector_id"), body.get("donneur"), body.get("donneur_tel"),
                body.get("entreprise"), body.get("executant"), body.get("executant_tel"),
                body.get("description"), body.get("lieux"), body.get("zone"), body.get("date_debut"), body.get("date_fin"),
                json.dumps(body.get("risques_a", [])), json.dumps(body.get("risques_b", [])),
                json.dumps(body.get("risques_c", [])), body.get("zone_conforme"), body.get("zone_comm"),
                int(bool(body.get("height_work"))), json.dumps(body.get("risques_hauteur", [])),
                body.get("height_acces"), body.get("height_m"), body.get("height_sauvetage"), body.get("height_vigie"),
                int(bool(body.get("bonbonne_work"))), json.dumps(body.get("risques_bonbonne", [])),
                body.get("bonbonne_type"), body.get("bonbonne_nombre"), body.get("bonbonne_levage"),
                int(bool(body.get("roof_work"))), json.dumps(body.get("risques_toit", [])),
                body.get("roof_type"), body.get("roof_resistance"), body.get("roof_perimetre"), body.get("roof_vigie"),
                int(bool(body.get("hot_work"))), json.dumps(body.get("risques_hot", [])),
                body.get("hot_nature"), body.get("hot_debut"), body.get("hot_fin"),
                body.get("hot_surv"), body.get("hot_ext"),
                body.get("statut", "Actif"), session["full_name"],
            ),
        )
        permit_id = cur.lastrowid
        add_status_history(conn, permit_id, body.get("statut", "Actif"), session["full_name"], "Création du permis")
        row = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
    return row_to_dict(row)


@app.get("/api/permits")
async def list_permits(
    request: Request,
    session=Depends(require_session),
    page: int = 1,
    page_size: int = 25,
    search: str = "",
    statut: str = "",
    sector_id: Optional[int] = None,
):
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    offset = (page - 1) * page_size

    where = []
    params = []
    if search:
        where.append("(num LIKE ? OR entreprise LIKE ? OR executant LIKE ? OR description LIKE ? OR lieux LIKE ? OR donneur LIKE ?)")
        like = f"%{search}%"
        params += [like] * 6
    if statut:
        where.append("statut = ?")
        params.append(statut)
    if sector_id:
        where.append("sector_id = ?")
        params.append(sector_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) c FROM permits {where_sql}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM permits {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        permits = [auto_close_if_expired(conn, r) for r in rows]

        stats_row = conn.execute(
            "SELECT COUNT(*) total, SUM(CASE WHEN statut='Actif' THEN 1 ELSE 0 END) actifs, "
            "SUM(height_work) hauteur, SUM(roof_work) toit, SUM(hot_work) chaud FROM permits"
        ).fetchone()

    return {
        "permits": permits,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "stats": dict(stats_row),
    }


@app.get("/api/permits/{permit_id}")
async def get_permit(permit_id: int, session=Depends(require_session)):
    with db() as conn:
        row = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Permis introuvable")
        p = auto_close_if_expired(conn, row)
        history = conn.execute(
            "SELECT * FROM status_history WHERE permit_id = ? ORDER BY id", (permit_id,)
        ).fetchall()
        photos = conn.execute(
            "SELECT * FROM photos WHERE permit_id = ? ORDER BY id", (permit_id,)
        ).fetchall()
    p["history"] = [dict(h) for h in history]
    p["photos"] = [dict(ph) for ph in photos]
    return p


@app.put("/api/permits/{permit_id}")
async def update_permit(permit_id: int, request: Request, session=Depends(require_session)):
    body = await request.json()
    validate_permit_payload(body)
    fields = [
        "sector_id", "donneur", "donneur_tel", "entreprise", "executant", "executant_tel",
        "description", "lieux", "zone", "date_debut", "date_fin", "zone_conforme", "zone_comm",
        "height_acces", "height_m", "height_sauvetage", "height_vigie",
        "bonbonne_type", "bonbonne_nombre", "bonbonne_levage",
        "roof_type", "roof_resistance", "roof_perimetre", "roof_vigie",
        "hot_nature", "hot_debut", "hot_fin", "hot_surv", "hot_ext",
    ]
    json_fields = ["risques_a", "risques_b", "risques_c", "risques_hauteur", "risques_bonbonne", "risques_toit", "risques_hot"]
    bool_fields = ["height_work", "bonbonne_work", "roof_work", "hot_work"]

    set_clauses = []
    params = []
    for f in fields:
        if f in body:
            set_clauses.append(f"{f} = ?")
            params.append(body[f])
    for f in json_fields:
        if f in body:
            set_clauses.append(f"{f} = ?")
            params.append(json.dumps(body[f]))
    for f in bool_fields:
        if f in body:
            set_clauses.append(f"{f} = ?")
            params.append(int(bool(body[f])))
    set_clauses.append("updated_at = datetime('now')")

    with db() as conn:
        existing = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Permis introuvable")
        params.append(permit_id)
        conn.execute(f"UPDATE permits SET {', '.join(set_clauses)} WHERE id = ?", params)

        if "statut" in body and body["statut"] != existing["statut"]:
            conn.execute("UPDATE permits SET statut = ? WHERE id = ?", (body["statut"], permit_id))
            add_status_history(conn, permit_id, body["statut"], session["full_name"], body.get("status_note"))

        row = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
    return row_to_dict(row)


@app.delete("/api/permits/{permit_id}")
async def delete_permit(permit_id: int, session=Depends(require_admin)):
    with db() as conn:
        conn.execute("DELETE FROM permits WHERE id = ?", (permit_id,))
    return {"ok": True}


@app.post("/api/permits/{permit_id}/close")
async def close_permit(permit_id: int, request: Request, session=Depends(require_session)):
    """Fermeture officielle avec double signature électronique."""
    body = await request.json()
    sig_donneur = body.get("signature_donneur")
    sig_executant = body.get("signature_executant")
    if not sig_donneur or not sig_executant:
        raise HTTPException(status_code=400, detail="Les deux signatures (donneur d'ordre et exécutant) sont requises")
    with db() as conn:
        existing = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Permis introuvable")
        conn.execute(
            "UPDATE permits SET statut='Fermé', signature_donneur=?, signature_executant=?, "
            "ferme_le=datetime('now'), updated_at=datetime('now') WHERE id=?",
            (sig_donneur, sig_executant, permit_id),
        )
        add_status_history(conn, permit_id, "Fermé", session["full_name"], "Fermeture officielle avec signatures")
        row = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
    return row_to_dict(row)


@app.post("/api/permits/{permit_id}/photos")
async def upload_photo(permit_id: int, file: UploadFile = File(...), session=Depends(require_session)):
    with db() as conn:
        existing = conn.execute("SELECT id FROM permits WHERE id = ?", (permit_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Permis introuvable")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
        raise HTTPException(status_code=400, detail="Format d'image non supporté")
    filename = f"{permit_id}_{uuid.uuid4().hex[:10]}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Photo trop volumineuse (max 15 Mo)")
    with open(path, "wb") as f:
        f.write(content)
    with db() as conn:
        conn.execute(
            "INSERT INTO photos (permit_id, filename, uploaded_by) VALUES (?,?,?)",
            (permit_id, filename, session["full_name"]),
        )
    return {"ok": True, "filename": filename, "url": f"/uploads/{filename}"}


@app.delete("/api/photos/{photo_id}")
async def delete_photo(photo_id: int, session=Depends(require_session)):
    with db() as conn:
        row = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
        if row:
            path = os.path.join(UPLOAD_DIR, row["filename"])
            if os.path.exists(path):
                os.remove(path)
            conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    return {"ok": True}


# ===========================================================================
# ACCÈS SOUS-TRAITANT — PUBLIC, SANS COMPTE (exigence #3)
# ===========================================================================
@app.get("/api/public/lookup")
async def public_lookup(request: Request, num: str, entreprise: str, sector_slug: Optional[str] = None):
    """Recherche publique par numéro de permis + nom d'entreprise (confirmation).
    Aucune authentification. Si sector_slug est fourni (arrivée par QR de secteur),
    le permis doit appartenir à ce secteur — sinon refusé, pour empêcher un
    sous-traitant de consulter un permis d'un autre secteur en devinant un numéro."""
    enforce_rate_limit(request, "public_lookup")
    num = (num or "").strip()
    entreprise = (entreprise or "").strip()
    if not num or not entreprise:
        raise HTTPException(status_code=400, detail="Numéro de permis et nom d'entreprise requis")

    with db() as conn:
        row = conn.execute("SELECT * FROM permits WHERE num = ?", (num,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Aucun permis trouvé avec ce numéro")
        p = row_to_dict(row)

        if p["entreprise"] is None or normalize_company_name(entreprise) != normalize_company_name(p["entreprise"]):
            raise HTTPException(status_code=404, detail="Le nom d'entreprise ne correspond pas à ce permis")

        if sector_slug:
            sector = conn.execute("SELECT * FROM sectors WHERE slug = ?", (sector_slug,)).fetchone()
            if not sector or p["sector_id"] != sector["id"]:
                raise HTTPException(status_code=404, detail="Ce permis n'appartient pas à ce secteur")

        p = auto_close_if_expired(conn, row)
        photos = conn.execute("SELECT filename FROM photos WHERE permit_id = ?", (p["id"],)).fetchall()

    # On ne renvoie que ce qui est utile au sous-traitant sur le terrain —
    # pas les coordonnées internes détaillées d'autres permis, pas le registre.
    safe_fields = [
        "num", "donneur", "entreprise", "executant", "description", "lieux", "zone",
        "date_debut", "date_fin", "risques_a", "risques_b", "risques_c",
        "zone_conforme", "height_work", "risques_hauteur", "height_acces", "height_m",
        "height_sauvetage", "height_vigie", "bonbonne_work", "risques_bonbonne",
        "bonbonne_type", "roof_work", "risques_toit", "roof_type", "roof_resistance",
        "roof_perimetre", "hot_work", "risques_hot", "hot_nature", "hot_debut", "hot_fin",
        "hot_surv", "hot_ext", "statut",
    ]
    result = {k: p.get(k) for k in safe_fields}
    result["photos"] = [f"/uploads/{ph['filename']}" for ph in photos]
    return result


@app.get("/api/public/sector/{slug}")
async def public_sector_info(slug: str):
    """Nom du secteur pour l'affichage de la page de recherche (public)."""
    with db() as conn:
        sector = conn.execute("SELECT * FROM sectors WHERE slug = ?", (slug,)).fetchone()
    if not sector:
        raise HTTPException(status_code=404, detail="Secteur introuvable")
    return dict(sector)


# ===========================================================================
# PAGES HTML
# ===========================================================================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request, "landing.html", {})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html", {})


@app.get("/secteur/{slug}", response_class=HTMLResponse)
async def secteur_page(request: Request, slug: str):
    with db() as conn:
        sector = conn.execute("SELECT * FROM sectors WHERE slug = ?", (slug,)).fetchone()
    if not sector:
        raise HTTPException(status_code=404, detail="Secteur introuvable")
    return templates.TemplateResponse(request, "secteur.html", {"sector": dict(sector)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
