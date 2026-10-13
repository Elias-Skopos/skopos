import base64
import hashlib
import json
import os
import time
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from joserfc import jwt
from joserfc.jwk import RSAKey
import requests
from streamlit.testing.v1 import AppTest

import db
import local_identity
from local_oidc import create_provider

ROOT = Path(__file__).resolve().parents[1]


class PublicDemoTests(unittest.TestCase):
    def test_dark_demo_uses_dark_charts_on_every_page_without_private_storage(self):
        with patch("db.connection", side_effect=AssertionError("No private storage")), \
                patch("demo_ui.st.context", SimpleNamespace(theme=SimpleNamespace(type="dark"))):
            at = AppTest.from_file(str(ROOT / "online_app.py"), default_timeout=20)
            at.query_params["view"] = "demo"
            at.run()
            for page in ("Visão geral", "Vendas", "Estoque", "Contas", "Curva ABC"):
                at.radio(key="public_demo_page").set_value(page).run()
                self.assertFalse(at.exception, page)
                for chart in at.get("plotly_chart"):
                    spec = json.loads(chart.proto.spec)
                    self.assertEqual(chart.proto.theme, "streamlit")
                    self.assertNotIn("paper_bgcolor", spec["layout"])
                    self.assertNotIn("font", spec["layout"])

    def test_cloud_switch_routes_before_accessing_any_private_database(self):
        with patch("db.connection", side_effect=AssertionError("Public edition must never open private storage")):
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
            at.secrets = {"distribution":{"edition":"public"}}
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(at.title[0].value, "Conheça o Skopos")
            at.button(key="enter_public_demo").click().run()
            self.assertFalse(at.exception)

    def test_public_page_and_every_demo_page_work_without_login_or_database(self):
        with patch("db.connection", side_effect=AssertionError("Public demo must never open a real database")), \
             patch("requests.sessions.Session.request", side_effect=AssertionError("No external request")):
            at = AppTest.from_file(str(ROOT / "online_app.py"), default_timeout=20).run()
            self.assertFalse(at.exception)
            self.assertTrue(at.button[0].disabled)
            at.button(key="enter_public_demo").click().run()
            self.assertFalse(at.exception)
            self.assertTrue(any("fictícios" in item.value for item in at.info))
            for page in ("Visão geral", "Vendas", "Estoque", "Contas", "Curva ABC"):
                at.radio(key="public_demo_page").set_value(page).run()
                self.assertFalse(at.exception, page)
            self.assertFalse(at.file_uploader)
            self.assertFalse(any("Salvar" in x.label or "Excluir" in x.label for x in at.button))
            at.button(key="demo_back").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.title[0].value, "Conheça o Skopos")


class LocalOIDCTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skopos-identity-")
        self.addCleanup(self.temp.cleanup)
        for p in (patch.object(db, "DB_PATH", Path(self.temp.name)/"test.db"), patch.object(db, "DATABASE_URL", ""),
                  patch.dict(os.environ, {"AUTHLIB_INSECURE_TRANSPORT":"1"})):
            p.start()
            self.addCleanup(p.stop)
        db.init_db()
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.key_path = Path(self.temp.name)/"key.pem"
        self.key_path.write_bytes(self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        self.settings = {"home":"http://skopos.test.localhost:8501", "issuer":"http://skopos.test.localhost:8501/identity",
                         "api":"http://127.0.0.1:8501/identity", "client_id":"local-client", "client_secret":"local-client-secret",
                         "cookie_secret":"cookie-secret-for-tests-with-sufficient-length", "installation_id":"installation-test",
                         "google_client_id":"test-google-client", "google_client_secret":"test-google-secret"}
        self.provider = create_provider(self.settings, self.key_path)
        self.client = self.provider.test_client()
        self.base = self.settings["home"]

    def request(self, method, path, **kwargs):
        return getattr(self.client, method)(path, base_url=self.base, **kwargs)

    def csrf(self, response):
        return re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True)).group(1)

    def authorization(self, nonce="unique-test-nonce"):
        verifier = "v" * 50
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        query = {"client_id":"local-client", "redirect_uri":self.base+"/oauth2callback", "response_type":"code",
                 "scope":"openid profile email", "state":"browser-state", "nonce":nonce,
                 "code_challenge":challenge, "code_challenge_method":"S256"}
        response = self.request("get", "/authorize", query_string=query)
        return query, response, verifier

    def test_account_and_signed_oidc_code_flow_are_individual_and_single_use(self):
        identity = local_identity.create_local_user("owner@example.invalid", "Owner", "long-test-password-123", "installation-test")
        company = db.create_company("Empresa local", identity["issuer"], identity["subject"])
        query, response, verifier = self.authorization()
        self.assertEqual(response.status_code, 200)
        response = self.request("post", "/authorize", query_string=query, data={"csrf":self.csrf(response), "email":"owner@example.invalid", "password":"long-test-password-123"})
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        code = parse_qs(urlparse(response.location).query)["code"][0]
        headers = {"Authorization":"Basic "+base64.b64encode(b"local-client:local-client-secret").decode()}
        payload = {"grant_type":"authorization_code", "code":code, "redirect_uri":self.base+"/oauth2callback", "code_verifier":verifier}
        token = self.request("post", "/token", data=payload, headers=headers)
        self.assertEqual(token.status_code, 200, token.get_data(as_text=True))
        decoded = jwt.decode(token.json["id_token"], RSAKey.import_key(self.key_path.read_bytes()), algorithms=["RS256"])
        self.assertEqual(decoded.claims["nonce"], query["nonce"])
        self.assertEqual(decoded.claims["skopos_issuer"], identity["issuer"])
        self.assertEqual(db.companies_for_user(decoded.claims["skopos_issuer"], decoded.claims["skopos_subject"])[0]["id"], company)
        self.assertEqual(self.request("post", "/token", data=payload, headers=headers).status_code, 400)
        self.assertNotEqual(db.query_df("SELECT password_hash FROM identity_credentials").iloc[0]["password_hash"], "long-test-password-123")

    def test_passwords_csrf_client_redirect_and_retry_lock_are_enforced(self):
        local_identity.create_local_user("owner@example.invalid", "Owner", "long-test-password-123", "installation-test")
        query, response, verifier = self.authorization()
        self.assertEqual(self.request("post", "/authorize", query_string=query, data={"email":"owner@example.invalid", "password":"long-test-password-123"}).status_code, 400)
        for _ in range(5):
            self.assertIsNone(local_identity.authenticate("owner@example.invalid", "wrong-password"))
        self.assertIsNone(local_identity.authenticate("owner@example.invalid", "long-test-password-123"))
        query["redirect_uri"] = "https://attacker.invalid/callback"
        response = self.request("get", "/authorize", query_string=query)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(local_identity.consume_state("identity_codes", "unknown"))

    def test_google_can_keep_existing_company_and_gain_local_password_without_email_merging(self):
        claims = {"iss":"https://accounts.google.com", "sub":"verified-google-subject", "email":"owner@example.invalid", "email_verified":True, "name":"Owner"}
        original = {"issuer":claims["iss"], "subject":claims["sub"]}
        db.register_identity(original["issuer"], original["subject"], claims["email"], "Owner", True)
        company = db.create_company("Empresa preservada", original["issuer"], original["subject"])
        google = local_identity.google_identity(claims)
        self.assertEqual(google, original)
        local_identity.set_password(google, "long-test-password-123", google_confirmed=True)
        local = local_identity.authenticate(claims["email"], "long-test-password-123")
        self.assertEqual(local, google)
        self.assertEqual(db.companies_for_user(local["issuer"], local["subject"])[0]["id"], company)
        with self.assertRaises(ValueError):
            local_identity.create_local_user(claims["email"], "Fake", "another-long-password-123", "installation-test")
        other = local_identity.create_local_user("other@example.invalid", "Other", "another-long-password-123", "installation-test")
        with self.assertRaises(ValueError):
            local_identity.google_identity(claims, target=other)

    def test_google_uses_pkce_and_completion_is_bound_to_starting_browser(self):
        response = self.request("get", "/google/start")
        params = parse_qs(urlparse(response.location).query)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["redirect_uri"], ["http://127.0.0.1:8501/identity/google/callback"])
        self.assertIn("nonce", params)
        local_identity.save_state("identity_flows", "stolen-ticket", {"browser":"wrong-browser", "claims":{}})
        self.assertEqual(self.request("get", "/google/complete?ticket=stolen-ticket").status_code, 400)

    def google_response(self, uri, body):
        response = requests.Response()
        response.status_code = 200
        response.url = uri
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps(body).encode()
        return response

    def test_google_callback_sends_desktop_secret_and_validates_complete_identity(self):
        self.check_google_callback(False)

    def test_native_google_callback_returns_to_original_window(self):
        self.check_google_callback(True)

    def check_google_callback(self, desktop):
        self.authorization()
        start = self.request("get", "/google/start", headers={"User-Agent":"SkoposDesktop/1.0"} if desktop else {})
        if desktop:
            script = re.search(r'api.open_google\((.+?)\)', start.get_data(as_text=True)).group(1)
            destination = json.loads(script)
        else:
            destination = start.location
        params = parse_qs(urlparse(destination).query)
        claims = {"iss":"https://accounts.google.com", "sub":"google-owner", "email":"google@example.invalid",
                  "email_verified":True, "name":"Google owner", "aud":"test-google-client",
                  "nonce":params["nonce"][0], "iat":int(time.time()), "exp":int(time.time())+120}
        google_key = RSAKey.import_key(self.key)
        public = google_key.as_dict(private=False)
        public["kid"] = "google-test"
        signed = jwt.encode({"alg":"RS256", "kid":"google-test"}, claims, google_key)
        def transport(session, request, **kwargs):
            if request.url == "https://oauth2.googleapis.com/token":
                body = parse_qs(request.body)
                self.assertEqual(body["client_secret"], ["test-google-secret"])
                self.assertEqual(body["client_id"], ["test-google-client"])
                challenge = base64.urlsafe_b64encode(hashlib.sha256(body["code_verifier"][0].encode()).digest()).decode().rstrip("=")
                self.assertEqual(challenge, params["code_challenge"][0])
                return self.google_response(request.url, {"id_token":signed, "access_token":"test-access-token", "token_type":"Bearer"})
            self.assertEqual(request.url, "https://www.googleapis.com/oauth2/v3/certs")
            return self.google_response(request.url, {"keys":[public]})
        with patch("requests.sessions.Session.send", new=transport):
            response = self.client.get("/google/callback", base_url="http://127.0.0.1:8501",
                                       query_string={"state":params["state"][0], "code":"test-auth-code"})
        if desktop:
            self.assertEqual(response.status_code, 200)
            self.assertIn("Volte à janela do Skopos", response.get_data(as_text=True))
            destination = self.request("get", "/google/poll").json["complete"]
        else:
            self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
            destination = response.location
        location = urlparse(destination)
        response = self.request("get", location.path.removeprefix("/identity")+"?"+location.query)
        self.assertEqual(response.status_code, 302)
        location = urlparse(response.location)
        response = self.request("get", location.path.removeprefix("/identity")+"?"+location.query)
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        self.assertEqual(urlparse(response.location).path, "/oauth2callback")
        self.assertEqual(db.query_df("SELECT email FROM users").iloc[0]["email"], "google@example.invalid")
        self.assertEqual(self.client.get("/google/callback", base_url="http://127.0.0.1:8501",
                                        query_string={"state":params["state"][0], "code":"test-auth-code"}).status_code, 400)

    def test_desktop_google_handoff_stays_bound_to_original_window_and_is_single_use(self):
        self.authorization()
        start = self.request("get", "/google/start", headers={"User-Agent":"SkoposDesktop/1.0"})
        self.assertEqual(start.status_code, 200)
        self.assertIn("pywebview.api.open_google", start.get_data(as_text=True))
        self.assertIn("script-src 'nonce-", start.headers["Content-Security-Policy"])
        with self.client.session_transaction(base_url=self.base) as state:
            result_key = state["desktop_result"]
            browser = local_identity.digest(state["browser"])
        self.assertTrue(self.request("get", "/google/poll").json["pending"])
        outsider = self.provider.test_client()
        self.assertEqual(outsider.get("/google/poll", base_url=self.base).status_code, 400)
        claims = {"iss":"https://accounts.google.com", "sub":"desktop-google", "email":"desktop@example.invalid",
                  "email_verified":True, "name":"Desktop"}
        local_identity.save_state("identity_flows", "desktop-ticket", {"browser":browser, "claims":claims})
        local_identity.save_state("identity_flows", result_key, {"browser":browser, "ticket":"desktop-ticket"})
        result = self.request("get", "/google/poll")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.request("get", "/google/poll").status_code, 400)
        location = urlparse(result.json["complete"])
        complete = self.request("get", location.path.removeprefix("/identity")+"?"+location.query)
        self.assertEqual(complete.status_code, 302)
        self.assertEqual(self.request("get", "/google/complete?ticket=desktop-ticket").status_code, 400)

    def test_google_errors_do_not_expose_provider_response_or_credentials(self):
        start = self.request("get", "/google/start")
        state = parse_qs(urlparse(start.location).query)["state"][0]
        def transport(session, request, **kwargs):
            response = self.google_response(request.url, {"error":"invalid_request", "error_description":"DO_NOT_EXPOSE_THIS_TOKEN_OR_SECRET"})
            response.status_code = 400
            return response
        with patch("requests.sessions.Session.send", new=transport), self.assertLogs("skopos_identity", level="WARNING") as captured:
            response = self.client.get("/google/callback", base_url="http://127.0.0.1:8501",
                                       query_string={"state":state, "code":"private-auth-code"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("G01", response.get_data(as_text=True))
        for text in (response.get_data(as_text=True), " ".join(captured.output)):
            self.assertNotIn("DO_NOT_EXPOSE_THIS_TOKEN_OR_SECRET", text)
            self.assertNotIn("private-auth-code", text)

    def test_unconfigured_google_preserves_local_access_and_requests_import(self):
        self.settings.pop("google_client_secret")
        provider = create_provider(self.settings, self.key_path)
        response = provider.test_client().get("/google/start", base_url=self.base)
        self.assertEqual(response.status_code, 400)
        self.assertIn("G00", response.get_data(as_text=True))

    def test_existing_google_issuer_variant_and_verified_email_change_preserve_profile(self):
        claims = {"iss":"https://accounts.google.com", "sub":"old-google-id", "email":"first@example.invalid", "email_verified":True}
        db.register_identity("accounts.google.com", "old-google-id", claims["email"], "Owner", True)
        company = db.create_company("Empresa antiga", "accounts.google.com", "old-google-id")
        identity = local_identity.google_identity(claims)
        self.assertEqual(identity, {"issuer":"accounts.google.com", "subject":"old-google-id"})
        local_identity.set_password(identity, "long-test-password-123", google_confirmed=True)
        local_identity.google_identity({**claims, "email":"updated@example.invalid"})
        self.assertEqual(local_identity.authenticate("updated@example.invalid", "long-test-password-123"), identity)
        self.assertEqual(db.companies_for_user(identity["issuer"], identity["subject"])[0]["id"], company)


if __name__ == "__main__":
    unittest.main()
