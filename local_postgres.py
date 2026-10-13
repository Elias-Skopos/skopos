"""Manage the private PostgreSQL instance used by the local Skopos installation.

Runtime, credentials and data live in .local_postgres/ and must never enter Git.
The PostgreSQL binaries must be installed before running `setup`.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import tempfile
import tomllib
from urllib.parse import quote
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from local_paths import APP_ROOT, DATA_ROOT, postgres_runtime

ROOT = APP_ROOT
LOCAL = DATA_ROOT / ".local_postgres"
BIN = postgres_runtime() / "bin"
DATA = LOCAL / "data"
SETTINGS = LOCAL / "settings.json"
BACKUPS = DATA_ROOT / "backup_local_postgres"
SECRETS = DATA_ROOT / ".streamlit" / "secrets.toml"


def run_binary(name: str, args: list[str], env: dict | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    executable = BIN / (name + (".exe" if os.name == "nt" else ""))
    if not executable.is_file():
        raise RuntimeError("Os binários PostgreSQL não foram encontrados na instalação local.")
    # A detached Windows server can inherit a pipe and keep communicate() waiting.
    # Use a real log file rather than captured pipes when running PostgreSQL tools.
    log_path = LOCAL / f"{name}-command.log"
    with log_path.open("ab") as log:
        offset = log.tell()
        runtime_env = {**os.environ, **(env or {})}
        runtime_env["PATH"] = str(APP_ROOT) + os.pathsep + str(BIN) + os.pathsep + runtime_env.get("PATH", "")
        result = subprocess.run([str(executable), *args], env=runtime_env, cwd=APP_ROOT, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                timeout=timeout)
    with log_path.open("rb") as log:
        log.seek(offset)
        result.stdout = log.read()
    result.stderr = b""
    return result


def read_settings() -> dict:
    if not SETTINGS.is_file():
        raise RuntimeError("O PostgreSQL local ainda não foi preparado. Execute local_postgres.py setup.")
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def database_url(settings: dict, test: bool = False) -> str:
    database = "skopos_test" if test else "skopos"
    return (f"postgresql://{quote(settings['app_user'], safe='')}:{quote(settings['app_password'], safe='')}"
            f"@127.0.0.1:{int(settings['port'])}/{database}?sslmode=disable")


def admin_connection(settings: dict, database: str = "postgres"):
    return psycopg.connect(host="127.0.0.1", port=int(settings["port"]), dbname=database,
                          user=settings["admin_user"], password=settings["admin_password"],
                          sslmode="disable", connect_timeout=10, autocommit=True)


def start() -> None:
    read_settings()
    if not (DATA / "PG_VERSION").is_file():
        raise RuntimeError("O diretório de dados não foi inicializado.")
    status = run_binary("pg_ctl", ["-D", str(DATA), "status"])
    if status.returncode == 0:
        return
    if status.returncode != 3:
        raise RuntimeError("Não foi possível consultar a instância PostgreSQL local.")
    result = run_binary("pg_ctl", ["-D", str(DATA), "-l", str(LOCAL / "server.log"), "-w", "-t", "30", "start"], timeout=40)
    if result.returncode:
        raise RuntimeError("Não foi possível iniciar o PostgreSQL. Consulte .local_postgres/server.log.")


def setup(port: int = 5432) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("Informe uma porta entre 1024 e 65535.")
    LOCAL.mkdir(exist_ok=True)
    if not SETTINGS.exists():
        if (DATA / "PG_VERSION").exists():
            raise RuntimeError("Há um banco existente sem suas credenciais. Nenhum dado será substituído.")
        settings = {"port": port, "admin_user": "skopos_local_admin", "admin_password": secrets.token_urlsafe(36),
                    "app_user": "skopos_app", "app_password": secrets.token_urlsafe(36)}
        SETTINGS.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    settings = read_settings()
    if not (DATA / "PG_VERSION").exists():
        if DATA.exists() and any(DATA.iterdir()):
            raise RuntimeError("O diretório de dados contém arquivos. Não será reinicializado.")
        pwfile = LOCAL / "init-password.tmp"
        try:
            pwfile.write_text(settings["admin_password"] + "\n", encoding="utf-8")
            result = run_binary("initdb", ["-D", str(DATA), "-U", settings["admin_user"],
                                          "--pwfile", str(pwfile), "--auth=scram-sha-256",
                                          "--encoding=UTF8", "--locale=C"], timeout=90)
            if result.returncode:
                (LOCAL / "initdb.log").write_bytes(result.stdout + result.stderr)
                raise RuntimeError("A inicialização falhou. Consulte .local_postgres/initdb.log.")
        finally:
            pwfile.unlink(missing_ok=True)
        with (DATA / "postgresql.conf").open("a", encoding="utf-8") as handle:
            handle.write(f"\n# Instância exclusiva do Skopos, acessível apenas neste computador.\n"
                         f"listen_addresses = '127.0.0.1'\nport = {int(settings['port'])}\n"
                         "shared_buffers = '64MB'\nmax_connections = 50\n"
                         "password_encryption = 'scram-sha-256'\n"
                         "timezone = 'America/Sao_Paulo'\nlog_timezone = 'UTC'\n")
    start()
    with admin_connection(settings) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (settings["app_user"],)).fetchone():
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}")
                         .format(sql.Identifier(settings["app_user"]), sql.Literal(settings["app_password"])))
        for name in ("skopos", "skopos_test"):
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'")
                             .format(sql.Identifier(name), sql.Identifier(settings["app_user"])))
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE skopos FROM PUBLIC"))
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE skopos_test FROM PUBLIC"))


def snapshot_sqlite(source: Path) -> Path:
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f"antes_postgres_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(backup)) as target:
            original.backup(target)
    return backup


def migrate_local(source: Path) -> dict:
    from migrate_postgres import migrate
    start()
    if not source.is_file():
        raise ValueError("O banco SQLite de origem não existe.")
    backup = snapshot_sqlite(source)
    print(f"Backup SQLite: {backup.relative_to(DATA_ROOT)}")
    with patch.dict(os.environ, {"SKOPOS_DATABASE_URL": database_url(read_settings())}):
        counts = migrate(backup, apply=True)
    (LOCAL / "migration.json").write_text(json.dumps({"sqlite_backup": str(backup), "counts": counts,
        "timestamp": datetime.now().isoformat()}, indent=2), encoding="utf-8")
    return counts


def secrets_with_database(content: str, url: str) -> str:
    """Preserve auth and other settings; refuse to replace a different database."""
    parsed = tomllib.loads(content)
    existing = parsed.get("database", {}).get("url", "")
    if existing and existing != url:
        raise ValueError("Já existe outra conexão no arquivo de Secrets. Ela não será substituída.")
    if existing == url:
        return content
    lines = content.splitlines(keepends=True)
    section = next((i for i, line in enumerate(lines) if re.fullmatch(r"\s*\[database\]\s*(?:#.*)?", line.rstrip())), None)
    value = f"url = {json.dumps(url)}\n"
    if section is None:
        output = content.rstrip() + "\n\n[database]\n" + value
    else:
        end = next((i for i in range(section+1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        lines = [line for i, line in enumerate(lines) if not (section < i < end and re.match(r"\s*url\s*=", line))]
        lines.insert(section+1, value)
        output = "".join(lines)
    result = tomllib.loads(output)
    if result.get("database", {}).get("url") != url:
        raise ValueError("A configuração não pôde ser atualizada com segurança.")
    result.pop("database", None)
    parsed.pop("database", None)
    if result != parsed:
        raise ValueError("As configurações existentes seriam alteradas. Operação cancelada.")
    return output


def activate() -> None:
    import db
    from migrate_postgres import TABLES
    settings = read_settings()
    url = database_url(settings)
    # Validate the migration before changing the app's connection.
    report = json.loads((LOCAL / "migration.json").read_text(encoding="utf-8"))
    with patch.object(db, "DATABASE_URL", url):
        with db.connection() as conn:
            actual = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
    if actual != report["counts"]:
        raise ValueError("As contagens do destino divergem da migração. A conexão do app não foi alterada.")
    content = SECRETS.read_text(encoding="utf-8-sig") if SECRETS.exists() else ""
    updated = secrets_with_database(content, url)
    SECRETS.parent.mkdir(exist_ok=True)
    if content and updated != content:
        BACKUPS.mkdir(exist_ok=True)
        (BACKUPS / f"secrets_antes_postgres_{datetime.now():%Y%m%d_%H%M%S_%f}.toml").write_text(content, encoding="utf-8")
    temporary = SECRETS.with_name("secrets.toml.new")
    try:
        temporary.write_text(updated, encoding="utf-8")
        temporary.replace(SECRETS)
    finally:
        temporary.unlink(missing_ok=True)


def backup() -> Path:
    start()
    settings = read_settings()
    BACKUPS.mkdir(exist_ok=True)
    destination = BACKUPS / f"skopos_{datetime.now():%Y%m%d_%H%M%S_%f}.dump"
    fd, filename = tempfile.mkstemp(prefix="pgpass-", dir=LOCAL)
    os.close(fd)
    passfile = Path(filename)
    try:
        passfile.write_text(f"127.0.0.1:{settings['port']}:skopos:{settings['app_user']}:{settings['app_password']}\n", encoding="utf-8")
        env = {**os.environ, "PGPASSFILE": str(passfile)}
        env.pop("PGPASSWORD", None)
        result = run_binary("pg_dump", ["--host=127.0.0.1", f"--port={settings['port']}",
                                       f"--username={settings['app_user']}", "--no-password", "--format=custom",
                                       "--file=" + str(destination), "skopos"], env, timeout=120)
        if result.returncode or not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError("O backup não foi concluído. O arquivo parcial não deve ser usado.")
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        destination.with_suffix(".sha256").write_text(digest + "\n", encoding="ascii")
        return destination
    finally:
        passfile.unlink(missing_ok=True)


def verify_backup(destination: Path | None = None) -> dict:
    """Restore only into a newly created disposable database, never over production."""
    from migrate_postgres import TABLES
    start()
    if destination is None:
        dumps = sorted(BACKUPS.glob("skopos_*.dump"))
        if not dumps:
            raise ValueError("Nenhum backup PostgreSQL foi encontrado.")
        destination = dumps[-1]
    destination = destination.resolve()
    if not destination.is_relative_to(BACKUPS.resolve()):
        raise ValueError("Selecione um backup dentro da pasta de backups do Skopos.")
    expected = destination.with_suffix(".sha256").read_text(encoding="ascii").strip()
    if hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
        raise ValueError("O backup não corresponde ao checksum registrado.")
    settings = read_settings()
    temporary_db = "skopos_restore_" + uuid4().hex
    with admin_connection(settings) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'")
                     .format(sql.Identifier(temporary_db), sql.Identifier(settings["app_user"])))
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(temporary_db)))
    fd, filename = tempfile.mkstemp(prefix="pgpass-", dir=LOCAL)
    os.close(fd)
    passfile = Path(filename)
    try:
        passfile.write_text(f"127.0.0.1:{settings['port']}:{temporary_db}:{settings['app_user']}:{settings['app_password']}\n", encoding="utf-8")
        env = {**os.environ, "PGPASSFILE": str(passfile)}
        env.pop("PGPASSWORD", None)
        result = run_binary("pg_restore", ["--host=127.0.0.1", f"--port={settings['port']}",
            f"--username={settings['app_user']}", "--no-password", "--no-owner", "--no-acl",
            "--exit-on-error", f"--dbname={temporary_db}", str(destination)], env, timeout=120)
        if result.returncode:
            raise RuntimeError("O backup não pôde ser restaurado no banco de validação.")
        restored_url = database_url(settings).replace("/skopos?", f"/{temporary_db}?")
        with psycopg.connect(database_url(settings), connect_timeout=10) as live:
            with psycopg.connect(restored_url, connect_timeout=10) as restored:
                counts = {}
                available = {row[0] for row in live.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
                recovered_tables = {row[0] for row in restored.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
                if available != recovered_tables:
                    raise ValueError("O backup e o banco ativo têm estruturas diferentes. Gere um backup atualizado antes de validar.")
                for table in TABLES:
                    if table not in available:
                        continue
                    query = sql.SQL("SELECT * FROM {} ORDER BY {}::text COLLATE \"C\"").format(sql.Identifier(table), sql.Identifier(table))
                    # The row text ordering is deterministic across both databases.
                    current = live.execute(query).fetchall()
                    recovered = restored.execute(query).fetchall()
                    if current != recovered:
                        raise ValueError(f"Os registros recuperados divergem em {table}. Faça um backup atualizado antes de validar.")
                    counts[table] = len(recovered)
        (LOCAL / "backup_validation.json").write_text(json.dumps({"backup": str(destination), "counts": counts,
            "timestamp": datetime.now().isoformat()}, indent=2), encoding="utf-8")
        return counts
    finally:
        passfile.unlink(missing_ok=True)
        # This name is generated here and cannot refer to an existing application DB.
        with admin_connection(settings) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(temporary_db)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "start", "stop", "status", "migrate", "activate", "backup", "verify-backup", "test"))
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--source", type=Path, default=DATA_ROOT / "livraria.db")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "setup":
            setup(args.port)
        elif args.action == "start":
            start()
        elif args.action == "stop":
            result = run_binary("pg_ctl", ["-D", str(DATA), "-m", "fast", "-w", "-t", "30", "stop"], timeout=40)
            if result.returncode:
                raise RuntimeError("Não foi possível parar o PostgreSQL local.")
        elif args.action == "status":
            status = run_binary("pg_ctl", ["-D", str(DATA), "status"])
            if status.returncode:
                print("PostgreSQL local parado.")
                return 1
            with psycopg.connect(database_url(read_settings()), connect_timeout=10) as conn:
                version, port, user = conn.execute("SELECT version(),inet_server_port(),current_user").fetchone()
                print(f"{version.split(' on ')[0]} · 127.0.0.1:{port} · Banco skopos · Usuário {user}")
        elif args.action == "migrate":
            for table, count in migrate_local(args.source).items():
                print(f"{table}: {count}")
        elif args.action == "activate":
            activate()
        elif args.action == "backup":
            print(f"Backup PostgreSQL: {backup().relative_to(DATA_ROOT)}")
        elif args.action == "verify-backup":
            for table, count in verify_backup(args.backup).items():
                print(f"{table}: {count}")
        elif args.action == "test":
            start()
            env = {**os.environ, "SKOPOS_TEST_DATABASE_URL": database_url(read_settings(), test=True)}
            result = subprocess.run([os.sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v", "-k", "postgres"], cwd=ROOT, env=env)
            return result.returncode
    except (ValueError, RuntimeError) as exc:
        print(str(exc))
        return 1
    except Exception:
        # Connection exceptions can contain credentials; do not print raw tracebacks.
        print("A operação não foi concluída. Verifique a instalação, o status e os arquivos locais de configuração.")
        return 1
    print("Operação concluída.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
