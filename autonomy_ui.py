"""Native Streamlit controls for the daily finance workflow."""
from datetime import date

import pandas as pd
import streamlit as st

import autonomy as data
import db
from import_contract import read_csv, csv_template, brazilian_frame
from ui import money


def import_form(kind, company_id, issuer, subject):
    daily = kind == "daily"
    columns = data.DAILY_COLUMNS if daily else data.FINANCE_COLUMNS
    label = "vendas diárias" if daily else "lançamentos financeiros"
    example = ([{"data": "2026-10-01", "total_vendas": "1250.00"}] if daily else [
        {"referencia": "REC-001", "data": "2026-10-01", "tipo": "Receita", "categoria": "Vendas de livros",
         "descricao": "Recebimento de vendas", "valor": "1250.00", "status": "Pago", "data_pagamento": "2026-10-03", "forma_pagamento": "Cartão"},
        {"referencia": "ALUGUEL-2026-10", "data": "2026-10-01", "tipo": "Despesa", "categoria": "Aluguel",
         "descricao": "Aluguel de outubro", "valor": "2800.00", "status": "Pendente", "vencimento": "2026-10-10"}])
    with st.expander(f"Importar {label}"):
        st.caption("CSV separado por ponto e vírgula (;), com datas DD-MM-AAAA e valores com vírgula decimal, até duas casas (1234,56), sem R$ ou separador de milhar. O arquivo inteiro é bloqueado se houver erro.")
        with st.container(horizontal=True):
            st.download_button("Baixar modelo", csv_template(columns), file_name=f"modelo_{kind}_skopos.csv",
                               mime="text/csv", key=f"{kind}_model_{company_id}")
            st.download_button("Baixar exemplo preenchido", csv_template(columns, example), file_name=f"exemplo_{kind}_skopos.csv",
                               mime="text/csv", key=f"{kind}_example_{company_id}")
        if daily:
            st.info("Uma linha por dia, com data e total_vendas. São vendas realizadas, não dinheiro recebido. Não alimentam pedidos, margens, clientes ou caixa. Reimportar uma data substitui o total desse dia.")
        else:
            st.info("Use uma referência estável e exclusiva por lançamento, por exemplo ALUGUEL-2026-10. Reimportar a referência atualiza o lançamento. Não use o total das vendas como recebimento sem confirmar quando o dinheiro entrou.")
            st.caption("Pago exige data_pagamento. Pendente exige vencimento e data_pagamento vazia. Forma de pagamento e observações são opcionais. Os registros manuais não são conciliados automaticamente com um CSV; não importe novamente a mesma movimentação com outra referência.")
        uploaded = st.file_uploader(f"CSV de {label}", type=["csv"], key=f"{kind}_csv_{company_id}")
        if uploaded:
            try:
                rows, errors = data.normalize_input(read_csv(uploaded.getvalue()), kind)
                if errors:
                    for error in errors[:20]:
                        st.error(error)
                    if len(errors) > 20:
                        st.caption(f"Mais {len(errors) - 20} erros. Corrija o arquivo e envie novamente.")
                else:
                    st.dataframe(brazilian_frame(pd.DataFrame(rows)).head(100), hide_index=True, width="stretch")
                    st.caption(f"{len(rows)} registros válidos. Confira a prévia antes de confirmar.")
                    if st.button("Confirmar importação", type="primary", key=f"import_{kind}_{company_id}"):
                        n = data.import_input(rows, kind, company_id, issuer, subject, f"CSV: {uploaded.name}")
                        st.session_state[f"input_notice_{company_id}_{kind}"] = f"Importação concluída: {n} registros."
                        st.rerun()
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
        notice = st.session_state.get(f"input_notice_{company_id}_{kind}")
        if notice:
            st.success(notice)


