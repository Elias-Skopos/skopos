"""Daily totals never create receipts; financial dates, atomic imports and permissions."""
from datetime import date
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

import autonomy as data
import db
from ai_insights import build_insight_payload
from import_contract import csv_template, read_csv

ROOT = Path(__file__).resolve().parents[1]
FINANCE = {"referencia": "R-001", "data": "2026-09-01", "tipo": "Receita", "categoria": "Vendas",
           "descricao": "Recebimento", "valor": "100.00", "status": "Pago", "data_pagamento": "2026-10-02"}


class Fixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="skopos-autonomy-")
        self.addCleanup(temp.cleanup)
        for p in (patch.object(db, "DB_PATH", Path(temp.name)/"test.db"), patch.object(db, "DATABASE_URL", ""),
                  patch.dict(os.environ, {"SKOPOS_DATABASE_URL": ""})):
            p.start()
            self.addCleanup(p.stop)
        db.init_db()
        self.company = db.create_company("Livraria", "test", "owner")
        self.other = db.create_company("Outra", "test", "owner2")
        with db.connection() as conn:
            conn.execute("INSERT INTO company_memberships(company_id,issuer,subject,role) VALUES (?,'test','viewer','collaborator')", (self.company,))

    def app(self, page, subject="owner"):
        for p in (patch.object(st, "user", {"is_logged_in": True, "iss": "test", "sub": subject,
                                           "email": subject+"@example.invalid", "name": "Teste", "email_verified": True}),
                  patch("requests.sessions.Session.request", side_effect=AssertionError("External calls blocked"))):
            p.start()
            self.addCleanup(p.stop)
        at = AppTest.from_file(str(ROOT/"app.py"), default_timeout=20)
        at.secrets = {"test": True}
        at.session_state["active_company_id"] = self.company
        at.session_state["active_page"] = page
        at.session_state["global_period"] = (date(2026, 10, 1), date(2026, 10, 31))
        at.session_state["hide_financial_values"] = False
        at.run()
        self.assertFalse(at.exception)
        return at


