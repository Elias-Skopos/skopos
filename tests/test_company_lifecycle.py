"""Deletion must preserve recovery, identities and other tenants on both backends."""
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import pandas as pd

import autonomy
import company_lifecycle as lifecycle
import db
from analytics import normalize_inventory_frame, normalize_sales_frame
from test_account_flow import AccountFixture


class LifecycleChecks:
    def prepare_data(self):
        db.register_identity("test", "owner", "owner@example.invalid", "Owner", True)
        db.register_identity("test", "viewer", "viewer@example.invalid", "Viewer", True)
        db.register_identity("test", "other", "other@example.invalid", "Other", True)
        self.company = db.create_company("Empresa alvo", "test", "owner")
        self.other = db.create_company("Outra empresa", "test", "other")
        for cid, subject in ((self.company, "owner"), (self.other, "other")):
            db.seed_demo(cid, "test", subject)
            db.upsert_budget("2026-10", "Aluguel", 1234.56, cid, "test", subject)
            db.set_app_settings({"dashboard_cover_data": "base64-example"}, cid, "test", subject)
            autonomy.import_input([{"data": "2026-10-01", "total_vendas": "1200.00"}], "daily", cid, "test", subject)
            autonomy.save_opening(cid, "2026-10-01", 2500, "test", subject)
            rid = autonomy.add_recurrence(cid, "Aluguel", "Aluguel", 100, "PIX", 5, "2026-10", "test", subject)
            autonomy.generate_recurrence(rid, "2026-10", cid, "test", subject)
            sales, errors = normalize_sales_frame(pd.DataFrame([{"pedido_id": "001", "data": "01-10-2026", "sku": "001",
                                      "titulo": "Livro", "quantidade": "2", "preco_unitario": "49,90", "custo_unitario": "25"}]))
            self.assertFalse(errors)
            db.import_sales_lines(sales, cid, "test", subject)
            stock, errors = normalize_inventory_frame(pd.DataFrame([{"data_ref": "01-10-2026", "sku": "001", "titulo": "Livro",
                                       "quantidade": "10", "custo_unitario": "25"}]))
            self.assertFalse(errors)
            db.import_inventory_snapshots(stock, cid, "test", subject)
        db.invite_company_member(self.company, "viewer@example.invalid", "collaborator", "test", "owner")
        invitation = db.invitations_for_user("test", "viewer")[0]
        db.respond_company_invitation(invitation["id"], "test", "viewer", True)
        db.invite_company_member(self.company, "pending@example.invalid", "collaborator", "test", "owner")
        db.set_user_settings({"display_name": "Owner", f"home_shortcuts_{self.company}": '["Contas"]',
                              f"home_shortcuts_{self.other}": '["Home"]'}, "test", "owner")

    def snapshot(self):
        with db.connection() as conn:
            return {table: Counter(json.dumps(dict(row), sort_keys=True) for row in conn.execute(f"SELECT * FROM {table}"))
                    for table in ("companies", "users", "user_settings", *lifecycle.SCOPED_TABLES)}

    def delete(self, **kwargs):
        return lifecycle.delete_company(self.company, "test", "owner", "Empresa alvo", **kwargs)

    def test_owner_deletion_and_recovery_preserve_every_record(self):
        before = self.snapshot()
        backup = self.delete(confirmed=True)
        self.assertEqual(len(db.companies_for_user("test", "owner")), 0)
        self.assertEqual(len(db.companies_for_user("test", "viewer")), 0)
        self.assertEqual(db.companies_for_user("test", "other")[0]["id"], self.other)
        with db.connection() as conn:
            for table in lifecycle.SCOPED_TABLES:
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE company_id=?", (self.company,)).fetchone()[0], 0)
        self.assertEqual(db.get_user_setting("display_name", "test", "owner"), "Owner")
        self.assertEqual(db.get_user_setting(f"home_shortcuts_{self.other}", "test", "owner"), '["Home"]')
        self.assertEqual(lifecycle.deleted_companies("test", "owner")[0]["id"], backup)
        lifecycle.restore_company(backup, "test", "owner", confirmed=True)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(lifecycle.deleted_companies("test", "owner"))
        with self.assertRaises(ValueError):
            lifecycle.restore_company(backup, "test", "owner", confirmed=True)

    def test_invalid_confirmation_or_wrong_owner_does_not_delete(self):
        before = self.snapshot()
        for name, confirmed in (("Empresa errada", True), ("Empresa alvo", False), ("Empresa alvo", "true")):
            with self.assertRaises(ValueError):
                lifecycle.delete_company(self.company, "test", "owner", name, confirmed)
        for subject in ("viewer", "other", "unknown"):
            with self.assertRaises(PermissionError):
                lifecycle.delete_company(self.company, "test", subject, "Empresa alvo", True)
        with db.connection() as conn:
            conn.execute("UPDATE company_memberships SET role='collaborator' WHERE company_id=? AND subject='owner'", (self.company,))
        with self.assertRaises(PermissionError):
            self.delete(confirmed=True)
        with db.connection() as conn:
            conn.execute("UPDATE company_memberships SET role='administrator' WHERE company_id=? AND subject='owner'", (self.company,))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(lifecycle.deleted_companies("test", "owner"))

    def test_recovery_and_backup_are_not_available_to_other_users(self):
        backup = self.delete(confirmed=True)
        for subject in ("viewer", "other"):
            self.assertFalse(lifecycle.deleted_companies("test", subject))
            with self.assertRaises(PermissionError):
                lifecycle.recovery_copy(backup, "test", subject)
            with self.assertRaises(PermissionError):
                lifecycle.restore_company(backup, "test", subject, confirmed=True)
        with self.assertRaises(ValueError):
            lifecycle.restore_company(backup, "test", "owner")
        self.assertTrue(lifecycle.recovery_copy(backup, "test", "owner"))

    def test_backup_failure_or_late_deletion_failure_rolls_back_everything(self):
        original_connection = db.connection
        before = self.snapshot()
        for failing_sql in ("INSERT INTO company_deletion_backups", "DELETE FROM companies"):
            class FailingConnection:
                def __init__(self, conn):
                    self.conn = conn
                def __getattr__(self, name):
                    return getattr(self.conn, name)
                def execute(self, sql, params=()):
                    if sql.startswith(failing_sql):
                        raise RuntimeError("Simulated database failure")
                    return self.conn.execute(sql, params)
            @contextmanager
            def failing_connection():
                with original_connection() as conn:
                    yield FailingConnection(conn)
            with patch.object(db, "connection", failing_connection), self.assertRaises(RuntimeError):
                self.delete(confirmed=True)
            self.assertEqual(self.snapshot(), before)
            self.assertFalse(lifecycle.deleted_companies("test", "owner"))

    def test_corrupted_backup_and_recovery_conflicts_preserve_existing_data(self):
        backup = self.delete(confirmed=True)
        with db.connection() as conn:
            original = conn.execute("SELECT backup_json FROM company_deletion_backups WHERE id=?", (backup,)).fetchone()[0]
            conn.execute("UPDATE company_deletion_backups SET backup_json='corrupted' WHERE id=?", (backup,))
        with self.assertRaises(ValueError):
            lifecycle.restore_company(backup, "test", "owner", True)
        with db.connection() as conn:
            conn.execute("UPDATE company_deletion_backups SET backup_json=? WHERE id=?", (original, backup))
        # A preference collision late in recovery must roll back all preceding inserts.
        db.set_user_settings({f"home_shortcuts_{self.company}": '["Home"]'}, "test", "owner")
        before = self.snapshot()
        with self.assertRaises(Exception):
            lifecycle.restore_company(backup, "test", "owner", True)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(lifecycle.deleted_companies("test", "owner"))

    def test_unknown_company_data_blocks_deletion_instead_of_leaving_orphans(self):
        with db.connection() as conn:
            conn.execute("CREATE TABLE new_feature(company_id INTEGER, value TEXT)")
            conn.execute("INSERT INTO new_feature(company_id,value) VALUES (?,?)", (self.company, "preserve"))
        with self.assertRaises(ValueError):
            self.delete(confirmed=True)
        self.assertTrue(db.companies_for_user("test", "owner"))
        with db.connection() as conn:
            self.assertEqual(conn.execute("SELECT value FROM new_feature").fetchone()[0], "preserve")


