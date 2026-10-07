"""Tests de bout en bout de l'API (base Postgres de test dédiée, tables
vidées avant chaque test — DATABASE_URL doit pointer vers une base Postgres
réservée aux tests, jamais vers la base de production)."""
import base64
import importlib
import os
import sys
import tempfile

import bcrypt
import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(__file__))
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
SIG = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()
ADMIN_PW = "motdepasse-admin-1"
DONNEUR_PW = "motdepasse-donneur-1"

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://permis_test:test@localhost:5432/permis_pytest"
)

_ALL_TABLES = (
    "notifications", "audits", "photos", "status_history", "permits", "sectors", "users",
)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    sys.path.insert(0, ROOT)
    for name in ("app", "database"):
        sys.modules.pop(name, None)
    app_module = importlib.import_module("app")
    db_module = importlib.import_module("database")
    db_module.init_db()
    with db_module.db() as conn:
        # Table dédiée aux tests, réutilisée d'un test à l'autre : on repart
        # de zéro à chaque test plutôt que de compter sur un fichier neuf
        # (comme le permettait l'ancienne base SQLite par tmp_path).
        conn.execute(f"TRUNCATE {', '.join(_ALL_TABLES)} RESTART IDENTITY CASCADE")
        for username, pw, role in (("admin", ADMIN_PW, "admin"), ("coord", DONNEUR_PW, "donneur")):
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?,?,?,?)",
                (username, bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode(), username.title(), role),
            )
    yield app_module, db_module
    sys.path.remove(ROOT)


@pytest.fixture(autouse=True)
def _reset_rate_limits(env):
    env[0]._rate_limit_buckets.clear()


def make_client(env, username=None, password=None):
    client = TestClient(env[0].app)
    if username:
        r = client.post("/api/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def admin(env):
    return make_client(env, "admin", ADMIN_PW)


@pytest.fixture()
def donneur(env):
    return make_client(env, "coord", DONNEUR_PW)


def permit_body(**over):
    body = {
        "donneur": "Coord SST", "entreprise": "Soudure Pro Inc.", "executant": "Martin Gagné",
        "description": "Soudure conduite", "lieux": "Salle 12", "date_debut": "2099-01-01",
        "date_fin": "2099-01-05", "statut": "Actif",
    }
    body.update(over)
    return body


# ---------------------------------------------------------------- authentification
def test_login_ok_and_bad_credentials(env):
    c = TestClient(env[0].app)
    assert c.post("/api/auth/login", json={"username": "admin", "password": "faux"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "inconnu", "password": "x"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW})
    assert r.status_code == 200 and r.json()["role"] == "admin" and "uid" in r.json()
    assert c.get("/api/auth/me").json()["authenticated"] is True


def test_login_bad_body(env):
    c = TestClient(env[0].app)
    assert c.post("/api/auth/login", content="pas du json").status_code == 400
    assert c.post("/api/auth/login", json=["liste"]).status_code == 400


def test_login_rate_limited_per_username_even_if_ip_is_spoofed(env):
    c = TestClient(env[0].app)
    codes = []
    for i in range(12):
        # Un visiteur malveillant change d'IP à chaque essai (en-tête falsifié).
        r = c.post("/api/auth/login", json={"username": "admin", "password": f"faux{i}"},
                   headers={"X-Forwarded-For": f"10.0.0.{i}"})
        codes.append(r.status_code)
    assert 429 in codes
    # ... même le bon mot de passe est refusé tant que la limite est atteinte
    r = c.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW},
               headers={"X-Forwarded-For": "10.9.9.9"})
    assert r.status_code == 429


def test_session_revoked_when_user_deleted(env, admin):
    c = make_client(env, "coord", DONNEUR_PW)
    assert c.get("/api/permits").status_code == 200
    users = admin.get("/api/users").json()
    coord_id = next(u["id"] for u in users if u["username"] == "coord")
    assert admin.delete(f"/api/users/{coord_id}").status_code == 200
    assert c.get("/api/permits").status_code == 401
    assert c.get("/api/auth/me").json()["authenticated"] is False


