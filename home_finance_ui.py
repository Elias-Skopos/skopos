"""Three focused Home blocks with native responsive containers and forms."""
from datetime import date

import streamlit as st

import home_finance as data
from ui import kpi, money


def render_summary(frame, start, end, company_id, issuer, subject, can_edit, hidden):
    with st.container(horizontal=True, wrap=True, gap="medium", key="home_financial_summary"):
        with st.container(border=True, width=360):
            render_break_even(company_id, issuer, subject, can_edit, hidden)
        with st.container(border=True, width=360):
            render_commitments(frame, company_id, issuer, subject, can_edit, hidden)
        with st.container(border=True, width=360):
            render_movements(frame, start, end, hidden)


def render_break_even(company_id, issuer, subject, can_edit, hidden):
    st.subheader("Ponto de equilíbrio")
    config = data.load_break_even(company_id)
    if config is None:
        kpi("Faturamento mínimo mensal", "Não configurado", hide_values=hidden)
        st.caption("Informe os custos fixos e a margem para estimar quanto a empresa precisa vender por mês.")
    elif config["amount"] is None:
        kpi("Faturamento mínimo mensal", "Sem equilíbrio", hide_values=hidden)
        st.caption("Com margem zero ou negativa, aumentar as vendas não cobre os custos fixos. Revise as premissas.")
    else:
        kpi("Faturamento mínimo mensal", money(config["amount"]), "Estimativa mensal pelas premissas da empresa", hide_values=hidden)
        if not hidden:
            margin_label = f"{config['margin_pct']:.2f}".replace(".", ",")
            st.caption(f"Custos fixos: {money(config['fixed_costs'])}/mês · Margem: {margin_label}%")
    st.caption("Custos fixos ÷ margem de contribuição. Não inclui parcelas do principal de dívidas nem reservas de caixa.")
    if can_edit:
        with st.expander("Configurar ponto de equilíbrio", expanded=config is None and not hidden):
            st.caption("Inclua aluguel, condomínio, folha, pró-labore e demais custos fixos. A margem deve considerar CMV, descontos, impostos, taxas de cartão e outros custos variáveis, sem descontar um item duas vezes.")
            if hidden:
                st.caption("Mostre os valores na barra superior para editar as premissas.")
            else:
                with st.form(f"home_break_even_form_{company_id}"):
                    costs = st.number_input("Custos fixos mensais (R$)", min_value=0.0, max_value=1e12,
                                            value=float(config["fixed_costs"]) if config else 0.0,
                                            step=100.0, format="%.2f", key=f"home_fixed_costs_{company_id}")
                    margin = st.number_input("Margem de contribuição estimada (%)", min_value=-100.0, max_value=100.0,
                                             value=float(config["margin_pct"]) if config else 0.0,
                                             step=0.5, format="%.2f", key=f"home_margin_{company_id}")
                    st.caption("Use a margem sobre o mesmo faturamento que deseja comparar com a meta. O cálculo é mensal, independente do período do filtro.")
                    if st.form_submit_button("Salvar premissas", type="primary", key=f"save_home_break_even_{company_id}"):
                        try:
                            data.save_break_even(company_id, costs, margin, issuer, subject)
                            st.rerun()
                        except (ValueError, PermissionError) as exc:
                            st.error(str(exc))
    elif config is None:
        st.caption("O proprietário pode configurar as premissas.")


def render_commitments(frame, company_id, issuer, subject, can_edit, hidden):
    st.subheader("Próximos compromissos")
    commitments, unscheduled = data.next_commitments(frame)
    st.caption("Até três pagamentos pendentes por vencimento, incluindo vencidos primeiro. Independente do filtro de período.")
    if unscheduled:
        st.caption(f"{unscheduled} despesas pendentes sem vencimento. Confira em Contas.")
    if not commitments:
        st.caption("Nenhum pagamento pendente com vencimento informado.")
        return
    with st.form(f"home_commitments_form_{company_id}", clear_on_submit=True):
        selected = []
        for row in commitments:
            amount = "••••••" if hidden else money(row["amount"])
            description = str(row["description"]).replace("\n", " ")
            checked = st.checkbox(description, key=f"home_commitment_{company_id}_{row['id']}", disabled=not can_edit)
            st.caption(f"{row['due_date']:%d/%m/%Y} · {amount}" + (" · Vencido" if row["overdue"] else ""))
            if checked:
                selected.append(int(row["id"]))
        if can_edit:
            payment_day = st.date_input("Data efetiva do pagamento", value=date.today(), max_value=date.today(),
                                         format="DD/MM/YYYY", key=f"home_payment_day_{company_id}")
            st.caption("Marque somente o que já pagou e confirme. A baixa também atualiza Contas e entradas/saídas.")
        else:
            st.caption("Somente o proprietário pode confirmar pagamentos.")
        confirmed = st.form_submit_button("Confirmar pagamentos", disabled=not can_edit, key=f"settle_home_commitments_{company_id}")
    if confirmed:
        try:
            data.settle_commitments(company_id, selected, payment_day.isoformat(), issuer, subject)
            st.rerun()
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))


def render_movements(frame, start, end, hidden):
    st.subheader("Entradas e saídas")
    st.caption(f"Recebidos e pagos de {start:%d/%m/%Y} a {end:%d/%m/%Y}.")
    totals = data.paid_totals(frame, start, end)
    kpi("Entradas", money(totals["income"]), "Receitas recebidas no período", hide_values=hidden)
    kpi("Saídas", money(totals["expense"]), "Despesas pagas no período", hide_values=hidden)
    if not totals["count"]:
        st.caption("Nenhum recebimento ou pagamento registrado no período.")
    st.caption("Usa a data efetiva de recebimento/pagamento. Não soma vendas ainda não recebidas nem contas pendentes. Registros antigos sem data efetiva usam a data original.")
