"""
Permis de travail de chantier — Danone
Backend FastAPI + PostgreSQL.

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
import base64
import psycopg2
import asyncio
import binascii
import secrets
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
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

# DATA_DIR pointe vers le disque persistant Render (ex. /var/data) quand la
# variable d'environnement est définie sur le service — sinon on reste sur le
# dossier de l'app (comportement d'avant, disque éphémère). Ne concerne plus
# la base de données (voir database.py : DATABASE_URL, Postgres externe,
# persistant indépendamment du disque de ce service) — seulement les photos/
# rapports d'audit téléversés et la clé de signature des sessions ci-dessous,
# qui restent sur ce disque éphémère pour l'instant.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
AUDIT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "audits")
os.makedirs(AUDIT_UPLOAD_DIR, exist_ok=True)

# Clé de signature des sessions. En production : variable d'environnement,
# jamais codée en dur. Générée une fois ici pour que la démo fonctionne
# sans configuration.
SECRET_KEY_PATH = os.path.join(DATA_DIR, ".secret_key")
if os.path.exists(SECRET_KEY_PATH):
    SECRET_KEY = open(SECRET_KEY_PATH).read().strip()
else:
    SECRET_KEY = secrets.token_hex(32)
    with open(SECRET_KEY_PATH, "w") as f:
        f.write(SECRET_KEY)

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="session")
# Jeton court qui autorise l'affichage d'une photo sur la page publique d'un
# sous-traitant (émis seulement après une recherche num + entreprise réussie).
photo_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="photo")
PHOTO_TOKEN_MAX_AGE = 60 * 60  # 1h
SESSION_COOKIE = "danone_session"
SESSION_MAX_AGE = 60 * 60 * 12  # 12h

MIN_PASSWORD_LENGTH = 10
AUTO_CLOSE_INTERVAL_SECONDS = 15 * 60
PERMIT_STATUSES = ("Brouillon", "Actif", "Fermé")
# On ne peut créer ou modifier un permis qu'en Brouillon ou Actif : « Fermé »
# n'est atteint que par la fermeture à deux signatures ou par l'échéance.
EDITABLE_STATUSES = ("Brouillon", "Actif")
MAX_FIELD_LENGTH = 5000
MAX_SIGNATURE_BYTES = 300 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ferme périodiquement les permis expirés, même si personne ne consulte
    le registre (en plus de la vérification faite à chaque lecture)."""
    async def loop():
        while True:
            try:
                await asyncio.to_thread(close_all_expired)
            except Exception as exc:  # ne jamais faire tomber le serveur
                print(f"[fermeture automatique] erreur : {exc}")
            await asyncio.sleep(AUTO_CLOSE_INTERVAL_SECONDS)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Permis de travail de chantier — Danone", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    # Les gabarits utilisent des scripts et styles intégrés : 'unsafe-inline'
    # reste nécessaire tant qu'ils n'ont pas été déplacés dans des fichiers.
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
    )
    if is_https_request(request):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


init_db()


# ---------------------------------------------------------------------------
# Comptes par défaut au premier démarrage (mots de passe hachés dès la création)
# ---------------------------------------------------------------------------
def seed_default_admin():
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        if count == 0:
            # Mots de passe temporaires générés aléatoirement à chaque premier
            # démarrage — jamais codés en dur, jamais affichés dans l'interface
            # ni écrits dans le dépôt. Visibles une seule fois, dans les logs
            # du serveur (ex. logs Render), pour la première connexion.
            defaults = [
                ("admin", secrets.token_urlsafe(9), "Administrateur SST", "admin"),
                ("coordinateur", secrets.token_urlsafe(9), "Coordinateur SST", "donneur"),
            ]
            print("=" * 72)
            print("PREMIER DÉMARRAGE — comptes créés avec mot de passe temporaire :")
            for username, password, full_name, role in defaults:
                print(f"    rôle={role:10s} utilisateur={username:14s} mot de passe={password}")
            print("Connecte-toi avec ces identifiants puis change les mots de passe")
            print("immédiatement dans le panneau admin (section \"Utilisateurs\").")
            print("Ce message ne réapparaîtra plus après ce premier démarrage.")
            print("=" * 72)
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
# IP et par point d'accès. Suffisant pour un déploiement mono-processus ;
# à remplacer par un stockage partagé (Redis, etc.) si l'app est un jour
# répartie sur plusieurs instances.
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
        parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        # TRUSTED_PROXY_HOPS = nombre de proxys de confiance devant l'app : on
        # lit alors l'adresse ajoutée par le dernier d'entre eux, qu'un visiteur
        # ne peut pas falsifier. Sans réglage, on garde la première adresse
        # (falsifiable) — les limites par nom d'utilisateur / par permis
        # compensent.
        hops = os.environ.get("TRUSTED_PROXY_HOPS", "")
        if hops.isdigit() and int(hops) >= 1 and len(parts) >= int(hops):
            return parts[-int(hops)]
        if parts:
            return parts[0]
    return request.client.host if request.client else "unknown"


