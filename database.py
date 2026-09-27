"""
Couche base de données — SQLite.
Un seul fichier permis.db ; toutes les tables créées au démarrage si absentes.
"""
import sqlite3
import json
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "permis.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','donneur')),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS permits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                permit_id INTEGER NOT NULL REFERENCES permits(id) ON DELETE CASCADE,
                statut TEXT NOT NULL,
                par TEXT,
                horodatage TEXT NOT NULL DEFAULT (datetime('now')),
                note TEXT
            );

            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                permit_id INTEGER NOT NULL REFERENCES permits(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                uploaded_by TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_permits_num ON permits(num);
            CREATE INDEX IF NOT EXISTS idx_permits_sector ON permits(sector_id);
            CREATE INDEX IF NOT EXISTS idx_permits_statut ON permits(statut);
            """
        )
        # Migration : ajoute la colonne "zone" (secteur du site, liste déroulante)
        # si elle n'existe pas déjà sur une base créée avant son introduction.
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(permits)")}
        if "zone" not in existing_cols:
            conn.execute("ALTER TABLE permits ADD COLUMN zone TEXT")

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
    return d
