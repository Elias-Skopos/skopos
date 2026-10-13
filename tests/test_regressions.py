"""Regressions run against temporary databases, with external calls blocked."""
from datetime import date
from io import BytesIO
from pathlib import Path
import logging
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

import db
from ai_insights import build_insight_payload
from analytics import SALES_NUMERIC_DEFAULTS, normalize_inventory_frame, normalize_sales_frame
from horus_api import HorusAPIError, sales_preview

ROOT = Path(__file__).resolve().parents[1]
SALE = {"pedido_id": "regression-order", "data": "09-10-2026", "sku": "book", "titulo": "Livro",
        "quantidade": "2", "preco_unitario": "50", "custo_unitario": "20"}
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)


class ImportValidationTests(unittest.TestCase):
    def test_bom_headers_are_normalized(self):
        frame = pd.DataFrame([SALE]).rename(columns={"pedido_id": "\ufeffpedido_id"})
        rows, errors = normalize_sales_frame(frame)
        self.assertFalse(errors)
        self.assertEqual(rows[0]["pedido_id"], SALE["pedido_id"])

    def test_invalid_optional_numbers_are_rejected_but_blanks_default_to_zero(self):
        for field in SALES_NUMERIC_DEFAULTS:
            for value in ("abc", "inf", "-inf", "nan"):
                with self.subTest(field=field, value=value):
                    rows, errors = normalize_sales_frame(pd.DataFrame([{**SALE, field: value}]))
                    self.assertTrue(errors)
                    self.assertFalse(rows)
            for value in ("", " ", None):
                with self.subTest(field=field, blank=value):
                    rows, errors = normalize_sales_frame(pd.DataFrame([{**SALE, field: value}]))
                    self.assertFalse(errors)
                    self.assertEqual(rows[0][field], 0)

    def test_required_numbers_reject_infinity_and_ambiguous_formats(self):
        for field in ("quantidade", "preco_unitario", "custo_unitario"):
            for value in ("inf", "-inf", "abc", ""):
                with self.subTest(field=field, value=value):
                    self.assertTrue(normalize_sales_frame(pd.DataFrame([{**SALE, field: value}]))[1])
        for value in ("1.234,56", "1,234.56", "49.90", "R$ 50", "1e3", "1 234.56"):
            rows, errors = normalize_sales_frame(pd.DataFrame([{**SALE, "preco_unitario": value}]))
            self.assertFalse(rows)
            self.assertIn("Linha 2", errors[0])
            self.assertIn("preco_unitario", errors[0])
        rows, errors = normalize_sales_frame(pd.DataFrame([{**SALE, "preco_unitario": "1234,56"}]))
        self.assertFalse(errors)
        self.assertEqual(rows[0]["preco_unitario"], 1234.56)

    def test_inventory_minimum_validation(self):
        stock = {"data_ref": "09-10-2026", "sku": "book", "titulo": "Livro", "quantidade": 10, "custo_unitario": 20}
        for field in ("quantidade", "custo_unitario", "estoque_minimo"):
            for value in ("abc", "inf", "-inf"):
                with self.subTest(field=field, value=value):
                    self.assertTrue(normalize_inventory_frame(pd.DataFrame([{**stock, field: value}]))[1])
        rows, errors = normalize_inventory_frame(pd.DataFrame([{**stock, "estoque_minimo": ""}]))
        self.assertFalse(errors)
        self.assertEqual(rows[0]["estoque_minimo"], 0)

    def test_horus_does_not_convert_bad_cost_to_zero(self):
        orders = [{"COD_EMPRESA": "1", "COD_FILIAL": "1", "COD_PED_VENDA": "1", "STATUS_PEDIDO_VENDA": "FAT", "DAT_PEDIDO": "09/10/2026"}]
        item = {"COD_EMPRESA": "1", "COD_FILIAL": "1", "COD_PED_VENDA": "1", "COD_ITEM": "book", "NOM_ITEM": "Livro", "QTD_ATENDIDA": 2, "VLR_PRECO": 50}
        for cost in ("abc", "inf", "nan"):
            with self.subTest(cost=cost), self.assertRaises(HorusAPIError):
                sales_preview(orders, [{**item, "VLR_CUSTO": cost}], "FAT")
        self.assertEqual(sales_preview(orders, [item], "FAT")[0]["custo_unitario"], "")