def _check_bucket(key: tuple, max_attempts: int) -> None:
    now = time.monotonic()
    attempts = _rate_limit_buckets[key]
    while attempts and now - attempts[0] > RATE_LIMIT_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= max_attempts:
        retry_after = max(1, int(RATE_LIMIT_WINDOW_SECONDS - (now - attempts[0])))
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives. Réessayez dans quelques minutes.",
            headers={"Retry-After": str(retry_after)},
        )
    attempts.append(now)


def enforce_rate_limit(request: Request, bucket_name: str, subject: Optional[str] = None,
                       subject_max: int = 20) -> None:
    """Limite par IP, et en plus par « sujet » (nom d'utilisateur, numéro de
    permis) : l'en-tête X-Forwarded-For peut être falsifié par le visiteur, donc
    la limite par IP seule ne suffit pas à bloquer un essai répété de mots de
    passe ou de noms d'entreprise."""
    _check_bucket((bucket_name, get_client_ip(request)), RATE_LIMIT_MAX_ATTEMPTS)
    if subject:
        _check_bucket((bucket_name + ":subject", subject.strip().lower()[:80]), subject_max)


def require_session(request: Request) -> dict:
    """Session valide ET utilisateur encore existant : le rôle est relu en base
    à chaque requête, donc une suppression de compte ou un changement de rôle
    prend effet immédiatement (pas seulement à l'expiration du cookie)."""
    session = read_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Non authentifié")
    with db() as conn:
        user = conn.execute(
            "SELECT id, username, full_name, role FROM users WHERE id = ?", (session["uid"],)
        ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return {"uid": user["id"], "username": user["username"], "role": user["role"], "full_name": user["full_name"]}


def require_admin(request: Request) -> dict:
    session = require_session(request)
    if session["role"] != "admin":
        raise HTTPException(status_code=403, detail="Accès admin requis")
    return session


# ---------------------------------------------------------------------------
# Validation des entrées
# ---------------------------------------------------------------------------
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DATA_URL_PREFIX = "data:image/png;base64,"


def validate_signature(value) -> str:
    """Une signature doit être une image PNG encodée en data-URL, de taille
    raisonnable. Elle est ensuite affichée dans <img src=...> : accepter une
    chaîne quelconque permettrait d'injecter du code dans la page."""
    if not isinstance(value, str) or not value.startswith(_DATA_URL_PREFIX):
        raise HTTPException(status_code=400, detail="Signature invalide (image PNG requise)")
    try:
        raw = base64.b64decode(value[len(_DATA_URL_PREFIX):], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Signature invalide (encodage incorrect)")
    if not raw.startswith(_PNG_MAGIC):
        raise HTTPException(status_code=400, detail="Signature invalide (image PNG requise)")
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise HTTPException(status_code=400, detail="Signature trop volumineuse")
    return value


async def read_json(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Corps de requête JSON invalide")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Corps de requête JSON invalide")
    return body


def check_text_lengths(body: dict) -> None:
    for key, value in body.items():
        if isinstance(value, str) and len(value) > MAX_FIELD_LENGTH:
            raise HTTPException(status_code=400, detail=f"Champ trop long : {key}")


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères",
        )
    if len(password.encode()) > 72:
        # bcrypt ignore tout ce qui dépasse 72 octets : on refuse plutôt que de tronquer en silence.
        raise HTTPException(status_code=400, detail="Le mot de passe est trop long (72 octets maximum)")


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


def _is_expired(p: dict) -> bool:
    if p["statut"] != "Actif" or not p["date_fin"]:
        return False
    try:
        return datetime.strptime(p["date_fin"], "%Y-%m-%d").date() < date.today()
    except ValueError:
        return False


def _close_expired_row(conn, p: dict) -> dict:
    ferme_le = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE permits SET statut='Fermé', ferme_le=?, updated_at=datetime('now') WHERE id=? AND statut='Actif'",
        (ferme_le, p["id"]),
    )
    add_status_history(conn, p["id"], "Fermé", "Système", "Fermeture automatique — date de fin dépassée")
    p["statut"] = "Fermé"
    p["ferme_le"] = ferme_le
    return p


def auto_close_if_expired(conn, permit_row) -> dict:
    """Ferme automatiquement un permis Actif dont la date de fin est dépassée.
    Appelé à chaque lecture ; close_all_expired() fait la même chose en tâche
    de fond toutes les 15 minutes."""
    p = row_to_dict(permit_row)
    if _is_expired(p):
        _close_expired_row(conn, p)
    return p


def close_all_expired() -> int:
    """Ferme tous les permis Actifs expirés. Retourne le nombre de permis fermés."""
    closed = 0
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM permits WHERE statut='Actif' AND date_fin IS NOT NULL AND date_fin != '' "
            "AND date_fin < ? AND archive_le IS NULL",
            (date.today().isoformat(),),
        ).fetchall()
        for row in rows:
            p = row_to_dict(row)
            if _is_expired(p):
                _close_expired_row(conn, p)
                closed += 1
    return closed