class DataTests(Fixture):
    def test_brazilian_raw_csv_converts_dates_and_values_without_month_swap(self):
        frame = read_csv(b"data;total_vendas\n12-10-2026;1234,56\n10-12-2026;49,90")
        rows, errors = data.normalize_input(frame, "daily")
        self.assertFalse(errors)
        self.assertEqual([r["data"] for r in rows], ["2026-10-12", "2026-12-10"])
        self.assertEqual([r["total_vendas"] for r in rows], [1234.56, 49.9])
        data.import_input(rows, "daily", self.company, "test", "owner")
        self.assertEqual(db.query_df("SELECT amount FROM daily_sales ORDER BY date")["amount"].tolist(), [1234.56, 49.9])
        for bad in (b"12-10-2026;1234.56", b"2026-10-12;1234,56", b"31-02-2026;1234,56"):
            with self.subTest(raw=bad):
                self.assertTrue(data.normalize_input(read_csv(b"data;total_vendas\n"+bad), "daily")[1])

    def test_daily_updates_without_creating_orders_or_cash_and_preserves_other_company(self):
        rows = [{"data": "2026-10-01", "total_vendas": "1250.00"}, {"data": "2026-10-02", "total_vendas": "0"}]
        data.import_input(rows, "daily", self.company, "test", "owner")
        data.import_input(rows, "daily", self.other, "test", "owner2")
        old = data.input_history(self.company).iloc[0]["id"]
        data.import_input([{**rows[0], "total_vendas": "1500.00"}], "daily", self.company, "test", "owner")
        self.assertEqual(data.delete_input(old, self.company, "test", "owner"), 1)
        self.assertEqual(db.query_df("SELECT amount FROM daily_sales WHERE company_id=?", [self.company]).iloc[0]["amount"], 1500)
        self.assertEqual(len(db.query_df("SELECT * FROM daily_sales WHERE company_id=?", [self.other])), 2)
        self.assertTrue(db.query_df("SELECT * FROM sales_lines").empty)
        self.assertTrue(db.query_df("SELECT * FROM transactions").empty)

    def test_invalid_daily_rows_dates_and_duplicates_do_not_import_anything(self):
        for bad in ("1.250,00", "R$ 1250", "inf", "-1", "1.123", ""):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                data.import_input([{"data": "2026-10-01", "total_vendas": "100"},
                                   {"data": "2026-10-02", "total_vendas": bad}], "daily", self.company, "test", "owner")
        for rows in ([{"data": "01/10/2026", "total_vendas": "100"}],
                     [{"data": "2026-10-01", "total_vendas": "100"}]*2):
            self.assertTrue(data.normalize_input(pd.DataFrame(rows), "daily")[1])
        self.assertTrue(data.input_history(self.company).empty)

    def test_finance_requires_settlement_or_due_date_and_reimport_updates_reference(self):
        for invalid in ({**FINANCE, "data_pagamento": ""}, {**FINANCE, "status": "Pendente", "vencimento": "2026-10-10"},
                        {**FINANCE, "status": "Pendente", "data_pagamento": ""}, {**FINANCE, "status": "Desconhecido"}):
            with self.assertRaises(ValueError):
                data.import_input([FINANCE, {**invalid, "referencia": "R-002"}], "finance", self.company, "test", "owner")
        self.assertTrue(db.query_df("SELECT * FROM transactions").empty)
        data.import_input([FINANCE], "finance", self.company, "test", "owner")
        data.import_input([{**FINANCE, "valor": "120"}], "finance", self.company, "test", "owner")
        frame = data.effective_finance(db.query_df("SELECT * FROM transactions"))
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["amount"], 120)
        self.assertEqual(frame.iloc[0]["date"].date(), date(2026, 10, 2))
        self.assertEqual(frame.iloc[0]["record_date"].date(), date(2026, 9, 1))
        self.assertEqual(build_insight_payload(frame, pd.DataFrame(), pd.DataFrame(), date(2026, 10, 1), date(2026, 10, 31))["lancamentos_financeiros"]["receitas_pagas"], 120)

    def test_owner_only_writes_and_company_scoped_deletion(self):
        with self.assertRaises(PermissionError):
            data.import_input([FINANCE], "finance", self.company, "test", "viewer")
        with self.assertRaises(PermissionError):
            data.save_opening(self.company, "2026-10-01", 100, "test", "viewer")
        with self.assertRaises(PermissionError):
            data.add_recurrence(self.company, "Aluguel", "Aluguel", 100, "PIX", 1, "2026-10", "test", "viewer")
        data.import_input([FINANCE], "finance", self.company, "test", "owner")
        batch = data.input_history(self.company).iloc[0]["id"]
        self.assertEqual(data.delete_input(batch, self.other, "test", "owner2"), 0)
        self.assertEqual(len(db.query_df("SELECT * FROM transactions")), 1)

    def test_opening_projection_uses_prior_paid_records_and_overdue_pending_without_counting_sales(self):
        data.import_input([FINANCE, {"referencia": "D-001", "data": "2026-09-01", "tipo": "Despesa", "categoria": "Aluguel",
                                    "descricao": "Aluguel", "valor": "200", "status": "Pendente", "vencimento": "2026-09-30"}],
                          "finance", self.company, "test", "owner")
        data.save_opening(self.company, "2026-10-01", 1000, "test", "owner")
        opening = db.query_df("SELECT * FROM opening_balances").iloc[0].to_dict()
        frame = db.query_df("SELECT * FROM transactions")
        cash = data.cash_projection(frame, opening, date(2026, 10, 3), date(2026, 10, 5))
        self.assertEqual(cash.iloc[0]["actual"], 1100)
        self.assertEqual(cash.iloc[0]["projected"], 900)
        self.assertEqual(cash.iloc[-1]["projected"], 900)
        before = data.cash_projection(frame, opening, date(2026, 9, 1), date(2026, 9, 30))
        self.assertTrue(before["actual"].isna().all())
        data.import_input([{"data": "2026-10-03", "total_vendas": "9999"}], "daily", self.company, "test", "owner")
        pd.testing.assert_frame_equal(cash, data.cash_projection(frame, opening, date(2026, 10, 3), date(2026, 10, 5)))

    def test_recurrences_clamp_month_end_and_do_not_duplicate_or_reset_paid_accounts(self):
        rid = data.add_recurrence(self.company, "Aluguel", "Aluguel", 1000, "PIX", 31, "2026-01", "test", "owner")
        with self.assertRaises(ValueError):
            data.add_recurrence(self.company, "Aluguel", "Aluguel", 1000, "PIX", 31, "2026-01", "test", "owner")
        self.assertEqual(data.generate_recurrence(rid, "2026-03", self.company, "test", "owner"), 3)
        frame = db.query_df("SELECT * FROM transactions ORDER BY due_date")
        self.assertEqual(frame["due_date"].tolist(), ["2026-01-31", "2026-02-28", "2026-03-31"])
        self.assertTrue((frame["status"] == "Pendente").all())
        db.update_status(int(frame.iloc[0]["id"]), "Pago", self.company, "test", "owner", payment_date="2026-02-02")
        self.assertEqual(data.generate_recurrence(rid, "2026-03", self.company, "test", "owner"), 0)
        paid = db.query_df("SELECT * FROM transactions WHERE status='Pago'")
        self.assertEqual(paid.iloc[0]["payment_date"], "2026-02-02")
        data.set_recurrence_active(rid, False, self.company, "test", "owner")
        with self.assertRaises(ValueError):
            data.generate_recurrence(rid, "2026-04", self.company, "test", "owner")


