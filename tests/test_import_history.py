import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import hashlib
import pandas as pd

import db
from analytics import SALES_COLUMNS, INVENTORY_COLUMNS, normalize_sales_frame, normalize_inventory_frame
from import_contract import read_csv, csv_template
from postgres_backend import sql_for_postgres, Row


SALE = {"pedido_id": "P001", "data": "01-10-2026", "sku": "L001", "titulo": "Livro", "quantidade": "2", "preco_unitario": "49,90", "custo_unitario": "25,00"}


class ContractTests(unittest.TestCase):
    def test_templates_round_trip_preserving_identifiers(self):
        rows, errors = normalize_sales_frame(read_csv(csv_template(SALES_COLUMNS, [{**SALE, "sku": "000123", "pedido_id": "NA"}])))
        self.assertFalse(errors)
        self.assertEqual(rows[0]["sku"], "000123")
        self.assertEqual(rows[0]["pedido_id"], "NA")
        self.assertEqual(rows[0]["data"], "2026-10-01")
        self.assertEqual(rows[0]["preco_unitario"], 49.9)
        example = {"data_ref": "2026-10-01", "sku": "001", "titulo": "Livro", "quantidade": "10", "custo_unitario": "25.00"}
        self.assertFalse(normalize_inventory_frame(read_csv(csv_template(INVENTORY_COLUMNS, [example])))[1])

    def test_csv_bad_headers_and_malformed_rows(self):
        for raw in (b"a;a\n1;2", b"a;b\n1;2\n3;4;5", b"a;b\n1;2\n\n"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                read_csv(raw)
        self.assertTrue(normalize_sales_frame(pd.DataFrame([{**SALE, "prco_unitario": "3"}]))[1])

    def test_dates_status_and_second_row_errors(self):
        rows, errors = normalize_sales_frame(pd.DataFrame([SALE, {**SALE, "data": "01/10/2026", "preco_unitario": "49.90", "status": "concluido"}]))
        self.assertFalse(rows)
        self.assertEqual(len(errors), 3)
        self.assertTrue(all("Linha 3" in error for error in errors))

    def test_semicolon_required_and_text_and_identifiers_are_not_reformatted(self):
        with self.assertRaisesRegex(ValueError, "ponto e vírgula"):
            read_csv(b"data,total_vendas\n12-10-2026,1234.56")
        raw = csv_template(SALES_COLUMNS, [{**SALE, "titulo": "Livro; edição 2, volume 1.0", "sku": "000123"}])
        self.assertIn(b"01-10-2026", raw)
        self.assertIn(b"49,90", raw)
        frame = read_csv(raw)
        self.assertEqual(frame.iloc[0]["titulo"], "Livro; edição 2, volume 1.0")
        self.assertEqual(frame.iloc[0]["sku"], "000123")

    def test_horus_completion_export_remains_importable_in_brazilian_format(self):
        example = {**SALE, "data": "12/10/2026", "preco_unitario": 49.9, "custo_unitario": ""}
        frame = read_csv(csv_template(SALES_COLUMNS, [example]))
        self.assertEqual(frame.iloc[0]["data"], "12-10-2026")
        frame.loc[0, "custo_unitario"] = "25,00"
        rows, errors = normalize_sales_frame(frame)
        self.assertFalse(errors)
        self.assertEqual(rows[0]["data"], "2026-10-12")
        api_rows, errors = normalize_sales_frame(pd.DataFrame([{**SALE, "data": "2026-10-12", "preco_unitario": 49.9, "custo_unitario": 25}]), strict=False)
        self.assertFalse(errors)
        self.assertEqual(api_rows[0]["preco_unitario"], rows[0]["preco_unitario"])


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        p = patch.object(db, "DB_PATH", Path(temp.name) / "test.db")
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(db, "DATABASE_URL", "")
        p.start()
        self.addCleanup(p.stop)
        db.init_db()
        self.company = db.create_company("A", "test", "admin")
        self.other = db.create_company("B", "test", "other")
        self.rows, _ = normalize_sales_frame(pd.DataFrame([SALE]))
        with db.connection() as c:
            c.execute("INSERT INTO company_memberships(company_id,issuer,subject,role) VALUES (?,'test','manager','manager')", (self.company,))

    def test_delete_batch_preserves_latest_reimport_and_other_company(self):
        db.import_sales_lines(self.rows, self.company, "test", "admin", source="first.csv")
        old = db.list_import_batches(self.company).iloc[0]["id"]
        db.import_sales_lines(self.rows, self.company, "test", "admin", source="second.csv")
        db.import_sales_lines(self.rows, self.other, "test", "other")
        self.assertEqual(db.delete_import_batch(old, self.company, "test", "admin"), 0)
        current = db.list_import_batches(self.company).iloc[0]["id"]
        with self.assertRaises(PermissionError):
            db.delete_import_batch(current, self.company, "test", "manager")
        self.assertEqual(db.delete_import_batch(current, self.other, "test", "other"), 0)
        self.assertEqual(db.delete_import_batch(current, self.company, "test", "admin"), 1)
        self.assertEqual(len(db.query_df("SELECT * FROM sales_lines WHERE company_id=?", [self.other])), 1)

    def test_stock_delete_and_legacy_migration_are_idempotent(self):
        rows, errors = normalize_inventory_frame(pd.DataFrame([{"data_ref": "01-10-2026", "sku": "001", "titulo": "Livro", "quantidade": "10", "custo_unitario": "25"}]))
        self.assertFalse(errors)
        db.import_inventory_snapshots(rows, self.company, "test", "admin")
        with db.connection() as c:
            c.execute("UPDATE inventory_snapshots SET import_id=NULL")
        db.init_db()
        db.init_db()
        batches = db.list_import_batches(self.company)
        legacy = batches[batches["source"] == "Dados anteriores ao histórico"].iloc[0]
        self.assertEqual(legacy["current_rows"], 1)
        self.assertEqual(db.delete_import_batch(legacy["id"], self.company, "test", "admin"), 1)

    def test_import_is_atomic_on_error(self):
        bad = {**self.rows[0], "pedido_id": "bad", "quantidade": -1}
        with self.assertRaises(Exception):
            db.import_sales_lines([self.rows[0], bad], self.company, "test", "admin")
        self.assertTrue(db.list_import_batches(self.company).empty)
        self.assertTrue(db.query_df("SELECT * FROM sales_lines").empty)

    def test_demo_cleanup_preserves_real_and_other_company(self):
        db.seed_demo(self.company, "test", "admin")
        db.seed_demo(self.other, "test", "other")
        db.add_transaction({"date": "2026-10-01", "kind": "Receita", "category": "Vendas", "description": "Real", "amount": 50, "payment_method": "PIX", "status": "Pago"}, self.company, "test", "admin")
        self.assertEqual(db.delete_demo_transactions(self.company, "test", "admin"), 9)
        self.assertEqual(len(db.query_df("SELECT * FROM transactions WHERE company_id=?", [self.company])), 1)
        self.assertEqual(len(db.query_df("SELECT * FROM transactions WHERE company_id=?", [self.other])), 9)

    def test_migration_dry_run_preserves_original(self):
        from migrate_postgres import migrate
        db.import_sales_lines(self.rows, self.company, "test", "admin")
        original = hashlib.sha256(db.DB_PATH.read_bytes()).hexdigest()
        counts = migrate(db.DB_PATH)
        self.assertEqual(counts["sales_lines"], 1)
        self.assertEqual(counts["companies"], 2)
        self.assertEqual(hashlib.sha256(db.DB_PATH.read_bytes()).hexdigest(), original)


class PostgresAdapterTests(unittest.TestCase):
    def test_parameter_and_schema_translation(self):
        self.assertEqual(sql_for_postgres("SELECT * FROM users WHERE subject=?"), "SELECT * FROM users WHERE subject=%s")
        self.assertIn("ON CONFLICT DO NOTHING", sql_for_postgres("INSERT OR IGNORE INTO t(x) VALUES (?)"))
        self.assertIn("GENERATED BY DEFAULT AS IDENTITY", sql_for_postgres("id INTEGER PRIMARY KEY AUTOINCREMENT"))
        self.assertEqual(sql_for_postgres("amount REAL"), "amount DOUBLE PRECISION")
        row = Row(id=5, name="A")
        self.assertEqual(row[0], row["id"])
        self.assertEqual(dict(row), {"id": 5, "name": "A"})


class ChartThemeTests(unittest.TestCase):
    def test_chart_uses_app_theme_without_changing_values(self):
        import plotly.graph_objects as go
        import ui
        for dark, color in ((False, "#17191f"), (True, "#edf1f7")):
            fig = go.Figure(go.Bar(x=["A"], y=[100]))
            with patch.object(ui.st, "session_state", {"dark_mode": dark}), patch.object(ui.st, "plotly_chart") as render:
                ui.render_plotly(fig)
                self.assertEqual(fig.layout.font.color, color)
                self.assertEqual(tuple(fig.data[0].y), (100,))
                self.assertIsNone(render.call_args.kwargs["theme"])
