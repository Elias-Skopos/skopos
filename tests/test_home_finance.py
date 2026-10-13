"""Home financial summary using temporary data; no real accounts are changed."""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

import db
import home_finance as data

ROOT = Path(__file__).resolve().parents[1]


class CalculationTests(unittest.TestCase):
    def test_break_even_examples_and_nonpositive_margin(self):
        self.assertEqual(data.break_even(23000, 35), Decimal("65714.29"))
        self.assertEqual(data.break_even(15500, 35), Decimal("44285.71"))
        self.assertEqual(data.break_even(0, 35), Decimal("0.00"))
        for margin in (0, -5):
            self.assertIsNone(data.break_even(23000, margin))
        for fixed, margin in ((-1, 35), (23000, 101), (23000, "nan"), ("inf", 35), (23000, "abc")):
            with self.subTest(fixed=fixed, margin=margin), self.assertRaises(ValueError):
                data.break_even(fixed, margin)

    def test_cash_uses_settlement_date_and_excludes_pending(self):
        frame = pd.DataFrame([
            {"id": 1, "date": "2026-09-01", "payment_date": "2026-10-02", "due_date": None, "kind": "Receita", "status": "Pago", "amount": 100},
            {"id": 2, "date": "2026-10-01", "payment_date": "2026-11-02", "due_date": None, "kind": "Despesa", "status": "Pago", "amount": 500},
            {"id": 3, "date": "2026-10-03", "payment_date": None, "due_date": "2026-10-20", "kind": "Despesa", "status": "Pendente", "amount": 1000},
            {"id": 4, "date": "2026-10-05", "payment_date": None, "due_date": None, "kind": "Despesa", "status": "Pago", "amount": .1},
            {"id": 5, "date": "2026-10-05", "payment_date": None, "due_date": None, "kind": "Despesa", "status": "Pago", "amount": .2},
        ])
        totals = data.paid_totals(frame, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(totals, {"income": Decimal("100.00"), "expense": Decimal("0.30"), "count": 3})

    def test_commitments_include_overdue_and_ignore_receipts_paid_unscheduled(self):
        frame = pd.DataFrame([
            {"id": i, "description": str(i), "kind": kind, "status": status, "due_date": day, "amount": i*10}
            for i, kind, status, day in ((5, "Despesa", "Pendente", "2026-10-15"), (3, "Despesa", "Pendente", "2026-10-12"),
                                        (2, "Despesa", "Pendente", "2026-10-12"), (1, "Despesa", "Pendente", "2026-10-01"),
                                        (6, "Receita", "Pendente", "2026-09-01"), (7, "Despesa", "Pago", "2026-09-01"),
                                        (8, "Despesa", "Pendente", None))])
        rows, missing = data.next_commitments(frame, date(2026, 10, 12))
        self.assertEqual([r["id"] for r in rows], [1, 2, 3])
        self.assertEqual([r["overdue"] for r in rows], [True, False, False])
        self.assertEqual(missing, 1)
        self.assertEqual(data.next_commitments(pd.DataFrame()), ([], 0))


class HomeFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skopos-home-")
        self.addCleanup(self.temp.cleanup)
        for p in (patch.object(db, "DB_PATH", Path(self.temp.name)/"home.db"), patch.object(db, "DATABASE_URL", "")):
            p.start()
            self.addCleanup(p.stop)
        self.seed()

    def seed(self):
        db.init_db()
        self.company = db.create_company("A", "home-test", "owner")
        self.other = db.create_company("B", "home-test", "owner")
        db.register_identity("home-test", "viewer", "viewer@example.invalid", "Viewer", True)
        db.invite_company_member(self.company, "viewer@example.invalid", "collaborator", "home-test", "owner")
        db.respond_company_invitation(db.invitations_for_user("home-test", "viewer")[0]["id"], "home-test", "viewer", True)
        self.ids = []
        for i in range(4):
            self.ids.append(self.add(self.company, "Despesa", f"Pagamento {i}", date.today()+timedelta(days=i), 100+i))

    def add(self, company, kind, description, due, amount):
        db.add_transaction({"date": date.today().isoformat(), "kind": kind, "category": "Outros", "description": description,
                            "amount": amount, "payment_method": "Pix", "status": "Pendente", "due_date": due.isoformat()},
                           company, "home-test", "owner")
        return int(db.query_df("SELECT id FROM transactions WHERE company_id=? AND description=?", [company, description]).iloc[0]["id"])

    def test_settings_scoped_and_owner_only(self):
        self.assertIsNone(data.load_break_even(self.company))
        data.save_break_even(self.company, 23000, 35, "home-test", "owner")
        self.assertEqual(data.load_break_even(self.company)["amount"], Decimal("65714.29"))
        self.assertIsNone(data.load_break_even(self.other))
        with self.assertRaises(PermissionError):
            data.save_break_even(self.company, 1, 50, "home-test", "viewer")
        with self.assertRaises(ValueError):
            data.save_break_even(self.company, "1e1000", 35, "home-test", "owner")

    def test_settlement_is_atomic_and_company_scoped(self):
        foreign = self.add(self.other, "Despesa", "Outro", date.today(), 999)
        income = self.add(self.company, "Receita", "Recebível", date.today(), 999)
        for invalid in (foreign, income):
            with self.assertRaises(ValueError):
                data.settle_commitments(self.company, [self.ids[0], invalid], date.today().isoformat(), "home-test", "owner")
            self.assertEqual(db.query_df("SELECT status FROM transactions WHERE id=?", [self.ids[0]]).iloc[0]["status"], "Pendente")
        with self.assertRaises(PermissionError):
            data.settle_commitments(self.company, [self.ids[0]], date.today().isoformat(), "home-test", "viewer")
        with self.assertRaises(ValueError):
            data.settle_commitments(self.company, [self.ids[0]], (date.today()+timedelta(days=1)).isoformat(), "home-test", "owner")
        data.settle_commitments(self.company, self.ids[:2], date.today().isoformat(), "home-test", "owner")
        with self.assertRaises(ValueError):
            data.settle_commitments(self.company, [self.ids[2], self.ids[0]], date.today().isoformat(), "home-test", "owner")
        remaining = db.query_df("SELECT * FROM transactions WHERE id=?", [self.ids[2]]).iloc[0]
        self.assertEqual(remaining["status"], "Pendente")
        paid = db.query_df("SELECT * FROM transactions WHERE id=?", [self.ids[0]]).iloc[0]
        self.assertEqual(paid["status"], "Pago")
        self.assertEqual(paid["payment_date"], date.today().isoformat())
        self.assertEqual(paid["due_date"], date.today().isoformat())


class HomeUITests(HomeFixture):
    def app(self, subject="owner", hidden=False):
        p = patch.object(st, "user", {"is_logged_in": True, "iss": "home-test", "sub": subject,
                                      "name": subject, "email": f"{subject}@example.invalid", "email_verified": True})
        p.start()
        self.addCleanup(p.stop)
        at = AppTest.from_file(str(ROOT/"app.py"), default_timeout=20)
        at.secrets = {"test": True}
        at.session_state["active_page"] = "Home"
        at.session_state["active_company_id"] = self.company
        at.session_state["hide_financial_values"] = hidden
        at.session_state["global_period"] = (date.today().replace(day=1), date.today())
        at.run()
        self.assertFalse(at.exception)
        return at

    def test_owner_configures_equilibrium_and_pays_from_checklist(self):
        at = self.app()
        at.number_input(key=f"home_fixed_costs_{self.company}").set_value(23000)
        at.number_input(key=f"home_margin_{self.company}").set_value(35)
        at.button(key=f"save_home_break_even_{self.company}").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("65.714,29" in m.value for m in at.markdown))
        self.assertEqual(len([c for c in at.checkbox if str(c.key).startswith("home_commitment_")]), 3)
        at.checkbox(key=f"home_commitment_{self.company}_{self.ids[0]}").check()
        at.button(key=f"settle_home_commitments_{self.company}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(db.query_df("SELECT status FROM transactions WHERE id=?", [self.ids[0]]).iloc[0]["status"], "Pago")
        self.assertTrue(any("100,00" in m.value and "Saídas" in m.value for m in at.markdown))
        self.assertEqual(len([c for c in at.checkbox if str(c.key).startswith("home_commitment_")]), 3)
        self.assertNotIn(f"home_commitment_{self.company}_{self.ids[0]}", [c.key for c in at.checkbox])

    def test_viewer_and_hidden_values(self):
        data.save_break_even(self.company, 23000, 35, "home-test", "owner")
        at = self.app("viewer", hidden=True)
        self.assertFalse(at.number_input)
        self.assertTrue(all(c.disabled for c in at.checkbox if str(c.key).startswith("home_commitment_")))
        self.assertTrue(at.button(key=f"settle_home_commitments_{self.company}").disabled)
        self.assertFalse(any("65.714,29" in m.value for m in at.markdown))
        self.assertFalse(any("R$" in c.value for c in at.caption))


@unittest.skipUnless(os.environ.get("SKOPOS_TEST_DATABASE_URL"), "PostgreSQL de teste não configurado")
class PostgreSQLHomeTests(HomeFixture):
    def setUp(self):
        import psycopg
        self.url = os.environ["SKOPOS_TEST_DATABASE_URL"]
        schema = "skopos_home_"+uuid4().hex
        real_connect = psycopg.connect
        with real_connect(self.url) as conn:
            conn.execute(f"CREATE SCHEMA {schema}")
        def cleanup():
            with real_connect(self.url) as conn:
                conn.execute(f"DROP SCHEMA {schema} CASCADE")
        self.addCleanup(cleanup)
        for p in (patch("psycopg.connect", side_effect=lambda url, **kw: real_connect(url, options=f"-c search_path={schema}", **kw)),
                  patch.object(db, "DATABASE_URL", self.url)):
            p.start()
            self.addCleanup(p.stop)
        self.seed()


if __name__ == "__main__":
    unittest.main()
