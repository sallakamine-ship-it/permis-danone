"""
Couche base de données — PostgreSQL (migré depuis SQLite le 29 sept. 2026,
pour ne plus perdre les données à chaque redémarrage/redéploiement du service
gratuit Render, qui n'a pas de disque persistant).

Connexion via la variable d'environnement DATABASE_URL (chaîne fournie par
l'hébergeur Postgres, ex. Neon : postgresql://user:pass@host/db?sslmode=require).

Pour éviter de réécrire les ~60 requêtes de app.py une par une, une petite
couche de compatibilité (_ConnWrapper / _CursorWrapper ci-dessous) traduit à
la volée le style SQLite utilisé dans tout le reste du code :
  - placeholders "?"  -> "%s" (style psycopg2)
  - datetime('now')   -> équivalent Postgres, MÊME format de sortie texte
                          ("YYYY-MM-DD HH:MM:SS") pour ne rien changer côté
                          app.js (parsing des dates) ou aux comparaisons de
                          dates en texte (filtre "cette semaine")
  - cur.lastrowid     -> ajoute "RETURNING id" aux INSERT et le récupère
Les lignes vraiment spécifiques à Postgres (verrou explicite, requêtes de
migration de colonnes) restent isolées dans app.py / init_db() ci-dessous,
avec un commentaire, plutôt que cachées dans la couche de compatibilité.
"""
import json
import os
import re
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL n'est pas défini. Configurez la variable d'environnement "
        "avec la chaîne de connexion Postgres (ex. celle fournie par Neon)."
    )

_QMARK_RE = re.compile(r"\?")
# Reproduit exactement le format texte que produisait SQLite pour
# datetime('now') : "2026-09-29 22:39:00" (espace, sans fuseau, sans
# microsecondes) — les colonnes restent TEXT, aucun changement de format
# ne doit se propager à app.js ni aux comparaisons de dates en texte.
_NOW_SQL = "to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')"


def _translate(sql: str) -> str:
    sql = sql.replace("datetime('now')", _NOW_SQL)
    return _QMARK_RE.sub("%s", sql)


