"""Owner-only deletion, with an atomic recovery copy in the same database."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from uuid import uuid4

import db

# Parents precede dependent data for recovery; reverse order for deletion.
SCOPED_TABLES = (
    "company_memberships", "company_invitations", "app_settings", "budgets",
    "import_batches", "input_batches", "recurring_expenses", "opening_balances",
    "sales_lines", "inventory_snapshots", "daily_sales", "transactions",
)
RECOVERY_TABLE = "company_deletion_backups"


def init_schema(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS company_deletion_backups (
        id TEXT PRIMARY KEY, company_id INTEGER NOT NULL, company_name TEXT NOT NULL,
        deleted_by_issuer TEXT NOT NULL, deleted_by_subject TEXT NOT NULL,
        deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        backup_json TEXT NOT NULL, backup_sha256 TEXT NOT NULL,
        restored_at TEXT
    )""")


def _check_tables(conn) -> None:
    """Stop rather than leave data behind if a later feature adds tenant tables."""
    if getattr(conn, "is_postgres", False):
        names = {r[0] for r in conn.execute("""SELECT table_name FROM information_schema.columns
                    WHERE table_schema=current_schema() AND column_name='company_id'""").fetchall()}
    else:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        names = {name for name in tables if re.fullmatch(r"[a-zA-Z0-9_]+", name)
                 and "company_id" in db._columns(conn, name)}
    if names != set(SCOPED_TABLES) | {RECOVERY_TABLE}:
        raise ValueError("A estrutura dos dados mudou. Atualize a rotina de exclusão antes de continuar.")


def delete_company(company_id: int, issuer: str, subject: str,
                   confirmation_name: str, confirmed: bool = False) -> str:
    with db.connection() as conn:
        # Checks live membership and locks the company until commit/rollback.
        db._require_role(conn, company_id, issuer, subject, ("administrator",))
        company = dict(conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone())
        if confirmed is not True or confirmation_name != company["name"]:
            raise ValueError("Digite o nome exato da empresa e marque a confirmação para excluí-la.")
        _check_tables(conn)
        data = {"companies": [company]}
        for table in SCOPED_TABLES:
            data[table] = [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE company_id=?", (company_id,)).fetchall()]
        key = f"home_shortcuts_{company_id}"
        data["user_settings"] = [dict(row) for row in conn.execute("SELECT * FROM user_settings WHERE setting_key=?", (key,)).fetchall()]
        snapshot = json.dumps({"version": 1, "data": data}, ensure_ascii=False, allow_nan=False, sort_keys=True)
        digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        backup_id = str(uuid4())
        conn.execute("""INSERT INTO company_deletion_backups
            (id,company_id,company_name,deleted_by_issuer,deleted_by_subject,backup_json,backup_sha256)
            VALUES (?,?,?,?,?,?,?)""", (backup_id, company_id, company["name"], issuer, subject, snapshot, digest))
        for table in reversed(SCOPED_TABLES):
            conn.execute(f"DELETE FROM {table} WHERE company_id=?", (company_id,))
        conn.execute("DELETE FROM user_settings WHERE setting_key=?", (key,))
        if conn.execute("DELETE FROM companies WHERE id=?", (company_id,)).rowcount != 1:
            raise ValueError("A empresa não pôde ser excluída. A operação foi cancelada.")
    return backup_id


def deleted_companies(issuer: str, subject: str) -> list[dict]:
    with db.connection() as conn:
        rows = conn.execute("""SELECT id,company_id,company_name,deleted_at FROM company_deletion_backups
            WHERE deleted_by_issuer=? AND deleted_by_subject=? AND restored_at IS NULL
            ORDER BY deleted_at DESC,id""", (issuer, subject)).fetchall()
    return [dict(row) for row in rows]


def _owned_backup(conn, backup_id: str, issuer: str, subject: str, lock: bool = False):
    if lock and not getattr(conn, "is_postgres", False):
        conn.execute("BEGIN IMMEDIATE")
    suffix = " FOR UPDATE" if lock and getattr(conn, "is_postgres", False) else ""
    row = conn.execute("SELECT * FROM company_deletion_backups WHERE id=?" + suffix, (backup_id,)).fetchone()
    if not row or (row["deleted_by_issuer"], row["deleted_by_subject"]) != (issuer, subject):
        raise PermissionError("Somente o proprietário que excluiu esta empresa pode recuperar sua cópia.")
    if row["restored_at"]:
        raise ValueError("Esta empresa já foi recuperada.")
    actual = hashlib.sha256(row["backup_json"].encode("utf-8")).hexdigest()
    if not hmac.compare_digest(actual, row["backup_sha256"]):
        raise ValueError("A cópia de recuperação não passou na verificação de integridade.")
    return row


def recovery_copy(backup_id: str, issuer: str, subject: str) -> bytes:
    with db.connection() as conn:
        row = _owned_backup(conn, backup_id, issuer, subject)
        return row["backup_json"].encode("utf-8")


def restore_company(backup_id: str, issuer: str, subject: str, confirmed: bool = False) -> int:
    if confirmed is not True:
        raise ValueError("Confirme a recuperação desta empresa.")
    with db.connection() as conn:
        row = _owned_backup(conn, backup_id, issuer, subject, lock=True)
        _check_tables(conn)
        company_id = row["company_id"]
        if conn.execute("SELECT 1 FROM companies WHERE id=?", (company_id,)).fetchone():
            raise ValueError("Já existe uma empresa com este identificador. Nenhum dado foi substituído.")
        payload = json.loads(row["backup_json"])
        data = payload.get("data", {})
        if payload.get("version") != 1 or set(data) != {"companies", "user_settings", *SCOPED_TABLES}:
            raise ValueError("O formato da cópia não é compatível com esta versão.")
        if len(data["companies"]) != 1 or data["companies"][0]["id"] != company_id:
            raise ValueError("A identificação da empresa na cópia é inválida.")
        for table in ("companies", *SCOPED_TABLES, "user_settings"):
            allowed = db._columns(conn, table)
            for record in data[table]:
                columns = list(record)
                if not columns or not set(columns) <= allowed or any(not re.fullmatch(r"[a-zA-Z0-9_]+", col) for col in columns):
                    raise ValueError("As colunas da cópia não são compatíveis com esta versão.")
                if table in SCOPED_TABLES and record.get("company_id") != company_id:
                    raise ValueError("A cópia contém dados de outra empresa. Recuperação cancelada.")
                if table == "user_settings" and record.get("setting_key") != f"home_shortcuts_{company_id}":
                    raise ValueError("A cópia contém preferências de outra empresa.")
                fields = ",".join(f'"{column}"' for column in columns)
                markers = ",".join("?" for _ in columns)
                conn.execute(f"INSERT INTO {table} ({fields}) VALUES ({markers})", [record[col] for col in columns])
        conn.execute("UPDATE company_deletion_backups SET restored_at=CURRENT_TIMESTAMP WHERE id=?", (backup_id,))
    return int(company_id)
