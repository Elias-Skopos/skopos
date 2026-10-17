"""Individual local credentials and short-lived OIDC state, stored in PostgreSQL."""
import hashlib
import hmac
import json
import secrets
import time
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

import db

PASSWORDS = PasswordHasher()
# Use the same expensive verification for missing usernames.
DUMMY_HASH = PASSWORDS.hash("not-a-user-password-" + uuid4().hex)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def init_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS identity_credentials (
        login TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL,
        password_hash TEXT NOT NULL, failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until INTEGER NOT NULL DEFAULT 0, UNIQUE(issuer,subject))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS identity_codes (
        code_hash TEXT PRIMARY KEY, payload TEXT NOT NULL, nonce TEXT NOT NULL,
        expires_at INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS identity_flows (
        flow_hash TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at INTEGER NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS identity_google_links (
        google_subject TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL,
        UNIQUE(issuer,subject))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS identity_recovery (
        issuer TEXT NOT NULL, subject TEXT NOT NULL, code_hash TEXT NOT NULL,
        failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(issuer,subject))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS identity_email_resets (
        login TEXT PRIMARY KEY, token_hash TEXT NOT NULL, password_hash_at_issue TEXT NOT NULL,
        expires_at INTEGER NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS identity_email_throttle (
        bucket TEXT PRIMARY KEY, window_start INTEGER NOT NULL, attempts INTEGER NOT NULL,
        last_request INTEGER NOT NULL)""")


def create_local_user(email, name, password, installation_id):
    email = email.strip().casefold()
    if not db.re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        raise ValueError("Informe um e-mail válido.")
    if not name.strip() or len(name.strip()) > 120 or not 12 <= len(password) <= 256:
        raise ValueError("Informe seu nome e uma senha com 12 a 256 caracteres.")
    password_hash = PASSWORDS.hash(password)
    with db.connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise ValueError("Esse e-mail já tem um perfil. Entre por ele antes de cadastrar uma senha local.")
        issuer, subject = f"urn:skopos:local:{installation_id}", uuid4().hex
        conn.execute("INSERT INTO users(issuer,subject,email,name,email_verified) VALUES (?,?,?,?,0)", (issuer, subject, email, name.strip()))
        conn.execute("INSERT INTO identity_credentials(login,issuer,subject,password_hash) VALUES (?,?,?,?)", (email, issuer, subject, password_hash))
    return {"issuer": issuer, "subject": subject}


def authenticate(email, password):
    email = email.strip().casefold()
    now = int(time.time())
    if len(email) > 254 or len(password) > 256:
        return None
    with db.connection() as conn:
        suffix = " FOR UPDATE" if getattr(conn, "is_postgres", False) else ""
        if not suffix:
            conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM identity_credentials WHERE login=?" + suffix, (email,)).fetchone()
        if row and row["locked_until"] > now:
            return None
        try:
            valid = PASSWORDS.verify(row["password_hash"] if row else DUMMY_HASH, password)
        except VerificationError:
            valid = False
        if not row:
            return None
        if not valid:
            attempts = row["failed_attempts"] + 1
            conn.execute("UPDATE identity_credentials SET failed_attempts=?,locked_until=? WHERE login=?",
                         (attempts, now+600 if attempts >= 5 else 0, email))
            return None
        conn.execute("UPDATE identity_credentials SET failed_attempts=0,locked_until=0 WHERE login=?", (email,))
        return {"issuer": row["issuer"], "subject": row["subject"]}


def user_info(identity):
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE issuer=? AND subject=?", (identity["issuer"], identity["subject"])).fetchone()
    if not row:
        raise ValueError("O perfil não está disponível.")
    return {"sub": digest(row["issuer"] + "\0" + row["subject"]), "name": row["name"], "email": row["email"],
            "email_verified": bool(row["email_verified"]), "skopos_issuer": row["issuer"], "skopos_subject": row["subject"]}


def set_password(identity, password, current_password=None, google_confirmed=False):
    if not 12 <= len(password) <= 256:
        raise ValueError("Use uma senha com 12 a 256 caracteres.")
    info = user_info(identity)
    if not google_confirmed:
        authenticated = authenticate(info["email"], current_password or "")
        if authenticated != identity:
            raise ValueError("Confirme a senha atual ou entre novamente pelo Google.")
    hashed = PASSWORDS.hash(password)
    with db.connection() as conn:
        other = conn.execute("SELECT issuer,subject FROM identity_credentials WHERE login=?", (info["email"],)).fetchone()
        if other and (other[0], other[1]) != (identity["issuer"], identity["subject"]):
            raise ValueError("Este e-mail pertence a outro perfil local.")
        conn.execute("""INSERT INTO identity_credentials(login,issuer,subject,password_hash) VALUES (?,?,?,?)
            ON CONFLICT(login) DO UPDATE SET password_hash=excluded.password_hash,failed_attempts=0,locked_until=0""",
            (info["email"], identity["issuer"], identity["subject"], hashed))


def create_recovery_code(identity, current_password=None, google_confirmed=False):
    """A new offline recovery secret replaces the previous one after reauthentication."""
    info = user_info(identity)
    if not google_confirmed and authenticate(info["email"], current_password or "") != identity:
        raise ValueError("Confirme a senha atual ou entre novamente pelo Google.")
    code = secrets.token_hex(24)
    with db.connection() as conn:
        conn.execute("""INSERT INTO identity_recovery(issuer,subject,code_hash) VALUES (?,?,?)
            ON CONFLICT(issuer,subject) DO UPDATE SET code_hash=excluded.code_hash,failed_attempts=0,locked_until=0""",
            (identity["issuer"], identity["subject"], digest(code)))
    return code


def recover_password(email, code, password):
    """Consume a high-entropy recovery code once, with transactional retry limits."""
    if not 12 <= len(password) <= 256:
        raise ValueError("Use uma senha com 12 a 256 caracteres.")
    email = email.strip().casefold()
    if len(email) > 254 or len(code) > 128:
        raise ValueError("E-mail ou código inválido. Após várias tentativas, aguarde dez minutos.")
    now = int(time.time())
    identity = None
    with db.connection() as conn:
        suffix = " FOR UPDATE" if getattr(conn, "is_postgres", False) else ""
        if not suffix:
            conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""SELECT r.* FROM identity_recovery r
            JOIN users u ON u.issuer=r.issuer AND u.subject=r.subject WHERE u.email=?""" + suffix, (email,)).fetchone()
        if row and row["locked_until"] <= now:
            if row["code_hash"] and hmac.compare_digest(row["code_hash"], digest(code.strip())):
                identity = {"issuer": row["issuer"], "subject": row["subject"]}
                other = conn.execute("SELECT issuer,subject FROM identity_credentials WHERE login=?", (email,)).fetchone()
                if other and (other[0], other[1]) != (row["issuer"], row["subject"]):
                    raise ValueError("Este e-mail pertence a outro perfil local. Nenhum acesso foi alterado.")
                hashed = PASSWORDS.hash(password)
                conn.execute("""INSERT INTO identity_credentials(login,issuer,subject,password_hash) VALUES (?,?,?,?)
                    ON CONFLICT(login) DO UPDATE SET password_hash=excluded.password_hash,failed_attempts=0,locked_until=0
                    WHERE identity_credentials.issuer=excluded.issuer AND identity_credentials.subject=excluded.subject""",
                    (email, row["issuer"], row["subject"], hashed))
                conn.execute("DELETE FROM identity_recovery WHERE issuer=? AND subject=?", (row["issuer"], row["subject"]))
            else:
                attempts = row["failed_attempts"] + 1 if row["locked_until"] == 0 else 1
                conn.execute("UPDATE identity_recovery SET failed_attempts=?,locked_until=? WHERE issuer=? AND subject=?",
                             (attempts, now+600 if attempts >= 5 else 0, row["issuer"], row["subject"]))
    if not identity:
        raise ValueError("E-mail ou código inválido. Após várias tentativas, aguarde dez minutos.")
    return identity


def request_email_reset(email):
    """Issue a hashed 15-minute token; all callers share the same response."""
    email = email.strip().casefold()
    if not db.re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        raise ValueError("Informe um e-mail válido.")
    now = int(time.time())
    token = None
    with db.connection() as conn:
        suffix = " FOR UPDATE" if getattr(conn, "is_postgres", False) else ""
        if not suffix:
            conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM identity_email_throttle WHERE bucket<>'global' AND last_request<?", (now-86400,))
        buckets = []
        for bucket, limit in (("global", 30), (digest(email), 5)):
            conn.execute("""INSERT INTO identity_email_throttle(bucket,window_start,attempts,last_request)
                VALUES (?,?,0,0) ON CONFLICT(bucket) DO NOTHING""", (bucket, now))
            row = conn.execute("SELECT * FROM identity_email_throttle WHERE bucket=?"+suffix, (bucket,)).fetchone()
            expired = now-row["window_start"] >= 3600
            if (not expired and row["attempts"] >= limit) or (bucket != "global" and now-row["last_request"] < 60):
                return None
            buckets.append((bucket, now if expired else row["window_start"], 1 if expired else row["attempts"]+1))
        for bucket, start, attempts in buckets:
            conn.execute("UPDATE identity_email_throttle SET window_start=?,attempts=?,last_request=? WHERE bucket=?",
                         (start, attempts, now, bucket))
        row = conn.execute("SELECT password_hash FROM identity_credentials WHERE login=?", (email,)).fetchone()
        if row:
            token = secrets.token_urlsafe(32)
            conn.execute("""INSERT INTO identity_email_resets(login,token_hash,password_hash_at_issue,expires_at) VALUES (?,?,?,?)
                ON CONFLICT(login) DO UPDATE SET token_hash=excluded.token_hash,
                password_hash_at_issue=excluded.password_hash_at_issue,expires_at=excluded.expires_at""",
                (email, digest(token), row["password_hash"], now+900))
        conn.execute("DELETE FROM identity_email_resets WHERE expires_at<=?", (now,))
    return token


def cancel_email_reset(email, token):
    with db.connection() as conn:
        conn.execute("DELETE FROM identity_email_resets WHERE login=? AND token_hash=?", (email.strip().casefold(), digest(token)))


def reset_password_by_email(email, token, password):
    if not 12 <= len(password) <= 256:
        raise ValueError("Use uma senha com 12 a 256 caracteres.")
    email = email.strip().casefold()
    if len(token) > 128 or len(email) > 254:
        raise ValueError("O link é inválido ou expirou. Solicite outro e-mail.")
    with db.connection() as conn:
        suffix = " FOR UPDATE" if getattr(conn, "is_postgres", False) else ""
        if not suffix:
            conn.execute("BEGIN IMMEDIATE")
        reset = conn.execute("SELECT * FROM identity_email_resets WHERE login=?"+suffix, (email,)).fetchone()
        if not reset or reset["expires_at"] <= int(time.time()) or not hmac.compare_digest(reset["token_hash"], digest(token)):
            raise ValueError("O link é inválido ou expirou. Solicite outro e-mail.")
        row = conn.execute("SELECT * FROM identity_credentials WHERE login=?"+suffix, (email,)).fetchone()
        if not row or not hmac.compare_digest(row["password_hash"], reset["password_hash_at_issue"]):
            raise ValueError("O link é inválido ou expirou. Solicite outro e-mail.")
        conn.execute("UPDATE identity_credentials SET password_hash=?,failed_attempts=0,locked_until=0 WHERE login=?",
                     (PASSWORDS.hash(password), email))
        conn.execute("DELETE FROM identity_email_resets WHERE login=?", (email,))
        conn.execute("DELETE FROM identity_recovery WHERE issuer=? AND subject=?", (row["issuer"], row["subject"]))
    return {"issuer": row["issuer"], "subject": row["subject"]}


def save_state(table, token, payload, ttl=300, nonce=""):
    if table not in ("identity_codes", "identity_flows"):
        raise ValueError("Invalid state store")
    now = int(time.time())
    with db.connection() as conn:
        conn.execute(f"DELETE FROM {table} WHERE expires_at<?", (now,))
        if table == "identity_codes":
            conn.execute("INSERT INTO identity_codes(code_hash,payload,nonce,expires_at) VALUES (?,?,?,?)",
                         (digest(token), json.dumps(payload), nonce, now+ttl))
        else:
            conn.execute("INSERT INTO identity_flows(flow_hash,payload,expires_at) VALUES (?,?,?)",
                         (digest(token), json.dumps(payload), now+ttl))


def consume_state(table, token):
    if table not in ("identity_codes", "identity_flows"):
        raise ValueError("Invalid state store")
    key = "code_hash" if table == "identity_codes" else "flow_hash"
    with db.connection() as conn:
        suffix = " FOR UPDATE" if getattr(conn, "is_postgres", False) else ""
        if not suffix:
            conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(f"SELECT * FROM {table} WHERE {key}=?"+suffix, (digest(token),)).fetchone()
        if not row or row["consumed"] or row["expires_at"] < int(time.time()):
            return None
        conn.execute(f"UPDATE {table} SET consumed=1 WHERE {key}=?", (digest(token),))
        return json.loads(row["payload"])


def google_identity(claims, target=None, existing_only=False):
    if claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com") or claims.get("email_verified") is not True:
        raise ValueError("O Google precisa confirmar esta identidade e o e-mail.")
    google_sub = claims["sub"]
    with db.connection() as conn:
        linked = conn.execute("SELECT issuer,subject FROM identity_google_links WHERE google_subject=?", (google_sub,)).fetchone()
        if linked:
            identity = {"issuer": linked[0], "subject": linked[1]}
        else:
            previous = conn.execute("SELECT issuer,subject FROM users WHERE subject=? AND issuer IN (?,?)",
                                    (google_sub, "https://accounts.google.com", "accounts.google.com")).fetchall()
            if len(previous) > 1:
                raise ValueError("Há mais de um perfil para este Google. Confira os vínculos antes de continuar.")
            if existing_only and not previous:
                raise ValueError("Este Google ainda não está vinculado a um perfil. Use seu código de recuperação ou entre com a senha local para vincular o Google.")
            if not target and not previous and conn.execute("SELECT 1 FROM users WHERE email=?", (claims["email"].strip().casefold(),)).fetchone():
                raise ValueError("Este e-mail já tem um perfil local. Entre com a senha local ou recupere com seu código; depois vincule o Google em Gerenciar senha local e Google.")
            identity = {"issuer": previous[0][0], "subject": previous[0][1]} if previous else {"issuer": "https://accounts.google.com", "subject": google_sub}
        if target:
            info = user_info(target)
            if info["email"].casefold() != claims["email"].casefold():
                raise ValueError("Use o Google com o mesmo e-mail do seu perfil local.")
            if linked and identity != target:
                raise ValueError("Este Google já está vinculado a outro perfil.")
            existing = conn.execute("SELECT 1 FROM users WHERE issuer=? AND subject=?", (identity["issuer"], identity["subject"])).fetchone()
            if not linked and existing and identity != target:
                raise ValueError("Esse Google já tem um perfil. Entre por ele e cadastre a senha local, preservando seus dados.")
            identity = target
        conn.execute("""INSERT INTO identity_google_links(google_subject,issuer,subject) VALUES (?,?,?)
            ON CONFLICT(google_subject) DO NOTHING""", (google_sub, identity["issuer"], identity["subject"]))
        linked = conn.execute("SELECT issuer,subject FROM identity_google_links WHERE google_subject=?", (google_sub,)).fetchone()
        if (linked[0], linked[1]) != (identity["issuer"], identity["subject"]):
            raise ValueError("Este Google já foi vinculado a outro perfil. Nenhum acesso foi alterado.")
        login = claims["email"].strip().casefold()
        credential = conn.execute("SELECT login FROM identity_credentials WHERE issuer=? AND subject=?",
                                  (identity["issuer"], identity["subject"])).fetchone()
        if credential and credential[0] != login:
            taken = conn.execute("SELECT 1 FROM identity_credentials WHERE login=?", (login,)).fetchone()
            if taken:
                raise ValueError("O novo e-mail já pertence a outro perfil local. Nenhum vínculo foi alterado.")
            conn.execute("UPDATE identity_credentials SET login=? WHERE issuer=? AND subject=?",
                         (login, identity["issuer"], identity["subject"]))
        conn.execute("""INSERT INTO users(issuer,subject,email,name,email_verified) VALUES (?,?,?,?,1)
            ON CONFLICT(issuer,subject) DO UPDATE SET email=excluded.email,name=excluded.name,
            email_verified=1,last_seen_at=CURRENT_TIMESTAMP""",
            (identity["issuer"], identity["subject"], claims["email"].strip().casefold(), claims.get("name", "")))
    return identity