class _CursorWrapper:
    """Imite l'API d'un curseur sqlite3 (execute/fetchone/fetchall/lastrowid/
    rowcount) au-dessus d'un vrai curseur psycopg2."""

    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None

    def execute(self, sql, params=()):
        pg_sql = _translate(sql)
        if pg_sql.lstrip()[:6].upper() == "INSERT" and "RETURNING" not in pg_sql.upper():
            pg_sql = pg_sql.rstrip().rstrip(";") + " RETURNING id"
            self._cursor.execute(pg_sql, params)
            row = self._cursor.fetchone()
            self.lastrowid = row["id"] if row else None
        else:
            self._cursor.execute(pg_sql, params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount


class _ConnWrapper:
    """Imite l'API d'une connexion sqlite3 : .execute() crée un curseur à la
    volée (comme le fait la méthode de confort sqlite3.Connection.execute)."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = _CursorWrapper(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))
        return cur.execute(sql, params)

    def executescript(self, script):
        # Uniquement du DDL (init_db, sans paramètres) : Postgres accepte
        # plusieurs instructions séparées par ";" dans un seul execute().
        self._conn.cursor().execute(_translate(script))

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_conn():
    raw = psycopg2.connect(DATABASE_URL)
    return _ConnWrapper(raw)


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _existing_columns(conn, table_name: str) -> set:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        (table_name,),
    ).fetchall()
    return {r["column_name"] for r in rows}


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','donneur')),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sectors (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS permits (
                id SERIAL PRIMARY KEY,
                num TEXT UNIQUE NOT NULL,
                sector_id INTEGER REFERENCES sectors(id),
                donneur TEXT NOT NULL,
                donneur_tel TEXT,
                entreprise TEXT,
                executant TEXT NOT NULL,
                executant_tel TEXT,
                description TEXT NOT NULL,
                lieux TEXT NOT NULL,
                zone TEXT,
                date_debut TEXT,
                date_fin TEXT,
                risques_a TEXT DEFAULT '[]',
                risques_b TEXT DEFAULT '[]',
                risques_c TEXT DEFAULT '[]',
                zone_conforme TEXT,
                zone_comm TEXT,
                height_work INTEGER DEFAULT 0,
                risques_hauteur TEXT DEFAULT '[]',
                height_acces TEXT,
                height_m TEXT,
                height_sauvetage TEXT,
                height_vigie TEXT,
                bonbonne_work INTEGER DEFAULT 0,
                risques_bonbonne TEXT DEFAULT '[]',
                bonbonne_type TEXT,
                bonbonne_nombre TEXT,
                bonbonne_levage TEXT,
                roof_work INTEGER DEFAULT 0,
                risques_toit TEXT DEFAULT '[]',
                roof_type TEXT,
                roof_resistance TEXT,
                roof_perimetre TEXT,
                roof_vigie TEXT,
                hot_work INTEGER DEFAULT 0,
                risques_hot TEXT DEFAULT '[]',
                hot_nature TEXT,
                hot_debut TEXT,
                hot_fin TEXT,
                hot_surv TEXT,
                hot_ext TEXT,
                statut TEXT NOT NULL DEFAULT 'Actif',
                cree_par TEXT,
                signature_donneur TEXT,
                signature_executant TEXT,
                ferme_le TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS status_history (
                id SERIAL PRIMARY KEY,
                permit_id INTEGER NOT NULL REFERENCES permits(id) ON DELETE CASCADE,
                statut TEXT NOT NULL,
                par TEXT,
                horodatage TEXT NOT NULL DEFAULT (datetime('now')),
                note TEXT
            );

            CREATE TABLE IF NOT EXISTS photos (
                id SERIAL PRIMARY KEY,
                permit_id INTEGER NOT NULL REFERENCES permits(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                uploaded_by TEXT
            );

            CREATE TABLE IF NOT EXISTS audits (
                id SERIAL PRIMARY KEY,
                sector_id INTEGER NOT NULL REFERENCES sectors(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                original_name TEXT,
                titre TEXT,
                date_audit TEXT,
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                uploaded_by TEXT
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                permit_id INTEGER NOT NULL REFERENCES permits(id) ON DELETE CASCADE,
                permit_num TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_permits_num ON permits(num);
            CREATE INDEX IF NOT EXISTS idx_permits_sector ON permits(sector_id);
            CREATE INDEX IF NOT EXISTS idx_permits_statut ON permits(statut);
            CREATE INDEX IF NOT EXISTS idx_audits_sector ON audits(sector_id);
            CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
            """
        )
        # Migration : ajoute la colonne "zone" (secteur du site, liste déroulante)
        # si elle n'existe pas déjà sur une base créée avant son introduction.
        existing_cols = _existing_columns(conn, "permits")
        if "zone" not in existing_cols:
            conn.execute("ALTER TABLE permits ADD COLUMN zone TEXT")

        # Migration : contenu du Permis mondial Danone (PTA), stocké en JSON.
        if "pta" not in existing_cols:
            conn.execute("ALTER TABLE permits ADD COLUMN pta TEXT")

        # Migration : signature de réception — le sous-traitant consulte son
        # permis (recherche publique par numéro + entreprise) puis le signe
        # électroniquement sur place, avant de commencer le travail. Distinct
        # de signature_donneur/signature_executant (fermeture officielle du
        # permis en fin de travaux, deux signatures).
        if "signature_reception" not in existing_cols:
            conn.execute("ALTER TABLE permits ADD COLUMN signature_reception TEXT")
        if "reception_nom" not in existing_cols:
            conn.execute("ALTER TABLE permits ADD COLUMN reception_nom TEXT")
        if "reception_le" not in existing_cols:
            conn.execute("ALTER TABLE permits ADD COLUMN reception_le TEXT")

        # Migration : archivage. Un permis n'est plus jamais supprimé (c'est un
        # document légal) : il est archivé, retiré du registre courant mais
        # conservé avec son historique et ses signatures.
        if "archive_le" not in existing_cols:
            conn.execute("ALTER TABLE permits ADD COLUMN archive_le TEXT")
        if "archive_par" not in existing_cols:
            conn.execute("ALTER TABLE permits ADD COLUMN archive_par TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_permits_archive ON permits(archive_le)")

        # Migration : notifications — quand l'exécutant signe la réception sur
        # place (voir signature_reception ci-dessus), une notification est
        # créée pour que le donneur d'ordre (et le reste de l'équipe SST) la
        # voie au prochain login. last_notif_seen_id suit, par utilisateur,
        # jusqu'où il a déjà consulté le fil de notifications.
        existing_user_cols = _existing_columns(conn, "users")
        if "last_notif_seen_id" not in existing_user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN last_notif_seen_id INTEGER NOT NULL DEFAULT 0")


def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    for k in list(d.keys()):
        if k.startswith("risques_"):
            try:
                d[k] = json.loads(d[k]) if d[k] else []
            except (TypeError, json.JSONDecodeError):
                d[k] = []
    if "pta" in d:
        try:
            d["pta"] = json.loads(d["pta"]) if d["pta"] else {}
        except (TypeError, json.JSONDecodeError):
            d["pta"] = {}
    return d