# ===========================================================================
# AUTHENTIFICATION
# ===========================================================================
# Hash factice comparé quand l'utilisateur n'existe pas : la durée de la
# réponse ne révèle plus si un nom d'utilisateur existe.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt()).decode()


@app.post("/api/auth/login")
async def login(request: Request, response: Response):
    body = await read_json(request)
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    enforce_rate_limit(request, "auth_login", subject=username or "(vide)", subject_max=10)
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    hash_to_check = user["password_hash"] if user else _DUMMY_HASH
    ok = bcrypt.checkpw(password.encode()[:72], hash_to_check.encode())
    if not user or not ok:
        raise HTTPException(status_code=401, detail="Nom d'utilisateur ou mot de passe incorrect")
    cookie_val = create_session_cookie(user["id"], user["username"], user["role"], user["full_name"])
    resp = JSONResponse({"ok": True, "uid": user["id"], "username": user["username"], "role": user["role"], "full_name": user["full_name"]})
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
    try:
        session = require_session(request)
    except HTTPException:
        return JSONResponse({"authenticated": False})
    return JSONResponse({"authenticated": True, **session})


@app.post("/api/auth/change-password")
async def change_password(request: Request, session=Depends(require_session)):
    """Changement de son propre mot de passe (ancien mot de passe exigé)."""
    body = await read_json(request)
    current = str(body.get("current_password") or "")
    new = str(body.get("new_password") or "")
    enforce_rate_limit(request, "change_password", subject=session["username"], subject_max=10)
    validate_password(new)
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["uid"],)).fetchone()
        if not user or not bcrypt.checkpw(current.encode()[:72], user["password_hash"].encode()):
            raise HTTPException(status_code=403, detail="Mot de passe actuel incorrect")
        if bcrypt.checkpw(new.encode(), user["password_hash"].encode()):
            raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit être différent de l'ancien")
        h = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (h, session["uid"]))
    return {"ok": True}


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
    body = await read_json(request)
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    full_name = str(body.get("full_name") or "").strip()
    role = body.get("role")
    if not username or not password or not full_name or role not in ("admin", "donneur"):
        raise HTTPException(status_code=400, detail="Champs manquants ou rôle invalide")
    if len(username) > 60 or len(full_name) > 120:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur ou nom complet trop long")
    validate_password(password)
    h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?,?,?,?)",
                (username, h, full_name, role),
            )
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà")
    return {"ok": True}


@app.put("/api/users/{user_id}/password")
async def reset_user_password(user_id: int, request: Request, session=Depends(require_admin)):
    """Réinitialisation du mot de passe d'un utilisateur par un administrateur."""
    body = await read_json(request)
    new = str(body.get("new_password") or "")
    validate_password(new)
    h = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
    with db() as conn:
        cur = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (h, user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"ok": True}


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, session=Depends(require_admin)):
    if user_id == session["uid"]:
        raise HTTPException(status_code=400, detail="Impossible de supprimer votre propre compte")
    with db() as conn:
        target = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        if target["role"] == "admin":
            admins = conn.execute("SELECT COUNT(*) c FROM users WHERE role = 'admin'").fetchone()["c"]
            if admins <= 1:
                raise HTTPException(status_code=400, detail="Impossible de supprimer le dernier administrateur")
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
    body = await read_json(request)
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de secteur requis")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Nom de secteur trop long (100 caractères maximum)")
    slug = slugify(name)
    try:
        with db() as conn:
            conn.execute("INSERT INTO sectors (name, slug) VALUES (?,?)", (name, slug))
    except psycopg2.IntegrityError:
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

TEXT_FIELDS = [
    "donneur", "donneur_tel", "entreprise", "executant", "executant_tel",
    "description", "lieux", "zone", "date_debut", "date_fin", "zone_conforme", "zone_comm",
    "height_acces", "height_m", "height_sauvetage", "height_vigie",
    "bonbonne_type", "bonbonne_nombre", "bonbonne_levage",
    "roof_type", "roof_resistance", "roof_perimetre", "roof_vigie",
    "hot_nature", "hot_debut", "hot_fin", "hot_surv", "hot_ext",
]
LIST_FIELDS = ["risques_a", "risques_b", "risques_c", "risques_hauteur", "risques_bonbonne", "risques_toit", "risques_hot"]
BOOL_FIELDS = ["height_work", "bonbonne_work", "roof_work", "hot_work"]


def _clean_list(value) -> list:
    if not isinstance(value, list):
        return []
    return [str(v)[:300] for v in value[:100] if isinstance(v, (str, int, float))]


