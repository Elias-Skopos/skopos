"""Company onboarding, batch invitations, permissions and legacy data isolation."""
from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

import db
from invitation_email import send_invitation

ROOT = Path(__file__).resolve().parents[1]


class AccountFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skopos-account-")
        self.addCleanup(self.temp.cleanup)
        for p in (patch.object(db, "DB_PATH", Path(self.temp.name)/"test.db"),
                  patch.object(db, "DATABASE_URL", ""), patch.dict(os.environ, {"SKOPOS_DATABASE_URL": ""})):
            p.start()
            self.addCleanup(p.stop)
        db.init_db()
        db.register_identity("test", "owner", "owner@example.invalid", "Owner", True)
        db.register_identity("test", "viewer", "viewer@example.invalid", "Viewer", True)
        self.company = db.create_company("Empresa A", "test", "owner")

    def app(self, subject="owner", active=None, page="Home"):
        user = {"is_logged_in": True, "iss": "test", "sub": subject, "email": f"{subject}@example.invalid",
                "name": subject, "email_verified": True}
        p = patch.object(st, "user", user)
        p.start()
        self.addCleanup(p.stop)
        p = patch("requests.sessions.Session.request", side_effect=AssertionError("Network blocked"))
        p.start()
        self.addCleanup(p.stop)
        at = AppTest.from_file(str(ROOT/"app.py"), default_timeout=20)
        at.secrets = {"test": True}
        if active is not None:
            at.session_state["active_company_id"] = active
            at.session_state["active_page"] = page
        at.run()
        self.assertFalse(at.exception)
        return at


