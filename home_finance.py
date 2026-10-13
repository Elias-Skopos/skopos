"""Small company-scoped Home summary; planning assumptions are not ledger entries."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json

import pandas as pd

import autonomy
import db

SETTING = "home_break_even"
CENT = Decimal("0.01")


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Informe um valor numérico válido.") from exc
    if not number.is_finite():
        raise ValueError("Informe um valor numérico finito.")
    return number


def break_even(fixed_costs, margin_pct):
    fixed, margin = _decimal(fixed_costs), _decimal(margin_pct)
    if not 0 <= fixed <= Decimal("1000000000000"):
        raise ValueError("Os custos fixos devem ser positivos ou zero, até R$ 1 trilhão.")
    if not Decimal("-100") <= margin <= Decimal("100"):
        raise ValueError("A margem deve estar entre -100% e 100%.")
    return (fixed * 100 / margin).quantize(CENT, rounding=ROUND_HALF_UP) if margin > 0 else None


def save_break_even(company_id, fixed_costs, margin_pct, issuer, subject):
    break_even(fixed_costs, margin_pct)
    fixed, margin = _decimal(fixed_costs).quantize(CENT, rounding=ROUND_HALF_UP), _decimal(margin_pct).quantize(CENT, rounding=ROUND_HALF_UP)
    break_even(fixed, margin)
    db.set_app_settings({SETTING: json.dumps({
        "fixed_costs": str(fixed), "margin_pct": str(margin),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })}, company_id, issuer, subject)


def load_break_even(company_id):
    raw = db.get_app_setting(SETTING, company_id)
    if not raw:
        return None
    try:
        config = json.loads(raw)
        fixed, margin = _decimal(config["fixed_costs"]), _decimal(config["margin_pct"])
        amount = break_even(fixed, margin)
        return {"fixed_costs": fixed, "margin_pct": margin, "amount": amount}
    except (ValueError, TypeError, KeyError):
        return None


def paid_totals(frame, start, end):
    data = autonomy.effective_finance(frame)
    if data.empty:
        return {"income": Decimal("0.00"), "expense": Decimal("0.00"), "count": 0}
    paid = data[(data["status"] == "Pago") & data["date"].dt.date.between(start, end)]
    def total(kind):
        return sum((_decimal(v) for v in paid.loc[paid["kind"] == kind, "amount"]), Decimal(0)).quantize(CENT, rounding=ROUND_HALF_UP)
    return {"income": total("Receita"), "expense": total("Despesa"), "count": len(paid)}


def next_commitments(frame, today=None):
    today = today or date.today()
    if frame.empty:
        return [], 0
    pending = frame[(frame["status"] == "Pendente") & (frame["kind"] == "Despesa")].copy()
    pending["due_date"] = pd.to_datetime(pending["due_date"], errors="coerce")
    unscheduled = int(pending["due_date"].isna().sum())
    scheduled = pending.dropna(subset=["due_date"]).sort_values(["due_date", "id"]).head(3)
    result = []
    for row in scheduled.to_dict("records"):
        row["due_date"] = row["due_date"].date()
        row["overdue"] = row["due_date"] < today
        result.append(row)
    return result, unscheduled


def settle_commitments(company_id, ids, payment_day, issuer, subject):
    """Confirm at most three pending expenses atomically, checking live permissions."""
    if not ids or len(ids) > 3 or len(set(ids)) != len(ids) or any(type(i) is not int for i in ids):
        raise ValueError("Selecione de um a três compromissos diferentes.")
    try:
        day = date.fromisoformat(payment_day)
    except (ValueError, TypeError) as exc:
        raise ValueError("Informe a data efetiva do pagamento.") from exc
    if day > date.today():
        raise ValueError("Um pagamento realizado não pode ter data futura.")
    with db.connection() as conn:
        if not getattr(conn, "is_postgres", False):
            conn.execute("BEGIN IMMEDIATE")
        db._require_role(conn, company_id, issuer, subject, ("administrator",))
        rows = []
        for transaction_id in ids:
            suffix = " FOR UPDATE" if getattr(conn, "is_postgres", False) else ""
            row = conn.execute("SELECT id,kind,status,due_date FROM transactions WHERE company_id=? AND id=?" + suffix,
                               (company_id, transaction_id)).fetchone()
            if row is None or row["kind"] != "Despesa" or row["status"] != "Pendente" or not row["due_date"]:
                raise ValueError("Um compromisso mudou ou não está mais pendente. Atualize a Home e confira novamente.")
            rows.append(transaction_id)
        for transaction_id in rows:
            conn.execute("UPDATE transactions SET status='Pago',payment_date=?,updated_at=CURRENT_TIMESTAMP WHERE company_id=? AND id=?",
                         (day.isoformat(), company_id, transaction_id))
