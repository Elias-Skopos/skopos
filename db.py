from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

import pandas as pd

DB_PATH = Path(__file__).with_name("livraria.db")
COMPANY_ROLES = ("administrator", "manager", "collaborator")
EDIT_ROLES = ("administrator", "manager")


@contextmanager
def connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_membership_roles(conn: sqlite3.Connection) -> None:
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


def register_identity(issuer: str, subject: str, email: str = "", name: str = "", email_verified: bool = False) -> None:
    with connection() as conn:
        conn.execute("""INSERT INTO users (issuer, subject, email, name, email_verified) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(issuer, subject) DO UPDATE SET email=excluded.email, name=excluded.name,
            email_verified=excluded.email_verified, last_seen_at=CURRENT_TIMESTAMP""",
            (issuer, subject, email.strip().casefold(), name, int(email_verified)))


def companies_for_user(issuer: str, subject: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute("""SELECT c.id, c.name, m.role FROM companies c
            JOIN company_memberships m ON m.company_id=c.id WHERE m.issuer=? AND m.subject=? ORDER BY c.id""",
            (issuer, subject)).fetchall()
    return [dict(row) for row in rows]


def accept_company_invitations(email: str, issuer: str, subject: str, email_verified: bool) -> int:
    clean_email = email.strip().casefold()
    if not email_verified or not clean_email:
        return 0
    with connection() as conn:
        invitations = conn.execute(
            "SELECT id, company_id, role FROM company_invitations WHERE email=?",
            (clean_email,),
        ).fetchall()
        for invitation in invitations:
            conn.execute(
                "INSERT OR IGNORE INTO company_memberships(company_id, issuer, subject, role) VALUES (?, ?, ?, ?)",
                (invitation["company_id"], issuer, subject, invitation["role"]),
            )
            conn.execute("DELETE FROM company_invitations WHERE id=?", (invitation["id"],))
    return len(invitations)


def has_pending_company_invitation(email: str) -> bool:
    clean_email = email.strip().casefold()
    if not clean_email:
        return False
    with connection() as conn:
        return conn.execute(
            "SELECT 1 FROM company_invitations WHERE email=? LIMIT 1", (clean_email,)
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
            "SELECT id, email, role, created_at FROM company_invitations WHERE company_id=? ORDER BY created_at DESC",
            (company_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def invite_company_member(company_id: int, email: str, role: str, issuer: str, subject: str) -> str:
    clean_email = email.strip().casefold()
    if role not in COMPANY_ROLES:
        raise ValueError("Selecione um perfil válido.")
    if len(clean_email) > 254 or "@" not in clean_email or "." not in clean_email.rsplit("@", 1)[-1]:
        raise ValueError("Informe um e-mail válido.")
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
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
            conn.execute(
                "INSERT INTO company_memberships(company_id, issuer, subject, role) VALUES (?, ?, ?, ?)",
                (company_id, existing_user["issuer"], existing_user["subject"], role),
            )
            return "added"
        conn.execute("""INSERT INTO company_invitations
                (company_id, email, role, invited_by_issuer, invited_by_subject)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(company_id, email) DO UPDATE SET role=excluded.role,
                invited_by_issuer=excluded.invited_by_issuer, invited_by_subject=excluded.invited_by_subject,
                created_at=CURRENT_TIMESTAMP""",
            (company_id, clean_email, role, issuer, subject))
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
                raise ValueError("A empresa precisa manter pelo menos um administrador.")
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
                raise ValueError("A empresa precisa manter pelo menos um administrador.")
        conn.execute(
            "DELETE FROM company_memberships WHERE company_id=? AND issuer=? AND subject=?",
            (company_id, target_issuer, target_subject),
        )


def delete_company_invitation(company_id: int, invitation_id: int, issuer: str, subject: str) -> None:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, ("administrator",))
        conn.execute("DELETE FROM company_invitations WHERE id=? AND company_id=?", (invitation_id, company_id))


def create_company(name: str, issuer: str, subject: str) -> int:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Informe o nome da livraria.")
    with connection() as conn:
        existing = conn.execute("SELECT company_id FROM company_memberships WHERE issuer=? AND subject=? ORDER BY company_id LIMIT 1", (issuer, subject)).fetchone()
        if existing:
            return int(existing[0])
        cursor = conn.execute("INSERT INTO companies(name) VALUES (?)", (clean_name,))
        company_id = int(cursor.lastrowid)
        conn.execute("INSERT INTO company_memberships(company_id, issuer, subject, role) VALUES (?, ?, ?, 'administrator')", (company_id, issuer, subject))
        # The first company claims pre-existing local data once; later companies always start empty.
        if conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1:
            for table in ("transactions", "budgets", "sales_lines", "inventory_snapshots", "app_settings"):
                conn.execute(f"UPDATE {table} SET company_id=? WHERE company_id IS NULL", (company_id,))
        return company_id


def update_company(company_id: int, name: str, issuer: str, subject: str) -> bool:
    clean_name = name.strip()
    if not clean_name:
        return False
    with connection() as conn:
        cursor = conn.execute("""UPDATE companies SET name=? WHERE id=? AND EXISTS (
            SELECT 1 FROM company_memberships WHERE company_id=? AND issuer=? AND subject=? AND role='administrator')""",
            (clean_name, company_id, company_id, issuer, subject))
        return cursor.rowcount == 1


def query_df(sql: str, params: Iterable | None = None) -> pd.DataFrame:
    with connection() as conn:
        return pd.read_sql_query(sql, conn, params=tuple(params or ()))


def add_transaction(data: dict, company_id: int, issuer: str, subject: str) -> None:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        conn.execute("""INSERT INTO transactions
            (company_id, date, kind, category, description, amount, payment_method, status, due_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_id, data["date"], data["kind"], data["category"], data["description"], data["amount"],
             data["payment_method"], data["status"], data.get("due_date"), data.get("notes")))


def update_status(transaction_id: int, status: str, company_id: int, issuer: str, subject: str) -> None:
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        conn.execute("UPDATE transactions SET status=? WHERE id=? AND company_id=?", (status, transaction_id, company_id))


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


def import_sales_lines(rows: list[dict], company_id: int, issuer: str, subject: str) -> int:
    if not rows:
        return 0
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        conn.executemany("""INSERT INTO sales_lines
            (company_id, order_id, sale_date, customer, customer_id, channel, city, state, sku, title, category,
             quantity, returned_quantity, unit_price, unit_cost, discount, taxes, shipping_charged, shipping_cost, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, order_id, sku) DO UPDATE SET sale_date=excluded.sale_date, customer=excluded.customer,
            customer_id=excluded.customer_id, channel=excluded.channel, city=excluded.city, state=excluded.state,
            title=excluded.title, category=excluded.category, quantity=excluded.quantity, returned_quantity=excluded.returned_quantity,
            unit_price=excluded.unit_price, unit_cost=excluded.unit_cost, discount=excluded.discount, taxes=excluded.taxes,
            shipping_charged=excluded.shipping_charged, shipping_cost=excluded.shipping_cost, status=excluded.status,
            updated_at=CURRENT_TIMESTAMP""",
            [(company_id, r["pedido_id"], r["data"], r["cliente"], r["cliente_id"], r["canal"], r["cidade"], r["uf"],
              r["sku"], r["titulo"], r["categoria"], r["quantidade"], r["quantidade_devolvida"], r["preco_unitario"],
              r["custo_unitario"], r["desconto"], r["impostos"], r["frete_cobrado"], r["frete_custo"], r["status"]) for r in rows])
    return len(rows)


def import_inventory_snapshots(rows: list[dict], company_id: int, issuer: str, subject: str) -> int:
    if not rows:
        return 0
    with connection() as conn:
        _require_role(conn, company_id, issuer, subject, EDIT_ROLES)
        conn.executemany("""INSERT INTO inventory_snapshots
            (company_id, snapshot_date, sku, title, quantity, unit_cost, minimum_quantity, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(company_id, snapshot_date, sku) DO UPDATE SET title=excluded.title, quantity=excluded.quantity,
            unit_cost=excluded.unit_cost, minimum_quantity=excluded.minimum_quantity, updated_at=CURRENT_TIMESTAMP""",
            [(company_id, r["data_ref"], r["sku"], r["titulo"], r["quantidade"], r["custo_unitario"], r["estoque_minimo"]) for r in rows])
    return len(rows)


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
            (company_id, date, kind, category, description, amount, payment_method, status, due_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", [(company_id, *row) for row in demo])