class SQLiteLifecycleTests(LifecycleChecks, unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="skopos-company-delete-")
        self.addCleanup(temp.cleanup)
        for p in (patch.object(db, "DB_PATH", Path(temp.name) / "test.db"), patch.object(db, "DATABASE_URL", "")):
            p.start()
            self.addCleanup(p.stop)
        db.init_db()
        self.prepare_data()


@unittest.skipUnless(os.environ.get("SKOPOS_TEST_DATABASE_URL"), "PostgreSQL test database not configured")
class PostgreSQLLifecycleTests(LifecycleChecks, unittest.TestCase):
    def setUp(self):
        import psycopg
        self.url = os.environ["SKOPOS_TEST_DATABASE_URL"]
        schema = "skopos_lifecycle_" + uuid4().hex
        connect = psycopg.connect
        with connect(self.url) as conn:
            conn.execute(f"CREATE SCHEMA {schema}")
        def cleanup():
            with connect(self.url) as conn:
                conn.execute(f"DROP SCHEMA {schema} CASCADE")
        self.addCleanup(cleanup)
        for p in (patch("psycopg.connect", side_effect=lambda url, **kw: connect(url, options=f"-c search_path={schema}", **kw)),
                  patch.object(db, "DATABASE_URL", self.url)):
            p.start()
            self.addCleanup(p.stop)
        db.init_db()
        self.prepare_data()


