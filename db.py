from __future__ import annotations

import sqlite3
import os
import re
from uuid import uuid4
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
from local_paths import DATA_ROOT

DB_PATH = DATA_ROOT / "livraria.db"
COMPANY_ROLES = ("administrator", "collaborator")
EDIT_ROLES = ("administrator",)
COMPANY_SEGMENTS = ("Livraria", "Padaria", "Bar", "Restaurante", "Comércio", "Serviços", "Outro")
DATABASE_URL = os.environ.get("SKOPOS_DATABASE_URL", "")


def configure_database(url: str | None = None) -> None:
    global DATABASE_URL
    DATABASE_URL = url or os.environ.get("SKOPOS_DATABASE_URL", "")
    if DATABASE_URL and not DATABASE_URL.startswith(("postgresql://", "postgres://")):
        raise ValueError("O banco externo deve usar uma URL PostgreSQL.")


def database_backend() -> str:
    return "PostgreSQL" if DATABASE_URL else "SQLite local"


@contextmanager
def connection():
    if DATABASE_URL:
        from postgres_backend import Connection
        conn = Connection(DATABASE_URL)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if getattr(conn, "is_postgres", False):
        return {row[0] for row in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?", (table,))}
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_membership_roles(conn: sqlite3.Connection) -> None:
    if getattr(conn, "is_postgres", False):
        return
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='company_memberships'").fetchone()
    if not row or "'owner'" not in (row[0] or ""):
        return
    conn.execute("""CREATE TABLE company_memberships_new (
        company_id INTEGER NOT NULL,
        issuer TEXT NOT NULL,
        subject TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'collaborator'
            CHECK(role IN ('administrator','manager','collaborator')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(company_id, issuer, subject)
    )""")
    conn.execute("""INSERT INTO company_memberships_new(company_id, issuer, subject, role, created_at)
        SELECT company_id, issuer, subject,
        CASE role WHEN 'owner' THEN 'administrator' WHEN 'admin' THEN 'administrator'
            WHEN 'member' THEN 'collaborator' ELSE role END,
        created_at FROM company_memberships""")
    conn.execute("DROP TABLE company_memberships")
    conn.execute("ALTER TABLE company_memberships_new RENAME TO company_memberships")


def _require_role(conn: sqlite3.Connection, company_id: int, issuer: str, subject: str, allowed: tuple[str, ...]) -> None:
    # Serialize permission changes with other writes and voluntary departures.
    if getattr(conn, "is_postgres", False):
        company = conn.execute("SELECT is_demo FROM companies WHERE id=? FOR UPDATE", (company_id,)).fetchone()
    else:
        conn.execute("UPDATE companies SET id=id WHERE id=?", (company_id,))
        company = conn.execute("SELECT is_demo FROM companies WHERE id=?", (company_id,)).fetchone()
    if not company:
        raise PermissionError("A empresa não está disponível ou foi excluída.")
    if company[0]:
        raise PermissionError("O ambiente de demonstração permite somente consulta.")
    row = conn.execute(
        "SELECT role FROM company_memberships WHERE company_id=? AND issuer=? AND subject=?",
        (company_id, issuer, subject),
    ).fetchone()
    if not row or row[0] not in allowed:
        raise PermissionError("Seu perfil não tem permissão para realizar esta ação nesta empresa.")


def _add_company_column(conn: sqlite3.Connection, table: str) -> None:
    if "company_id" not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN company_id INTEGER")


def _rebuild_tenant_table(conn: sqlite3.Connection, table: str, create_sql: str, columns: str) -> None:
    """Replace global unique keys with company-scoped unique keys, preserving rows."""
    if getattr(conn, "is_postgres", False):
        return
    if "company_id" not in _columns(conn, table):
        _add_company_column(conn, table)
    has_global_unique = False
    for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if not index[2]:
            continue
        indexed_columns = {column[2] for column in conn.execute(f"PRAGMA index_info({index[1]})")}
        if "company_id" not in indexed_columns and indexed_columns != {"id"}:
            has_global_unique = True
            break
    # Rebuild only when legacy table-level unique constraints are still present.
    if not has_global_unique:
        return
    old_name = f"{table}_legacy_company_migration"
    conn.execute(f"DROP TABLE IF EXISTS {old_name}")
    conn.execute(f"ALTER TABLE {table} RENAME TO {old_name}")
    conn.execute(create_sql)
    conn.execute(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM {old_name}")
    conn.execute(f"DROP TABLE {old_name}")


def init_db() -> None:
    with connection() as conn:
        if not getattr(conn, "is_postgres", False) and _columns(conn, "companies") and "segment" not in _columns(conn, "companies"):
            backup_dir = DB_PATH.parent / "backup_account_upgrade"
            backup_dir.mkdir(exist_ok=True)
            backup_path = backup_dir / f"livraria_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
            target = sqlite3.connect(backup_path)
            try:
                conn.backup(target)
            finally:
                target.close()
        if getattr(conn, "is_postgres", False):
            conn.execute("SELECT pg_advisory_xact_lock(736567001)")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS company_memberships (
                company_id INTEGER NOT NULL,
                issuer TEXT NOT NULL,
                subject TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'collaborator' CHECK(role IN ('administrator','manager','collaborator')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(company_id, issuer, subject)
            );
            CREATE TABLE IF NOT EXISTS company_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('administrator','manager','collaborator')),
                invited_by_issuer TEXT NOT NULL,
                invited_by_subject TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_id, email)
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER,
                date TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('Receita','Despesa')),
                category TEXT NOT NULL, description TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0), payment_method TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pago' CHECK(status IN ('Pago','Pendente')),
                due_date TEXT, notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER,
                month TEXT NOT NULL, category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0), UNIQUE(company_id, month, category)
            );
            CREATE TABLE IF NOT EXISTS sales_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER,
                order_id TEXT NOT NULL, sale_date TEXT NOT NULL,
                customer TEXT NOT NULL DEFAULT '', customer_id TEXT NOT NULL DEFAULT '',
                channel TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
                sku TEXT NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL CHECK(quantity >= 0), returned_quantity REAL NOT NULL DEFAULT 0 CHECK(returned_quantity >= 0),
                unit_price REAL NOT NULL CHECK(unit_price >= 0), unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost >= 0),
                discount REAL NOT NULL DEFAULT 0 CHECK(discount >= 0), taxes REAL NOT NULL DEFAULT 0 CHECK(taxes >= 0),
                shipping_charged REAL NOT NULL DEFAULT 0 CHECK(shipping_charged >= 0), shipping_cost REAL NOT NULL DEFAULT 0 CHECK(shipping_cost >= 0),
                status TEXT NOT NULL DEFAULT 'Concluído', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_id, order_id, sku), CHECK(returned_quantity <= quantity)
            );
            CREATE TABLE IF NOT EXISTS inventory_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER,
                snapshot_date TEXT NOT NULL, sku TEXT NOT NULL, title TEXT NOT NULL,
                quantity REAL NOT NULL CHECK(quantity >= 0), unit_cost REAL NOT NULL CHECK(unit_cost >= 0),
                minimum_quantity REAL NOT NULL DEFAULT 0 CHECK(minimum_quantity >= 0),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(company_id, snapshot_date, sku)
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                company_id INTEGER, setting_key TEXT NOT NULL, setting_value TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(company_id, setting_key)
            );
            CREATE TABLE IF NOT EXISTS users (
                issuer TEXT NOT NULL, subject TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
                email_verified INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (issuer, subject)
            );
            """
        )
        _migrate_membership_roles(conn)
        # Keep existing administrators as owners; legacy managers become read-only.
        for table in ("company_memberships", "company_invitations"):
            conn.execute(f"UPDATE {table} SET role='collaborator' WHERE role='manager'")
        for column, definition in {
            "segment": "TEXT NOT NULL DEFAULT 'Livraria'",
            "contact_email": "TEXT NOT NULL DEFAULT ''",
            "city": "TEXT NOT NULL DEFAULT ''",
            "is_demo": "INTEGER NOT NULL DEFAULT 0",
            "demo_key": "TEXT",
        }.items():
            if column not in _columns(conn, "companies"):
                conn.execute(f"ALTER TABLE companies ADD COLUMN {column} {definition}")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_demo_key ON companies(demo_key)")
        for column, definition in {
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "expires_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in _columns(conn, "company_invitations"):
                conn.execute(f"ALTER TABLE company_invitations ADD COLUMN {column} {definition}")
        conn.execute("""CREATE TABLE IF NOT EXISTS user_settings (
            issuer TEXT NOT NULL, subject TEXT NOT NULL, setting_key TEXT NOT NULL,
            setting_value TEXT NOT NULL DEFAULT '', PRIMARY KEY(issuer,subject,setting_key))""")
        if "email_verified" not in _columns(conn, "users"):
            conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        _add_company_column(conn, "transactions")
        # Older installs need table rebuilds because their uniqueness constraints were global.
        _rebuild_tenant_table(conn, "budgets", """CREATE TABLE budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, month TEXT NOT NULL, category TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0), UNIQUE(company_id, month, category))""",
            "id, company_id, month, category, amount")
        _rebuild_tenant_table(conn, "sales_lines", """CREATE TABLE sales_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, order_id TEXT NOT NULL, sale_date TEXT NOT NULL,
            customer TEXT NOT NULL DEFAULT '', customer_id TEXT NOT NULL DEFAULT '', channel TEXT NOT NULL DEFAULT '',
            city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '', sku TEXT NOT NULL, title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '', quantity REAL NOT NULL CHECK(quantity >= 0),
            returned_quantity REAL NOT NULL DEFAULT 0 CHECK(returned_quantity >= 0), unit_price REAL NOT NULL CHECK(unit_price >= 0),
            unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost >= 0), discount REAL NOT NULL DEFAULT 0 CHECK(discount >= 0),
            taxes REAL NOT NULL DEFAULT 0 CHECK(taxes >= 0), shipping_charged REAL NOT NULL DEFAULT 0 CHECK(shipping_charged >= 0),
            shipping_cost REAL NOT NULL DEFAULT 0 CHECK(shipping_cost >= 0), status TEXT NOT NULL DEFAULT 'Concluído',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(company_id, order_id, sku),
            CHECK(returned_quantity <= quantity))""",
            "id, company_id, order_id, sale_date, customer, customer_id, channel, city, state, sku, title, category, quantity, returned_quantity, unit_price, unit_cost, discount, taxes, shipping_charged, shipping_cost, status, updated_at")
        _rebuild_tenant_table(conn, "inventory_snapshots", """CREATE TABLE inventory_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, snapshot_date TEXT NOT NULL, sku TEXT NOT NULL,
            title TEXT NOT NULL, quantity REAL NOT NULL CHECK(quantity >= 0), unit_cost REAL NOT NULL CHECK(unit_cost >= 0),
            minimum_quantity REAL NOT NULL DEFAULT 0 CHECK(minimum_quantity >= 0), updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_id, snapshot_date, sku))""",
            "id, company_id, snapshot_date, sku, title, quantity, unit_cost, minimum_quantity, updated_at")
        if "company_id" not in _columns(conn, "app_settings"):
            conn.execute("ALTER TABLE app_settings RENAME TO app_settings_legacy")
            conn.execute("CREATE TABLE app_settings (company_id INTEGER, setting_key TEXT NOT NULL, setting_value TEXT NOT NULL DEFAULT '', PRIMARY KEY(company_id, setting_key))")
            conn.execute("INSERT INTO app_settings(company_id, setting_key, setting_value) SELECT NULL, setting_key, setting_value FROM app_settings_legacy")
            conn.execute("DROP TABLE app_settings_legacy")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_lines_date ON sales_lines(sale_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_lines_sku ON sales_lines(sku)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_snapshot_date ON inventory_snapshots(snapshot_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_company_date ON transactions(company_id, date)")
        conn.execute("""CREATE TABLE IF NOT EXISTS import_batches (
            id TEXT PRIMARY KEY, company_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('sales','inventory')), source TEXT NOT NULL,
            row_count INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        for table, kind in (("sales_lines", "sales"), ("inventory_snapshots", "inventory")):
            if "import_id" not in _columns(conn, table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN import_id TEXT")
            # Historical rows are preserved, with an explicit legacy batch per company.
            for row in conn.execute(f"SELECT company_id, COUNT(*) AS n FROM {table} WHERE import_id IS NULL AND company_id IS NOT NULL GROUP BY company_id").fetchall():
                batch = _create_import_batch(conn, row["company_id"], kind, "Dados anteriores ao histórico", row["n"])
                conn.execute(f"UPDATE {table} SET import_id=? WHERE company_id=? AND import_id IS NULL", (batch, row["company_id"]))
        if "is_demo" not in _columns(conn, "transactions"):
            conn.execute("ALTER TABLE transactions ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
        from autonomy import init_schema
        init_schema(conn)
        from company_lifecycle import init_schema as init_company_lifecycle
        init_company_lifecycle(conn)
        from local_identity import init_schema as init_identity
        init_identity(conn)


def register_identity(issuer: str, subject: str, email: str = "", name: str = "", email_verified: bool = False) -> None:
    with connection() as conn:
        conn.execute("""INSERT INTO users (issuer, subject, email, name, email_verified) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(issuer, subject) DO UPDATE SET email=excluded.email, name=excluded.name,
            email_verified=excluded.email_verified, last_seen_at=CURRENT_TIMESTAMP""",
            (issuer, subject, email.strip().casefold(), name, int(email_verified)))


def companies_for_user(issuer: str, subject: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute("""SELECT c.id, c.name, c.segment, c.contact_email, c.city, c.is_demo,
            CASE m.role WHEN 'manager' THEN 'collaborator' ELSE m.role END AS role FROM companies c
            JOIN company_memberships m ON m.company_id=c.id WHERE m.issuer=? AND m.subject=? AND c.is_demo=0 ORDER BY c.id""",
            (issuer, subject)).fetchall()
    return [dict(row) for row in rows]


def _invitation_is_current(invitation: dict) -> bool:
    if invitation["status"] != "pending":
        return False
    expiry = invitation["expires_at"]
    if not expiry:
        expiry = (datetime.fromisoformat(str(invitation["created_at"])) + timedelta(days=7)).isoformat()
    deadline = datetime.fromisoformat(expiry)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline > datetime.now(timezone.utc)


def invitations_for_user(issuer: str, subject: str) -> list[dict]:
    with connection() as conn:
        user = conn.execute("SELECT email,email_verified FROM users WHERE issuer=? AND subject=?", (issuer, subject)).fetchone()
        if not user or not user["email_verified"]:
            return []
        rows = conn.execute("""SELECT i.*,c.name,c.segment FROM company_invitations i
            JOIN companies c ON c.id=i.company_id
            WHERE i.email=? AND i.status='pending' AND c.is_demo=0 ORDER BY i.created_at DESC""", (user["email"],)).fetchall()
    return [dict(row) for row in rows if _invitation_is_current(dict(row))]


def respond_company_invitation(invitation_id: int, issuer: str, subject: str, accept: bool) -> int:
    with connection() as conn:
        if not getattr(conn, "is_postgres", False):
            conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT email,email_verified FROM users WHERE issuer=? AND subject=?", (issuer, subject)).fetchone()
        initial = conn.execute("SELECT company_id FROM company_invitations WHERE id=?", (invitation_id,)).fetchone()
        if initial and getattr(conn, "is_postgres", False):
            # Keep the same company-first lock order as team edits/deletion.
            conn.execute("SELECT id FROM companies WHERE id=? FOR UPDATE", (initial[0],)).fetchone()
        lock = " FOR UPDATE" if getattr(conn, "is_postgres", False) else ""
        invitation = conn.execute("SELECT * FROM company_invitations WHERE id=?" + lock, (invitation_id,)).fetchone()
        if not user or not user["email_verified"] or not invitation or invitation["email"] != user["email"]:
            raise PermissionError("Este convite pertence a outra conta ou o e-mail não foi verificado.")
        if not _invitation_is_current(dict(invitation)):
            raise ValueError("Este convite expirou ou já foi respondido. Solicite um novo convite ao proprietário.")
        if accept:
            company = conn.execute("SELECT is_demo FROM companies WHERE id=?", (invitation["company_id"],)).fetchone()
            if not company or company[0]:
                raise ValueError("A empresa deste convite não está disponível.")
            conn.execute("INSERT OR IGNORE INTO company_memberships(company_id,issuer,subject,role) VALUES (?,?,?,?)",
                         (invitation["company_id"], issuer, subject, invitation["role"]))
        conn.execute("UPDATE company_invitations SET status=? WHERE id=?", ("accepted" if accept else "declined", invitation_id))
        return int(invitation["company_id"])


def has_pending_company_invitation(email: str) -> bool:
    clean_email = email.strip().casefold()
    if not clean_email:
        return False
    with connection() as conn:
        return conn.execute(
            "SELECT 1 FROM company_invitations WHERE email=? AND status='pending' LIMIT 1", (clean_email,)
        ).fetchone() is not None


def company_members(company_id: int) -> list[dict]:
    with connection() as conn:
        rows = conn.execute("""SELECT m.issuer, m.subject, m.role,
                COALESCE(NULLIF(u.name, ''), NULLIF(u.email, ''), 'Conta Google') AS name,
                COALESCE(u.email, '') AS email
            FROM company_memberships m LEFT JOIN users u ON u.issuer=m.issuer AND u.subject=m.subject
            WHERE m.company_id=? ORDER BY CASE m.role WHEN 'administrator' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END, name""",
            (company_id,)).fetchall()
    return [dict(row) for row in rows]


def pending_company_invitations(company_id: int) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, email, role, created_at, status, expires_at FROM company_invitations WHERE company_id=? AND status='pending' ORDER BY created_at DESC",
            (company_id,),
        ).fetchall()
    return [dict(row) for row in rows if _invitation_is_current(dict(row))]


def invite_company_member(company_id: int, email: str, role: str, issuer: str, subject: str) -> str:
    return invite_company_members(company_id, [(email, role)], issuer, subject)[0][2]


def invite_company_members(company_id: int, invitations: list[tuple[str, str]], issuer: str,
                           subject: str) -> list[tuple[str, str, str]]:
    """Validate the entire batch before registering any invitation, in one transaction."""
    if not invitations:
        raise ValueError("Informe pelo menos um e-mail para adicionar à empresa.")
    recipients = []
    seen = set()
    for email, role in invitations:
        clean_email = email.strip().casefold()
        if role not in COMPANY_ROLES:
            raise ValueError("Selecione um perfil válido.")
        if len(clean_email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", clean_email):
            raise ValueError(f"Confira o e-mail da pessoa {len(recipients) + 1}: {email or '(vazio)'}.")
        if clean_email in seen:
            raise ValueError(f"O e-mail {clean_email} está repetido. Mantenha apenas uma linha para essa pessoa.")
        recipients.append((clean_email, role))
        seen.add(clean_email)
    results = []
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
        for clean_email, role in recipients:
            result = _register_company_invitation(conn, company_id, clean_email, role, issuer, subject)
            results.append((clean_email, role, result))
    return results


def _register_company_invitation(conn, company_id: int, clean_email: str, role: str,
                                 issuer: str, subject: str) -> str:
    existing_user = conn.execute(
        "SELECT issuer, subject FROM users WHERE lower(email)=? AND email_verified=1 ORDER BY created_at LIMIT 1",
        (clean_email,),
    ).fetchone()
    if existing_user:
        membership = conn.execute(
            "SELECT 1 FROM company_memberships WHERE company_id=? AND issuer=? AND subject=?",
            (company_id, existing_user["issuer"], existing_user["subject"]),
        ).fetchone()
        if membership:
            return "already_member"
    conn.execute("""INSERT INTO company_invitations
            (company_id, email, role, invited_by_issuer, invited_by_subject, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id, email) DO UPDATE SET role=excluded.role,
            invited_by_issuer=excluded.invited_by_issuer, invited_by_subject=excluded.invited_by_subject,
            created_at=CURRENT_TIMESTAMP, status='pending', expires_at=excluded.expires_at""",
        (company_id, clean_email, role, issuer, subject,
         (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()))
    return "invited"


def update_company_member_role(
    company_id: int,
    target_issuer: str,
    target_subject: str,
    role: str,
    issuer: str,
    subject: str,
) -> None:
    if role not in COMPANY_ROLES:
        raise ValueError("Selecione um perfil válido.")
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
        target = conn.execute(
            "SELECT role FROM company_memberships WHERE company_id=? AND issuer=? AND subject=?",
            (company_id, target_issuer, target_subject),
        ).fetchone()
        if not target:
            raise ValueError("A pessoa não pertence mais a esta empresa.")
        if target["role"] == "administrator" and role != "administrator":
            admins = conn.execute(
                "SELECT COUNT(*) FROM company_memberships WHERE company_id=? AND role='administrator'",
                (company_id,),
            ).fetchone()[0]
            if admins <= 1:
                raise ValueError("A empresa precisa manter pelo menos um proprietário.")
        conn.execute(
            "UPDATE company_memberships SET role=? WHERE company_id=? AND issuer=? AND subject=?",
            (role, company_id, target_issuer, target_subject),
        )


def remove_company_member(
    company_id: int, target_issuer: str, target_subject: str, issuer: str, subject: str
) -> None:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
        target = conn.execute(
            "SELECT role FROM company_memberships WHERE company_id=? AND issuer=? AND subject=?",
            (company_id, target_issuer, target_subject),
        ).fetchone()
        if not target:
            return
        if target["role"] == "administrator":
            admins = conn.execute(
                "SELECT COUNT(*) FROM company_memberships WHERE company_id=? AND role='administrator'",
                (company_id,),
            ).fetchone()[0]
            if admins <= 1:
                raise ValueError("A empresa precisa manter pelo menos um proprietário.")
        conn.execute(
            "DELETE FROM company_memberships WHERE company_id=? AND issuer=? AND subject=?",
            (company_id, target_issuer, target_subject),
        )


def delete_company_invitation(company_id: int, invitation_id: int, issuer: str, subject: str) -> None:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
        conn.execute("DELETE FROM company_invitations WHERE id=? AND company_id=?", (invitation_id, company_id))


def create_company(name: str, issuer: str, subject: str, segment: str = "Livraria", contact_email: str = "", city: str = "") -> int:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Informe o nome da empresa.")
    if segment not in COMPANY_SEGMENTS:
        raise ValueError("Selecione um tipo de empresa válido.")
    with connection() as conn:
        if getattr(conn, "is_postgres", False):
            conn.execute("SELECT pg_advisory_xact_lock(736567003)")
        cursor = conn.execute("INSERT INTO companies(name,segment,contact_email,city) VALUES (?,?,?,?)", (clean_name, segment, contact_email.strip(), city.strip()))
        company_id = int(cursor.lastrowid)
        conn.execute("INSERT INTO company_memberships(company_id, issuer, subject, role) VALUES (?, ?, ?, 'administrator')", (company_id, issuer, subject))
        # The first company claims pre-existing local data once; later companies always start empty.
        if conn.execute("SELECT COUNT(*) FROM companies WHERE is_demo=0").fetchone()[0] == 1:
            for table in ("transactions", "budgets", "sales_lines", "inventory_snapshots", "app_settings"):
                conn.execute(f"UPDATE {table} SET company_id=? WHERE company_id IS NULL", (company_id,))
        return company_id


def update_company(company_id: int, name: str, issuer: str, subject: str, segment: str = "Livraria", contact_email: str = "", city: str = "") -> bool:
    clean_name = name.strip()
    if not clean_name:
        return False
    if segment not in COMPANY_SEGMENTS:
        raise ValueError("Selecione um tipo de empresa válido.")
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
        cursor = conn.execute("""UPDATE companies SET name=?,segment=?,contact_email=?,city=? WHERE id=? AND EXISTS (
            SELECT 1 FROM company_memberships WHERE company_id=? AND issuer=? AND subject=? AND role='administrator')""",
            (clean_name, segment, contact_email.strip(), city.strip(), company_id, company_id, issuer, subject))
        return cursor.rowcount == 1


def leave_company(company_id: int, issuer: str, subject: str) -> None:
    with connection() as conn:
        if not getattr(conn, "is_postgres", False):
            conn.execute("BEGIN IMMEDIATE")
        else:
            conn.execute("SELECT id FROM companies WHERE id=? FOR UPDATE", (company_id,))
        member = conn.execute("SELECT role FROM company_memberships WHERE company_id=? AND issuer=? AND subject=?", (company_id, issuer, subject)).fetchone()
        if not member:
            raise PermissionError("Você não participa desta empresa.")
        if member[0] == "administrator" and conn.execute("SELECT COUNT(*) FROM company_memberships WHERE company_id=? AND role='administrator'", (company_id,)).fetchone()[0] <= 1:
            raise ValueError("Defina outro proprietário antes de sair da empresa.")
        conn.execute("DELETE FROM company_memberships WHERE company_id=? AND issuer=? AND subject=?", (company_id, issuer, subject))


def get_user_setting(key: str, issuer: str, subject: str, default: str = "") -> str:
    with connection() as conn:
        row = conn.execute("SELECT setting_value FROM user_settings WHERE issuer=? AND subject=? AND setting_key=?", (issuer, subject, key)).fetchone()
        return row[0] if row else default


def set_user_settings(settings: dict[str, str], issuer: str, subject: str) -> None:
    with connection() as conn:
        conn.executemany("""INSERT INTO user_settings(issuer,subject,setting_key,setting_value) VALUES (?,?,?,?)
            ON CONFLICT(issuer,subject,setting_key) DO UPDATE SET setting_value=excluded.setting_value""",
            [(issuer, subject, key, str(value)) for key, value in settings.items()])


def demo_company() -> dict:
    """Create an isolated, read-only sample, never claiming unassigned real data."""
    month = date.today().strftime("%Y-%m")
    demo_key = f"financeiro-{month}-v1"
    with connection() as conn:
        if getattr(conn, "is_postgres", False):
            conn.execute("SELECT pg_advisory_xact_lock(736567002)")
        else:
            conn.execute("BEGIN IMMEDIATE")
        company = conn.execute("SELECT * FROM companies WHERE demo_key=?", (demo_key,)).fetchone()
        if not company:
            cursor = conn.execute("INSERT INTO companies(name,segment,is_demo,demo_key) VALUES (?, ?, 1, ?)",
                                  ("Livraria Horizonte · Demo", "Livraria", demo_key))
            cid = int(cursor.lastrowid)
            products = [("D001", "Jardins de papel", "Literatura", 55, 28),
                        ("D002", "Uma viagem pelo tempo", "História", 72, 38),
                        ("D003", "Pequenos exploradores", "Infantil", 39, 18),
                        ("D004", "Rotas do conhecimento", "Educação", 89, 45),
                        ("D005", "Entre versos", "Poesia", 45, 22)]
            sale_rows = []
            total_sales = 0
            for n in range(45):
                sku, title, category, price, cost = products[n % len(products)]
                quantity = 1 + n % 3
                total_sales += quantity * price
                sale_rows.append((cid, f"DEMO-{n+1:03}", f"{month}-{1+n%8:02}",
                                  f"Cliente fictício {1+n%12:02}", f"DEMO-C{n%12}",
                                  "Loja física" if n%2 else "Online", "São Paulo", "SP", sku, title,
                                  category, quantity, price, cost))
            conn.executemany("""INSERT INTO sales_lines(company_id,order_id,sale_date,customer,customer_id,
                channel,city,state,sku,title,category,quantity,unit_price,unit_cost)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", sale_rows)
            conn.executemany("""INSERT INTO inventory_snapshots(company_id,snapshot_date,sku,title,quantity,
                unit_cost,minimum_quantity) VALUES (?,?,?,?,?,?,?)""",
                [(cid, f"{month}-08", sku, title, 3 if n==0 else 15+n*5, cost, 5)
                 for n, (sku,title,_,_,cost) in enumerate(products)])
            movements = [("Receita", "Vendas de livros", "Vendas de demonstração", total_sales, "Pago", "08"),
                         ("Despesa", "Fornecedores", "Compra de livros", 2200, "Pago", "03"),
                         ("Despesa", "Aluguel", "Aluguel da loja", 1800, "Pago", "05"),
                         ("Despesa", "Marketing", "Campanha de divulgação", 320, "Pago", "06"),
                         ("Despesa", "Folha e encargos", "Folha mensal", 2400, "Pendente", "22"),
                         ("Receita", "Eventos", "Evento literário", 650, "Pendente", "25")]
            conn.executemany("""INSERT INTO transactions(company_id,date,kind,category,description,amount,
                payment_method,status,due_date,notes,is_demo) VALUES (?,?,?,?,?,?,'PIX',?,?,?,1)""",
                [(cid, f"{month}-{day if status=='Pago' else '08'}", kind, category, description, amount,
                  status, f"{month}-{day}" if status=="Pendente" else None, "Dados fictícios")
                 for kind,category,description,amount,status,day in movements])
            conn.executemany("INSERT INTO budgets(company_id,month,category,amount) VALUES (?,?,?,?)",
                             [(cid, month, "Aluguel", 1800), (cid, month, "Fornecedores", 3000), (cid, month, "Marketing", 500)])
            company = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    return {**dict(company), "role": "demo"}


def query_df(sql: str, params: Iterable | None = None) -> pd.DataFrame:
    with connection() as conn:
        cursor = conn.execute(sql, tuple(params or ()))
        return pd.DataFrame([dict(row) for row in cursor.fetchall()], columns=[column[0] for column in cursor.description])


def add_transaction(data: dict, company_id: int, issuer: str, subject: str) -> None:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        due = _validate_due_date(data.get("due_date")) if data["status"] == "Pendente" else None
        payment_date = _validate_due_date(data.get("payment_date") or data["date"]) if data["status"] == "Pago" else None
        conn.execute("""INSERT INTO transactions
            (company_id, date, kind, category, description, amount, payment_method, status, due_date, notes, payment_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_id, data["date"], data["kind"], data["category"], data["description"], data["amount"],
             data["payment_method"], data["status"], due, data.get("notes"), payment_date))


def _validate_due_date(value: str | None) -> str:
    try:
        return date.fromisoformat(value or "").isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("Informe uma data de vencimento válida para o lançamento pendente.") from exc


def update_status(
    transaction_id: int, status: str, company_id: int, issuer: str, subject: str,
    due_date: str | None = None, payment_date: str | None = None,
) -> None:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        if status not in {"Pago", "Pendente"}:
            raise ValueError("Selecione um status válido.")
        row = conn.execute("SELECT due_date FROM transactions WHERE id=? AND company_id=?", (transaction_id, company_id)).fetchone()
        if row is None:
            return
        selected_due = _validate_due_date(due_date or row["due_date"]) if status == "Pendente" else row["due_date"]
        settled = _validate_due_date(payment_date or date.today().isoformat()) if status == "Pago" else None
        conn.execute("UPDATE transactions SET status=?, due_date=?, payment_date=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND company_id=?", (status, selected_due, settled, transaction_id, company_id))


def delete_transaction(transaction_id: int, company_id: int, issuer: str, subject: str) -> None:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        conn.execute("DELETE FROM transactions WHERE id=? AND company_id=?", (transaction_id, company_id))


def upsert_budget(month: str, category: str, amount: float, company_id: int, issuer: str, subject: str) -> None:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        conn.execute("""INSERT INTO budgets(company_id, month, category, amount) VALUES (?, ?, ?, ?)
            ON CONFLICT(company_id, month, category) DO UPDATE SET amount=excluded.amount""",
            (company_id, month, category, amount))


def import_sales_lines(rows: list[dict], company_id: int, issuer: str, subject: str, source: str = "CSV de vendas") -> int:
    if not rows:
        return 0
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        batch = _create_import_batch(conn, company_id, "sales", source, len(rows))
        conn.executemany("""INSERT INTO sales_lines
            (company_id, order_id, sale_date, customer, customer_id, channel, city, state, sku, title, category,
             quantity, returned_quantity, unit_price, unit_cost, discount, taxes, shipping_charged, shipping_cost, status, import_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, order_id, sku) DO UPDATE SET sale_date=excluded.sale_date, customer=excluded.customer,
            customer_id=excluded.customer_id, channel=excluded.channel, city=excluded.city, state=excluded.state,
            title=excluded.title, category=excluded.category, quantity=excluded.quantity, returned_quantity=excluded.returned_quantity,
            unit_price=excluded.unit_price, unit_cost=excluded.unit_cost, discount=excluded.discount, taxes=excluded.taxes,
            shipping_charged=excluded.shipping_charged, shipping_cost=excluded.shipping_cost, status=excluded.status,
            import_id=excluded.import_id, updated_at=CURRENT_TIMESTAMP""",
            [(company_id, r["pedido_id"], r["data"], r["cliente"], r["cliente_id"], r["canal"], r["cidade"], r["uf"],
              r["sku"], r["titulo"], r["categoria"], r["quantidade"], r["quantidade_devolvida"], r["preco_unitario"],
              r["custo_unitario"], r["desconto"], r["impostos"], r["frete_cobrado"], r["frete_custo"], r["status"], batch) for r in rows])
    return len(rows)


def import_inventory_snapshots(rows: list[dict], company_id: int, issuer: str, subject: str, source: str = "CSV de estoque") -> int:
    if not rows:
        return 0
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        batch = _create_import_batch(conn, company_id, "inventory", source, len(rows))
        conn.executemany("""INSERT INTO inventory_snapshots
            (company_id, snapshot_date, sku, title, quantity, unit_cost, minimum_quantity, import_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, snapshot_date, sku) DO UPDATE SET title=excluded.title, quantity=excluded.quantity,
            unit_cost=excluded.unit_cost, minimum_quantity=excluded.minimum_quantity, import_id=excluded.import_id, updated_at=CURRENT_TIMESTAMP""",
            [(company_id, r["data_ref"], r["sku"], r["titulo"], r["quantidade"], r["custo_unitario"], r["estoque_minimo"], batch) for r in rows])
    return len(rows)


def _create_import_batch(conn, company_id, kind, source, count):
    batch = uuid4().hex
    conn.execute("INSERT INTO import_batches(id,company_id,kind,source,row_count) VALUES (?,?,?,?,?)",
                 (batch, company_id, kind, str(source)[:240], int(count)))
    return batch


def list_import_batches(company_id: int) -> pd.DataFrame:
    return query_df("""SELECT b.*,
        (SELECT COUNT(*) FROM sales_lines s WHERE s.company_id=b.company_id AND s.import_id=b.id)
        + (SELECT COUNT(*) FROM inventory_snapshots i WHERE i.company_id=b.company_id AND i.import_id=b.id) AS current_rows
        FROM import_batches b WHERE b.company_id=? ORDER BY b.created_at DESC, b.id""", [company_id])


def delete_import_batch(batch_id: str, company_id: int, issuer: str, subject: str) -> int:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
        count = 0
        for table in ("sales_lines", "inventory_snapshots"):
            count += conn.execute(f"DELETE FROM {table} WHERE company_id=? AND import_id=?", (company_id, batch_id)).rowcount
        conn.execute("DELETE FROM import_batches WHERE company_id=? AND id=?", (company_id, batch_id))
        return count


def delete_demo_transactions(company_id: int, issuer: str, subject: str) -> int:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
        return conn.execute("DELETE FROM transactions WHERE company_id=? AND is_demo=1", (company_id,)).rowcount


def get_app_setting(key: str, company_id: int, default: str = "") -> str:
    with connection() as conn:
        row = conn.execute("SELECT setting_value FROM app_settings WHERE company_id=? AND setting_key=?", (company_id, key)).fetchone()
    return row[0] if row else default


def set_app_settings(settings: dict[str, str], company_id: int, issuer: str, subject: str) -> None:
    if not settings:
        return
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
        conn.executemany("""INSERT INTO app_settings(company_id, setting_key, setting_value) VALUES (?, ?, ?)
            ON CONFLICT(company_id, setting_key) DO UPDATE SET setting_value=excluded.setting_value""",
            [(company_id, key, value) for key, value in settings.items()])


def seed_demo(company_id: int, issuer: str, subject: str) -> None:
    count = query_df("SELECT COUNT(*) AS n FROM transactions WHERE company_id=?", [company_id]).iloc[0]["n"]
    if count:
        return
    demo = [
        ("2026-09-01", "Receita", "Vendas de livros", "Vendas balcão", 4820.00, "Cartão", "Pago", None, ""),
        ("2026-09-03", "Despesa", "Fornecedores", "Reposição editora Aurora", 2100.00, "PIX", "Pago", None, ""),
        ("2026-09-05", "Receita", "Vendas online", "Pedidos e-commerce", 3270.00, "Cartão", "Pago", None, ""),
        ("2026-09-07", "Despesa", "Aluguel", "Aluguel da loja", 2800.00, "Boleto", "Pago", None, ""),
        ("2026-09-09", "Despesa", "Marketing", "Campanha clube do livro", 650.00, "Cartão", "Pago", None, ""),
        ("2026-09-11", "Receita", "Eventos", "Sessão de autógrafos", 1450.00, "PIX", "Pago", None, ""),
        ("2026-09-18", "Despesa", "Fornecedores", "Pedido editora Horizonte", 3350.00, "Boleto", "Pendente", "2026-09-18", ""),
        ("2026-09-22", "Despesa", "Folha e encargos", "Folha mensal", 4200.00, "Transferência", "Pendente", "2026-09-22", ""),
        ("2026-09-25", "Receita", "Vendas de livros", "Recebíveis cartões", 2600.00, "Cartão", "Pendente", "2026-09-25", ""),
    ]
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        conn.executemany("""INSERT INTO transactions
            (company_id, date, kind, category, description, amount, payment_method, status, due_date, notes, is_demo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""", [(company_id, *row) for row in demo])