class AccountDatabaseTests(AccountFixture):
    def test_batch_invites_validate_every_address_before_writing(self):
        with self.assertRaises(ValueError):
            db.invite_company_members(self.company, [("viewer@example.invalid", "collaborator"),
                                                       ("email incorreto", "administrator")], "test", "owner")
        self.assertFalse(db.pending_company_invitations(self.company))
        with self.assertRaises(ValueError):
            db.invite_company_members(self.company, [("viewer@example.invalid", "collaborator"),
                                                       (" VIEWER@example.invalid ", "administrator")], "test", "owner")
        self.assertFalse(db.pending_company_invitations(self.company))
        with self.assertRaises(PermissionError):
            db.invite_company_members(self.company, [("other@example.invalid", "collaborator")], "test", "viewer")
        self.assertFalse(db.pending_company_invitations(self.company))

    def test_member_can_create_another_company_and_roles_are_company_scoped(self):
        db.invite_company_member(self.company, "viewer@example.invalid", "collaborator", "test", "owner")
        invite = db.invitations_for_user("test", "viewer")[0]
        db.respond_company_invitation(invite["id"], "test", "viewer", True)
        other = db.create_company("Padaria B", "test", "viewer", "Padaria", "b@example.invalid", "Curitiba")
        companies = db.companies_for_user("test", "viewer")
        self.assertEqual([(x["id"], x["role"]) for x in companies], [(self.company, "collaborator"), (other, "administrator")])
        with self.assertRaises(PermissionError):
            db.upsert_budget("2026-10", "Aluguel", 10, self.company, "test", "viewer")
        db.upsert_budget("2026-10", "Aluguel", 10, other, "test", "viewer")
        self.assertEqual(db.query_df("SELECT * FROM budgets WHERE company_id=?", [self.company]).shape[0], 0)

    def test_invites_require_acceptance_and_verified_matching_identity(self):
        db.invite_company_member(self.company, "viewer@example.invalid", "collaborator", "test", "owner")
        self.assertEqual(len(db.company_members(self.company)), 1)
        invite = db.invitations_for_user("test", "viewer")[0]
        with self.assertRaises(PermissionError):
            db.respond_company_invitation(invite["id"], "test", "owner", True)
        db.register_identity("test", "viewer", "viewer@example.invalid", "Viewer", False)
        self.assertFalse(db.invitations_for_user("test", "viewer"))
        with self.assertRaises(PermissionError):
            db.respond_company_invitation(invite["id"], "test", "viewer", True)
        db.register_identity("test", "viewer", "viewer@example.invalid", "Viewer", True)
        db.respond_company_invitation(invite["id"], "test", "viewer", True)
        self.assertEqual(len(db.company_members(self.company)), 2)
        with self.assertRaises(ValueError):
            db.respond_company_invitation(invite["id"], "test", "viewer", True)

    def test_declined_and_expired_invites_do_not_grant_access(self):
        db.invite_company_member(self.company, "viewer@example.invalid", "collaborator", "test", "owner")
        invite = db.invitations_for_user("test", "viewer")[0]
        db.respond_company_invitation(invite["id"], "test", "viewer", False)
        self.assertFalse(db.companies_for_user("test", "viewer"))
        db.invite_company_member(self.company, "viewer@example.invalid", "collaborator", "test", "owner")
        with db.connection() as conn:
            conn.execute("UPDATE company_invitations SET expires_at=?", ((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),))
        self.assertFalse(db.invitations_for_user("test", "viewer"))
        with self.assertRaises(ValueError):
            db.respond_company_invitation(invite["id"], "test", "viewer", True)

    def test_collaborator_can_leave_without_deleting_company_data(self):
        db.seed_demo(self.company, "test", "owner")
        before = len(db.query_df("SELECT * FROM transactions"))
        with db.connection() as conn:
            conn.execute("INSERT INTO company_memberships(company_id,issuer,subject,role) VALUES (?,'test','viewer','collaborator')", (self.company,))
        db.leave_company(self.company, "test", "viewer")
        self.assertFalse(db.companies_for_user("test", "viewer"))
        self.assertEqual(len(db.query_df("SELECT * FROM transactions")), before)
        self.assertEqual(len(db.query_df("SELECT * FROM users")), 2)

    def test_last_owner_cannot_leave_be_removed_or_demoted(self):
        with self.assertRaises(ValueError):
            db.leave_company(self.company, "test", "owner")
        with self.assertRaises(ValueError):
            db.remove_company_member(self.company, "test", "owner", "test", "owner")
        with self.assertRaises(ValueError):
            db.update_company_member_role(self.company, "test", "owner", "collaborator", "test", "owner")

    def test_owner_can_transfer_privileges_and_collaborator_cannot_manage_access(self):
        with db.connection() as conn:
            conn.execute("INSERT INTO company_memberships(company_id,issuer,subject,role) VALUES (?,'test','viewer','collaborator')", (self.company,))
        with self.assertRaises(PermissionError):
            db.update_company_member_role(self.company, "test", "viewer", "administrator", "test", "viewer")
        with self.assertRaises(PermissionError):
            db.invite_company_member(self.company, "third@example.invalid", "administrator", "test", "viewer")
        db.update_company_member_role(self.company, "test", "viewer", "administrator", "test", "owner")
        db.leave_company(self.company, "test", "owner")
        self.assertEqual(db.company_members(self.company)[0]["subject"], "viewer")

    def test_demo_has_complete_data_and_every_company_write_is_rejected(self):
        demo = db.demo_company()
        self.assertEqual(demo["id"], db.demo_company()["id"])
        cid = demo["id"]
        for table in ("transactions", "sales_lines", "inventory_snapshots", "budgets"):
            self.assertFalse(db.query_df(f"SELECT * FROM {table} WHERE company_id=?", [cid]).empty)
            self.assertTrue(db.query_df(f"SELECT * FROM {table} WHERE company_id=?", [self.company]).empty)
        # Even a mistakenly assigned owner cannot change the read-only demo.
        with db.connection() as conn:
            conn.execute("INSERT INTO company_memberships(company_id,issuer,subject,role) VALUES (?,'test','owner','administrator')", (cid,))
        operations = [lambda: db.upsert_budget("2026-10", "Aluguel", 1, cid, "test", "owner"),
                      lambda: db.set_app_settings({"x": "y"}, cid, "test", "owner"),
                      lambda: db.update_company(cid, "Bad", "test", "owner"),
                      lambda: db.invite_company_member(cid, "viewer@example.invalid", "collaborator", "test", "owner"),
                      lambda: db.delete_import_batch("missing", cid, "test", "owner")]
        for operation in operations:
            with self.assertRaises(PermissionError):
                operation()
        self.assertEqual(len(db.companies_for_user("test", "owner")), 1)

    def test_demo_created_first_never_claims_legacy_rows(self):
        with db.connection() as conn:
            conn.execute("DELETE FROM company_memberships")
            conn.execute("DELETE FROM companies")
            conn.execute("INSERT INTO budgets(company_id,month,category,amount) VALUES (NULL,'2026-10','Legado',123)")
        demo = db.demo_company()
        self.assertTrue(db.query_df("SELECT * FROM budgets WHERE company_id IS NULL").shape[0])
        real = db.create_company("Real", "test", "owner")
        legacy = db.query_df("SELECT company_id FROM budgets WHERE category='Legado'").iloc[0]["company_id"]
        self.assertEqual(legacy, real)
        self.assertNotEqual(real, demo["id"])

    def test_personal_settings_are_not_shared(self):
        db.set_user_settings({"dark_mode": "true", "home_shortcuts_1": '["Home"]'}, "test", "owner")
        self.assertEqual(db.get_user_setting("dark_mode", "test", "owner"), "true")
        self.assertEqual(db.get_user_setting("dark_mode", "test", "viewer"), "")

    def test_upgrade_creates_backup_and_preserves_financial_rows(self):
        old = Path(self.temp.name)/"old.db"
        with closing(sqlite3.connect(old)) as conn:
            conn.executescript("""CREATE TABLE companies(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO companies(name) VALUES ('Livraria existente');
                CREATE TABLE company_memberships(company_id INTEGER,issuer TEXT,subject TEXT,role TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(company_id,issuer,subject));
                INSERT INTO company_memberships(company_id,issuer,subject,role) VALUES (1,'test','owner','administrator'),(1,'test','viewer','manager');
                CREATE TABLE budgets(id INTEGER PRIMARY KEY AUTOINCREMENT,month TEXT,category TEXT,amount REAL,UNIQUE(month,category));
                INSERT INTO budgets(month,category,amount) VALUES ('2026-10','Aluguel',123);""")
        with patch.object(db, "DB_PATH", old):
            db.init_db()
            db.init_db()
            members = db.company_members(1)
            self.assertEqual({m["subject"]: m["role"] for m in members}, {"owner": "administrator", "viewer": "collaborator"})
            self.assertEqual(db.companies_for_user("test", "owner")[0]["segment"], "Livraria")
            self.assertEqual(db.query_df("SELECT amount FROM budgets").iloc[0]["amount"], 123)
        backups = list((Path(self.temp.name)/"backup_account_upgrade").glob("*.db"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as conn:
            self.assertEqual(conn.execute("SELECT name FROM companies").fetchone()[0], "Livraria existente")
            self.assertEqual(conn.execute("SELECT amount FROM budgets").fetchone()[0], 123)


class AccountAppTests(AccountFixture):
    def test_removed_membership_returns_to_picker_and_clears_credentials(self):
        at = self.app(active=self.company)
        at.session_state["horus_password"] = "temporary-secret"
        at.session_state["gemini_session_key_1"] = "temporary-secret"
        with db.connection() as conn:
            conn.execute("DELETE FROM company_memberships WHERE company_id=? AND subject='owner'", (self.company,))
        at.run()
        self.assertFalse(at.exception)
        self.assertNotIn("horus_password", at.session_state)
        self.assertNotIn("gemini_session_key_1", at.session_state)
        self.assertTrue(any(x.key == "onboarding_name" for x in at.text_input))
        self.assertFalse(any(x.key == "enter_demo" for x in at.button))

    def test_creation_with_invitation_and_split_account_menus(self):
        at = self.app()
        at.text_input(key="onboarding_name").set_value("Empresa com equipe")
        next(x for x in at.button if x.label == "Criar empresa").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["active_page"], "Empresa")
        cid = at.session_state["active_company_id"]
        prefix = f"team_invite_{cid}"
        at.text_input(key=f"{prefix}_email_0").set_value("viewer@example.invalid")
        at.button(key=f"{prefix}_add_row").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.text_input(key=f"{prefix}_email_0").value, "viewer@example.invalid")
        self.assertFalse(db.pending_company_invitations(cid))
        at.text_input(key=f"{prefix}_email_1").set_value("another@example.invalid")
        at.selectbox(key=f"{prefix}_role_1").select("administrator")
        at.button(key=f"{prefix}_submit").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(db.company_members(cid)), 1)
        self.assertEqual(db.invitations_for_user("test", "viewer")[0]["company_id"], cid)
        invites = {item["email"]: item["role"] for item in db.pending_company_invitations(cid)}
        self.assertEqual(invites, {"viewer@example.invalid": "collaborator", "another@example.invalid": "administrator"})
        self.assertEqual(at.text_input(key=f"{prefix}_email_0").value, "")
        self.assertTrue(any("não está configurado" in x.value for x in at.info))
        self.assertIn("account_profile", {x.key for x in at.button})
        self.assertIn("account_company", {x.key for x in at.button})
        keys = [x.key for x in at.button]
        self.assertLess(keys.index("account_company"), keys.index("account_profile"))
        self.assertEqual(keys.index("nav_Meu perfil"), keys.index("nav_Empresa") + 1)
        at.button(key="account_profile").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["active_page"], "Meu perfil")
        self.assertFalse(any(x.key == f"remove_member_{cid}" for x in at.button))

    def test_existing_user_starts_at_picker_and_can_create_second_company(self):
        at = self.app()
        self.assertTrue(any(x.key == f"enter_company_{self.company}" for x in at.button))
        at.text_input(key="onboarding_name").set_value("Pão da Vila")
        at.selectbox(key="onboarding_segment").select("Padaria")
        next(x for x in at.button if x.label == "Criar empresa").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(db.companies_for_user("test", "owner")), 2)
        at.button(key="top_home_button").click().run()
        self.assertFalse(at.exception)
        company = next(item for item in db.companies_for_user("test", "owner")
                       if item["id"] == at.session_state["active_company_id"])
        self.assertEqual(company["segment"], "Padaria")

    def test_invited_user_accepts_and_sees_read_only_navigation(self):
        db.invite_company_member(self.company, "viewer@example.invalid", "collaborator", "test", "owner")
        iid = db.invitations_for_user("test", "viewer")[0]["id"]
        at = self.app("viewer")
        at.button(key=f"accept_invite_{iid}").click().run()
        self.assertFalse(at.exception)
        keys = {x.key for x in at.button}
        self.assertIn("nav_Meu perfil", keys)
        self.assertIn("nav_Lançamentos", keys)
        self.assertNotIn("nav_Empresa", keys)
        self.assertNotIn("nav_API do Horus", keys)
        at.button(key="nav_Lançamentos").click().run()
        self.assertFalse(at.exception)
        self.assertFalse(any(x.label == "Salvar lançamento" for x in at.button))
        at.button(key="nav_Meu perfil").click().run()
        at.checkbox(key=f"leave_confirm_{self.company}").check()
        next(x for x in at.button if x.label == "Sair da empresa").click().run()
        self.assertFalse(at.exception)
        self.assertFalse(db.companies_for_user("test", "viewer"))
        self.assertTrue(any(x.key == "onboarding_name" for x in at.text_input))

    def test_demo_is_unavailable_even_with_an_old_active_session(self):
        demo = db.demo_company()
        at = self.app()
        self.assertFalse(any("demo" in x.label.casefold() for x in at.button))
        at.session_state["active_company_id"] = demo["id"]
        at.session_state["demo_active"] = True
        at.session_state["workspace_picker"] = False
        at.run()
        self.assertFalse(at.exception)
        self.assertNotIn("active_company_id", at.session_state)
        self.assertNotIn("demo_active", at.session_state)
        self.assertFalse(any("demo" in x.label.casefold() for x in at.button))
        at.button(key=f"enter_company_{self.company}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["active_company_id"], self.company)

    def test_batch_validation_preserves_fields_and_sends_nothing(self):
        at = self.app(active=self.company, page="Empresa")
        prefix = f"team_invite_{self.company}"
        at.text_input(key=f"{prefix}_email_0").set_value("viewer@example.invalid")
        at.button(key=f"{prefix}_add_row").click().run()
        at.text_input(key=f"{prefix}_email_1").set_value("email incorreto")
        with patch("account_ui.send_invitation") as send:
            at.button(key=f"{prefix}_submit").click().run()
            send.assert_not_called()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertFalse(db.pending_company_invitations(self.company))
        self.assertEqual(at.text_input(key=f"{prefix}_email_0").value, "viewer@example.invalid")
        self.assertEqual(at.text_input(key=f"{prefix}_email_1").value, "email incorreto")
        at.text_input(key=f"{prefix}_email_1").set_value(" VIEWER@example.invalid ")
        at.button(key=f"{prefix}_submit").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("repetido" in x.value for x in at.error))
        self.assertFalse(db.pending_company_invitations(self.company))


class InvitationDeliveryTests(unittest.TestCase):
    def test_unconfigured_delivery_does_not_contact_server(self):
        with patch("smtplib.SMTP") as smtp:
            self.assertFalse(send_invitation("x@example.invalid", "A", "Colaborador", {}))
            smtp.assert_not_called()

    def test_delivery_uses_tls_and_explicit_acceptance_message(self):
        with patch("smtplib.SMTP") as smtp:
            self.assertTrue(send_invitation("x@example.invalid", "A", "Colaborador",
                                           {"host": "smtp.example.invalid", "from_email": "owner@example.invalid", "app_url": "https://example.invalid"}))
            client = smtp.return_value.__enter__.return_value
            client.starttls.assert_called_once()
            message = client.send_message.call_args.args[0]
            self.assertIn("aceitar ou recusar", message.get_content())


if __name__ == "__main__":
    unittest.main()