def test_role_read_from_database_not_cookie(env, admin, donneur):
    assert donneur.get("/api/users").status_code == 403
    assert donneur.delete("/api/permits/1").status_code == 403
    assert admin.get("/api/users").status_code == 200


def test_cannot_delete_self_or_last_admin(env, admin):
    me = admin.get("/api/auth/me").json()
    assert admin.delete(f"/api/users/{me['uid']}").status_code == 400
    assert admin.post("/api/users", json={"username": "admin2", "password": "unautremotdepasse", "full_name": "A2", "role": "admin"}).status_code == 200
    admin2 = make_client(env, "admin2", "unautremotdepasse")
    # admin2 supprime admin : autorisé (il reste admin2) ; puis admin2 ne peut pas se supprimer lui-même.
    assert admin2.delete(f"/api/users/{me['uid']}").status_code == 200
    me2 = admin2.get("/api/auth/me").json()
    assert admin2.delete(f"/api/users/{me2['uid']}").status_code == 400


def test_change_password_flow(env, donneur):
    assert donneur.post("/api/auth/change-password", json={"current_password": "faux", "new_password": "nouveau-mot-de-passe"}).status_code == 403
    assert donneur.post("/api/auth/change-password", json={"current_password": DONNEUR_PW, "new_password": "court"}).status_code == 400
    assert donneur.post("/api/auth/change-password", json={"current_password": DONNEUR_PW, "new_password": DONNEUR_PW}).status_code == 400
    assert donneur.post("/api/auth/change-password", json={"current_password": DONNEUR_PW, "new_password": "nouveau-mot-de-passe"}).status_code == 200
    fresh = TestClient(env[0].app)
    assert fresh.post("/api/auth/login", json={"username": "coord", "password": DONNEUR_PW}).status_code == 401
    assert fresh.post("/api/auth/login", json={"username": "coord", "password": "nouveau-mot-de-passe"}).status_code == 200


def test_admin_reset_password_and_validation(env, admin):
    users = admin.get("/api/users").json()
    coord_id = next(u["id"] for u in users if u["username"] == "coord")
    assert admin.put(f"/api/users/{coord_id}/password", json={"new_password": "court"}).status_code == 400
    assert admin.put("/api/users/9999/password", json={"new_password": "un-long-mot-de-passe"}).status_code == 404
    assert admin.put(f"/api/users/{coord_id}/password", json={"new_password": "un-long-mot-de-passe"}).status_code == 200
    assert make_client(env, "coord", "un-long-mot-de-passe")
    # création d'utilisateur : mot de passe trop court / rôle invalide / doublon
    base = {"username": "nouveau", "full_name": "Nouveau", "role": "donneur"}
    assert admin.post("/api/users", json={**base, "password": "court"}).status_code == 400
    assert admin.post("/api/users", json={**base, "password": "long-mot-de-passe", "role": "root"}).status_code == 400
    assert admin.post("/api/users", json={**base, "password": "long-mot-de-passe"}).status_code == 200
    assert admin.post("/api/users", json={**base, "password": "long-mot-de-passe"}).status_code == 409


def test_security_headers(env):
    r = TestClient(env[0].app).get("/")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    api = TestClient(env[0].app).get("/api/auth/me")
    assert api.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------- permis
def test_permit_create_list_and_numbering(env, donneur):
    a = donneur.post("/api/permits", json=permit_body()).json()
    b = donneur.post("/api/permits", json=permit_body()).json()
    assert a["num"] == "00525" and b["num"] == "00526"
    data = donneur.get("/api/permits").json()
    assert data["total"] == 2 and data["stats"]["actifs"] == 2
    assert "signature_donneur" in data["permits"][0] and data["permits"][0]["signature_donneur"] is False
    assert donneur.get("/api/permits", params={"search": "Soudure"}).json()["total"] == 2
    assert donneur.get("/api/permits", params={"search": "zzz"}).json()["total"] == 0


