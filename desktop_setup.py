"""Initialize a fresh per-user installation; updates never replace stored data."""
import csv
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from local_config import CONFIG_PATH, LocalConfig, company_hostname, load_config, save_config
from local_paths import APP_ROOT, DATA_ROOT

AUTH_PATH = DATA_ROOT / ".local_auth/settings.json"
KEY_PATH = DATA_ROOT / ".local_auth/signing-key.pem"


def protect_data_directory():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True,
                                stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        sid = next(csv.reader([result.stdout.strip()]))[1]
        subprocess.run(["icacls", str(DATA_ROOT), "/inheritance:r", "/grant:r",
                        f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)


def free_database_port():
    for port in range(5432, 5500):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if os.name == "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                pass
    raise RuntimeError("Não há porta local disponível para preparar o banco.")


def free_app_port():
    for port in range(8501, 8600):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                pass
    raise RuntimeError("Não há porta local disponível para o aplicativo.")


def auth_settings(config=None):
    config = config or load_config()
    values = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    values.update(home=config.url, issuer=config.url+"/identity", api=f"http://127.0.0.1:{config.port}/identity")
    from desktop_google import expected_client_id, load_credentials
    # Adopt the current public Desktop client on upgrade without rotating the
    # installation identity, password credentials, cookies, or local OIDC client.
    values["google_client_id"] = expected_client_id()
    values.pop("google_client_secret", None)
    try:
        google = load_credentials(values.get("google_client_id", ""))
        if google:
            values["google_client_secret"] = google["client_secret"]
    except ValueError:
        # An invalid optional Google file must not prevent local-password access.
        values["google_config_error"] = True
    return values


def setup(company_name="Minha empresa"):
    import db
    import local_postgres

    protect_data_directory()
    if not CONFIG_PATH.exists():
        save_config(LocalConfig(company_hostname(company_name), port=free_app_port()))
    config = load_config()
    if not local_postgres.SETTINGS.exists():
        local_postgres.setup(free_database_port())
    else:
        local_postgres.start()
        local_postgres.backup()
    AUTH_PATH.parent.mkdir(exist_ok=True)
    if not AUTH_PATH.exists():
        if KEY_PATH.exists():
            raise RuntimeError("Há uma chave existente sem configuração de acesso; nenhum arquivo será substituído.")
        defaults = json.loads((APP_ROOT / "desktop_defaults.json").read_text(encoding="utf-8"))
        values = {"installation_id": uuid4().hex, "client_id": "skopos-local-"+uuid4().hex,
                  "client_secret": secrets.token_urlsafe(48), "cookie_secret": secrets.token_urlsafe(48),
                  "google_client_id": defaults.get("google_client_id", ""), "initial_company_name": company_name}
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        KEY_PATH.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        AUTH_PATH.write_text(json.dumps(values, indent=2), encoding="utf-8")
    from desktop_google import install_bundled_credentials
    install_bundled_credentials()
    values = auth_settings(config)
    secret_file = DATA_ROOT / ".streamlit/secrets.toml"
    url = local_postgres.database_url(local_postgres.read_settings())
    if not secret_file.exists():
        secret_file.parent.mkdir(exist_ok=True)
        encode = json.dumps
        secret_file.write_text(f'''[auth]
redirect_uri = {encode(config.url+"/oauth2callback")}
cookie_secret = {encode(values["cookie_secret"])}
[auth.local]
client_id = {encode(values["client_id"])}
client_secret = {encode(values["client_secret"])}
server_metadata_url = {encode(values["api"]+"/.well-known/openid-configuration")}
[auth.local.client_kwargs]
scope = "openid profile email"
code_challenge_method = "S256"
[database]
url = {encode(url)}
[desktop]
issuer = {encode(values["issuer"])}
''', encoding="utf-8")
    db.configure_database(url)
    db.init_db()
    return config
