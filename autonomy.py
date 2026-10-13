"""Daily sales, financial imports and cash planning, kept separate from item sales."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
import math
import re
from uuid import uuid4

import pandas as pd

import db
from import_contract import brazilian_date, brazilian_number

DAILY_COLUMNS = ["data", "total_vendas"]
FINANCE_COLUMNS = ["referencia", "data", "tipo", "categoria", "descricao", "valor", "status",
                   "data_pagamento", "vencimento", "forma_pagamento", "observacoes"]
FINANCE_REQUIRED = ["referencia", "data", "tipo", "categoria", "descricao", "valor", "status"]


def init_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS input_batches (
            id TEXT PRIMARY KEY, company_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('daily','finance')), source TEXT NOT NULL,
            row_count INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS daily_sales (
            company_id INTEGER NOT NULL, date TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>=0),
            input_id TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(company_id,date));
        CREATE TABLE IF NOT EXISTS opening_balances (
            company_id INTEGER PRIMARY KEY, date TEXT NOT NULL, amount REAL NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS recurring_expenses (
            id TEXT PRIMARY KEY, company_id INTEGER NOT NULL, description TEXT NOT NULL,
            category TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>0), payment_method TEXT NOT NULL,
            due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31), start_month TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)
    for column, definition in {"payment_date": "TEXT", "external_id": "TEXT", "input_id": "TEXT", "updated_at": "TEXT NOT NULL DEFAULT ''",
                                "recurring_id": "TEXT", "recurring_month": "TEXT"}.items():
        if column not in db._columns(conn, "transactions"):
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {column} {definition}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_finance_reference ON transactions(company_id,external_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_recurring_month ON transactions(company_id,recurring_id,recurring_month)")


def iso_date(value):
    text = str(value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("use uma data válida no formato AAAA-MM-DD")
    parsed = date.fromisoformat(text)
    if not 1900 <= parsed.year <= 2200:
        raise ValueError("use uma data entre 1900 e 2200")
    return parsed.isoformat()


def money_number(value, positive=False, signed=False):
    text = str(value).strip()
    pattern = r"-?[0-9]+(?:\.[0-9]{1,2})?" if signed else r"[0-9]+(?:\.[0-9]{1,2})?"
    if not re.fullmatch(pattern, text):
        raise ValueError("use ponto decimal e até duas casas, sem moeda ou separador de milhar (ex.: 1234.56)")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("valor inválido") from exc
    result = float(number)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError("informe um valor finito maior que zero" if positive else "valor fora do limite suportado")
    return result


def normalize_input(frame, kind, *, strict=True):
    columns = DAILY_COLUMNS if kind == "daily" else FINANCE_COLUMNS
    required = DAILY_COLUMNS if kind == "daily" else FINANCE_REQUIRED
    data = frame.copy()
    data.columns = [str(c).strip().lstrip("\ufeff").lower() for c in data.columns]
    if data.columns.duplicated().any():
        return [], ["O cabeçalho contém colunas repetidas."]
    missing = [c for c in required if c not in data]
    unknown = [c for c in data if c not in columns]
    if missing or unknown:
        return [], ([f"Colunas obrigatórias ausentes: {', '.join(missing)}."] if missing else []) + ([f"Colunas não reconhecidas: {', '.join(unknown)}."] if unknown else [])
    if data.empty:
        return [], ["O arquivo não contém registros."]
    rows, errors, seen = [], [], set()
    for line, raw in enumerate(data.to_dict("records"), 2):
        row = {c: "" if pd.isna(raw.get(c)) else str(raw.get(c, "")).strip() for c in columns}
        for field in required:
            if not row[field]:
                errors.append(f"Linha {line}, coluna '{field}': campo obrigatório vazio.")
        for field in (["data"] if kind == "daily" else ["data", "data_pagamento", "vencimento"]):
            if row[field]:
                try:
                    row[field] = iso_date(brazilian_date(row[field]) if strict else row[field])
                except ValueError:
                    errors.append(f"Linha {line}, coluna '{field}': use uma data válida {'DD-MM-AAAA' if strict else 'AAAA-MM-DD'}.")
        field = "total_vendas" if kind == "daily" else "valor"
        try:
            value = brazilian_number(row[field], decimal_places=2) if strict else row[field]
            row[field] = money_number(value, positive=kind == "finance")
        except ValueError as exc:
            errors.append(f"Linha {line}, coluna '{field}', valor {row[field]!r}: {exc}.")
        key = row["data"] if kind == "daily" else row["referencia"]
        if key in seen:
            errors.append(f"Linha {line}: {'data' if kind == 'daily' else 'referência'} repetida: {key}.")
        seen.add(key)
        if kind == "finance":
            if row["tipo"] not in {"Receita", "Despesa"}:
                errors.append(f"Linha {line}, coluna 'tipo': use Receita ou Despesa.")
            if row["status"] not in {"Pago", "Pendente"}:
                errors.append(f"Linha {line}, coluna 'status': use Pago ou Pendente.")
            if row["status"] == "Pago" and not row["data_pagamento"]:
                errors.append(f"Linha {line}: informe data_pagamento para o recebimento/pagamento realizado.")
            if row["status"] == "Pendente" and (not row["vencimento"] or row["data_pagamento"]):
                errors.append(f"Linha {line}: um lançamento Pendente exige vencimento e data_pagamento vazia.")
            row["forma_pagamento"] = row["forma_pagamento"] or "Não informado"
            if len(row["referencia"]) > 120:
                errors.append(f"Linha {line}: referência deve ter até 120 caracteres.")
        rows.append(row)
    return ([], errors) if errors else (rows, [])


def import_input(rows, kind, company_id, issuer, subject, source="CSV"):
    if kind not in {"daily", "finance"}:
        raise ValueError("Selecione um tipo de importação válido.")
    validated, errors = normalize_input(pd.DataFrame(rows), kind, strict=False)
    if errors:
        raise ValueError("\n".join(errors[:20]))
    with db.connection() as conn:
        db._require_role(conn, company_id, issuer, subject, db.EDIT_ROLES)
        batch = uuid4().hex
        conn.execute("INSERT INTO input_batches(id,company_id,kind,source,row_count) VALUES (?,?,?,?,?)",
                     (batch, company_id, kind, source, len(validated)))
        for row in validated:
            if kind == "daily":
                conn.execute("""INSERT INTO daily_sales(company_id,date,amount,input_id) VALUES (?,?,?,?)
                    ON CONFLICT(company_id,date) DO UPDATE SET amount=excluded.amount,input_id=excluded.input_id,updated_at=CURRENT_TIMESTAMP""",
                             (company_id, row["data"], row["total_vendas"], batch))
            else:
                conn.execute("""INSERT INTO transactions(company_id,date,kind,category,description,amount,
                    payment_method,status,payment_date,due_date,notes,external_id,input_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id,external_id) DO UPDATE SET
                    date=excluded.date,kind=excluded.kind,category=excluded.category,description=excluded.description,
                    amount=excluded.amount,payment_method=excluded.payment_method,status=excluded.status,
                    payment_date=excluded.payment_date,due_date=excluded.due_date,notes=excluded.notes,input_id=excluded.input_id,updated_at=CURRENT_TIMESTAMP""",
                    (company_id, row["data"], row["tipo"], row["categoria"], row["descricao"], row["valor"],
                     row["forma_pagamento"], row["status"], row["data_pagamento"] or None, row["vencimento"] or None,
                     row["observacoes"], row["referencia"], batch))
    return len(validated)


def input_history(company_id):
    return db.query_df("""SELECT b.*,(SELECT COUNT(*) FROM daily_sales d WHERE d.company_id=b.company_id AND d.input_id=b.id)
        +(SELECT COUNT(*) FROM transactions t WHERE t.company_id=b.company_id AND t.input_id=b.id) AS current_rows
        FROM input_batches b WHERE b.company_id=? ORDER BY b.created_at DESC,b.id""", [company_id])


def delete_input(batch, company_id, issuer, subject):
    with db.connection() as conn:
        db._require_role(conn, company_id, issuer, subject, db.EDIT_ROLES)
        count = 0
        for table in ("daily_sales", "transactions"):
            count += conn.execute(f"DELETE FROM {table} WHERE company_id=? AND input_id=?", (company_id, batch)).rowcount
        conn.execute("DELETE FROM input_batches WHERE company_id=? AND id=?", (company_id, batch))
    return count


def save_opening(company_id, day, amount, issuer, subject):
    day, amount = iso_date(day), money_number(amount, signed=True)
    with db.connection() as conn:
        db._require_role(conn, company_id, issuer, subject, db.EDIT_ROLES)
        conn.execute("""INSERT INTO opening_balances(company_id,date,amount) VALUES (?,?,?) ON CONFLICT(company_id)
            DO UPDATE SET date=excluded.date,amount=excluded.amount,updated_at=CURRENT_TIMESTAMP""", (company_id, day, amount))


def add_recurrence(company_id, description, category, amount, payment, due_day, start_month, issuer, subject):
    if not description.strip() or not category.strip() or not re.fullmatch(r"\d{4}-\d{2}", start_month):
        raise ValueError("Informe descrição, categoria e mês inicial AAAA-MM.")
    iso_date(start_month + "-01")
    if not 1 <= int(due_day) <= 31:
        raise ValueError("O dia de vencimento deve estar entre 1 e 31.")
    amount = money_number(amount, positive=True)
    rid = uuid4().hex
    with db.connection() as conn:
        db._require_role(conn, company_id, issuer, subject, db.EDIT_ROLES)
        existing = conn.execute("SELECT id FROM recurring_expenses WHERE company_id=? AND description=? AND start_month=?",
                                (company_id, description.strip(), start_month)).fetchone()
        if existing:
            raise ValueError("Essa despesa já foi cadastrada para esse mês inicial. Selecione a recorrência existente abaixo.")
        conn.execute("""INSERT INTO recurring_expenses(id,company_id,description,category,amount,payment_method,due_day,start_month)
            VALUES (?,?,?,?,?,?,?,?)""", (rid, company_id, description.strip(), category.strip(), amount, payment, int(due_day), start_month))
    return rid


def set_recurrence_active(rid, active, company_id, issuer, subject):
    with db.connection() as conn:
        db._require_role(conn, company_id, issuer, subject, db.EDIT_ROLES)
        conn.execute("UPDATE recurring_expenses SET active=? WHERE id=? AND company_id=?", (int(bool(active)), rid, company_id))


def generate_recurrence(rid, through_month, company_id, issuer, subject):
    end = date.fromisoformat(iso_date(through_month + "-01"))
    with db.connection() as conn:
        db._require_role(conn, company_id, issuer, subject, db.EDIT_ROLES)
        rule = conn.execute("SELECT * FROM recurring_expenses WHERE id=? AND company_id=? AND active=1", (rid, company_id)).fetchone()
        if not rule:
            raise ValueError("Selecione uma despesa recorrente ativa.")
        start = date.fromisoformat(rule["start_month"] + "-01")
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        if not 1 <= months <= 24:
            raise ValueError("Escolha um período de 1 a 24 meses a partir do início da recorrência.")
        count = 0
        for n in range(months):
            value = start.year * 12 + start.month - 1 + n
            year, month = value // 12, value % 12 + 1
            due = date(year, month, min(rule["due_day"], monthrange(year, month)[1])).isoformat()
            period = f"{year:04d}-{month:02d}"
            count += conn.execute("""INSERT INTO transactions(company_id,date,kind,category,description,amount,
                payment_method,status,due_date,recurring_id,recurring_month) VALUES (?,?,'Despesa',?,?,?,?, 'Pendente',?,?,?)
                ON CONFLICT(company_id,recurring_id,recurring_month) DO NOTHING""",
                (company_id, due, rule["category"], f"{rule['description']} · {period}", rule["amount"], rule["payment_method"], due, rid, period)).rowcount
    return count


def effective_finance(frame):
    """Paid records use settlement date; legacy records retain their original date."""
    data = frame.copy()
    if data.empty:
        return data
    payments = pd.to_datetime(data.get("payment_date", data["date"]), errors="coerce")
    data["record_date"] = pd.to_datetime(data.get("record_date", data["date"]))
    data["date"] = payments.fillna(data["record_date"]).where(data["status"] == "Pago", data["record_date"])
    data["due_date"] = pd.to_datetime(data["due_date"], errors="coerce")
    return data


def cash_projection(frame, opening, start, end):
    data = effective_finance(frame)
    days = pd.date_range(start, end, freq="D")
    result = pd.DataFrame({"date": days})
    anchor = pd.Timestamp(opening["date"]) if opening else pd.Timestamp(start)
    actual_before = 0.0
    if not data.empty:
        data["cash_date"] = data["date"].where(data["status"] == "Pago", data["due_date"])
        floor = max(anchor, pd.Timestamp(start))
        overdue = (data["status"] == "Pendente") & (data["cash_date"] < floor)
        data.loc[overdue, "cash_date"] = floor
        data["signed"] = data["amount"].where(data["kind"] == "Receita", -data["amount"])
        actual_before = data.loc[(data["status"] == "Pago") & (data["cash_date"] >= anchor)
                                 & (data["cash_date"] < pd.Timestamp(start)), "signed"].sum()
        scoped = data[data["cash_date"].between(max(anchor, pd.Timestamp(start)), pd.Timestamp(end))]
        actual = scoped[scoped["status"] == "Pago"].groupby("cash_date")["signed"].sum()
        pending = scoped[scoped["status"] == "Pendente"].groupby("cash_date")["signed"].sum()
        result["movement"] = result["date"].map(actual).fillna(0)
        result["pending"] = result["date"].map(pending).fillna(0)
    else:
        result["movement"], result["pending"] = 0.0, 0.0
    base = (float(opening["amount"]) if opening else 0.0) + float(actual_before)
    result["actual"] = base + result["movement"].cumsum()
    result["projected"] = result["actual"] + result["pending"].cumsum()
    if opening:
        result.loc[result["date"] < anchor, ["actual", "projected"]] = float("nan")
    return result