def test_permit_validation(env, donneur):
    assert donneur.post("/api/permits", json=permit_body(description="")).status_code == 400
    assert donneur.post("/api/permits", json=permit_body(statut="Fermé")).status_code == 400
    assert donneur.post("/api/permits", json=permit_body(statut="<img src=x onerror=alert(1)>")).status_code == 400
    assert donneur.post("/api/permits", json=permit_body(date_debut="pas une date")).status_code == 400
    assert donneur.post("/api/permits", json=permit_body(date_debut="2099-02-01", date_fin="2099-01-01")).status_code == 400
    assert donneur.post("/api/permits", json=permit_body(description="x" * 6000)).status_code == 400
    assert donneur.post("/api/permits", json=permit_body(sector_id=999)).status_code == 400
    assert donneur.post("/api/permits", json=permit_body(donneur=12345)).status_code == 200  # nombre accepté, converti en texte
    # règles conditionnelles du permis papier
    assert donneur.post("/api/permits", json=permit_body(height_work=True)).status_code == 400
    assert donneur.post("/api/permits", json=permit_body(height_work=True, height_vigie="Paul", height_sauvetage="Plan A")).status_code == 200
    assert donneur.post("/api/permits", json=permit_body(hot_work=True)).status_code == 400
    assert donneur.post("/api/permits", json=permit_body(hot_work=True, hot_surv="Luc")).status_code == 200


def test_permit_requires_login(env):
    c = TestClient(env[0].app)
    assert c.get("/api/permits").status_code == 401
    assert c.post("/api/permits", json=permit_body()).status_code == 401


def test_update_records_changed_fields_and_blocks_closed_status(env, donneur):
    p = donneur.post("/api/permits", json=permit_body()).json()
    r = donneur.put(f"/api/permits/{p['id']}", json=permit_body(description="Nouvelle description"))
    assert r.status_code == 200 and r.json()["description"] == "Nouvelle description"
    history = donneur.get(f"/api/permits/{p['id']}").json()["history"]
    assert any("description" in (h["note"] or "") for h in history)
    # impossible de fermer par la modification : il faut passer par /close
    assert donneur.put(f"/api/permits/{p['id']}", json=permit_body(statut="Fermé")).status_code == 400
    # Actif -> Brouillon -> Actif est permis, avec historique
    assert donneur.put(f"/api/permits/{p['id']}", json=permit_body(statut="Brouillon", status_note="Retour")).status_code == 200
    assert donneur.get(f"/api/permits/{p['id']}").json()["statut"] == "Brouillon"


def test_close_permit_with_signatures_and_lock(env, donneur):
    p = donneur.post("/api/permits", json=permit_body()).json()
    url = f"/api/permits/{p['id']}/close"
    assert donneur.post(url, json={}).status_code == 400
    assert donneur.post(url, json={"signature_donneur": SIG, "signature_executant": ""}).status_code == 400
    # une chaîne quelconque (tentative d'injection) est refusée
    evil = 'x" onerror="alert(1)'
    assert donneur.post(url, json={"signature_donneur": evil, "signature_executant": SIG}).status_code == 400
    assert donneur.post(url, json={"signature_donneur": "data:image/png;base64,AAAA", "signature_executant": SIG}).status_code == 400
    assert donneur.post(url, json={"signature_donneur": "data:image/png;base64," + "A" * 500000, "signature_executant": SIG}).status_code == 400
    r = donneur.post(url, json={"signature_donneur": SIG, "signature_executant": SIG})
    assert r.status_code == 200 and r.json()["statut"] == "Fermé" and r.json()["ferme_le"]
    assert donneur.post(url, json={"signature_donneur": SIG, "signature_executant": SIG}).status_code == 409
    # permis fermé : verrouillé
    assert donneur.put(f"/api/permits/{p['id']}", json=permit_body(description="Modif tardive")).status_code == 409