def _clean_pta(value) -> dict:
    """Contenu du PTA Danone : dict clé -> texte ou liste de textes (borné)."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for k, v in list(value.items())[:200]:
        key = str(k)[:60]
        if isinstance(v, list):
            out[key] = _clean_list(v)
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            out[key] = str(v).strip()[:1000]
    return out


def _clean_text(value):
    if value is None:
        return None
    return str(value).strip()


def _parse_iso_date(value: Optional[str], label: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Date invalide pour {label} (format AAAA-MM-JJ attendu)")


def validate_permit_payload(body: dict):
    check_text_lengths(body)
    missing = [f for f in REQUIRED_BASE if not str(body.get(f) or "").strip()]
    if body.get("height_work") or body.get("roof_work"):
        if not (body.get("height_vigie") or body.get("roof_vigie")):
            missing.append("vigie (obligatoire si travail en hauteur ou au toit)")
        if body.get("height_work") and not body.get("height_sauvetage"):
            missing.append("plan de sauvetage (obligatoire si travail en hauteur)")
    if body.get("hot_work") and not body.get("hot_surv"):
        missing.append("surveillance incendie (obligatoire si travail à chaud)")
    if missing:
        raise HTTPException(status_code=400, detail="Champs obligatoires manquants : " + ", ".join(missing))
    debut = _parse_iso_date(str(body.get("date_debut") or "").strip() or None, "la date de début")
    fin = _parse_iso_date(str(body.get("date_fin") or "").strip() or None, "la date de fin")
    if debut and fin and fin < debut:
        raise HTTPException(status_code=400, detail="La date de fin est antérieure à la date de début")


def _validate_sector(conn, sector_id):
    if sector_id in (None, ""):
        return None
    try:
        sector_id = int(sector_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Secteur invalide")
    if not conn.execute("SELECT 1 FROM sectors WHERE id = ?", (sector_id,)).fetchone():
        raise HTTPException(status_code=400, detail="Secteur introuvable")
    return sector_id


@app.get("/api/donneurs")
async def list_donneurs(session=Depends(require_session)):
    """Noms des comptes 'donneur d'ordre' enregistrés — pour suggérer un nom
    exact dans le formulaire de permis (le rapprochement du tableau de bord
    personnel /api/permits?mine=true compare ce texte au nom complet de la
    session, donc une orthographe cohérente évite les faux négatifs)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT full_name FROM users WHERE role='donneur' ORDER BY full_name"
        ).fetchall()
    return [r["full_name"] for r in rows]


@app.post("/api/permits")
async def create_permit(request: Request, session=Depends(require_session)):
    body = await read_json(request)
    validate_permit_payload(body)
    statut = body.get("statut", "Actif")
    if statut not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Un permis se crée en Brouillon ou Actif ; il ne se ferme qu'avec les deux signatures",
        )
    with db() as conn:
        # Verrou d'écriture avant de lire le dernier numéro : deux créations
        # simultanées ne peuvent plus obtenir le même numéro. (Postgres :
        # verrou exclusif sur la table, bloque les autres écritures jusqu'au
        # commit, mais n'empêche pas les lectures concurrentes.)
        conn.execute("LOCK TABLE permits IN EXCLUSIVE MODE")
        num = next_permit_num(conn)
        values = {"num": num, "sector_id": _validate_sector(conn, body.get("sector_id"))}
        for f in TEXT_FIELDS:
            values[f] = _clean_text(body.get(f))
        for f in LIST_FIELDS:
            values[f] = json.dumps(_clean_list(body.get(f, [])))
        for f in BOOL_FIELDS:
            values[f] = int(bool(body.get(f)))
        values["pta"] = json.dumps(_clean_pta(body.get("pta")))
        values["statut"] = statut
        values["cree_par"] = session["full_name"]
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        cur = conn.execute(f"INSERT INTO permits ({columns}) VALUES ({placeholders})", list(values.values()))
        permit_id = cur.lastrowid
        add_status_history(conn, permit_id, statut, session["full_name"], "Création du permis")
        row = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
    return row_to_dict(row)


@app.get("/api/permits/next-num")
async def get_next_permit_num(session=Depends(require_session)):
    """Numéro qu'obtiendra le prochain permis créé — affiché sur le formulaire
    de création avant l'enregistrement. Prévisualisation seule : le numéro
    définitif est (re)calculé et assigné de façon atomique au moment du
    POST /api/permits, donc deux formulaires ouverts en même temps peuvent
    prévisualiser le même numéro sans conflit réel."""
    with db() as conn:
        num = next_permit_num(conn)
    return {"num": num}


