"""Import a user-selected Google Desktop client into private installation data."""
import json
from pathlib import Path
from uuid import uuid4

from local_paths import APP_ROOT, DATA_ROOT

CLIENT_FILE = DATA_ROOT / ".local_auth/google-desktop-client.json"
BUNDLED_CLIENT_FILE = APP_ROOT / "google/desktop-client.json"


def expected_client_id():
    return json.loads((APP_ROOT / "desktop_defaults.json").read_text(encoding="utf-8"))["google_client_id"]


def parse_credentials(path, expected_id):
    try:
        path = Path(path)
        if path.stat().st_size > 65536:
            raise ValueError
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("Escolha um JSON de credenciais Google válido, com até 64 KB.") from exc
    installed = document.get("installed") if isinstance(document, dict) else None
    if not isinstance(installed, dict):
        raise ValueError("Use o JSON do cliente Aplicativo para computador. O cliente web não serve para esta instalação.")
    if installed.get("client_id") != expected_id:
        raise ValueError("Esse JSON pertence a outro cliente Google. Baixe o cliente de computador configurado para o Skopos.")
    secret = installed.get("client_secret")
    if not isinstance(secret, str) or not secret or len(secret) > 4096 or secret.strip() != secret:
        raise ValueError("O JSON precisa conter o client_secret do cliente para computador.")
    return {"client_id": expected_id, "client_secret": secret}


def load_credentials(expected_id):
    if not CLIENT_FILE.exists():
        return None
    return parse_credentials(CLIENT_FILE, expected_id)


def import_credentials(path, destination=None, expected_id=None):
    values = parse_credentials(path, expected_id or expected_client_id())
    destination = Path(destination) if destination else CLIENT_FILE
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.new")
    temporary.write_text(json.dumps({"installed": values}, indent=2), encoding="utf-8")
    temporary.replace(destination)


def install_bundled_credentials():
    """Apply the explicitly bundled Desktop client without prompting on login."""
    if not BUNDLED_CLIENT_FILE.exists():
        return False
    expected = expected_client_id()
    parse_credentials(BUNDLED_CLIENT_FILE, expected)
    if CLIENT_FILE.exists():
        try:
            parse_credentials(CLIENT_FILE, expected)
            return False  # Preserve a matching client imported by the user.
        except ValueError:
            # Keep an old/invalid configuration privately before changing client.
            backup = CLIENT_FILE.with_name(f"google-client-previous-{uuid4().hex}.json")
            backup.write_bytes(CLIENT_FILE.read_bytes())
    import_credentials(BUNDLED_CLIENT_FILE, expected_id=expected)
    return True