class InterfaceTests(Fixture):
    def test_daily_upload_preview_confirm_and_dashboard_do_not_show_fake_profit(self):
        at = self.app("Vendas e estoque")
        payload = csv_template(data.DAILY_COLUMNS, [{"data": "2026-10-01", "total_vendas": "1250.00"}])
        at.file_uploader(key=f"daily_csv_{self.company}").set_value(("daily.csv", payload, "text/csv")).run()
        self.assertFalse(at.exception)
        self.assertTrue(db.query_df("SELECT * FROM daily_sales").empty)
        at.button(key=f"import_daily_{self.company}").click().run()
        self.assertFalse(at.exception)
        at.session_state["active_page"] = "Visão geral"
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(any(x.label == "Total de vendas informado" for x in at.metric))
        self.assertTrue(any("Margens, pedidos e clientes" in x.value for x in at.info))
        self.assertTrue(db.query_df("SELECT * FROM transactions").empty)

    def test_finance_upload_rejects_invalid_file_before_showing_confirmation(self):
        at = self.app("Lançamentos")
        payload = csv_template(data.FINANCE_COLUMNS, [FINANCE]).replace(b"100,00", b"100.00")
        at.file_uploader(key=f"finance_csv_{self.company}").set_value(("bad.csv", payload, "text/csv")).run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertNotIn(f"import_finance_{self.company}", {x.key for x in at.button})
        payload = csv_template(data.FINANCE_COLUMNS, [FINANCE])
        at.file_uploader(key=f"finance_csv_{self.company}").set_value(("good.csv", payload, "text/csv")).run()
        at.button(key=f"import_finance_{self.company}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(db.query_df("SELECT * FROM transactions")), 1)

    def test_collaborator_cannot_import_generate_or_set_balance(self):
        for page in ("Vendas e estoque", "Lançamentos", "Fluxo de caixa"):
            at = self.app(page, "viewer")
            self.assertFalse(at.exception)
            self.assertFalse(at.file_uploader)
            self.assertFalse(any(x.label in {"Salvar saldo inicial", "Cadastrar despesa recorrente"} for x in at.button))

    def test_balance_and_recurrence_workflow(self):
        at = self.app("Fluxo de caixa")
        next(x for x in at.date_input if x.label == "Data do saldo inicial").set_value(date(2026, 10, 1))
        next(x for x in at.number_input if x.label == "Saldo inicial (R$)").set_value(1000)
        next(x for x in at.button if x.label == "Salvar saldo inicial").click().run()
        self.assertTrue(at.error)
        next(x for x in at.checkbox if x.label == "Conferi o saldo com o caixa e as contas da empresa").check()
        next(x for x in at.button if x.label == "Salvar saldo inicial").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(db.query_df("SELECT amount FROM opening_balances").iloc[0]["amount"], 1000)
        at.session_state["active_page"] = "Lançamentos"
        at.run()
        next(x for x in at.text_input if x.label == "Descrição da despesa recorrente").set_value("Aluguel")
        next(x for x in at.number_input if x.label == "Valor mensal (R$)").set_value(500)
        next(x for x in at.date_input if x.label == "Primeiro mês da recorrência").set_value(date(2026, 10, 1))
        next(x for x in at.button if x.label == "Cadastrar despesa recorrente").click().run()
        self.assertFalse(at.exception)
        next(x for x in at.date_input if x.label == "Gerar contas até o mês").set_value(date(2026, 12, 1))
        next(x for x in at.button if x.label == "Gerar contas pendentes").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(db.query_df("SELECT * FROM transactions WHERE status='Pendente'")), 3)


if __name__ == "__main__":
    unittest.main()
