"""Anonymous read-only demonstration of Skopos; never imports the live database."""
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import calculate_inventory, calculate_sales
from demo_data import build_demo
from ui import CHART_COLORS, DARK_CHART_COLORS, money

ROOT = Path(__file__).resolve().parent
PAGES = ["Visão geral", "Vendas", "Estoque", "Contas", "Curva ABC"]


def render_demo_chart(figure):
    # Theme changes are handled in the frontend without a Python rerun. Avoid
    # pinning Plotly background/text colors to the theme of the previous run.
    st.plotly_chart(figure, theme="streamlit", width="stretch")


def render_demo(back):
    # Native theming also reaches canvas tables, calendars and menus. A light
    # CSS override here left those widgets dark while the rest became light.
    dark = st.context.theme.type == "dark"
    data = build_demo()
    px.defaults.color_discrete_sequence = DARK_CHART_COLORS if dark else CHART_COLORS
    with st.sidebar:
        logo = "logo_barra_lateral_dark.svg" if dark else "logo_barra_lateral.svg"
        st.image(str(ROOT / "assets" / logo), width="stretch")
        st.caption("Demonstração sem cadastro")
        page = st.radio("Acompanhamento", PAGES, key="public_demo_page", label_visibility="collapsed")
        period = st.date_input("Período", value=(data["latest_month"], data["end"]),
                               min_value=data["start"], max_value=data["end"], key="public_demo_period")
        st.button("Voltar ao início", on_click=back, icon=":material/arrow_back:", key="demo_back", width="stretch")
    st.caption("SKOPOS · DEMONSTRAÇÃO")
    st.title(data["company"])
    st.info("Todos os nomes e números são fictícios. Explore os painéis; esta demonstração não permite importar ou alterar dados.")
    if len(period) != 2:
        st.info("Selecione o início e o fim do período.")
        return
    start, end = period
    report = calculate_sales(data["sales"], start, end)
    finance = data["finance"].copy()
    finance["date"] = pd.to_datetime(finance["date"])
    scoped = finance[finance["date"].dt.date.between(start, end)]
    paid = scoped[scoped.status == "Pago"]
    if page == "Visão geral":
        revenue = float(paid[paid.kind == "Receita"].amount.sum())
        expense = float(paid[paid.kind == "Despesa"].amount.sum())
        with st.container(horizontal=True, gap="medium"):
            st.metric("Recebimentos", money(revenue))
            st.metric("Pagamentos", money(expense))
            st.metric("Variação do caixa", money(revenue-expense))
        st.caption("Variação considera apenas os recebimentos e pagamentos fictícios do período; não representa saldo bancário.")
        if report:
            with st.container(horizontal=True, gap="medium"):
                st.metric("Vendas", money(report["revenue"]))
                st.metric("Pedidos", report["orders"])
                st.metric("Ticket médio", money(report["ticket"]))
        by_day = paid.groupby(["date", "kind"], as_index=False).amount.sum()
        render_demo_chart(px.line(by_day, x="date", y="amount", color="kind", labels={"date":"Data", "amount":"Valor (R$)", "kind":"Tipo"}))
    elif page == "Vendas":
        st.subheader("Vendas da livraria")
        if report:
            with st.container(horizontal=True):
                st.metric("Faturamento", money(report["revenue"]))
                st.metric("Custo dos produtos", money(report["cogs"]))
                st.metric("Margem de contribuição", money(report["contribution"]))
            by_channel = report["rows"].groupby("channel", as_index=False).net_revenue.sum()
            render_demo_chart(px.bar(by_channel, x="channel", y="net_revenue", labels={"channel":"Canal", "net_revenue":"Vendas (R$)"}))
            st.dataframe(report["rows"][["sale_date", "order_id", "title", "quantity", "net_revenue"]], hide_index=True, width="stretch")
    elif page == "Estoque":
        stock = calculate_inventory(data["stock"], start, end)
        st.subheader("Estoque demonstrativo")
        with st.container(horizontal=True):
            st.metric("Valor em estoque", money(stock["current_value"]))
            st.metric("Itens no mínimo", stock["low_stock_count"])
        st.dataframe(stock["latest"][["title", "quantity", "unit_cost", "minimum_quantity", "stock_value"]], hide_index=True, width="stretch")
        st.caption("Exibe a última posição fictícia disponível, como no painel de estoque do aplicativo.")
    elif page == "Contas":
        st.subheader("Contas a pagar e receber")
        status = st.radio("Status", ["Pendente", "Pago"], horizontal=True, key="demo_status")
        selected = finance[finance.status == status].copy() if status == "Pendente" else scoped[scoped.status == status].copy()
        with st.container(horizontal=True):
            st.metric("A receber" if status == "Pendente" else "Recebido", money(float(selected[selected.kind == "Receita"].amount.sum())))
            st.metric("A pagar" if status == "Pendente" else "Pago", money(float(selected[selected.kind == "Despesa"].amount.sum())))
        st.dataframe(selected.rename(columns={"date":"Data", "kind":"Tipo", "category":"Categoria", "description":"Descrição", "amount":"Valor", "status":"Status", "due_date":"Vencimento"}), hide_index=True, width="stretch")
        if status == "Pendente":
            st.caption("Contas fictícias do mês atual, mostradas à parte do filtro de vendas dos meses encerrados.")
    else:
        st.subheader("Curva ABC de títulos")
        if report:
            ranked = report["rows"].groupby("title", as_index=False).net_revenue.sum().sort_values("net_revenue", ascending=False)
            ranked["Participação acumulada (%)"] = ranked.net_revenue.cumsum()/ranked.net_revenue.sum()*100
            before = ranked["Participação acumulada (%)"] - ranked.net_revenue/ranked.net_revenue.sum()*100
            ranked["Classe"] = before.map(lambda value: "A" if value < 80 else "B" if value < 95 else "C")
            render_demo_chart(px.bar(ranked, x="title", y="net_revenue", color="Classe", labels={"title":"Título", "net_revenue":"Vendas (R$)"}))
            st.dataframe(ranked.rename(columns={"title":"Título", "net_revenue":"Vendas (R$)"}), hide_index=True, width="stretch")