@app.get("/api/permits")
async def list_permits(
    request: Request,
    session=Depends(require_session),
    page: int = 1,
    page_size: int = 25,
    search: str = "",
    statut: str = "",
    sector_id: Optional[int] = None,
    archives: bool = False,
    mine: bool = False,
    period: str = "",
):
    if archives and session["role"] != "admin":
        raise HTTPException(status_code=403, detail="Accès admin requis")
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    offset = (page - 1) * page_size

    where = ["archive_le IS NOT NULL" if archives else "archive_le IS NULL"]
    params = []
    if mine:
        # Tableau de bord personnel du donneur d'ordre : le champ "donneur"
        # est du texte libre sur le permis (pas de compte lié), donc on
        # rapproche sur le nom complet de la session, insensible à la casse
        # et aux espaces superflus.
        where.append("LOWER(TRIM(donneur)) = LOWER(TRIM(?))")
        params.append(session["full_name"])
    if period == "week":
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        where.append("date(created_at) BETWEEN date(?) AND date(?)")
        params.append(week_start.isoformat())
        params.append(week_end.isoformat())
    if search:
        # ILIKE (Postgres) au lieu de LIKE : SQLite était insensible à la
        # casse par défaut pour LIKE (texte ASCII), Postgres ne l'est pas.
        where.append("(num ILIKE ? OR entreprise ILIKE ? OR executant ILIKE ? OR description ILIKE ? OR lieux ILIKE ? OR donneur ILIKE ?)")
        like = f"%{search}%"
        params += [like] * 6
    if statut:
        where.append("statut = ?")
        params.append(statut)
    if sector_id:
        where.append("sector_id = ?")
        params.append(sector_id)
    where_sql = "WHERE " + " AND ".join(where)

    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) c FROM permits {where_sql}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM permits {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        permits = [auto_close_if_expired(conn, r) for r in rows]
        # Les images de signature (lourdes) ne servent qu'au détail d'un permis.
        for permit in permits:
            for key in ("signature_donneur", "signature_executant", "signature_reception"):
                permit[key] = bool(permit.get(key))

        stats_row = conn.execute(
            "SELECT COUNT(*) total, SUM(CASE WHEN statut='Actif' THEN 1 ELSE 0 END) actifs, "
            "SUM(height_work) hauteur, SUM(roof_work) toit, SUM(hot_work) chaud "
            "FROM permits WHERE archive_le IS NULL"
        ).fetchone()

    return {
        "permits": permits,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "stats": dict(stats_row),
    }


def _get_visible_permit(conn, permit_id: int, session: dict):
    row = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
    if not row or (row["archive_le"] and session["role"] != "admin"):
        raise HTTPException(status_code=404, detail="Permis introuvable")
    return row


@app.get("/api/permits/{permit_id}")
async def get_permit(permit_id: int, session=Depends(require_session)):
    with db() as conn:
        row = _get_visible_permit(conn, permit_id, session)
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
    body = await read_json(request)
    validate_permit_payload(body)
    if "statut" in body and body["statut"] not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Le statut ne peut être que Brouillon ou Actif ; la fermeture se fait avec les deux signatures",
        )

    with db() as conn:
        existing_row = _get_visible_permit(conn, permit_id, session)
        existing = auto_close_if_expired(conn, existing_row)
        if existing_row["archive_le"]:
            raise HTTPException(status_code=409, detail="Ce permis est archivé — modification impossible")
        if existing["statut"] == "Fermé":
            raise HTTPException(status_code=409, detail="Ce permis est fermé — il n'est plus modifiable")

        updates = {}
        changed = []
        if "sector_id" in body:
            updates["sector_id"] = _validate_sector(conn, body["sector_id"])
            if updates["sector_id"] != existing["sector_id"]:
                changed.append("sector_id")
        for f in TEXT_FIELDS:
            if f in body:
                updates[f] = _clean_text(body[f])
                if (updates[f] or "") != str(existing[f] or ""):
                    changed.append(f)
        for f in LIST_FIELDS:
            if f in body:
                updates[f] = json.dumps(_clean_list(body[f]))
                if _clean_list(body[f]) != existing[f]:
                    changed.append(f)
        for f in BOOL_FIELDS:
            if f in body:
                updates[f] = int(bool(body[f]))
                if updates[f] != int(bool(existing[f])):
                    changed.append(f)
        if "pta" in body:
            new_pta = _clean_pta(body["pta"])
            updates["pta"] = json.dumps(new_pta)
            if new_pta != (existing.get("pta") or {}):
                changed.append("pta")
        new_statut = body.get("statut", existing["statut"])
        status_changed = new_statut != existing["statut"]
        if status_changed:
            updates["statut"] = new_statut

        set_sql = ", ".join(f"{k} = ?" for k in updates) + (", " if updates else "") + "updated_at = datetime('now')"
        conn.execute(f"UPDATE permits SET {set_sql} WHERE id = ?", list(updates.values()) + [permit_id])

        if status_changed:
            note = body.get("status_note") or "Changement de statut"
            add_status_history(conn, permit_id, new_statut, session["full_name"], str(note)[:500])
        if changed:
            add_status_history(
                conn, permit_id, new_statut, session["full_name"],
                "Permis modifié — champs : " + ", ".join(changed),
            )

        row = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
    return row_to_dict(row)


@app.delete("/api/permits/{permit_id}")
async def delete_permit(permit_id: int, session=Depends(require_admin)):
    """Archive le permis (jamais de suppression : c'est un document légal).
    Il disparaît du registre courant, mais reste en base avec son historique et
    ses signatures ; un administrateur peut le retrouver via ?archives=true."""
    with db() as conn:
        row = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Permis introuvable")
        if row["archive_le"]:
            return {"ok": True, "archived": True}
        conn.execute(
            "UPDATE permits SET archive_le = ?, archive_par = ?, updated_at = datetime('now') WHERE id = ?",
            (datetime.utcnow().isoformat(), session["full_name"], permit_id),
        )
        add_status_history(conn, permit_id, row["statut"], session["full_name"], "Permis archivé")
    return {"ok": True, "archived": True}