class CompanyLifecycleAppTests(AccountFixture):
    def test_owner_confirms_deletion_and_recovers_from_workspace_picker(self):
        at = self.app(active=self.company, page="Empresa")
        at.session_state["horus_password"] = "fake-private-session"
        at.button(key=f"company_delete_submit_{self.company}").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertTrue(db.companies_for_user("test", "owner"))
        at.text_input(key=f"company_delete_name_{self.company}").set_value("Empresa A")
        at.checkbox(key=f"company_delete_confirm_{self.company}").check()
        at.button(key=f"company_delete_submit_{self.company}").click().run()
        self.assertFalse(at.exception)
        self.assertNotIn("active_company_id", at.session_state)
        self.assertNotIn("horus_password", at.session_state)
        self.assertFalse(db.companies_for_user("test", "owner"))
        backup_id = lifecycle.deleted_companies("test", "owner")[0]["id"]
        at.button(key=f"company_restore_submit_{backup_id}").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        at.checkbox(key=f"company_restore_confirm_{backup_id}").check()
        at.button(key=f"company_restore_submit_{backup_id}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["active_company_id"], self.company)
        self.assertEqual(at.session_state["active_page"], "Home")

    def test_collaborator_has_no_delete_button_or_recovery_copy(self):
        db.invite_company_member(self.company, "viewer@example.invalid", "collaborator", "test", "owner")
        invite = db.invitations_for_user("test", "viewer")[0]
        db.respond_company_invitation(invite["id"], "test", "viewer", True)
        at = self.app("viewer", active=self.company, page="Empresa")
        self.assertFalse(any(x.key == f"company_delete_submit_{self.company}" for x in at.button))
        lifecycle.delete_company(self.company, "test", "owner", "Empresa A", True)
        at.run()
        self.assertFalse(at.exception)
        self.assertFalse(any((x.key or "").startswith("company_restore_") for x in at.button))

    def test_abc_is_immediately_after_accounts_in_both_navigation_modes(self):
        at = self.app(active=self.company)
        keys = [x.key for x in at.button]
        self.assertEqual(keys.index("nav_Curva ABC"), keys.index("nav_Contas") + 1)
        at.button(key="collapsed_nav_group_acompanhamento").click().run()
        self.assertFalse(at.exception)
        keys = [x.key for x in at.button]
        self.assertEqual(keys.index("collapsed_nav_page_Curva ABC"), keys.index("collapsed_nav_page_Contas") + 1)


if __name__ == "__main__":
    unittest.main()