def test_draft_cannot_be_closed(env, donneur):
    p = donneur.post("/api/permits", json=permit_body(statut="Brouillon")).json()
    r = donneur.post(f"/api/permits/{p['id']}/close", json={"signature_donneur": SIG, "signature_executant": SIG})
    assert r.status_code == 400


def test_archive_instead_of_delete(env, admin, donneur):
    p = donneur.post("/api/permits", json=permit_body()).json()
    assert donneur.delete(f"/api/permits/{p['id']}").status_code == 403
    assert admin.delete(f"/api/permits/{p['id']}").status_code == 200
    assert donneur.get("/api/permits").json()["total"] == 0
    assert donneur.get(f"/api/permits/{p['id']}").status_code == 404
    assert donneur.get("/api/permits", params={"archives": "true"}).status_code == 403
    archived = admin.get("/api/permits", params={"archives": "true"}).json()
    assert archived["total"] == 1
    detail = admin.get(f"/api/permits/{p['id']}").json()
    assert any(h["note"] == "Permis archivé" for h in detail["history"])
    assert admin.put(f"/api/permits/{p['id']}", json=permit_body()).status_code == 409
    # le numéro n'est jamais réutilisé
    assert donneur.post("/api/permits", json=permit_body()).json()["num"] == "00526"
    # et le permis archivé n'est plus consultable par un sous-traitant
    assert TestClient(env[0].app).get("/api/public/lookup", params={"num": p["num"], "entreprise": "Soudure Pro Inc."}).status_code == 404


def test_auto_close_expired_on_read_and_in_background(env, donneur):
    old = donneur.post("/api/permits", json=permit_body(date_debut="2020-01-01", date_fin="2020-01-02")).json()
    other = donneur.post("/api/permits", json=permit_body(date_debut="2020-01-01", date_fin="2020-01-02")).json()
    # 1) lecture directe
    assert donneur.get(f"/api/permits/{old['id']}").json()["statut"] == "Fermé"
    # 2) tâche de fond : ferme l'autre sans que personne ne le consulte
    assert env[0].close_all_expired() == 1
    with env[1].db() as conn:
        row = conn.execute("SELECT statut FROM permits WHERE id=?", (other["id"],)).fetchone()
    assert row["statut"] == "Fermé"
    assert env[0].close_all_expired() == 0


# ---------------------------------------------------------------- consultation publique
def test_public_lookup_generic_errors_and_content(env, donneur):
    p = donneur.post("/api/permits", json=permit_body()).json()
    pub = TestClient(env[0].app)
    ok = pub.get("/api/public/lookup", params={"num": p["num"], "entreprise": "  soudure   PRO inc. "})
    assert ok.status_code == 200
    body = ok.json()
    assert body["num"] == p["num"] and "signature_reception" not in body and "cree_par" not in body
    wrong_company = pub.get("/api/public/lookup", params={"num": p["num"], "entreprise": "Autre"})
    wrong_num = pub.get("/api/public/lookup", params={"num": "99999", "entreprise": "Soudure Pro Inc."})
    assert wrong_company.status_code == wrong_num.status_code == 404
    assert wrong_company.json()["detail"] == wrong_num.json()["detail"]  # n'indique pas si le numéro existe


def test_public_lookup_never_rate_limited_unlimited_retries(env, donneur):
    """Le sous-traitant sur le terrain doit pouvoir se tromper de nom
    d'entreprise autant de fois que nécessaire sans jamais être bloqué —
    contrairement à la connexion admin/donneur, qui reste limitée."""
    p = donneur.post("/api/permits", json=permit_body()).json()
    pub = TestClient(env[0].app)
    codes = [
        pub.get("/api/public/lookup", params={"num": p["num"], "entreprise": f"Essai {i}"}).status_code
        for i in range(30)
    ]
    assert 429 not in codes
    assert all(c == 404 for c in codes)


