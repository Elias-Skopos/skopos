"""Launch Skopos on loopback, keeping the database and login configuration intact."""
from __future__ import annotations

import argparse
from datetime import datetime
import os
import secrets
import socket
import subprocess
import sys
import time
import tomllib
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
import webbrowser

from local_config import LocalConfig, company_hostname, load_config, save_config
from local_paths import APP_ROOT, DATA_ROOT


def validate_login(config: LocalConfig, settings: dict) -> None:
    """Never switch auth origins silently: cookies/state belong to one hostname."""
    auth = settings.get("auth", {})
    google = auth.get("local", {}) if os.environ.get("SKOPOS_DESKTOP") == "1" else auth.get("google", {})
    required = ("client_id", "client_secret", "server_metadata_url")
    if not all(google.get(field) for field in required):
        raise ValueError("O login ainda precisa ser preparado para esta instalação. Consulte POSTGRESQL_LOCAL.md.")
    redirect_uri = auth.get("redirect_uri", "")
    if not isinstance(redirect_uri, str):
        raise ValueError("A URL de retorno do login é inválida.")
    if redirect_uri.replace("{port}", str(config.port)) != config.url + "/oauth2callback":
        raise ValueError("O nome/porta escolhido difere do retorno do login Google. "
                         "A autenticação precisa ser adaptada antes de ativar o endereço personalizado. "
                         "A configuração de login existente foi preservada.")
    if not auth.get("cookie_secret"):
        raise ValueError("A configuração do login precisa de cookie_secret.")


def preflight(config: LocalConfig) -> None:
    import local_postgres

    secret_path = DATA_ROOT / ".streamlit/secrets.toml"
    if not secret_path.is_file():
        raise ValueError("A configuração privada da instalação não foi encontrada.")
    try:
        settings = tomllib.loads(secret_path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("A configuração privada precisa ser corrigida; nenhum dado foi alterado.") from exc
    validate_login(config, settings)
    expected = local_postgres.database_url(local_postgres.read_settings())
    if settings.get("database", {}).get("url") != expected:
        raise ValueError("O app não está conectado ao PostgreSQL desta instalação. "
                         "Valide e ative o banco local antes de abrir; a conexão existente foi preservada.")


def streamlit_command(config: LocalConfig, python: str = sys.executable) -> list[str]:
    prefix = [python, "--serve", "--data-dir", str(DATA_ROOT)] if getattr(sys, "frozen", False) else [python, "-m", "streamlit", "run"]
    return [*prefix, str(APP_ROOT / "local_app_server.py"),
            "--global.developmentMode", "false",
            "--server.address", "127.0.0.1", "--server.port", str(config.port),
            "--browser.serverAddress", config.hostname, "--browser.serverPort", str(config.port),
            "--server.headless", "true", "--server.fileWatcherType", "none",
            "--server.enableCORS", "true", "--server.enableXsrfProtection", "true",
            "--browser.gatherUsageStats", "false",
            "--secrets.files", str(DATA_ROOT / ".streamlit/secrets.toml")]


def require_free_port(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise ValueError("A porta do Skopos já está em uso. "
                             "Se o aplicativo está aberto, use a guia existente. "
                             "Caso contrário, confira os programas locais antes de alterar a porta.") from exc


def wait_ready(process: subprocess.Popen, port: int, token: str, timeout: float = 60) -> None:
    # Use loopback explicitly: the Windows OS resolver may not handle .localhost
    # subdomains even when Chrome/Edge resolve them internally. Ignore proxies.
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("O servidor encerrou antes de ficar pronto. Consulte .local_postgres/app.log.")
        try:
            request = Request(f"http://127.0.0.1:{port}/_skopos/health", headers={"X-Skopos-Instance": token})
            with opener.open(request, timeout=1) as response:
                if response.status == 200 and response.read(32).strip() == b"ok":
                    if process.poll() is None:
                        return
        except (OSError, URLError):
            pass
        time.sleep(0.25)
    raise RuntimeError("O aplicativo não ficou pronto a tempo. Consulte .local_postgres/app.log.")


def launch(config: LocalConfig, on_ready=None, stop_event=None) -> int:
    import local_postgres

    preflight(config)
    require_free_port(config.port)
    local_postgres.start()
    local_postgres.backup()
    token = secrets.token_urlsafe(32)
    environment = {**os.environ, "SKOPOS_INSTANCE_TOKEN": token, "SKOPOS_DATA_DIR": str(DATA_ROOT)}
    if os.environ.get("SKOPOS_DESKTOP") == "1":
        environment["AUTHLIB_INSECURE_TRANSPORT"] = "1"
        environment["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    log_path = DATA_ROOT / ".local_postgres/app.log"
    process = None
    try:
        with log_path.open("ab") as log:
            log.write(f"\nAbertura do aplicativo: {datetime.now().isoformat()}\n".encode("utf-8"))
            log.flush()
            process = subprocess.Popen(streamlit_command(config), cwd=APP_ROOT,
                                       env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            wait_ready(process, config.port, token)
            if on_ready:
                on_ready(config, token)
            print(f"Skopos pronto em {config.url}")
            if not webbrowser.open(config.url, new=0):
                print("Abra o endereço acima no Chrome ou Edge.")
            print("Fechar a guia não encerra o aplicativo. Use Ctrl+C neste iniciador para encerrar.")
            if stop_event is None:
                return process.wait()
            while process.poll() is None and not stop_event.wait(0.25):
                pass
            return process.returncode or 0
    finally:
        if process is not None and process.poll() is None:
            # Terminate only the child created by this launcher, never another server.
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        # The existing PostgreSQL instance stays running for maintenance/backups.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="start", choices=("start", "configure", "check"))
    naming = parser.add_mutually_exclusive_group()
    naming.add_argument("--company", help="Nome da empresa para gerar skopos.nome.localhost")
    naming.add_argument("--hostname", help="Nome local completo; deve terminar em .localhost")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    try:
        if args.action == "configure":
            try:
                current = load_config()
            except ValueError:
                if args.company is None and args.hostname is None:
                    raise
                # An explicit new name can repair a corrupt public config.
                # Never touch private Secrets or database settings here.
                current = LocalConfig()
            hostname = company_hostname(args.company) if args.company is not None else args.hostname
            chosen = LocalConfig(hostname=hostname if hostname is not None else current.hostname,
                                 port=args.port if args.port is not None else current.port)
            save_config(chosen)
            print(f"Endereço escolhido: {chosen.url}")
            print("Configuração salva. Execute check para validar banco e login antes de abrir.")
            return 0
        if args.company is not None or args.hostname is not None or args.port is not None:
            raise ValueError("Use configure para salvar o nome/porta; start e check usam a configuração salva.")
        chosen = load_config()
        if args.action == "check":
            preflight(chosen)
            print(f"Configuração local conferida para {chosen.url}. O servidor não foi iniciado.")
            return 0
        return launch(chosen)
    except KeyboardInterrupt:
        print("Aplicativo encerrado. O banco e os dados foram preservados.")
        return 0
    except (ValueError, RuntimeError) as exc:
        print(str(exc))
        return 1
    except Exception:
        # Third-party/DB exceptions may include private URLs. Never print them.
        print("Não foi possível abrir o Skopos. Confira a instalação e a configuração local.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