class DatabaseFixture(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {"SKOPOS_DATABASE_URL": ""})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.backend_patch = patch.object(db, "DATABASE_URL", "")
        self.backend_patch.start()
        self.addCleanup(self.backend_patch.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="skopos-regressions-")
        self.addCleanup(self.temp.cleanup)
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temp.name) / "test.db")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        db.init_db()
        self.company = db.create_company("Test A", "audit", "owner")
        self.other = db.create_company("Test B", "audit", "other-owner")
        with db.connection() as conn:
            conn.execute("INSERT INTO company_memberships(company_id,issuer,subject,role) VALUES (?,'audit','owner','administrator')", (self.other,))
            conn.execute("INSERT INTO company_memberships(company_id,issuer,subject,role) VALUES (?,'audit','viewer','collaborator')", (self.company,))
        db.seed_demo(self.company, "audit", "owner")
        self.rows, _ = normalize_sales_frame(pd.DataFrame([SALE]))
        db.import_sales_lines(self.rows, self.company, "audit", "owner")


class DatabaseTests(DatabaseFixture):
    def test_pending_requires_due_date_and_respects_company_and_role(self):
        with db.connection() as conn:
            transaction_id = conn.execute("SELECT id FROM transactions WHERE status='Pago' LIMIT 1").fetchone()[0]
        with self.assertRaises(ValueError):
            db.update_status(transaction_id, "Pendente", self.company, "audit", "owner")
        db.update_status(transaction_id, "Pendente", self.company, "audit", "owner", due_date="2026-10-20")
        with db.connection() as conn:
            self.assertEqual(tuple(conn.execute("SELECT status,due_date FROM transactions WHERE id=?", (transaction_id,)).fetchone()), ("Pendente", "2026-10-20"))
        with self.assertRaises(PermissionError):
            db.update_status(transaction_id, "Pago", self.company, "audit", "viewer")
        db.update_status(transaction_id, "Pago", self.other, "audit", "owner")
        with db.connection() as conn:
            self.assertEqual(conn.execute("SELECT status FROM transactions WHERE id=?", (transaction_id,)).fetchone()[0], "Pendente")
        db.update_status(transaction_id, "Pago", self.company, "audit", "owner")
        db.update_status(transaction_id, "Pendente", self.company, "audit", "owner")

    def test_new_pending_without_due_is_rejected(self):
        data = {"date": "2026-10-09", "kind": "Despesa", "category": "Aluguel", "description": "Test", "amount": 10,
                "payment_method": "PIX", "status": "Pendente"}
        with self.assertRaises(ValueError):
            db.add_transaction(data, self.company, "audit", "owner")

    def test_ai_pending_uses_due_date(self):
        transactions = pd.DataFrame([
            {"date": pd.Timestamp("2026-09-01"), "due_date": "2026-10-09", "status": "Pendente", "kind": "Despesa", "amount": 50, "category": "Aluguel"},
            {"date": pd.Timestamp("2026-10-09"), "due_date": "2026-11-01", "status": "Pendente", "kind": "Despesa", "amount": 100, "category": "Aluguel"},
        ])
        payload = build_insight_payload(transactions, pd.DataFrame(), pd.DataFrame(), date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(payload["lancamentos_financeiros"]["a_pagar"], 50)


class AppTests(DatabaseFixture):
    def setUp(self):
        super().setUp()
        self.user_patch = patch.object(st, "user", {"is_logged_in": True, "iss": "audit", "sub": "owner",
                                                   "email": "owner@example.invalid", "name": "Audit", "email_verified": True})
        self.user_patch.start()
        self.addCleanup(self.user_patch.stop)
        self.network_patch = patch("requests.sessions.Session.request", side_effect=AssertionError("External calls are blocked in tests"))
        self.network_patch.start()
        self.addCleanup(self.network_patch.stop)

    def app(self, page):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
        at.secrets = {"audit": True}
        at.session_state["active_page"] = page
        at.session_state["active_company_id"] = self.company
        at.session_state["global_period"] = (date(2026, 9, 1), date(2026, 10, 31))
        at.session_state["hide_financial_values"] = False
        at.run()
        self.assertFalse(at.exception)
        return at

    def test_pages_and_legacy_team_route(self):
        for page in ("Home", "Visão geral", "Curva ABC", "Relatórios", "Fluxo de caixa", "Contas", "Insights com IA",
                     "Vendas e estoque", "Lançamentos", "Orçamento", "API do Horus", "Configuração de IA", "Meu perfil", "Empresa", "Conta", "Equipe"):
            with self.subTest(page=page):
                at = self.app(page)
                if page == "Equipe":
                    self.assertEqual(at.session_state["active_page"], "Empresa")
                if page == "Conta":
                    self.assertEqual(at.session_state["active_page"], "Meu perfil")

    def test_csv_upload_bom_latin1_and_validation(self):
        for encoding, separator in (("utf-8-sig", ";"), ("latin-1", ";")):
            with self.subTest(encoding=encoding):
                at = self.app("Vendas e estoque")
                data = pd.DataFrame([{**SALE, "titulo": "Título ç"}]).to_csv(index=False, sep=separator).encode(encoding)
                at.file_uploader(key="sales_csv").set_value(("sales.csv", data, "text/csv")).run()
                self.assertFalse(at.exception)
                self.assertFalse(at.error)
                at.button(key="import_sales").click().run()
                self.assertFalse(at.exception)
        at = self.app("Vendas e estoque")
        invalid = pd.DataFrame([{**SALE, "desconto": "abc"}]).to_csv(index=False).encode("utf-8-sig")
        at.file_uploader(key="sales_csv").set_value(("invalid.csv", invalid, "text/csv")).run()
        self.assertTrue(at.error)
        self.assertFalse(any(b.key == "import_sales" for b in at.button))

    def test_delete_import_requires_confirmation_and_preserves_other_company(self):
        db.import_sales_lines(self.rows, self.other, "audit", "owner")
        at = self.app("Vendas e estoque")
        at.button(key=f"delete_batch_{self.company}").click().run()
        self.assertTrue(any("Confirme a exclusão" in e.value for e in at.error))
        self.assertEqual(len(db.query_df("SELECT * FROM sales_lines WHERE company_id=?", [self.company])), 1)
        next(w for w in at.checkbox if w.label == "Confirmo a exclusão das linhas deste lote").check()
        at.button(key=f"delete_batch_{self.company}").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(db.query_df("SELECT * FROM sales_lines WHERE company_id=?", [self.company]).empty)
        self.assertEqual(len(db.query_df("SELECT * FROM sales_lines WHERE company_id=?", [self.other])), 1)

    def test_manager_cannot_delete_imports(self):
        with db.connection() as conn:
            conn.execute("UPDATE company_memberships SET role='manager' WHERE company_id=? AND subject='owner'", (self.company,))
        at = self.app("Vendas e estoque")
        self.assertFalse(any(b.key == f"delete_batch_{self.company}" for b in at.button))
        self.assertFalse(any(b.key == f"delete_demo_{self.company}" for b in at.button))

    def test_transaction_controls_update_before_submit(self):
        at = self.app("Lançamentos")
        at.selectbox(key=f"new_transaction_kind_{self.company}").select("Despesa").run()
        at.selectbox(key=f"new_transaction_status_{self.company}").select("Pendente").run()
        category = next(w for w in at.selectbox if w.label == "Categoria")
        self.assertIn("Aluguel", category.options)
        category.select("Aluguel")
        due = next(w for w in at.date_input if w.label == "Vencimento")
        self.assertFalse(due.disabled)
        due.set_value(date(2026, 10, 20))
        next(w for w in at.text_input if w.label == "Descrição").set_value("Form regression")
        next(w for w in at.number_input if w.label == "Valor (R$)").set_value(100.0)
        next(w for w in at.button if w.label == "Salvar lançamento").click().run()
        self.assertFalse(at.exception)
        with db.connection() as conn:
            row = conn.execute("SELECT kind,category,status,due_date FROM transactions WHERE description='Form regression'").fetchone()
        self.assertEqual(tuple(row), ("Despesa", "Aluguel", "Pendente", "2026-10-20"))

    def test_literal_search_does_not_crash(self):
        at = self.app("Lançamentos")
        for query in ("[", "(", ".*", "\\"):
            with self.subTest(query=query):
                next(w for w in at.text_input if w.label == "Buscar").set_value(query).run()
                self.assertFalse(at.exception)
                self.assertTrue(at.dataframe[0].value.empty)

    def test_reopen_paid_account_has_selected_due_date_and_is_visible(self):
        at = self.app("Lançamentos")
        with db.connection() as conn:
            transaction_id = conn.execute("SELECT id FROM transactions WHERE status='Pago' LIMIT 1").fetchone()[0]
        next(w for w in at.selectbox if w.label == "ID do lançamento").select(transaction_id).run()
        next(w for w in at.date_input if w.label == "Vencimento ao marcar como pendente").set_value(date(2026, 10, 20)).run()
        next(w for w in at.button if w.label == "Alternar status").click().run()
        self.assertFalse(at.exception)
        at = self.app("Contas")
        self.assertIn("20/10/2026", at.dataframe[0].value["Vencimento"].tolist())

    def test_remove_requires_confirmation_and_submits_in_one_step(self):
        at = self.app("Empresa")
        def submit_button():
            return at.button(key=f"remove_member_{self.company}")
        at.selectbox(key=f"team_member_selection_{self.company}").select("audit|viewer").run()
        self.assertFalse(submit_button().disabled)
        submit_button().click().run()
        self.assertTrue(any("Confirme a remoção" in w.value for w in at.error))
        self.assertTrue(any(m["subject"] == "viewer" for m in db.company_members(self.company)))
        next(w for w in at.checkbox if w.label.startswith("Confirmo a remoção")).check()
        submit_button().click().run()
        self.assertFalse(at.exception)
        self.assertFalse(any(m["subject"] == "viewer" for m in db.company_members(self.company)))

    def test_horus_preview_and_credentials_are_cleared_on_company_switch(self):
        for company, suffix in ((self.company, "a"), (self.other, "b")):
            db.set_app_settings({"horus_base_url": f"https://{suffix}.example.invalid/", "horus_company": suffix, "horus_branch": "1"}, company, "audit", "owner")
        at = self.app("API do Horus")
        at.text_input(key="horus_username").set_value("test-user")
        at.text_input(key="horus_password").set_value("test-password")
        orders = [{"COD_EMPRESA": "1", "COD_FILIAL": "1", "COD_PED_VENDA": "1", "STATUS_PEDIDO_VENDA": "FAT", "DAT_PEDIDO": "09/10/2026"}]
        items = [{"COD_EMPRESA": "1", "COD_FILIAL": "1", "COD_PED_VENDA": "1", "COD_ITEM": "horus-book", "NOM_ITEM": "Livro", "QTD_ATENDIDA": 2, "VLR_PRECO": 50, "VLR_CUSTO": 20}]
        with patch("horus_api.fetch_orders_and_items", return_value=(orders, items)):
            at.button(key="horus_fetch").click().run()
        self.assertTrue(at.session_state["horus_sales_preview"])
        self.assertEqual(at.session_state["horus_preview_company_id"], self.company)
        at.button(key=f"account_switch_company_{self.other}").click().run()
        self.assertFalse(at.exception)
        self.assertNotIn("horus_sales_preview", at.session_state)
        self.assertEqual(at.text_input(key="horus_base_url_input").value, "https://b.example.invalid/")
        self.assertEqual(at.text_input(key="horus_password").value, "")
        self.assertFalse(any(b.key == "horus_import_sales" for b in at.button))
        with db.connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sales_lines WHERE company_id=?", (self.other,)).fetchone()[0], 0)

    def test_stale_preview_cannot_be_imported_without_matching_context(self):
        at = self.app("API do Horus")
        at.session_state["horus_sales_preview"] = [{**self.rows[0], "valor_liquido_horus": 100}]
        at.session_state["horus_preview_company_id"] = self.other
        at.run()
        self.assertFalse(at.exception)
        self.assertNotIn("horus_sales_preview", at.session_state)
        self.assertFalse(any(b.key == "horus_import_sales" for b in at.button))

    def test_matching_horus_preview_can_be_imported(self):
        at = self.app("API do Horus")
        at.session_state["horus_sales_preview"] = [{**self.rows[0], "pedido_id": "valid-horus-import", "valor_liquido_horus": 100}]
        at.session_state["horus_preview_company_id"] = self.company
        at.run()
        at.button(key="horus_import_sales").click().run()
        self.assertFalse(at.exception)
        with db.connection() as conn:
            row = conn.execute("SELECT company_id,quantity,unit_cost FROM sales_lines WHERE order_id='valid-horus-import'").fetchone()
        self.assertEqual(tuple(row), (self.company, 2, 20))


if __name__ == "__main__":
    unittest.main()