def import_history(kind, company_id, issuer, subject):
    batches = data.input_history(company_id)
    batches = batches[batches["kind"] == kind]
    with st.expander("Histórico das importações simplificadas"):
        if batches.empty:
            st.caption("Nenhuma importação registrada.")
            return
        options = {r["id"]: f"{r['created_at']} · {r['source']} · {r['current_rows']} registros atuais" for r in batches.to_dict("records")}
        batch = st.selectbox("Lote", list(options), format_func=options.get, key=f"input_history_{company_id}_{kind}")
        table = "daily_sales" if kind == "daily" else "transactions"
        rows = db.query_df(f"SELECT * FROM {table} WHERE company_id=? AND input_id=?", [company_id, batch])
        st.caption("A exclusão remove apenas os registros que ainda pertencem a este lote. Reimportações transferem registros ao novo lote; a exclusão não recupera valores anteriores. A exportação abaixo é para conferência, não é o modelo de importação.")
        st.download_button("Exportar registros do lote", rows.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"conferencia_{kind}.csv", mime="text/csv", key=f"input_export_{company_id}_{kind}")
        confirmed = st.checkbox("Confirmo a exclusão dos registros deste lote", key=f"input_confirm_{company_id}_{kind}_{batch}")
        if st.button("Excluir lote", key=f"input_delete_{company_id}_{kind}"):
            if not confirmed:
                st.error("Confirme a exclusão do lote.")
            else:
                data.delete_input(batch, company_id, issuer, subject)
                st.session_state.pop(f"input_notice_{company_id}_{kind}", None)
                st.rerun()


def daily_summary(company_id, start, end, hide=False):
    frame = db.query_df("SELECT date,amount FROM daily_sales WHERE company_id=? AND date BETWEEN ? AND ? ORDER BY date",
                        [company_id, start.isoformat(), end.isoformat()])
    if frame.empty:
        return
    st.subheader("Vendas diárias informadas")
    with st.container(horizontal=True):
        st.metric("Total de vendas informado", "••••••" if hide else money(frame["amount"].sum()))
        st.metric("Dias informados", len(frame))
        st.metric("Média por dia informado", "••••••" if hide else money(frame["amount"].mean()))
    st.caption("Esses totais não são somados às vendas por item nem aos recebimentos. Dias sem registro não são considerados vendas zero. Para confirmar um dia sem vendas, importe total_vendas = 0.")
    if not hide:
        chart = frame.assign(date=pd.to_datetime(frame["date"])).set_index("date")["amount"]
        st.line_chart(chart, x_label="Data", y_label="Vendas (R$)")


def data_status(company_id):
    lines = []
    for label, table, date_column, updated in [
        ("Vendas diárias", "daily_sales", "date", "updated_at"),
        ("Vendas por item", "sales_lines", "sale_date", "updated_at"),
        ("Estoque", "inventory_snapshots", "snapshot_date", "updated_at"),
        ("Lançamentos financeiros", "transactions", "CASE WHEN status='Pago' THEN COALESCE(payment_date,date) ELSE date END", "COALESCE(NULLIF(updated_at,''),created_at)")]:
        row = db.query_df(f"SELECT COUNT(*) AS n,MAX({date_column}) AS latest,MAX({updated}) AS updated FROM {table} WHERE company_id=?", [company_id]).iloc[0]
        lines.append({"Dados": label, "Registros": int(row["n"]), "Última data informada": row["latest"] or "Não informado",
                      "Última gravação (UTC)": row["updated"] or "Não informado"})
    with st.expander("Dados disponíveis e atualização", expanded=not any(r["Registros"] for r in lines)):
        st.dataframe(pd.DataFrame(lines), hide_index=True, width="stretch")
        st.caption("Última data informada não garante que todos os dias estejam completos. Confira os totais com a origem. Vendas por item, vendas diárias e recebimentos são fontes separadas.")
        legacy = db.query_df("SELECT COUNT(*) AS n FROM transactions WHERE company_id=? AND status='Pago' AND payment_date IS NULL", [company_id]).iloc[0]["n"]
        if legacy:
            st.caption(f"{legacy} lançamentos antigos pagos usam a data original como data de caixa. Confira as datas em Lançamentos e use a ação de corrigir a data de recebimento/pagamento quando necessário.")