@app.post("/api/permits/{permit_id}/close")
async def close_permit(permit_id: int, request: Request, session=Depends(require_session)):
    """Fermeture officielle avec double signature électronique."""
    body = await read_json(request)
    if not body.get("signature_donneur") or not body.get("signature_executant"):
        raise HTTPException(status_code=400, detail="Les deux signatures (donneur d'ordre et exécutant) sont requises")
    sig_donneur = validate_signature(body.get("signature_donneur"))
    sig_executant = validate_signature(body.get("signature_executant"))
    with db() as conn:
        existing_row = _get_visible_permit(conn, permit_id, session)
        existing = auto_close_if_expired(conn, existing_row)
        if existing_row["archive_le"]:
            raise HTTPException(status_code=409, detail="Ce permis est archivé")
        if existing["statut"] == "Fermé":
            raise HTTPException(status_code=409, detail="Ce permis est déjà fermé")
        if existing["statut"] != "Actif":
            raise HTTPException(status_code=400, detail="Seul un permis actif peut être fermé")
        conn.execute(
            "UPDATE permits SET statut='Fermé', signature_donneur=?, signature_executant=?, "
            "ferme_le=?, updated_at=datetime('now') WHERE id=?",
            (sig_donneur, sig_executant, datetime.utcnow().isoformat(), permit_id),
        )
        add_status_history(conn, permit_id, "Fermé", session["full_name"], "Fermeture officielle avec signatures")
        row = conn.execute("SELECT * FROM permits WHERE id = ?", (permit_id,)).fetchone()
    return row_to_dict(row)


MAX_PHOTO_BYTES = 15 * 1024 * 1024


def _looks_like_image(ext: str, head: bytes) -> bool:
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return head.startswith(_PNG_MAGIC)
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == ".heic":
        return head[4:8] == b"ftyp"
    return False


@app.post("/api/permits/{permit_id}/photos")
async def upload_photo(permit_id: int, file: UploadFile = File(...), session=Depends(require_session)):
    with db() as conn:
        existing = conn.execute("SELECT id, archive_le FROM permits WHERE id = ?", (permit_id,)).fetchone()
        if not existing or existing["archive_le"]:
            raise HTTPException(status_code=404, detail="Permis introuvable")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
        raise HTTPException(status_code=400, detail="Format d'image non supporté")
    content = await file.read(MAX_PHOTO_BYTES + 1)
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="Photo trop volumineuse (max 15 Mo)")
    if not _looks_like_image(ext, content[:16]):
        raise HTTPException(status_code=400, detail="Le fichier n'est pas une image valide")
    filename = f"{permit_id}_{uuid.uuid4().hex[:16]}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
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


@app.get("/uploads/{filename}")
async def serve_upload(filename: str, request: Request, t: Optional[str] = None):
    """Photos de permis. Avant, tout le dossier était servi sans contrôle ;
    maintenant il faut soit une session, soit un jeton court émis par la
    consultation publique (numéro + entreprise valides). Les rapports d'audit,
    rangés dans un sous-dossier, ne passent jamais par ici."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,120}", filename):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    authorized = False
    try:
        require_session(request)
        authorized = True
    except HTTPException:
        pass
    if not authorized and t:
        try:
            authorized = photo_serializer.loads(t, max_age=PHOTO_TOKEN_MAX_AGE) == filename
        except (BadSignature, SignatureExpired):
            authorized = False
    if not authorized:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


# ===========================================================================
# AUDITS — rapports d'audit importés, classés par secteur
# ===========================================================================
AUDIT_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png")


@app.get("/api/audits")
async def list_audits(sector_id: Optional[int] = None, session=Depends(require_session)):
    where = ""
    params = []
    if sector_id:
        where = "WHERE a.sector_id = ?"
        params.append(sector_id)
    with db() as conn:
        rows = conn.execute(
            f"""SELECT a.*, s.name AS sector_name FROM audits a
                JOIN sectors s ON s.id = a.sector_id
                {where}
                ORDER BY COALESCE(a.date_audit, a.uploaded_at) DESC, a.id DESC""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/audits")
async def upload_audit(
    sector_id: int = Form(...),
    titre: str = Form(""),
    date_audit: str = Form(""),
    file: UploadFile = File(...),
    session=Depends(require_session),
):
    with db() as conn:
        sector = conn.execute("SELECT id FROM sectors WHERE id = ?", (sector_id,)).fetchone()
    if not sector:
        raise HTTPException(status_code=404, detail="Secteur introuvable")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in AUDIT_EXTS:
        raise HTTPException(status_code=400, detail="Format de fichier non supporté (PDF, Word, Excel ou image)")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 25 Mo)")
    filename = f"{sector_id}_{uuid.uuid4().hex[:10]}{ext}"
    path = os.path.join(AUDIT_UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(content)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO audits (sector_id, filename, original_name, titre, date_audit, uploaded_by) "
            "VALUES (?,?,?,?,?,?)",
            (sector_id, filename, file.filename, titre or None, date_audit or None, session["full_name"]),
        )
        audit_id = cur.lastrowid
        row = conn.execute(
            "SELECT a.*, s.name AS sector_name FROM audits a JOIN sectors s ON s.id = a.sector_id WHERE a.id = ?",
            (audit_id,),
        ).fetchone()
    return dict(row)


