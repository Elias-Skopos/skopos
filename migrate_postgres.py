"""Copy a local SQLite snapshot into an EMPTY PostgreSQL database.

Credentials are read only from SKOPOS_DATABASE_URL. The source is never changed.
"""
import argparse
import os
from pathlib import Path
import sqlite3
import tempfile
from contextlib import closing
from unittest.mock import patch

import db

TABLES = ("companies", "users", "company_memberships", "company_invitations", "transactions", "budgets", "sales_lines", "inventory_snapshots", "app_settings", "import_batches")
IDENTITY_TABLES = ("companies", "company_invitations", "transactions", "budgets", "sales_lines", "inventory_snapshots")


def migrate(source: Path, apply: bool = False):
    if not source.is_file():
        raise ValueError("O arquivo SQLite de origem não existe.")
    with tempfile.TemporaryDirectory(prefix="skopos-migrate-") as temp:
        copy = Path(temp) / "snapshot.db"
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(copy)) as target:
                original.backup(target)
        with patch.object(db, "DB_PATH", copy), patch.object(db, "DATABASE_URL", ""):
            db.init_db()
            data = {table: db.query_df(f"SELECT * FROM {table}") for table in TABLES}
        counts = {table: len(frame) for table, frame in data.items()}
        if not apply:
            return counts
        url = os.environ.get("SKOPOS_DATABASE_URL", "")
        if not url:
            raise ValueError("Defina SKOPOS_DATABASE_URL com a conexão do PostgreSQL de destino.")
        with patch.object(db, "DATABASE_URL", url):
            db.configure_database(url)
            db.init_db()
            with db.connection() as target:
                target.execute("SELECT pg_advisory_xact_lock(736567001)")
                target.execute("LOCK TABLE " + ", ".join(TABLES) + " IN ACCESS EXCLUSIVE MODE")
                if any(target.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES):
                    raise ValueError("A migração exige um banco de destino vazio. Nenhum dado existente será sobrescrito.")
                for table, frame in data.items():
                    if frame.empty:
                        continue
                    columns = list(frame.columns)
                    query = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
                    values = frame.astype(object).where(frame.notna(), None).to_dict("records")
                    target.executemany(query, [tuple(row[column] for column in columns) for row in values])
                for table in IDENTITY_TABLES:
                    target.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE((SELECT MAX(id) FROM {table}),1), EXISTS(SELECT 1 FROM {table}))")
                for table, expected in counts.items():
                    if target.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] != expected:
                        raise ValueError(f"Contagem divergente em {table}; a transação será revertida.")
        return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).with_name("livraria.db"))
    parser.add_argument("--apply", action="store_true", help="Executar a cópia no PostgreSQL vazio; sem este argumento, apenas conferir a origem.")
    args = parser.parse_args()
    try:
        result = migrate(args.source, args.apply)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    except Exception:
        parser.exit(1, "Não foi possível concluir a migração. Confira a conexão, as permissões e o esquema do destino.\n")
    print("Migração concluída." if args.apply else "Simulação concluída; nenhum banco foi alterado.")
    for table, count in result.items():
        print(f"{table}: {count}")