def opening_form(company_id, issuer, subject, can_edit):
    records = db.query_df("SELECT * FROM opening_balances WHERE company_id=?", [company_id])
    opening = records.iloc[0].to_dict() if not records.empty else None
    if can_edit:
        with st.expander("Cadastrar ou ajustar saldo inicial", expanded=opening is None):
            st.caption("Informe o saldo consolidado do caixa e das contas da empresa no início do dia escolhido, antes das movimentações desse dia. Não cadastre esse saldo como receita. Transferências entre contas da própria empresa não são entradas ou saídas deste caixa consolidado.")
            with st.form(f"opening_balance_{company_id}"):
                day = st.date_input("Data do saldo inicial", value=date.fromisoformat(opening["date"]) if opening else date.today())
                amount = st.number_input("Saldo inicial (R$)", value=float(opening["amount"]) if opening else 0.0, step=100.0, format="%.2f")
                confirmed = st.checkbox("Conferi o saldo com o caixa e as contas da empresa")
                if st.form_submit_button("Salvar saldo inicial", type="primary"):
                    if not confirmed:
                        st.error("Confira e confirme o saldo antes de salvar.")
                    else:
                        try:
                            data.save_opening(company_id, day.isoformat(), amount, issuer, subject)
                            st.rerun()
                        except (ValueError, PermissionError) as exc:
                            st.error(str(exc))
    return opening


def recurrence_form(company_id, issuer, subject, categories, payments):
    with st.expander("Despesas recorrentes: aluguel e outras contas"):
        st.caption("Cadastre valor e vencimento uma vez e gere as contas dos próximos meses. Elas ficam pendentes até você confirmar o pagamento. Dias 29–31 são ajustados ao último dia do mês quando necessário.")
        with st.form(f"recurrence_{company_id}"):
            description = st.text_input("Descrição da despesa recorrente", placeholder="Aluguel da loja")
            category = st.selectbox("Categoria recorrente", categories)
            amount = st.number_input("Valor mensal (R$)", min_value=0.0, step=100.0, format="%.2f")
            payment = st.selectbox("Forma de pagamento recorrente", payments)
            due = st.number_input("Dia do vencimento", min_value=1, max_value=31, value=10)
            first = st.date_input("Primeiro mês da recorrência", value=date.today())
            if st.form_submit_button("Cadastrar despesa recorrente", type="primary"):
                try:
                    data.add_recurrence(company_id, description, category, amount, payment, due, first.strftime("%Y-%m"), issuer, subject)
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
        rules = db.query_df("SELECT * FROM recurring_expenses WHERE company_id=? ORDER BY description", [company_id])
        if rules.empty:
            return
        options = {r["id"]: r for r in rules.to_dict("records")}
        selected = st.selectbox("Despesa cadastrada", list(options), format_func=lambda rid: f"{options[rid]['description']} · {money(options[rid]['amount'])} · {'Ativa' if options[rid]['active'] else 'Inativa'}", key=f"recurrence_selected_{company_id}")
        rule = options[selected]
        with st.form(f"recurrence_generate_{company_id}"):
            through = st.date_input("Gerar contas até o mês", value=max(date.today(), date.fromisoformat(rule["start_month"] + "-01")))
            if st.form_submit_button("Gerar contas pendentes", disabled=not bool(rule["active"])):
                try:
                    n = data.generate_recurrence(selected, through.strftime("%Y-%m"), company_id, issuer, subject)
                    st.session_state[f"recurrence_notice_{company_id}"] = f"{n} contas novas geradas. Contas já existentes não foram alteradas."
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
        if st.button("Desativar recorrência" if rule["active"] else "Reativar recorrência", key=f"recurrence_toggle_{company_id}"):
            data.set_recurrence_active(selected, not rule["active"], company_id, issuer, subject)
            st.rerun()
        st.caption("Desativar impede novas gerações e preserva as contas já criadas. Para um reajuste, desative a regra antiga e cadastre uma nova a partir do mês correto; revise os lançamentos futuros existentes para evitar duplicação.")
        notice = st.session_state.get(f"recurrence_notice_{company_id}")
        if notice:
            st.success(notice)
