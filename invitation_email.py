"""Optional SMTP delivery; the invitation itself remains in the local database."""
import smtplib
import ssl
from email.message import EmailMessage


def send_invitation(email: str, company: str, role: str, config: dict) -> bool:
    if not config.get("host") or not config.get("from_email") or not config.get("app_url"):
        return False
    message = EmailMessage()
    message["From"] = config["from_email"]
    message["To"] = email
    message["Subject"] = f"Convite para {company} no Skopos"
    message.set_content(
        f"Você foi convidado para {company}, com o perfil {role}.\n\n"
        f"Acesse {config['app_url']} e entre com o Google usando {email}. "
        "O convite aparecerá para você aceitar ou recusar e é válido por sete dias.\n"
    )
    port = int(config.get("port", 587))
    context = ssl.create_default_context()
    client = smtplib.SMTP_SSL(config["host"], port, timeout=15, context=context) if port == 465 else smtplib.SMTP(config["host"], port, timeout=15)
    with client as smtp:
        if port != 465:
            smtp.starttls(context=context)
        if config.get("username"):
            smtp.login(config["username"], config.get("password", ""))
        smtp.send_message(message)
    return True