def test_public_lookup_by_number_only(env, donneur):
    p = donneur.post("/api/permits", json=permit_body()).json()
    pub = TestClient(env[0].app)
    r = pub.get("/api/public/lookup", params={"num": p["num"]})
    assert r.status_code == 200, r.text
    assert r.json()["entreprise"] == "Soudure Pro Inc."


def test_public_lookup_by_company_only_unique_match(env, donneur):
    p = donneur.post("/api/permits", json=permit_body(entreprise="Compagnie Unique Inc.")).json()
    pub = TestClient(env[0].app)
    r = pub.get("/api/public/lookup", params={"entreprise": "Compagnie Unique Inc."})
    assert r.status_code == 200, r.text
    assert r.json()["num"] == p["num"]


def test_public_lookup_by_company_only_ambiguous(env, donneur):
    donneur.post("/api/permits", json=permit_body(entreprise="Doublon Inc.", description="Premier"))
    donneur.post("/api/permits", json=permit_body(entreprise="Doublon Inc.", description="Second"))
    pub = TestClient(env[0].app)
    r = pub.get("/api/public/lookup", params={"entreprise": "Doublon Inc."})
    assert r.status_code == 409, r.text


def test_public_lookup_requires_at_least_one_field(env):
    pub = TestClient(env[0].app)
    assert pub.get("/api/public/lookup").status_code == 400


def test_public_sign_once_only_and_validated(env, donneur):
    p = donneur.post("/api/permits", json=permit_body()).json()
    pub = TestClient(env[0].app)
    payload = {"num": p["num"], "entreprise": "Soudure Pro Inc.", "nom": "Martin Gagné", "signature": SIG}
    assert pub.post("/api/public/sign", json={**payload, "signature": "n'importe quoi"}).status_code == 400
    assert pub.post("/api/public/sign", json={**payload, "signature": 'x" onerror="alert(1)'}).status_code == 400
    assert pub.post("/api/public/sign", json={**payload, "nom": ""}).status_code == 400
    assert pub.post("/api/public/sign", json={**payload, "entreprise": "Autre"}).status_code == 404
    assert pub.post("/api/public/sign", json=payload).status_code == 200
    # impossible d'écraser une signature existante
    assert pub.post("/api/public/sign", json={**payload, "nom": "Imposteur"}).status_code == 409
    assert pub.get("/api/public/lookup", params={"num": p["num"], "entreprise": "Soudure Pro Inc."}).json()["reception_nom"] == "Martin Gagné"


def test_public_sign_refused_on_draft_and_closed(env, donneur):
    draft = donneur.post("/api/permits", json=permit_body(statut="Brouillon")).json()
    closed = donneur.post("/api/permits", json=permit_body()).json()
    donneur.post(f"/api/permits/{closed['id']}/close", json={"signature_donneur": SIG, "signature_executant": SIG})
    pub = TestClient(env[0].app)
    for p in (draft, closed):
        r = pub.post("/api/public/sign", json={"num": p["num"], "entreprise": "Soudure Pro Inc.", "nom": "Martin", "signature": SIG})
        assert r.status_code == 400


# ---------------------------------------------------------------- fichiers
def _upload_photo(client, permit_id, name="photo.png", content=PNG_1PX):
    return client.post(f"/api/permits/{permit_id}/photos", files={"file": (name, content, "image/png")})


def test_photo_upload_validation(env, donneur):
    p = donneur.post("/api/permits", json=permit_body()).json()
    assert _upload_photo(donneur, p["id"]).status_code == 200
    assert _upload_photo(donneur, p["id"], "faux.png", b"<html><script>alert(1)</script></html>").status_code == 400
    assert _upload_photo(donneur, p["id"], "script.html", PNG_1PX).status_code == 400
    assert _upload_photo(donneur, 9999).status_code == 404
    big = PNG_1PX + b"0" * (15 * 1024 * 1024)
    assert _upload_photo(donneur, p["id"], "grosse.png", big).status_code == 400