@app.get("/api/audits/{audit_id}/download")
async def download_audit(audit_id: int, session=Depends(require_session)):
    with db() as conn:
        row = conn.execute("SELECT * FROM audits WHERE id = ?", (audit_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Rapport introuvable")
    path = os.path.join(AUDIT_UPLOAD_DIR, row["filename"])
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return FileResponse(path, filename=row["original_name"] or row["filename"])


@app.delete("/api/audits/{audit_id}")
async def delete_audit(audit_id: int, session=Depends(require_session)):
    with db() as conn:
        row = conn.execute("SELECT * FROM audits WHERE id = ?", (audit_id,)).fetchone()
        if row:
            path = os.path.join(AUDIT_UPLOAD_DIR, row["filename"])
            if os.path.exists(path):
                os.remove(path)
            conn.execute("DELETE FROM audits WHERE id = ?", (audit_id,))
    return {"ok": True}


# ===========================================================================
# ACCÈS SOUS-TRAITANT — PUBLIC, SANS COMPTE (exigence #3)
# ===========================================================================
NOT_FOUND_PUBLIC = "Aucun permis ne correspond à ces informations"
AMBIGUOUS_PUBLIC = (
    "Plusieurs permis actifs correspondent à cette entreprise — "
    "précisez aussi le numéro de permis pour continuer"
)


def _find_public_permit(conn, num: str, entreprise: str):
    """Trouve le permis pour un sous-traitant, à partir du numéro, du nom
    d'entreprise, ou des deux (au moins un des deux est requis — voir
    public_lookup/public_sign). Même message d'erreur générique dans tous
    les cas d'échec : on ne confirme jamais qu'un numéro existe à un inconnu
    qui n'aurait pas la bonne entreprise, et inversement."""
    num = (num or "").strip()
    entreprise_norm = normalize_company_name(entreprise)

    if num:
        row = conn.execute("SELECT * FROM permits WHERE num = ? AND archive_le IS NULL", (num,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=NOT_FOUND_PUBLIC)
        if entreprise_norm:
            # Les deux sont fournis : les deux doivent correspondre (comme avant).
            if row["entreprise"] is None or entreprise_norm != normalize_company_name(row["entreprise"]):
                raise HTTPException(status_code=404, detail=NOT_FOUND_PUBLIC)
        return row

    # Pas de numéro : recherche par entreprise seule. Peut être ambigu si
    # l'entreprise a plusieurs permis actifs — on demande alors le numéro
    # plutôt que de deviner lequel. Pré-filtre large en SQL (insensible à la
    # casse), confirmation exacte en Python avec normalize_company_name
    # (espaces multiples compris) pour rester cohérent avec le cas num+entreprise.
    candidates = conn.execute(
        "SELECT * FROM permits WHERE archive_le IS NULL AND entreprise ILIKE ? ORDER BY id DESC",
        (f"%{entreprise.strip()}%",),
    ).fetchall()
    rows = [r for r in candidates if normalize_company_name(r["entreprise"]) == entreprise_norm]
    if not rows:
        raise HTTPException(status_code=404, detail=NOT_FOUND_PUBLIC)
    if len(rows) > 1:
        raise HTTPException(status_code=409, detail=AMBIGUOUS_PUBLIC)
    return rows[0]


@app.get("/api/public/lookup")
async def public_lookup(request: Request, num: str = "", entreprise: str = "", sector_slug: Optional[str] = None):
    """Recherche publique par numéro de permis et/ou nom d'entreprise (au
    moins un des deux). Aucune authentification. Le secteur n'est plus
    utilisé pour restreindre la recherche (aucun secteur n'est assigné à la
    création) : sector_slug est accepté pour compatibilité mais n'est plus
    vérifié. Pas de limite de tentatives ici — un sous-traitant sur le
    terrain doit pouvoir réessayer autant de fois que nécessaire pour
    retrouver son permis (une limite reste en place à la signature, qui est
    l'action qui compte réellement)."""
    num = (num or "").strip()
    entreprise = (entreprise or "").strip()
    if not num and not entreprise:
        raise HTTPException(status_code=400, detail="Numéro de permis ou nom d'entreprise requis")

    with db() as conn:
        row = _find_public_permit(conn, num, entreprise)
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
        "hot_surv", "hot_ext", "statut", "reception_nom", "reception_le",
    ]
    result = {k: p.get(k) for k in safe_fields}
    result["photos"] = [
        f"/uploads/{ph['filename']}?t={photo_serializer.dumps(ph['filename'])}" for ph in photos
    ]
    return result


@app.post("/api/public/sign")
async def public_sign(request: Request):
    """Signature électronique du sous-traitant à la consultation du permis
    (reconnaissance de lecture avant le début des travaux). Publique, mais
    revérifie num + entreprise comme /api/public/lookup — pas de session.
    Une fois signé, le permis ne peut plus être re-signé (ni écrasé)."""
    body = await read_json(request)
    num = str(body.get("num") or "").strip()
    entreprise = str(body.get("entreprise") or "").strip()
    nom = str(body.get("nom") or "").strip()
    sector_slug = str(body.get("sector_slug") or "").strip()
    if not num or not entreprise or not nom or not body.get("signature"):
        raise HTTPException(status_code=400, detail="Nom de l'exécutant et signature requis")
    if len(nom) > 120:
        raise HTTPException(status_code=400, detail="Nom trop long")
    enforce_rate_limit(request, "public_sign", subject=num, subject_max=20)
    signature = validate_signature(body.get("signature"))

    with db() as conn:
        row = _find_public_permit(conn, num, entreprise)
        p = auto_close_if_expired(conn, row)
        if p["statut"] == "Fermé":
            raise HTTPException(status_code=400, detail="Ce permis est fermé — signature impossible")
        if p["statut"] != "Actif":
            raise HTTPException(status_code=400, detail="Ce permis n'est pas encore actif — signature impossible")
        if p.get("reception_nom"):
            raise HTTPException(status_code=409, detail="Ce permis a déjà été signé à la réception")

        horodatage = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE permits SET signature_reception=?, reception_nom=?, reception_le=?, updated_at=datetime('now') WHERE id=?",
            (signature, nom, horodatage, p["id"]),
        )
        # Le secteur physique où le permis a été consulté/signé (QR scanné sur
        # place) attribue le permis à ce secteur dans le registre, s'il n'en
        # avait pas déjà un — la recherche elle-même reste libre (voir
        # /api/public/lookup) mais la signature, elle, ancre le permis.
        if sector_slug and not p.get("sector_id"):
            sector = conn.execute("SELECT id FROM sectors WHERE slug = ?", (sector_slug,)).fetchone()
            if sector:
                conn.execute("UPDATE permits SET sector_id=? WHERE id=? AND sector_id IS NULL", (sector["id"], p["id"]))
        add_status_history(
            conn, p["id"], p["statut"], nom,
            f"Permis consulté et signé sur place par {nom} ({entreprise})",
        )
        # Notifie le donneur d'ordre (et le reste de l'équipe SST) : l'exécutant
        # vient de consulter et signer le permis sur place, avant de commencer.
        conn.execute(
            "INSERT INTO notifications (permit_id, permit_num, message) VALUES (?,?,?)",
            (
                p["id"], p["num"],
                f"✍️ {nom} ({entreprise}) a signé la réception du permis {p['num']} — "
                f"donneur d'ordre : {p['donneur']}",
            ),
        )
    return {"ok": True, "reception_nom": nom, "reception_le": horodatage}


# ===========================================================================
# NOTIFICATIONS — signatures de réception, vues par l'équipe SST (admin +
# donneurs d'ordre) au prochain login. Fil global (le donneur d'ordre du
# permis est un champ texte libre, pas un compte utilisateur), lu jusqu'à
# users.last_notif_seen_id pour calculer le compteur non-lu par utilisateur.
# ===========================================================================
@app.get("/api/notifications")
async def list_notifications(session=Depends(require_session)):
    with db() as conn:
        rows = conn.execute(
            "SELECT id, permit_id, permit_num, message, created_at FROM notifications "
            "ORDER BY id DESC LIMIT 30"
        ).fetchall()
        last_seen = conn.execute(
            "SELECT last_notif_seen_id FROM users WHERE id = ?", (session["uid"],)
        ).fetchone()["last_notif_seen_id"]
    return {
        "notifications": [dict(r) for r in rows],
        "unread_count": sum(1 for r in rows if r["id"] > last_seen),
    }


@app.post("/api/notifications/seen")
async def mark_notifications_seen(session=Depends(require_session)):
    with db() as conn:
        max_id = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM notifications").fetchone()["m"]
        conn.execute("UPDATE users SET last_notif_seen_id = ? WHERE id = ?", (max_id, session["uid"]))
    return {"ok": True}


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

# Entreprises clientes actives sur SafeOp. Pour ajouter un client : une entrée
# ici, aucune page à refaire (clients.html boucle sur cette liste).
SAFEOP_CLIENTS = [
    {
        "name": "Danone",
        "logo": "/static/img/logo-danone-icon.png",
        "url": "/admin",
    },
]


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


@app.get("/formation", response_class=HTMLResponse)
async def formation_page(request: Request):
    return templates.TemplateResponse(request, "formation.html", {})


@app.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request):
    return templates.TemplateResponse(request, "clients.html", {"clients": SAFEOP_CLIENTS})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
