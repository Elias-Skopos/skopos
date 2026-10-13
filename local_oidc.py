"""Loopback OIDC provider: Authlib code flow, Argon2 accounts and Google PKCE.

Mounted only by the installed edition. Streamlit uses its native st.login/st.user.
"""
import base64
import hmac
import json
from pathlib import Path
import secrets
import time
from urllib.parse import urlencode

from authlib.integrations.flask_oauth2 import AuthorizationServer
from authlib.integrations.requests_client import OAuth2Session
from authlib.oauth2.rfc6749 import AuthorizationCodeMixin, ClientMixin, grants
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oidc.core.grants import OpenIDCode
from flask import Flask, abort, jsonify, redirect, render_template_string, request, session, send_file
from joserfc.jwk import RSAKey, KeySet
from joserfc import jwt
from joserfc.jwt import JWTClaimsRegistry
import requests

import db
import local_identity as identities
from local_paths import APP_ROOT

FORM = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skopos · Acesso</title><style>
*{box-sizing:border-box}body{margin:0;font:16px system-ui;color:#171927;background:#fff}.layout{display:flex;min-height:100vh}
.left,.right{width:50%;padding:5vw;display:flex;flex-direction:column;justify-content:center}.left>div{max-width:470px;width:100%;margin:auto}
.right{background:#625fe9;color:white;text-align:center;border-radius:14px 0 0 14px}.logo{width:100%;max-width:420px;margin-bottom:36px}
h1{font-size:36px;letter-spacing:-1px}p{line-height:1.6;color:#73798b}.right p{color:#ffffffce}.art{width:100%;max-width:570px;margin:auto}
label{display:block;margin-top:16px}input{width:100%;border:1px solid #d9d8ed;border-radius:10px;padding:13px;margin:6px 0;font:inherit}
button,.button{display:block;text-align:center;width:100%;padding:15px;margin-top:18px;border:0;border-radius:10px;background:#625fe9;color:#fff;text-decoration:none;font:inherit;cursor:pointer}
a{color:#514ed5}.secondary{background:#efeeff;color:#514ed5}.error{background:#efeeff;color:#514ed5;padding:14px;border-radius:10px}
.small{font-size:13px} @media(max-width:760px){.layout{display:block}.left,.right{width:100%;padding:32px 24px}.right{border-radius:14px 14px 0 0}}
</style><body><div class="layout"><section class="left"><div><img class="logo" src="{{ issuer }}/assets/logo_login.svg" alt="Skopos">
<h1>{{ title }}</h1><p>{{ description }}</p>{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
{% if mode == 'register' %}<label>Seu nome<input name="name" maxlength="120" required autocomplete="name"></label>{% endif %}
{% if mode != 'password' %}<label>E-mail<input type="email" name="email" maxlength="254" required autocomplete="username"></label>{% endif %}
{% if mode == 'password' and not google_fresh %}<label>Senha atual<input type="password" name="current_password" required autocomplete="current-password"></label>{% endif %}
<label>{{ 'Nova senha' if mode == 'password' else 'Senha' }}<input type="password" name="password" required maxlength="256" minlength="{{ 12 if mode != 'login' else 1 }}" autocomplete="{{ 'current-password' if mode == 'login' else 'new-password' }}"></label>
{% if mode != 'login' %}<label>Repita a senha<input type="password" name="repeat" required minlength="12" maxlength="256" autocomplete="new-password"></label>{% endif %}
<button>{{ 'Criar perfil local' if mode == 'register' else 'Salvar senha local' if mode == 'password' else 'Entrar' }}</button></form>
{% if mode == 'login' %}<a class="button secondary" href="{{ issuer }}/register">Criar perfil local</a>
{% if google_enabled %}<a class="button secondary" href="{{ issuer }}/google/start">Continuar com Google</a>{% endif %}
{% if google_pending %}<p class="small">Para usar Google, clique em Configurar Google: importar JSON na janela do iniciador. Use as credenciais de Aplicativo para computador e reabra o Skopos.</p>{% endif %}
{% endif %}
{% if mode == 'password' %}{% if google_enabled %}<a class="button secondary" href="{{ issuer }}/google/start?link=1">Vincular ou confirmar Google</a>{% endif %}<a class="button secondary" href="{{ home }}">Voltar ao Skopos</a>{% endif %}
<p class="small">A senha local pertence ao Skopos e é independente da senha do Google. Seus dados ficam neste computador.</p>
</div></section><section class="right"><h2>Sua empresa em equilíbrio.</h2><p>Faturamento, caixa e estoque em um só lugar.</p>
<img class="art" src="{{ issuer }}/assets/login_illustration.svg" alt="Ilustração Skopos"></section></div></body></html>'''


def create_provider(settings, key_path: Path):
    issuer, home = settings["issuer"], settings["home"]
    api = settings["api"]
    client_id, client_secret = settings["client_id"], settings["client_secret"]
    private_key = RSAKey.import_key(key_path.read_bytes())
    app = Flask("skopos_identity")
    app.secret_key = settings["cookie_secret"]
    app.config.update(SESSION_COOKIE_NAME="skopos_identity", SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=16384)

    class Client(ClientMixin):
        def get_client_id(self): return client_id
        def get_default_redirect_uri(self): return home + "/oauth2callback"
        def get_allowed_scope(self, scope): return " ".join(s for s in (scope or "").split() if s in ("openid", "profile", "email"))
        def check_redirect_uri(self, uri): return uri == self.get_default_redirect_uri()
        def check_client_secret(self, secret): return hmac.compare_digest((secret or "").encode(), client_secret.encode())
        def check_endpoint_auth_method(self, method, endpoint): return method in ("client_secret_basic", "client_secret_post")
        def check_response_type(self, response_type): return response_type == "code"
        def check_grant_type(self, grant_type): return grant_type == "authorization_code"

    class Code(AuthorizationCodeMixin):
        def __init__(self, data):
            self.data = data
            self.code_challenge = data.get("code_challenge")
            self.code_challenge_method = data.get("code_challenge_method")
        def get_redirect_uri(self): return self.data["redirect_uri"]
        def get_scope(self): return self.data["scope"]
        def get_nonce(self): return self.data["nonce"]
        def get_auth_time(self): return self.data["auth_time"]
        def get_acr(self): return None
        def get_amr(self): return [self.data.get("method", "pwd")]

    class Grant(grants.AuthorizationCodeGrant):
        def save_authorization_code(self, code, req):
            payload = {"identity": req.user, "redirect_uri": req.payload.redirect_uri,
                       "scope": req.payload.scope, "nonce": req.payload.data.get("nonce", ""),
                       "auth_time": int(time.time()), "method": session.get("method", "pwd"),
                       "code_challenge": req.payload.data.get("code_challenge"),
                       "code_challenge_method": req.payload.data.get("code_challenge_method")}
            identities.save_state("identity_codes", code, payload, ttl=60, nonce=payload["nonce"])
        def query_authorization_code(self, code, client):
            payload = identities.consume_state("identity_codes", code)
            return Code(payload) if payload else None
        def delete_authorization_code(self, code): pass  # consumed atomically when queried
        def authenticate_user(self, code): return code.data["identity"]

    class OIDC(OpenIDCode):
        DEFAULT_EXPIRES_IN = 3600
        def resolve_client_private_key(self, client): return private_key
        def get_client_algorithm(self, client): return "RS256"
        def get_client_claims(self, client): return {"iss": issuer, "aud": [client_id]}
        def get_encode_header(self, client): return {"alg": "RS256", "kid": "skopos-local"}
        def generate_user_info(self, user, scope): return identities.user_info(user)
        def exists_nonce(self, nonce, req):
            with db.connection() as conn:
                return bool(conn.execute("SELECT 1 FROM identity_codes WHERE nonce=? AND expires_at>?", (nonce, int(time.time()))).fetchone())

    oauth = AuthorizationServer(app, query_client=lambda cid: Client() if cid == client_id else None,
                                save_token=lambda token, req: None)
    oauth.register_grant(Grant, [OIDC(require_nonce=True), CodeChallenge(required=True)])

    def current():
        if session.get("expires", 0) < time.time():
            session.pop("identity", None)
        return session.get("identity")

    def csrf_check():
        expected = session.get("csrf", "")
        if not expected or not hmac.compare_digest(request.form.get("csrf", "").encode(), expected.encode()):
            abort(400)

    def display(mode, error=""):
        csrf = session.setdefault("csrf", secrets.token_urlsafe(32))
        return render_template_string(FORM, mode=mode, issuer=issuer, home=home, csrf=csrf, error=error,
             title={"login":"Faça seu login", "register":"Crie seu perfil", "password":"Seu acesso local"}[mode],
             description={"login":"Entre com sua senha local ou com o Google.", "register":"Uma conta individual para usar o Skopos neste computador.",
                          "password":"Use os dois acessos no mesmo perfil, com as mesmas empresas e permissões."}[mode],
             google_enabled=bool(settings.get("google_client_id") and settings.get("google_client_secret")),
             google_pending=bool(settings.get("google_client_id") and not settings.get("google_client_secret")),
             google_fresh=session.get("google_until", 0) > time.time())

    @app.before_request
    def guard_host():
        from urllib.parse import urlparse
        allowed = {urlparse(home).netloc, urlparse(api).netloc}
        if request.host not in allowed:
            abort(400)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.get("/.well-known/openid-configuration")
    def discovery():
        return jsonify(issuer=issuer, authorization_endpoint=issuer+"/authorize", token_endpoint=api+"/token",
                       jwks_uri=api+"/jwks", end_session_endpoint=issuer+"/logout", response_types_supported=["code"],
                       subject_types_supported=["public"], id_token_signing_alg_values_supported=["RS256"],
                       scopes_supported=["openid", "profile", "email"], grant_types_supported=["authorization_code"],
                       token_endpoint_auth_methods_supported=["client_secret_basic", "client_secret_post"],
                       code_challenge_methods_supported=["S256"])

    @app.get("/jwks")
    def jwks():
        key = private_key.as_dict(private=False)
        key.update(kid="skopos-local", use="sig", alg="RS256")
        return jsonify(keys=[key])

    @app.route("/authorize", methods=["GET", "POST"])
    def authorize():
        identity = current()
        if request.method == "GET":
            try:
                oauth.get_consent_grant(end_user=identity)
            except Exception:
                return "Solicitação de acesso inválida. Volte ao Skopos e tente novamente.", 400
            if request.args.get("code_challenge_method") != "S256":
                return "O acesso exige PKCE S256.", 400
            session["authorization"] = request.full_path
            if not identity or request.args.get("prompt") == "login":
                return display("login")
        else:
            csrf_check()
            identity = identities.authenticate(request.form.get("email", ""), request.form.get("password", ""))
            if not identity:
                return display("login", "E-mail ou senha inválidos. Após várias tentativas, aguarde dez minutos."), 401
            session.update(identity=identity, expires=time.time()+900, method="pwd", google_until=0)
        # The same validated query is retained on POST; Authlib validates it again.
        return oauth.create_authorization_response(grant_user=identity)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            csrf_check()
            try:
                if request.form.get("password") != request.form.get("repeat"):
                    raise ValueError("As senhas devem ser iguais.")
                identity = identities.create_local_user(request.form.get("email", ""), request.form.get("name", ""),
                                request.form.get("password", ""), settings["installation_id"])
                session.update(identity=identity, expires=time.time()+900, method="pwd", google_until=0)
                return redirect(issuer+session.get("authorization", "/account"))
            except ValueError as exc:
                return display("register", str(exc)), 400
        return display("register")

    @app.route("/account", methods=["GET", "POST"])
    def account():
        identity = current()
        if not identity:
            return redirect(home)
        if request.method == "POST":
            csrf_check()
            try:
                if request.form.get("password") != request.form.get("repeat"):
                    raise ValueError("As senhas devem ser iguais.")
                identities.set_password(identity, request.form.get("password", ""), request.form.get("current_password"),
                                        google_confirmed=session.get("google_until", 0) > time.time())
                return display("password", "Senha local salva. Os dois acessos usam este mesmo perfil.")
            except ValueError as exc:
                return display("password", str(exc)), 400
        return display("password")

    @app.post("/token")
    def token():
        return oauth.create_token_response()

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(home)

    @app.get("/assets/<name>")
    def asset(name):
        if name not in ("logo_login.svg", "login_illustration.svg"):
            abort(404)
        return send_file(APP_ROOT / "assets" / name)

    @app.get("/google/start")
    def google_start():
        google_client = settings.get("google_client_id")
        if not google_client or not settings.get("google_client_secret"):
            return display("login", "Configure o Google na janela do iniciador: importe o JSON do cliente Aplicativo para computador e reabra o Skopos. Código G00."), 400
        verifier, nonce = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        browser = session.setdefault("browser", secrets.token_urlsafe(32))
        target = current() if request.args.get("link") == "1" else None
        if request.args.get("link") == "1" and not target:
            return redirect(home)
        redirect_uri = api+"/google/callback"
        client = OAuth2Session(google_client, redirect_uri=redirect_uri, scope="openid email profile", code_challenge_method="S256")
        url, state = client.create_authorization_url("https://accounts.google.com/o/oauth2/v2/auth", code_verifier=verifier, nonce=nonce, prompt="select_account")
        identities.save_state("identity_flows", state, {"verifier":verifier, "nonce":nonce, "browser":identities.digest(browser),
                            "target":target, "authorization":session.get("authorization"), "redirect_uri":redirect_uri})
        return redirect(url)

    @app.get("/google/callback")
    def google_callback():
        payload = identities.consume_state("identity_flows", request.args.get("state", ""))
        if not payload or request.args.get("error") or not request.args.get("code"):
            return "O acesso Google expirou ou foi cancelado. Volte ao Skopos.", 400
        stage = "token"
        try:
            client = OAuth2Session(settings["google_client_id"], client_secret=settings.get("google_client_secret"),
                                   redirect_uri=payload["redirect_uri"], token_endpoint_auth_method="client_secret_post")
            token = client.fetch_token("https://oauth2.googleapis.com/token", code=request.args["code"], code_verifier=payload["verifier"], timeout=20)
            stage = "certificates"
            response = requests.get("https://www.googleapis.com/oauth2/v3/certs", timeout=15)
            response.raise_for_status()
            stage = "claims"
            decoded = jwt.decode(token["id_token"], KeySet.import_key_set(response.json()), algorithms=["RS256"])
            claims = decoded.claims
            JWTClaimsRegistry(leeway=30, iss={"essential":True,"values":["https://accounts.google.com", "accounts.google.com"]},
                aud={"essential":True,"value":settings["google_client_id"]}, nonce={"essential":True,"value":payload["nonce"]},
                exp={"essential":True}, sub={"essential":True}).validate(claims)
            if claims.get("email_verified") is not True:
                raise ValueError
            ticket = secrets.token_urlsafe(48)
            stage = "completion"
            payload["claims"] = dict(claims)
            identities.save_state("identity_flows", ticket, payload, ttl=60)
            return redirect(issuer+"/google/complete?"+urlencode({"ticket":ticket}))
        except Exception as exc:
            oauth_error = getattr(exc, "error", None)
            if oauth_error in ("invalid_client", "invalid_request", "unauthorized_client"):
                code, message = "G01", "O Google recusou a configuração do cliente. Importe novamente o JSON correto na janela do iniciador e reabra o Skopos."
            elif oauth_error == "invalid_grant":
                code, message = "G02", "A autorização Google expirou ou já foi usada. Volte ao Skopos e comece um novo login."
            elif isinstance(exc, requests.RequestException):
                code, message = "G03", "Não foi possível conectar ao Google. Confira a conexão e tente novamente."
            elif stage == "claims":
                code, message = "G04", "O Google respondeu, mas a identidade não passou na validação. Confira a data e a hora do computador e comece um novo login."
            else:
                code, message = "G05", "Não foi possível concluir a validação Google. Volte ao Skopos e tente novamente."
            # Controlled codes only: never log exception bodies, tokens, or credentials.
            app.logger.warning("google_login_failed code=%s stage=%s", code, stage)
            return f"{message} Código {code}.", 400

    @app.get("/google/complete")
    def google_complete():
        payload = identities.consume_state("identity_flows", request.args.get("ticket", ""))
        if not payload or not hmac.compare_digest(payload["browser"], identities.digest(session.get("browser", ""))):
            abort(400)
        try:
            target = payload.get("target")
            if target and current() != target:
                abort(400)
            identity = identities.google_identity(payload["claims"], target)
            session.update(identity=identity, expires=time.time()+900, method="google", google_until=time.time()+300)
            if target:
                return redirect(issuer+"/account")
            return redirect(issuer+payload["authorization"] if payload.get("authorization") else issuer+"/account")
        except ValueError as exc:
            return display("login", str(exc)), 400

    return app