def test_uploads_need_session_or_token(env, donneur):
    p = donneur.post("/api/permits", json=permit_body()).json()
    filename = _upload_photo(donneur, p["id"]).json()["filename"]
    anon = TestClient(env[0].app)
    assert anon.get(f"/uploads/{filename}").status_code == 401
    assert donneur.get(f"/uploads/{filename}").status_code == 200
    # jeton émis par la consultation publique
    photos = anon.get("/api/public/lookup", params={"num": p["num"], "entreprise": "Soudure Pro Inc."}).json()["photos"]
    assert len(photos) == 1 and "?t=" in photos[0]
    assert anon.get(photos[0]).status_code == 200
    # un jeton ne vaut que pour SON fichier
    other = _upload_photo(donneur, p["id"]).json()["filename"]
    token = photos[0].split("?t=")[1]
    assert anon.get(f"/uploads/{other}", params={"t": token}).status_code == 401
    assert anon.get(f"/uploads/{filename}", params={"t": "jeton-bidon"}).status_code == 401


def test_audit_files_never_public_and_no_traversal(env, admin, donneur):
    sector = donneur.post("/api/sectors", json={"name": "Entrepôt Nord"})
    assert sector.status_code == 200
    sector_id = donneur.get("/api/sectors").json()[0]["id"]
    r = donneur.post("/api/audits", data={"sector_id": str(sector_id), "titre": "Audit"}, files={"file": ("rapport.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 200
    stored = os.listdir(os.path.join(os.environ["DATA_DIR"], "uploads", "audits"))[0]
    anon = TestClient(env[0].app)
    assert anon.get(f"/uploads/audits/{stored}").status_code == 404
    assert anon.get(f"/api/audits/{r.json()['id']}/download").status_code == 401
    assert donneur.get(f"/api/audits/{r.json()['id']}/download").status_code == 200
    for evil in ("../permis.db", "..%2Fpermis.db", "%2e%2e/.secret_key", ".secret_key"):
        assert anon.get(f"/uploads/{evil}").status_code in (401, 404)
        assert donneur.get(f"/uploads/{evil}").status_code == 404


def test_sectors_and_qr(env, donneur, admin):
    assert donneur.post("/api/sectors", json={"name": ""}).status_code == 400
    assert donneur.post("/api/sectors", json={"name": "x" * 200}).status_code == 400
    assert donneur.post("/api/sectors", json={"name": "Zone A"}).json()["slug"] == "zone-a"
    assert donneur.post("/api/sectors", json={"name": "Zone A"}).status_code == 409
    qr = TestClient(env[0].app).get("/api/sectors/zone-a/qrcode.png")
    assert qr.status_code == 200 and qr.content.startswith(b"\x89PNG")
    assert TestClient(env[0].app).get("/secteur/zone-a").status_code == 200
    assert TestClient(env[0].app).get("/secteur/inconnu").status_code == 404
    sector_id = donneur.get("/api/sectors").json()[0]["id"]
    assert donneur.delete(f"/api/sectors/{sector_id}").status_code == 403
    assert admin.delete(f"/api/sectors/{sector_id}").status_code == 200


def test_pta_roundtrip_and_sanitizing(env, donneur):
    pta = {"ppe": ["Casque de sécurité"], "loto": "Oui", "loto_panneau": "P-12", "bad": {"x": 1}, "flag": True}
    p = donneur.post("/api/permits", json=permit_body(pta=pta)).json()
    assert p["pta"] == {"ppe": ["Casque de sécurité"], "loto": "Oui", "loto_panneau": "P-12"}
    got = donneur.get(f"/api/permits/{p['id']}").json()
    assert got["pta"]["loto"] == "Oui"
    r = donneur.put(f"/api/permits/{p['id']}", json=permit_body(pta={"loto": "Non"}))
    assert r.status_code == 200 and r.json()["pta"] == {"loto": "Non"}
    assert donneur.post("/api/permits", json=permit_body()).json()["pta"] == {}
