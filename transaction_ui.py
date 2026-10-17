"""Inline, explicitly confirmed edits for financial status and effective dates."""
import hashlib

import pandas as pd
import streamlit as st

import db


def iso_date(value):
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date().isoformat()


def status_editor(filtered, view, company_id, issuer, subject):
    columns = ["Data", "Data do registro", "Tipo", "Categoria", "Descrição", "Status", "Valor"]
    table = view[columns].copy()
    table["Vencimento"] = pd.to_datetime(filtered["due_date"]).dt.date
    table["Pagamento / recebimento"] = pd.to_datetime(filtered["payment_date"]).dt.date
    # A new snapshot resets old editor deltas after a save, filter or refresh.
    snapshot = filtered[["id", "status", "due_date", "payment_date"]].to_json(date_format="iso")
    version = hashlib.sha256(snapshot.encode()).hexdigest()[:16]
    st.caption("Edite Status e as datas na tabela. Pago exige pagamento/recebimento; Pendente exige vencimento. Confira as mudanças e salve juntas.")
    edited = st.data_editor(
        table, hide_index=True, width="stretch", num_rows="fixed",
        disabled=[column for column in columns if column != "Status"],
        column_config={
            "Status": st.column_config.SelectboxColumn(options=["Pago", "Pendente"], required=True),
            "Vencimento": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Pagamento / recebimento": st.column_config.DateColumn(format="DD/MM/YYYY"),
        }, key=f"transaction_editor_{company_id}_{version}",
    )
    changes = []
    for index, original in filtered.iterrows():
        row = edited.loc[index]
        expected = {"status": original["status"], "due_date": iso_date(original["due_date"]),
                    "payment_date": iso_date(original["payment_date"])}
        values = {"status": row["Status"], "due_date": iso_date(row["Vencimento"]),
                  "payment_date": iso_date(row["Pagamento / recebimento"])}
        if values["status"] == "Pendente":
            values["payment_date"] = None
        if values != expected:
            changes.append({"id": int(original["id"]), "expected": expected, **values})
    if changes:
        st.info(f"{len(changes)} lançamento(s) com alterações para conferir.")
    if st.button("Salvar alterações de status", disabled=not changes, type="primary", key=f"save_statuses_{company_id}"):
        try:
            count = db.update_transaction_statuses(changes, company_id, issuer, subject)
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))
        else:
            st.session_state[f"transaction_notice_{company_id}"] = f"{count} lançamento(s) atualizado(s)."
            st.rerun()
