"""Private, optional Gmail/SMTP configuration and password recovery delivery."""
import json
from pathlib import Path
import re
import smtplib
import ssl
import threading
import tomllib
from email.message import EmailMessage
from urllib.parse import urlencode, urlparse

from local_paths import DATA_ROOT

CONFIG_FILE = DATA_ROOT / ".local_auth/email.json"
SECRETS_FILE = DATA_ROOT / ".streamlit/secrets.toml"


def validate_config(config):
    values = {key: config.get(key, "") for key in ("host", "port", "username", "password", "from_email")}
    values["port"] = int(values["port"] or 587)
    if (not isinstance(values["host"], str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", values["host"])
            or values["port"] not in (465, 587)):
        raise ValueError("Use SMTP com TLS na porta 465 ou 587.")
    for key in ("username", "from_email"):
        if not isinstance(values[key], str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values[key]) or len(values[key]) > 254:
            raise ValueError("Informe e-mails válidos para usuário e remetente.")
    if not isinstance(values["password"], str) or not values["password"] or len(values["password"]) > 4096:
        raise ValueError("Informe a senha de app do serviço de envio.")
    if values["host"].casefold() == "smtp.gmail.com":
        values["host"] = "smtp.gmail.com"
        values["password"] = values["password"].replace(" ", "")
        if len(values["password"]) != 16 or values["from_email"].casefold() != values["username"].casefold():
            raise ValueError("No Gmail, use a senha de app de 16 caracteres e o mesmo e-mail em usuário e remetente.")
    return values


def import_gmail_config(source, destination=None):
    try:
        source = Path(source)
        if source.stat().st_size > 16384:
            raise ValueError
        config = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict) or config.get("host") != "smtp.gmail.com":
            raise ValueError
        values = validate_config(config)
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("Escolha um JSON Gmail válido com e-mail remetente e senha de app de 16 caracteres.") from exc
    target = Path(destination) if destination else CONFIG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.new")
    temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
    temporary.replace(target)


def load_config():
    try:
        if CONFIG_FILE.exists():
            return validate_config(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        if SECRETS_FILE.exists():
            config = tomllib.loads(SECRETS_FILE.read_text(encoding="utf-8")).get("email", {})
            if config:
                return validate_config(config)
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return None


def send_reset(email, token, issuer, config):
    config = validate_config(config)
    origin = urlparse(issuer)
    if origin.scheme not in ("http", "https") or not origin.hostname or origin.username or origin.password:
        raise ValueError("Endereço de recuperação inválido.")
    # The fragment never reaches HTTP access logs and is removed by the form.
    link = issuer + "/reset-email#" + urlencode({"email": email, "token": token})
    message = EmailMessage()
    message["From"] = config["from_email"]
    message["To"] = email
    message["Subject"] = "Redefina sua senha local do Skopos"
    message.set_content(
        "Foi solicitada uma nova senha local do Skopos neste computador.\n\n"
        f"Abra o link no computador em que o Skopos está instalado e aberto:\n{link}\n\n"
        "O link vale por 15 minutos e só pode ser usado uma vez. "
        "Ele não altera a senha do Google. Se você não pediu a recuperação, ignore esta mensagem.\n"
    )
    context = ssl.create_default_context()
    client = (smtplib.SMTP_SSL(config["host"], config["port"], timeout=15, context=context)
              if config["port"] == 465 else smtplib.SMTP(config["host"], config["port"], timeout=15))
    with client as smtp:
        if config["port"] == 587:
            smtp.starttls(context=context)
        smtp.login(config["username"], config["password"])
        smtp.send_message(message)


def dispatch_reset(email, token, issuer, config, logger):
    # Return the same prompt response for known and unknown accounts without
    # exposing SMTP timing or error details to the unauthenticated caller.
    def deliver():
        try:
            send_reset(email, token, issuer, config)
        except Exception:
            import local_identity
            try:
                local_identity.cancel_email_reset(email, token)
            except Exception:
                pass
            logger.warning("password_recovery_delivery_failed code=E01")
    threading.Thread(target=deliver, name="skopos-password-email", daemon=True).start()
