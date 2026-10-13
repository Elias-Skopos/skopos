"""Opt-in PostgreSQL integration. Uses and removes only its own random schema."""
import os
import unittest
import hashlib
from pathlib import Path
import tempfile
from collections import Counter
from datetime import date
from uuid import uuid4
from unittest.mock import patch
import pandas as pd

import db
from analytics import normalize_sales_frame, normalize_inventory_frame


@unittest.skipUnless(os.environ.get("SKOPOS_TEST_DATABASE_URL"), "PostgreSQL de homologação ainda não configurado")
class PostgreSQLIntegrationTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.url = os.environ["SKOPOS_TEST_DATABASE_URL"]
        self.schema = "skopos_test_" + uuid4().hex
        self.real_connect = psycopg.connect
        with self.real_connect(self.url) as conn:
            conn.execute(f"CREATE SCHEMA {self.schema}")
        self.addCleanup(self.remove_schema)
        p = patch("psycopg.connect", side_effect=lambda url, **kw: self.real_connect(url, options=f"-c search_path={self.schema}", **kw))
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(db, "DATABASE_URL", self.url)
        p.start()
        self.addCleanup(p.stop)
        db.init_db()
        db.init_db()

    def remove_schema(self):
        with self.real_connect(self.url) as conn:
            conn.execute(f"DROP SCHEMA {self.schema} CASCADE")

    def test_postgres_identity_queries_imports_and_company_isolation(self):
        company = db.create_company("A", "test", "admin")
        other = db.create_company("B", "test", "other")
        self.assertNotEqual(company, other)
        db.register_identity("test", "viewer", "viewer@example.invalid", "Viewer", True)
        db.invite_company_member(company, "viewer@example.invalid", "collaborator", "test", "admin")
        self.assertEqual(len(db.company_members(company)), 1)
        invitation = db.invitations_for_user("test", "viewer")[0]
        db.respond_company_invitation(invitation["id"], "test", "viewer", True)
        self.assertEqual(len(db.company_members(company)), 2)
        db.register_identity("test", "pending", "pending@example.invalid", "Pending", True)
        db.invite_company_member(company, "pending@example.invalid", "collaborator", "test", "admin")
        invitation = db.invitations_for_user("test", "pending")[0]
        db.respond_company_invitation(invitation["id"], "test", "pending", True)
        rows, errors = normalize_sales_frame(pd.DataFrame([{"pedido_id": "001", "data": "01-10-2026", "sku": "001", "titulo": "Livro", "quantidade": "2", "preco_unitario": "49,90", "custo_unitario": "25"}]))
        self.assertFalse(errors)
        db.import_sales_lines(rows, company, "test", "admin")
        self.assertAlmostEqual(db.query_df("SELECT unit_price FROM sales_lines WHERE company_id=?", [company]).iloc[0]["unit_price"], 49.9)
        batch = db.list_import_batches(company).iloc[0]["id"]
        self.assertEqual(db.delete_import_batch(batch, other, "test", "other"), 0)
        self.assertEqual(db.delete_import_batch(batch, company, "test", "admin"), 1)
        stock, errors = normalize_inventory_frame(pd.DataFrame([{"data_ref": "01-10-2026", "sku": "001", "titulo": "Livro", "quantidade": "10", "custo_unitario": "25"}]))
        self.assertFalse(errors)
        db.import_inventory_snapshots(stock, company, "test", "admin")
        db.seed_demo(company, "test", "admin")
        db.upsert_budget("2026-10", "Aluguel", 300, company, "test", "admin")
        db.upsert_budget("2026-10", "Aluguel", 400, company, "test", "admin")
        self.assertEqual(db.query_df("SELECT amount FROM budgets").iloc[0]["amount"], 400)
        self.assertEqual(db.delete_demo_transactions(company, "test", "admin"), 9)

    def test_postgres_batch_invitations_validate_and_register_together(self):
        company = db.create_company("Convites em lote", "pg-test", "owner")
        with self.assertRaises(ValueError):
            db.invite_company_members(company, [("viewer@example.invalid", "collaborator"),
                                                 ("email inválido", "administrator")], "pg-test", "owner")
        self.assertFalse(db.pending_company_invitations(company))
        result = db.invite_company_members(company, [("viewer@example.invalid", "collaborator"),
                                                     ("partner@example.invalid", "administrator")], "pg-test", "owner")
        self.assertEqual([item[2] for item in result], ["invited", "invited"])
        self.assertEqual(len(db.pending_company_invitations(company)), 2)
        self.assertEqual(len(db.company_members(company)), 1)

    def test_postgres_sqlite_migration_preserves_every_record_and_source(self):
        import autonomy
        from migrate_postgres import migrate, TABLES
        with tempfile.TemporaryDirectory(prefix="skopos-pg-migrate-") as directory:
            source = Path(directory) / "source.db"
            with patch.object(db, "DB_PATH", source), patch.object(db, "DATABASE_URL", ""):
                db.init_db()
                company = db.create_company("Migração", "test", "owner", "Padaria")
                db.register_identity("test", "owner", "owner@example.invalid", "Owner", True)
                db.seed_demo(company, "test", "owner")
                db.upsert_budget("2026-10", "Aluguel", 1234.56, company, "test", "owner")
                db.set_user_settings({"display_name": "Owner"}, "test", "owner")
                autonomy.import_input([{"data": "2026-10-01", "total_vendas": "1500.00"}], "daily", company, "test", "owner")
                autonomy.save_opening(company, "2026-10-01", 1000, "test", "owner")
                recurrence = autonomy.add_recurrence(company, "Aluguel", "Aluguel", 300, "PIX", 31, "2026-10", "test", "owner")
                autonomy.generate_recurrence(recurrence, "2026-11", company, "test", "owner")
                rows, _ = normalize_sales_frame(pd.DataFrame([{"pedido_id": "007", "data": "01-10-2026", "sku": "004", "titulo": "Produto", "quantidade": "2", "preco_unitario": "49,90", "custo_unitario": "25"}]))
                db.import_sales_lines(rows, company, "test", "owner")
                with db.connection() as conn:
                    expected = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")] for table in TABLES}
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.dict(os.environ, {"SKOPOS_DATABASE_URL": self.url}):
                counts = migrate(source, apply=True)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            with db.connection() as conn:
                for table in TABLES:
                    actual = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
                    self.assertEqual(counts[table], len(actual))
                    if expected[table]:
                        columns = list(expected[table][0])
                        self.assertEqual(Counter(tuple(row[c] for c in columns) for row in expected[table]),
                                         Counter(tuple(row[c] for c in columns) for row in actual), table)
            with patch.dict(os.environ, {"SKOPOS_DATABASE_URL": self.url}):
                with self.assertRaises(ValueError):
                    migrate(source, apply=True)

    def test_postgres_streamlit_pages_use_real_postgres_connections(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        company = db.create_company("Livraria de teste PostgreSQL", "pg-test", "owner")
        db.seed_demo(company, "pg-test", "owner")
        user = {"is_logged_in": True, "iss": "pg-test", "sub": "owner", "email": "pg-owner@example.invalid",
                "name": "PostgreSQL test", "email_verified": True}
        with patch.object(st, "user", user), patch("requests.sessions.Session.request", side_effect=AssertionError("External calls blocked")):
            at = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"), default_timeout=20)
            at.secrets = {"database": {"url": self.url}}
            at.run()
            self.assertFalse(at.exception)
            at.button(key=f"enter_company_{company}").click().run()
            self.assertFalse(at.exception)
            at.session_state["global_period"] = (date(2026, 9, 1), date(2026, 10, 31))
            for page in ("Visão geral", "Lançamentos", "Contas", "Orçamento", "Vendas e estoque", "Empresa", "Meu perfil"):
                at.session_state["active_page"] = page
                at.run()
                self.assertFalse(at.exception, page)

    def test_postgres_daily_finance_and_recurring_workflow(self):
        import autonomy
        company = db.create_company("Rotina financeira", "pg-test", "owner")
        autonomy.import_input([{"data": "2026-10-01", "total_vendas": "1500.00"}], "daily", company, "pg-test", "owner")
        self.assertTrue(db.query_df("SELECT * FROM transactions").empty)
        row = {"referencia": "REC-01", "data": "2026-09-01", "tipo": "Receita", "categoria": "Vendas",
               "descricao": "Recebimento", "valor": "100", "status": "Pago", "data_pagamento": "2026-10-02"}
        autonomy.import_input([row], "finance", company, "pg-test", "owner")
        autonomy.import_input([{**row, "valor": "200"}], "finance", company, "pg-test", "owner")
        self.assertEqual(len(db.query_df("SELECT * FROM transactions")), 1)
        autonomy.save_opening(company, "2026-10-01", 1000, "pg-test", "owner")
        rid = autonomy.add_recurrence(company, "Aluguel", "Aluguel", 300, "PIX", 31, "2026-10", "pg-test", "owner")
        self.assertEqual(autonomy.generate_recurrence(rid, "2026-11", company, "pg-test", "owner"), 2)
        self.assertEqual(autonomy.generate_recurrence(rid, "2026-11", company, "pg-test", "owner"), 0)
        frame = db.query_df("SELECT * FROM transactions")
        opening = db.query_df("SELECT * FROM opening_balances").iloc[0].to_dict()
        projection = autonomy.cash_projection(frame, opening, date(2026, 10, 1), date(2026, 11, 30))
        self.assertEqual(projection.iloc[-1]["actual"], 1200)
        self.assertEqual(projection.iloc[-1]["projected"], 600)
