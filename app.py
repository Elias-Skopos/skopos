from __future__ import annotations

import os
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

# Opt in on the existing Cloud URL after preserving any hosted data.
# The public entry is selected before importing any database/account module.
try:
    public_edition = st.secrets.get("distribution", {}).get("edition") == "public"
except StreamlitSecretNotFoundError:
    public_edition = False
if public_edition and os.environ.get("SKOPOS_DESKTOP") != "1":
    from online_app import render_public
    render_public()
    st.stop()

import base64
import importlib
import json
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image, ImageOps

from analytics import (
    INVENTORY_COLUMNS,
    SALES_COLUMNS,
    calculate_inventory,
    calculate_sales,
    normalize_inventory_frame,
    normalize_sales_frame,
)
from ai_insights import AIServiceError, build_insight_payload, generate_gemini_insights
from db import (
    configure_database,
    database_backend,
    list_import_batches,
    delete_import_batch,
    delete_demo_transactions,
    COMPANY_ROLES,
    COMPANY_SEGMENTS,
    get_user_setting,
    set_user_settings,
    add_transaction,
    companies_for_user,
    company_members,
    create_company,
    delete_company_invitation,
    delete_transaction,
    get_app_setting,
    import_inventory_snapshots,
    import_sales_lines,
    init_db,
    pending_company_invitations,
    query_df,
    remove_company_member,
    register_identity,
    set_app_settings,
    update_status,
    update_company,
    update_company_member_role,
    upsert_budget,
)
from import_contract import read_csv, csv_template, brazilian_frame
from horus_api import HorusAPIError, fetch_orders_and_items, sales_preview, test_connection
import ui as ui_module
import autonomy
import autonomy_ui
import home_finance_ui
import transaction_ui
from account_ui import (
    ROLE_LABELS, activate_company, clear_company_session, company_invitation_form, company_deletion_panel,
    open_workspace_picker, personal_profile, workspace_picker,
)

ui_module = importlib.reload(ui_module)
px.defaults.color_discrete_sequence = ui_module.CHART_COLORS
inject_css, kpi, money, page_header = (
    ui_module.inject_css,
    ui_module.kpi,
    ui_module.money,
    ui_module.page_header,
)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

st.set_page_config(
    page_title="Skopos",
    page_icon=str(ASSETS_DIR / "logo_novo.png"),
    layout="wide",
    initial_sidebar_state="auto",
)

# CSS global independente dos estilos de cada página e carregado antes do login.
st.html(Path(__file__).with_name("app_chrome.css"))


def configured_identity_providers() -> list[tuple[str, str]]:
    try:
        auth_config = st.secrets.get("auth", {})
    except StreamlitSecretNotFoundError:
        return []
    provider_config = auth_config.get("google", {})
    required = ("client_id", "client_secret", "server_metadata_url")
    if os.environ.get("SKOPOS_DESKTOP") == "1" and all(auth_config.get("local", {}).get(key) for key in required):
        return [("local", "Senha local ou Google")]
    if all(provider_config.get(key) for key in required):
        return [("google", "Google")]
    return []


def render_login_page(identity_providers: list[tuple[str, str]]) -> None:
    st.html(Path(__file__).with_name("welcome.css"))

    with st.container(key="login_layout"):
        left_panel, right_panel = st.columns([0.86, 1.14], gap=None)
    with left_panel.container(key="login_left_panel"):
        st.markdown('<span class="login-left-marker"></span>', unsafe_allow_html=True)
        with st.container(key="login_logo_image"):
            st.image(str(ASSETS_DIR / "logo_login.svg"), width=420)
        st.title("Faça seu login")
        st.markdown(
            '<div class="login-description">Entre com seu perfil para acompanhar '
            'as finanças e as vendas da sua empresa.</div>',
            unsafe_allow_html=True,
        )
        if identity_providers:
            if st.button(
                "Entrar com senha ou Google" if identity_providers[0][0] == "local" else "Continuar com Google",
                icon=":material/login:",
                key="login_google",
                type="primary",
                width="stretch",
            ):
                st.login(identity_providers[0][0])
        else:
            st.markdown(
                '<div class="login-notice">O acesso pelo Google ainda precisa ser configurado. '
                'Confira as credenciais locais do app.</div>',
                unsafe_allow_html=True,
            )
        st.markdown('<div class="login-divider">acesso seguro</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-footnote">No primeiro acesso, entre com o Google e escolha '
            'uma empresa ou crie a sua.</div>',
            unsafe_allow_html=True,
        )

    with right_panel.container(key="login_right_panel"):
        st.markdown('<span class="login-right-marker"></span>', unsafe_allow_html=True)
        st.markdown('<div class="login-hero-eyebrow">Visão clara, boas decisões</div>', unsafe_allow_html=True)
        st.markdown('<h2>Sua empresa em equilíbrio.</h2>', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-hero-copy">Acompanhe faturamento, caixa e estoque '
            'em um só lugar, com os números que ajudam você a seguir em frente.</div>',
            unsafe_allow_html=True,
        )
        st.image(
            Path(__file__).resolve().parent / "assets" / "login_illustration.svg",
            width="stretch",
            caption=None,
        )
        st.markdown('<div class="login-hero-caption">Os números da sua empresa, sempre à vista.</div>', unsafe_allow_html=True)


if not st.user.get("is_logged_in", False):
    render_login_page(configured_identity_providers())
    st.stop()

try:
    configure_database(st.secrets.get("database", {}).get("url", ""))
    init_db()
except Exception:
    st.error("Não foi possível conectar ao banco. Confira a configuração [database] nos Secrets e a disponibilidade do serviço. Os dados não serão gravados em outro banco automaticamente.")
    st.stop()
identity_subject = st.user.get("sub", "")
identity_issuer = st.user.get("iss", "")
if os.environ.get("SKOPOS_DESKTOP") == "1":
    if identity_issuer != st.secrets.get("desktop", {}).get("issuer"):
        st.error("Este acesso não pertence à instalação local.")
        st.stop()
    # The OIDC token expires after one hour; the signed application session has
    # its own lifetime. Older installed tokens use their original issuance time.
    session_expires = st.user.get("skopos_session_expires", st.user.get("iat", 0) + 30 * 86400)
    if session_expires < time.time():
        st.logout()
        st.stop()
    identity_issuer = st.user.get("skopos_issuer", "")
    identity_subject = st.user.get("skopos_subject", "")
if not identity_subject or not identity_issuer:
    st.error("O provedor não retornou os dados necessários para identificar esta conta.")
    st.stop()
verified_claim = st.user.get("email_verified", False)
email_verified = verified_claim is True or str(verified_claim).lower() == "true"
register_identity(
    issuer=identity_issuer,
    subject=identity_subject,
    email=st.user.get("email", ""),
    name=st.user.get("name", ""),
    email_verified=email_verified,
)
previous_identity = st.session_state.get("session_identity")
if previous_identity and previous_identity != (identity_issuer, identity_subject):
    st.session_state.clear()
st.session_state["session_identity"] = (identity_issuer, identity_subject)
st.session_state.setdefault("dark_mode", get_user_setting("dark_mode", identity_issuer, identity_subject) == "true")
inject_css(dark_mode=st.session_state["dark_mode"])
user_companies = companies_for_user(identity_issuer, identity_subject)
st.session_state.pop("demo_active", None)
selected_id = st.session_state.get("active_company_id")
company_ids = {int(item["id"]) for item in user_companies}
if selected_id is not None and selected_id not in company_ids:
    clear_company_session()
    st.session_state.pop("active_company_id", None)
if st.session_state.get("workspace_picker") or selected_id not in company_ids:
    workspace_picker(user_companies, identity_issuer, identity_subject, st.logout)
    st.stop()
active_company = next(item for item in user_companies if int(item["id"]) == selected_id)
company_id = int(active_company["id"])
company_name = active_company["name"]
company_segment = active_company["segment"]
membership_role = active_company["role"]
can_edit = membership_role == "administrator"
can_manage_team = can_edit
PRODUCT_LABEL = "Título" if company_segment == "Livraria" else "Produto"
PRODUCT_GROUP = "Títulos" if company_segment == "Livraria" else "Produtos"
role_context = (company_id, membership_role)
if st.session_state.get("role_context") not in (None, role_context):
    clear_company_session()
st.session_state["role_context"] = role_context

REVENUE_CATEGORIES = ["Vendas de livros" if company_segment == "Livraria" else "Vendas de produtos e serviços", "Vendas online", "Eventos", "Assinaturas", "Outras receitas"]
EXPENSE_CATEGORIES = ["Fornecedores", "Aluguel", "Folha e encargos", "Marketing", "Fretes", "Impostos", "Tecnologia", "Outras despesas"]
PAYMENT_METHODS = ["Não informado", "PIX", "Cartão", "Dinheiro", "Boleto", "Transferência"]


def load_sales() -> pd.DataFrame:
    df = query_df("SELECT * FROM sales_lines WHERE company_id = ? ORDER BY sale_date DESC, order_id DESC", [company_id])
    if not df.empty:
        for column in ["quantity", "returned_quantity", "unit_price", "unit_cost", "discount", "taxes", "shipping_charged", "shipping_cost"]:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    return df


def load_inventory() -> pd.DataFrame:
    df = query_df("SELECT * FROM inventory_snapshots WHERE company_id = ? ORDER BY snapshot_date DESC, sku", [company_id])
    if not df.empty:
        for column in ["quantity", "unit_cost", "minimum_quantity"]:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    return df


def read_csv_upload(uploaded_file) -> pd.DataFrame:
    return read_csv(uploaded_file.getvalue())


def render_import_errors(errors: list[str]) -> None:
    for error in errors:
        st.error(error)


def go_to_overview() -> None:
    navigate_to("Visão geral")


def navigate_to(page: str) -> None:
    if page == "Conta":
        page = "Meu perfil"
    if page == "Equipe":
        st.session_state["account_team_expanded"] = True
        page = "Empresa"
    st.session_state["active_page"] = page
    st.query_params["page"] = page


def clear_horus_session() -> None:
    for key in list(st.session_state):
        if key.startswith("horus_"):
            del st.session_state[key]


def switch_company(company_id: int) -> None:
    company = next(item for item in user_companies if int(item["id"]) == company_id)
    activate_company(company_id, home=False)


def toggle_financial_values() -> None:
    st.session_state["hide_financial_values"] = not st.session_state.get("hide_financial_values", True)


def toggle_dark_mode() -> None:
    st.session_state["dark_mode"] = not st.session_state.get("dark_mode", False)
    set_user_settings({"dark_mode": str(st.session_state["dark_mode"]).lower()}, identity_issuer, identity_subject)


def logout_user() -> None:
    st.session_state.clear()
    st.logout()


def account_menu() -> None:
    st.session_state.setdefault("hide_financial_values", True)
    dark_mode = st.session_state.get("dark_mode", False)
    with st.container(
        key="app_topbar",
        horizontal=True,
        wrap=False,
        horizontal_alignment="right",
        vertical_alignment="center",
        gap="small",
    ):
        st.button(
            "Home",
            icon=":material/home:",
            help="Voltar para a página inicial",
            key="top_home_button",
            on_click=navigate_to,
            args=("Home",),
            width="content",
        )
        if st.session_state.get("active_page") in {"Home", "Visão geral"}:
            hidden = st.session_state["hide_financial_values"]
            st.button(
                "Valores",
                icon=":material/visibility_off:" if hidden else ":material/visibility:",
                help="Mostrar valores" if hidden else "Ocultar valores",
                key="toggle_overview_values",
                on_click=toggle_financial_values,
                width="content",
            )
        st.button(
            "☾",
            help="Ativar modo claro" if dark_mode else "Ativar modo escuro",
            key="toggle_dark_mode_topbar_dark" if dark_mode else "toggle_dark_mode_topbar_light",
            on_click=toggle_dark_mode,
            width="content",
        )
        with st.popover("Conta", icon=":material/account_circle:", width="content"):
                account_name = st.user.get("name", "") or "Conta Google"
                account_email = st.user.get("email", "")
                st.markdown(f"**{account_name}**")
                if account_email:
                    st.caption(account_email)
                st.caption(f"Empresa ativa: {company_name}")
                st.caption(f"Perfil: {ROLE_LABELS.get(membership_role, 'Colaborador')}")
                if can_manage_team:
                    st.button("Gerenciar empresa", icon=PAGE_ICONS["Empresa"], key="account_company",
                              on_click=navigate_to, args=("Empresa",), width="stretch")
                st.button("Meu perfil", icon=PAGE_ICONS["Meu perfil"], key="account_profile",
                          on_click=navigate_to, args=("Meu perfil",), width="stretch")
                st.button("Empresas e convites", icon=":material/domain:", key="account_workspaces",
                          on_click=open_workspace_picker, width="stretch")
                if len(user_companies) > 1:
                    st.divider()
                    st.caption("Mudar empresa / perfil")
                    active_company_id = int(st.session_state.get("active_company_id", company_id))
                    for company in user_companies:
                        option_id = int(company["id"])
                        st.button(
                            f"{company['name']} · {ROLE_LABELS.get(company['role'], 'Colaborador')}",
                            key=f"account_switch_company_{option_id}",
                            type="primary" if option_id == active_company_id else "secondary",
                            on_click=switch_company,
                            args=(option_id,),
                            width="stretch",
                        )
                st.divider()
                st.button(
                    "Sair da conta",
                    icon=":material/logout:",
                    key="top_logout_button",
                    on_click=logout_user,
                    width="stretch",
                )


PAGE_ICONS = {
    "Home": ":material/home:",
    "Visão geral": ":material/space_dashboard:",
    "Curva ABC": ":material/bar_chart:",
    "Relatórios": ":material/assessment:",
    "Fluxo de caixa": ":material/payments:",
    "Contas": ":material/receipt_long:",
    "Insights com IA": ":material/auto_awesome:",
    "Vendas e estoque": ":material/inventory_2:",
    "Lançamentos": ":material/swap_horiz:",
    "Orçamento": ":material/account_balance_wallet:",
    "API do Horus": ":material/sync:",
    "Configuração de IA": ":material/psychology:",
    "Equipe": ":material/groups:",
    "Empresa": ":material/store:",
    "Meu perfil": ":material/account_circle:",
}

SHORTCUT_TARGETS = [
    "Visão geral", "Relatórios", "Fluxo de caixa", "Contas", "Curva ABC",
    "Insights com IA", "Vendas e estoque", "Lançamentos", "Orçamento", "API do Horus",
    "Configuração de IA", "Empresa", "Meu perfil",
]


def accessible_shortcuts(role: str) -> list[str]:
    allowed = {"Visão geral", "Curva ABC", "Relatórios", "Fluxo de caixa", "Contas", "Insights com IA",
               "Vendas e estoque", "Lançamentos", "Orçamento", "Meu perfil"}
    if role == "administrator":
        allowed.update({"API do Horus", "Configuração de IA", "Empresa"})
    return [target for target in SHORTCUT_TARGETS if target in allowed]


def toggle_collapsed_rail_group(group: str) -> None:
    current = st.session_state.get("collapsed_rail_open_group")
    st.session_state["collapsed_rail_open_group"] = None if current == group else group


def navigate_collapsed_rail(target: str) -> None:
    navigate_to(target)
    st.session_state["collapsed_rail_open_group"] = None


def collapsed_nav_rail(role: str) -> None:
    groups = {
        "Acompanhamento": [
            "Visão geral", "Relatórios", "Fluxo de caixa", "Contas", "Curva ABC", "Insights com IA",
        ],
        "Alimentar e planejar": ["Vendas e estoque", "Lançamentos", "Orçamento"],
        "Gestão da Plataforma": (["API do Horus", "Configuração de IA", "Empresa"] if role == "administrator" else []) + ["Meu perfil"],
    }
    groups = {group: destinations for group, destinations in groups.items() if destinations}
    group_icons = {
        "Acompanhamento": ":material/visibility:",
        "Alimentar e planejar": ":material/edit_note:",
        "Gestão da Plataforma": ":material/settings:",
    }
    group_keys = {
        "Acompanhamento": "acompanhamento",
        "Alimentar e planejar": "alimentar",
        "Gestão da Plataforma": "gestao",
    }
    st.session_state.setdefault("collapsed_rail_open_group", None)
    open_group = st.session_state.get("collapsed_rail_open_group")
    if open_group not in groups:
        open_group = None
        st.session_state["collapsed_rail_open_group"] = None
    rail_key = "collapsed_nav_rail_expanded" if open_group else "collapsed_nav_rail"
    with st.container(key=rail_key):
        st.button(
            "Home" if open_group else "",
            key="collapsed_nav_home",
            icon=PAGE_ICONS["Home"],
            help="Home",
            type="primary" if st.session_state.get("active_page") == "Home" else "secondary",
            on_click=navigate_collapsed_rail,
            args=("Home",),
            width="stretch",
        )
        for group, destinations in groups.items():
            group_key = group_keys[group]
            st.markdown('<div class="collapsed-rail-group-separator"></div>', unsafe_allow_html=True)
            selected = st.session_state.get("active_page") in destinations
            st.button(
                group if open_group else "",
                key=f"collapsed_nav_group_{group_key}",
                icon=group_icons[group],
                help=group,
                type="primary" if open_group == group or selected else "secondary",
                on_click=toggle_collapsed_rail_group,
                args=(group,),
                width="stretch",
            )
            if open_group == group:
                with st.container(key=f"collapsed_nav_submenu_{group_key}"):
                    for target in destinations:
                        st.button(
                            target,
                            key=f"collapsed_nav_page_{target}",
                            icon=PAGE_ICONS[target],
                            type="primary" if st.session_state.get("active_page") == target else "secondary",
                            on_click=navigate_collapsed_rail,
                            args=(target,),
                            width="stretch",
                        )
                    if group == "Gestão da Plataforma":
                        dark_mode = st.session_state.get("dark_mode", False)
                        st.button(
                            "Modo claro" if dark_mode else "Modo escuro",
                            icon=":material/light_mode:" if dark_mode else ":material/dark_mode:",
                            key="collapsed_nav_theme_toggle",
                            on_click=toggle_dark_mode,
                            width="stretch",
                        )


def home_shortcuts_settings() -> None:
    available = accessible_shortcuts(membership_role)
    current_value = get_user_setting(f"home_shortcuts_{company_id}", identity_issuer, identity_subject, get_app_setting("home_shortcuts", company_id))
    try:
        saved_shortcuts = json.loads(current_value) if current_value else ["Visão geral", "Vendas e estoque", "Lançamentos", "Contas"]
    except (json.JSONDecodeError, TypeError):
        saved_shortcuts = ["Visão geral", "Vendas e estoque", "Lançamentos", "Contas"]
    saved_shortcuts = [target for target in saved_shortcuts if target in available]
    with st.form(f"home_shortcuts_form_{company_id}"):
        selected = st.multiselect(
            "Telas para acesso rápido",
            available,
            default=saved_shortcuts,
            format_func=lambda target: target,
            help="Estes Favoritos são pessoais e valem para a empresa selecionada.",
        )
        save = st.form_submit_button("Salvar Favoritos", type="primary")
    if save:
        if not selected:
            st.error("Selecione pelo menos uma tela para manter um atalho na Home.")
        else:
            set_user_settings(
                {f"home_shortcuts_{company_id}": json.dumps(selected, ensure_ascii=False)},
                identity_issuer, identity_subject,
            )
            st.success("Favoritos da Home atualizados.")


def home_page(df: pd.DataFrame, start: date, end: date) -> None:
    display_name = get_user_setting("display_name", identity_issuer, identity_subject) or st.user.get("given_name") or st.user.get("name", "").strip()
    if not display_name:
        display_name = st.user.get("email", "").split("@", 1)[0] or "por aqui"
    render_dashboard_welcome(company_id, display_name)
    start, end = render_period_filter(start, end)

    raw_shortcuts = get_user_setting(f"home_shortcuts_{company_id}", identity_issuer, identity_subject, get_app_setting("home_shortcuts", company_id))
    try:
        shortcuts = json.loads(raw_shortcuts) if raw_shortcuts else ["Visão geral", "Vendas e estoque", "Lançamentos", "Contas"]
    except (json.JSONDecodeError, TypeError):
        shortcuts = ["Visão geral", "Vendas e estoque", "Lançamentos", "Contas"]
    shortcuts = [target for target in shortcuts if target in accessible_shortcuts(membership_role)]
    if shortcuts:
        st.subheader("Favoritos")
        with st.container(horizontal=True, wrap=True, gap="small"):
            for index, target in enumerate(shortcuts):
                st.button(
                    target,
                    key=f"home_shortcut_{company_id}_{index}",
                    icon=PAGE_ICONS.get(target),
                    on_click=navigate_to,
                    args=(target,),
                    width="content",
                )

    home_finance_ui.render_summary(df, start, end, company_id, identity_issuer, identity_subject,
                                   can_edit, st.session_state.get("hide_financial_values", True))

def account_settings_page() -> None:
    page_header("Minha conta", "Meu perfil", "Seu perfil, preferências pessoais e participação nas empresas.")
    personal_profile(active_company, identity_issuer, identity_subject, logout_user,
                     home_shortcuts_settings, toggle_dark_mode)


def company_settings_page() -> None:
    page_header("Gestão da empresa", "Empresa", f"Informações e acessos de {company_name}.")
    if not can_manage_team:
        st.info("Somente proprietários podem gerenciar a empresa.")
        return
    with st.container(border=True):
        st.subheader("Perfil da empresa")
        with st.form(f"company_profile_form_{company_id}"):
            updated_name = st.text_input("Nome da empresa", value=company_name, max_chars=120)
            segment = st.selectbox("Tipo de empresa", COMPANY_SEGMENTS, index=COMPANY_SEGMENTS.index(company_segment))
            contact = st.text_input("E-mail de contato (opcional)", value=active_company["contact_email"], max_chars=254)
            city = st.text_input("Cidade (opcional)", value=active_company["city"], max_chars=120)
            save = st.form_submit_button("Salvar empresa", type="primary")
        if save:
            try:
                if update_company(company_id, updated_name, identity_issuer, identity_subject, segment, contact, city):
                    st.rerun()
                st.error("Informe o nome da empresa.")
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
    render_company_cover_settings(company_id)
    with st.expander("Equipe e convites", expanded=st.session_state.get("account_team_expanded", False)):
        team_page(show_header=False)
    with st.container(border=True):
        st.subheader("Integrações da empresa")
        with st.container(horizontal=True):
            st.button("API do Horus", on_click=navigate_to, args=("API do Horus",), key="company_horus")
            st.button("Configuração de IA", on_click=navigate_to, args=("Configuração de IA",), key="company_ai")
        st.caption(f"Banco em uso: {database_backend()}")
    company_deletion_panel(active_company, identity_issuer, identity_subject)


def load_transactions() -> pd.DataFrame:
    df = query_df("SELECT * FROM transactions WHERE company_id = ? ORDER BY date DESC, id DESC", [company_id])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce")
    return autonomy.effective_finance(df)


def scope_df(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    mask = df["date"].dt.date.between(start, end)
    return df.loc[mask].copy()


def default_period() -> tuple[date, date]:
    today = date.today()
    return today.replace(day=1), today


def normalize_period(period) -> tuple[date, date]:
    if isinstance(period, (tuple, list)):
        dates = [item for item in period if isinstance(item, date)]
        if len(dates) == 2:
            start, end = dates
            return (start, end) if start <= end else (end, start)
        if len(dates) == 1:
            return dates[0], dates[0]
    if isinstance(period, date):
        return period, period
    return default_period()


def dashboard_cover_bytes(company_id: int) -> bytes | None:
    encoded = get_app_setting("dashboard_cover_data", company_id)
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return None


def render_company_cover_settings(company_id: int) -> None:
    cover = dashboard_cover_bytes(company_id)
    with st.expander("Imagem de capa da empresa"):
        st.caption("A capa é compartilhada com as pessoas que têm acesso a esta empresa. Somente proprietários podem alterá-la.")
        with st.form(f"dashboard_cover_form_{company_id}", clear_on_submit=True):
            uploaded_cover = st.file_uploader(
                "Escolha uma imagem",
                type="image",
                help="A imagem será ajustada ao formato de capa. Tamanho máximo do arquivo: 10 MB.",
                max_upload_size=10,
            )
            save_cover = st.form_submit_button("Salvar imagem de capa", type="primary")
            if save_cover:
                if uploaded_cover is None:
                    st.error("Escolha uma imagem antes de salvar.")
                elif uploaded_cover.size > 10 * 1024 * 1024:
                    st.error("A imagem deve ter no máximo 10 MB.")
                else:
                    try:
                        with Image.open(BytesIO(uploaded_cover.getvalue())) as source_image:
                            cover_image = ImageOps.fit(source_image.convert("RGB"), (1600, 600))
                            output = BytesIO()
                            cover_image.save(output, format="JPEG", quality=86, optimize=True)
                        encoded_cover = base64.b64encode(output.getvalue()).decode("ascii")
                        set_app_settings(
                            {"dashboard_cover_data": encoded_cover},
                            company_id,
                            identity_issuer,
                            identity_subject,
                        )
                        st.success("Imagem de capa atualizada para esta empresa.")
                        st.rerun()
                    except (OSError, ValueError, Image.DecompressionBombError) as exc:
                        st.error(f"Não foi possível abrir essa imagem: {exc}")
        if cover and st.button("Remover imagem de capa", key=f"remove_cover_{company_id}"):
            set_app_settings(
                {"dashboard_cover_data": ""},
                company_id,
                identity_issuer,
                identity_subject,
            )
            st.rerun()


def render_dashboard_welcome(company_id: int, display_name: str) -> None:
    cover = dashboard_cover_bytes(company_id)
    with st.container(border=True):
        welcome_col, image_col = st.columns([1.1, 1], vertical_alignment="center")
        with welcome_col:
            st.subheader(f"Olá, {display_name}!")
            st.write(f"Bem-vindo(a) à gestão de **{company_name}**. Aqui está o panorama da sua empresa.")
        with image_col:
            if cover:
                st.image(cover, width="stretch")
            else:
                st.image(
                    Path(__file__).resolve().parent / "assets" / "login_illustration.svg",
                    width="stretch",
                )

def sync_period_from_fields() -> None:
    start = st.session_state.get("period_start_input")
    end = st.session_state.get("period_end_input")
    if not isinstance(start, date) or not isinstance(end, date):
        return
    if start > end:
        if st.session_state.get("period_changed_field") == "start":
            end = start
            st.session_state["period_end_input"] = end
        else:
            start = end
            st.session_state["period_start_input"] = start
    st.session_state["global_period"] = (start, end)
    st.session_state["period_range_picker"] = (start, end)


def sync_period_from_picker() -> None:
    period = st.session_state.get("period_range_picker")
    start, end = normalize_period(period)
    st.session_state["global_period"] = (start, end)
    st.session_state["period_start_input"] = start
    st.session_state["period_end_input"] = end


def mark_period_field_changed(field: str) -> None:
    st.session_state["period_changed_field"] = field
    sync_period_from_fields()


def render_period_filter(start: date, end: date) -> tuple[date, date]:
    st.session_state.setdefault("global_period", (start, end))
    current_start, current_end = normalize_period(st.session_state["global_period"])
    st.session_state.setdefault("period_start_input", current_start)
    st.session_state.setdefault("period_end_input", current_end)
    st.session_state.setdefault("period_range_picker", (current_start, current_end))
    with st.container(horizontal=True, horizontal_alignment="right", key="period_filter_row"):
        with st.popover(f"{current_start:%d/%m/%Y} — {current_end:%d/%m/%Y}", icon=":material/date_range:", width="content"):
            st.caption("Período")
            date_start_col, date_end_col = st.columns(2, vertical_alignment="bottom")
            with date_start_col:
                st.date_input(
                    "Data inicial",
                    key="period_start_input",
                    format="DD/MM/YYYY",
                    on_change=mark_period_field_changed,
                    args=("start",),
                    persist_state="session",
                )
            with date_end_col:
                st.date_input(
                    "Data final",
                    key="period_end_input",
                    format="DD/MM/YYYY",
                    on_change=mark_period_field_changed,
                    args=("end",),
                    persist_state="session",
                )
            with st.container():
                with st.container():
                    st.caption("Também é possível selecionar o intervalo arrastando pelo calendário.")
                    st.date_input(
                        "Intervalo no calendário",
                        key="period_range_picker",
                        format="DD/MM/YYYY",
                        on_change=sync_period_from_picker,
                        persist_state="session",
                    )
    return normalize_period(st.session_state["global_period"])


def sidebar() -> tuple[str, date, date, int]:
    with st.sidebar:
        with st.container(key="sidebar_logo"):
            logo_data = base64.b64encode((ASSETS_DIR / "logo_barra_lateral.svg").read_bytes()).decode("ascii")
            st.button(
                f"![Skopos](data:image/svg+xml;base64,{logo_data})",
                key="sidebar_logo_home",
                help="Voltar para a página inicial",
                on_click=navigate_to,
                args=("Home",),
                width="stretch",
            )
        company_options = {int(item["id"]): item["name"] for item in user_companies}
        selected_company_id = int(st.session_state.get("active_company_id", company_id))
        if selected_company_id not in company_options:
            selected_company_id = company_id
            st.session_state["active_company_id"] = selected_company_id
        selected_membership = next(item for item in user_companies if int(item["id"]) == selected_company_id)
        st.divider()
        view_pages = [
            ("Visão geral", "Visão geral"),
            ("Relatórios", "Relatórios"),
            ("Fluxo de caixa", "Fluxo de caixa"),
            ("Contas", "Contas"),
            ("Curva ABC", "Curva ABC"),
            ("Insights com IA", "Insights com IA"),
        ]
        data_pages = [
            ("Vendas e estoque", "Vendas e estoque"),
            ("Lançamentos", "Lançamentos"),
            ("Orçamento", "Orçamento"),
        ]
        platform_pages = []
        if selected_membership["role"] == "administrator":
            platform_pages.extend([
                ("API do Horus", "API do Horus"),
                ("Configuração de IA", "Configuração de IA"),
                ("Empresa", "Empresa"),
            ])
        platform_pages.append(("Meu perfil", "Meu perfil"))
        old_page = st.query_params.get("page") or st.session_state.get("page_navigation", "Home")
        old_page_map = {"Configuração de API": "API do Horus", "Conta": "Meu perfil"}
        st.session_state.setdefault("active_page", old_page_map.get(old_page, old_page))
        if st.session_state["active_page"] == "Equipe":
            navigate_to("Equipe")
        if st.session_state["active_page"] == "Conta":
            navigate_to("Conta")
        available_pages = {"Home"} | {target for _, target in view_pages + data_pages + platform_pages}
        if st.session_state.get("active_page") not in available_pages:
            navigate_to("Home")
        active_page = st.session_state["active_page"]
        if not st.query_params.get("page"):
            st.query_params["page"] = active_page

        view_targets = {target for _, target in view_pages}
        with st.expander("Acompanhamento", expanded=active_page in view_targets, key="navigation_view_group", icon=":material/visibility:"):
            for label, target in view_pages:
                st.button(
                    label,
                    key=f"nav_{target}",
                    type="primary" if active_page == target else "secondary",
                    icon=PAGE_ICONS[target],
                    on_click=navigate_to,
                    args=(target,),
                    width="stretch",
                )
        data_targets = {target for _, target in data_pages}
        if data_pages:
            with st.expander("Alimentar e planejar", expanded=active_page in data_targets, key="navigation_data_group", icon=":material/edit_note:"):
                for label, target in data_pages:
                    st.button(
                        label,
                        key=f"nav_{target}",
                        type="primary" if active_page == target else "secondary",
                        icon=PAGE_ICONS[target],
                        on_click=navigate_to,
                        args=(target,),
                        width="stretch",
                    )
        platform_targets = {target for _, target in platform_pages}
        if platform_pages:
            with st.expander(
                "Gestão da Plataforma",
                expanded=active_page in platform_targets,
                icon=":material/settings:",
            ):
                for label, target in platform_pages:
                    st.button(
                        label,
                        key=f"nav_{target}",
                        type="primary" if active_page == target else "secondary",
                        icon=PAGE_ICONS[target],
                        on_click=navigate_to,
                        args=(target,),
                        width="stretch",
                    )
                if selected_membership["role"] == "administrator":
                    dark_mode = st.session_state.get("dark_mode", False)
                    st.button(
                        "Modo escuro" if not dark_mode else "Modo claro",
                        key="toggle_dark_mode_sidebar",
                        icon=":material/dark_mode:" if not dark_mode else ":material/light_mode:",
                        help="Altera apenas a aparência da sua sessão.",
                        on_click=toggle_dark_mode,
                        width="stretch",
                    )
        page = active_page
        st.divider()
        st.session_state.setdefault("global_period", default_period())
        start, end = normalize_period(st.session_state["global_period"])
        st.divider()
    return page, start, end, selected_company_id


def overview(df: pd.DataFrame, start: date, end: date) -> None:
    page_header("Painel executivo", "Visão geral", "Indicadores essenciais para acompanhar liquidez, resultado e compromissos da empresa.")
    sdf = scope_df(df, start, end)
    paid = sdf[sdf["status"] == "Pago"] if not sdf.empty else sdf
    revenue = paid.loc[paid["kind"] == "Receita", "amount"].sum() if not paid.empty else 0
    expense = paid.loc[paid["kind"] == "Despesa", "amount"].sum() if not paid.empty else 0
    result = revenue - expense
    margin = (result / revenue * 100) if revenue else 0
    pending_pay = sdf[(sdf["kind"] == "Despesa") & (sdf["status"] == "Pendente")]["amount"].sum() if not sdf.empty else 0

    cols = st.columns(4)
    with cols[0]: kpi("Receitas realizadas", money(revenue), f"{start:%d/%m} — {end:%d/%m}")
    with cols[1]: kpi("Despesas realizadas", money(expense), "Somente valores pagos")
    with cols[2]: kpi("Resultado", money(result), f"Margem de {margin:.1f}%")
    with cols[3]: kpi("A pagar", money(pending_pay), "Compromissos pendentes no período")

    st.write("")
    left, right = st.columns([1.65, 1])
    with left:
        st.subheader("Receitas x despesas")
        if sdf.empty:
            st.info("Sem movimentações no período selecionado.")
        else:
            chart = sdf.copy()
            chart["month"] = chart["date"].dt.to_period("M").dt.to_timestamp()
            chart = chart[chart["status"] == "Pago"].groupby(["month", "kind"], as_index=False)["amount"].sum()
            fig = px.bar(chart, x="month", y="amount", color="kind", barmode="group", labels={"month":"Mês","amount":"Valor","kind":"Tipo"})
            fig.update_layout(
                height=350,
                margin=dict(l=8, r=8, t=10, b=8),
                legend_title_text="",
                xaxis=dict(type="date", tickformat="%m/%Y", hoverformat="%m/%Y"),
            )
            ui_module.render_plotly(fig)

    with right:
        st.subheader("Despesas por categoria")
        exp = sdf[(sdf["kind"] == "Despesa") & (sdf["status"] == "Pago")]
        if exp.empty:
            st.info("Nenhuma despesa realizada neste período.")
        else:
            cat = exp.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
            fig = px.pie(cat, names="category", values="amount", hole=.62)
            fig.update_layout(height=350, margin=dict(l=8,r=8,t=10,b=8), showlegend=False)
            ui_module.render_plotly(fig)

    st.subheader("Próximos compromissos")
    pending = df[df["status"] == "Pendente"].copy() if not df.empty else df
    if pending.empty:
        st.success("Não há contas pendentes cadastradas.")
    else:
        pending["Vencimento"] = pending["due_date"].dt.strftime("%d/%m/%Y").fillna("—")
        pending["Tipo"] = pending["kind"]
        pending["Descrição"] = pending["description"]
        pending["Categoria"] = pending["category"]
        pending["Valor"] = pending["amount"].map(money)
        st.dataframe(pending[["Vencimento", "Tipo", "Descrição", "Categoria", "Valor"]].head(8), width="stretch", hide_index=True)


def analytics_overview(df: pd.DataFrame, sales_df: pd.DataFrame, inventory_df: pd.DataFrame, start: date, end: date) -> None:
    page_header("Painel executivo", "Visão geral", "Vendas, rentabilidade, clientes, operação e caixa em um só lugar.")
    start, end = render_period_filter(start, end)
    hide_values = st.session_state.get("hide_financial_values", True)
    autonomy_ui.data_status(company_id)
    autonomy_ui.daily_summary(company_id, start, end, hide=hide_values)
    show_kpi_info = st.toggle(
        "Exibir explicações dos indicadores",
        value=True,
        key="overview_show_kpi_info",
        help="Mostra ou oculta o ícone de informação nos cards de KPI.",
    )
    kpi_explanations = {
        "Faturamento líquido": "Valor das vendas após subtrair devoluções, descontos e impostos. Não representa necessariamente o dinheiro já recebido.",
        "CMV estimado": "Custo das mercadorias vendidas: custo unitário multiplicado pelas unidades líquidas vendidas.",
        "Margem bruta": "Faturamento líquido menos CMV. O percentual indica quanto da receita sobra antes de frete e outras despesas.",
        "Margem de contribuição": "Percentual da receita que sobra após CMV e frete líquido. O valor em reais aparece no texto abaixo do número.",
        "Pedidos": "Quantidade de pedidos concluídos no período selecionado.",
        "Ticket médio": "Faturamento líquido dividido pelo número de pedidos concluídos.",
        "Clientes ativos": "Quantidade de clientes identificados com ao menos uma compra no período.",
        "Frequência de compra": "Média de pedidos por cliente identificado no período.",
        "Exemplares líquidos": "Quantidade vendida menos exemplares devolvidos.",
        "Preço médio por exemplar": "Faturamento líquido dividido pelos exemplares líquidos.",
        "Custo médio por exemplar": "CMV dividido pelos exemplares líquidos.",
        "Contribuição por exemplar": "Receita por exemplar após descontar CMV e frete líquido.",
        "Frete por pedido": "Custo líquido de frete dividido pela quantidade de pedidos.",
        "Participação do frete": "Custo líquido de frete como percentual do faturamento líquido.",
        "Descontos concedidos": "Total de descontos aplicados às vendas; o percentual abaixo compara com as vendas brutas.",
        "Cancelamentos": "Percentual de pedidos cancelados entre os pedidos tentados; o texto abaixo mostra as quantidades.",
        "Faturamento médio diário": "Faturamento líquido dividido pelos dias corridos do período selecionado.",
        "Pedidos por dia": "Quantidade média de pedidos por dia corrido no período.",
        "Run-rate anual": "Projeção anualizada do faturamento observado no período. É uma estimativa, não uma previsão.",
        "Run-rate físico": "Projeção anual de exemplares líquidos no ritmo médio do período.",
        "Valor do estoque atual": "Valor estimado das unidades em estoque, com base na última posição importada e no custo cadastrado.",
        "Abaixo do estoque mínimo": "Quantidade de itens cuja posição importada está abaixo do estoque mínimo configurado.",
        "Giro de estoque no período": "CMV dividido pelo valor médio do estoque. Só é calculado com ao menos duas posições de estoque.",
        "Receitas pagas": "Soma dos lançamentos financeiros de receita marcados como pagos no período.",
        "Despesas pagas": "Soma dos lançamentos financeiros de despesa marcados como pagos no período.",
        "Saldo dos lançamentos": "Receitas pagas menos despesas pagas no período. Não substitui a conciliação bancária.",
        "A pagar no período": "Soma das despesas pendentes com vencimento dentro do período selecionado.",
    }
    sales = calculate_sales(sales_df, start, end)
    if sales is None:
        st.info("Dados não informados para vendas por item neste período. Margens, pedidos e clientes precisam de vendas detalhadas; os totais diários não permitem calcular esses indicadores. Importe o modelo por item ou consulte o Horus quando esses dados estiverem disponíveis.")
    else:
        st.subheader("Fluxo financeiro e resultado")
        st.caption("Receita líquida = vendas brutas − devoluções − descontos − impostos. A contribuição considera CMV e frete; os valores de frete são contados uma vez por pedido.")
        metric_rows = [
            [
                ("Faturamento líquido", money(sales["revenue"]), f"Bruto {money(sales['gross_sales'])}"),
                ("CMV estimado", money(sales["cogs"]), "Unidades líquidas × custo unitário"),
                ("Margem bruta", money(sales["gross_margin"]), f"{sales['gross_margin_pct']:.1f}% da receita"),
                ("Margem de contribuição", f"{sales['margin_pct']:.1f}%", money(sales["contribution"])),
            ],
            [
                ("Pedidos", f"{sales['orders']:,}".replace(",", "."), "Pedidos concluídos no período"),
                ("Ticket médio", money(sales["ticket"]), "Receita líquida ÷ pedidos"),
                ("Clientes ativos", f"{sales['customers']:,}".replace(",", ".") if sales['customers'] else "Não informado", "Clientes identificados no período"),
                ("Frequência de compra", f"{sales['order_frequency']:.2f}" if sales['customers'] else "Não informado", "Pedidos por cliente identificado"),
            ],
            [
                ("Exemplares líquidos", f"{sales['units']:,.0f}".replace(",", "."), "Vendidos menos devolvidos"),
                ("Preço médio por exemplar", money(sales["average_unit_price"]), "Após descontos e devoluções"),
                ("Custo médio por exemplar", money(sales["average_unit_cost"]), "CMV ÷ unidades líquidas"),
                ("Contribuição por exemplar", money(sales["unit_profit"]), "Após CMV e frete líquido"),
            ],
            [
                ("Frete por pedido", money(sales["average_freight_per_order"]), "Custo de frete ÷ pedidos"),
                ("Participação do frete", f"{sales['freight_share_pct']:.1f}%", "Custo do frete ÷ receita líquida"),
                ("Descontos concedidos", money(sales["discounts"]), f"{sales['discount_pct']:.1f}% das vendas brutas"),
                ("Cancelamentos", f"{sales['cancellation_pct']:.1f}%", f"{sales['cancelled_orders']} de {sales['attempted_orders']} pedidos"),
            ],
            [
                ("Faturamento médio diário", money(sales["average_daily_revenue"]), "Média no período selecionado"),
                ("Pedidos por dia", f"{sales['average_daily_orders']:.1f}", "Média em dias corridos"),
                ("Run-rate anual", money(sales["annualized_run_rate"]), "Ritmo do período × 365 dias"),
                ("Run-rate físico", f"{sales['physical_run_rate']:,.0f}".replace(",", "."), "Exemplares por ano no ritmo atual"),
            ],
        ]
        for row in metric_rows:
            columns = st.columns(4)
            for column, (label, value, foot) in zip(columns, row):
                with column:
                    kpi(
                        label,
                        value,
                        foot,
                        info=kpi_explanations.get(label) if show_kpi_info else None,
                        hide_values=hide_values,
                    )
            st.write("")

        inventory = calculate_inventory(inventory_df, start, end)
        st.subheader("Estoque e concentração")
        if inventory is None:
            st.info("Importe posições de estoque para ver valor atual, itens abaixo do mínimo e giro.")
        else:
            turnover = (
                f"{sales['cogs'] / inventory['average_stock_value']:.2f}×"
                if inventory["average_stock_value"] and inventory["average_stock_value"] > 0
                else "—"
            )
            inv_cols = st.columns(3)
            with inv_cols[0]:
                kpi("Valor do estoque atual", money(inventory["current_value"]), "Última posição importada por SKU", info=kpi_explanations["Valor do estoque atual"] if show_kpi_info else None, hide_values=hide_values)
            with inv_cols[1]:
                kpi("Abaixo do estoque mínimo", f"{inventory['low_stock_count']}", "Itens na última posição", info=kpi_explanations["Abaixo do estoque mínimo"] if show_kpi_info else None, hide_values=hide_values)
            with inv_cols[2]:
                kpi("Giro de estoque no período", turnover, f"{inventory['snapshot_count']} datas de inventário", info=kpi_explanations["Giro de estoque no período"] if show_kpi_info else None, hide_values=hide_values)
            if inventory["average_stock_value"] is None:
                st.caption("O giro só é calculado quando há ao menos duas posições de estoque no período.")

        st.write("")
        chart_cols = st.columns(2)
        with chart_cols[0]:
            st.subheader("Receita líquida e CMV por mês")
            monthly = sales["monthly"]
            if monthly.empty:
                st.info("Sem série mensal neste período.")
            else:
                chart_data = monthly.melt(id_vars="month", value_vars=["net_revenue", "cogs"], var_name="indicador", value_name="valor")
                chart_data["indicador"] = chart_data["indicador"].map({"net_revenue": "Receita líquida", "cogs": "CMV"})
                fig = px.line(chart_data, x="month", y="valor", color="indicador", markers=True, labels={"month": "Mês", "valor": "Valor", "indicador": ""})
                fig.update_layout(
                    height=340,
                    margin=dict(l=8, r=8, t=12, b=8),
                    legend_title_text="",
                    xaxis=dict(type="date", tickformat="%m/%Y", hoverformat="%m/%Y"),
                )
                if hide_values:
                    st.caption("Valores do gráfico ocultos. Use o ícone de olho acima para mostrá-los.")
                else:
                    ui_module.render_plotly(fig)
        with chart_cols[1]:
            st.subheader("Canais de venda")
            if sales["channels"].empty:
                st.info("Preencha o campo canal na importação para analisar este gráfico.")
            else:
                fig = px.bar(sales["channels"], x="channel", y="net_revenue", labels={"channel": "Canal", "net_revenue": "Receita líquida"})
                fig.update_layout(height=340, margin=dict(l=8, r=8, t=12, b=8))
                if hide_values:
                    st.caption("Valores do gráfico ocultos. Use o ícone de olho acima para mostrá-los.")
                else:
                    ui_module.render_plotly(fig)

        rank_cols = st.columns(2)
        with rank_cols[0]:
            st.subheader(f"Curva ABC de {PRODUCT_GROUP.lower()}")
            rank = sales["product_rank"].head(20)
            if rank.empty:
                st.info(f"Sem {PRODUCT_GROUP.lower()} identificados.")
            else:
                fig = px.bar(rank, x="title", y="net_revenue", color="class", labels={"title": PRODUCT_LABEL, "net_revenue": "Receita", "class": "Classe"})
                fig.update_layout(height=360, margin=dict(l=8, r=8, t=12, b=80), xaxis_tickangle=-35, legend_title_text="")
                if hide_values:
                    st.caption("Valores do gráfico ocultos. Use o ícone de olho acima para mostrá-los.")
                else:
                    ui_module.render_plotly(fig)
        with rank_cols[1]:
            st.subheader("Principais clientes")
            customers = sales["customer_rank"].head(10)
            if customers.empty:
                st.info("Preencha o campo cliente para montar o ranking.")
            else:
                fig = px.bar(customers, x="net_revenue", y="customer", orientation="h", labels={"net_revenue": "Receita líquida", "customer": "Cliente"})
                fig.update_layout(height=360, margin=dict(l=8, r=8, t=12, b=8), yaxis={"categoryorder": "total ascending"})
                if hide_values:
                    st.caption("Valores do gráfico ocultos. Use o ícone de olho acima para mostrá-los.")
                else:
                    ui_module.render_plotly(fig)

        if not sales["state_rank"].empty:
            st.subheader("Receita líquida por UF")
            state_table = sales["state_rank"].rename(columns={"state": "UF", "net_revenue": "Receita líquida"}).copy()
            state_table["Receita líquida"] = "••••••" if hide_values else state_table["Receita líquida"].map(money)
            if hide_values:
                st.caption("Valores do relatório ocultos. Use o ícone de olho acima para mostrá-los.")
            else:
                st.dataframe(state_table, hide_index=True, width="stretch")

    st.divider()
    st.subheader("Financeiro e compromissos")
    if df.empty:
        st.info("Recebimentos e despesas não informados. Cadastre ou importe em Lançamentos. Os totais de vendas não preenchem o caixa automaticamente.")
    sdf = scope_df(df, start, end)
    paid = sdf[sdf["status"] == "Pago"] if not sdf.empty else sdf
    revenue = paid.loc[paid["kind"] == "Receita", "amount"].sum() if not paid.empty else 0
    expense = paid.loc[paid["kind"] == "Despesa", "amount"].sum() if not paid.empty else 0
    result = revenue - expense
    pending = df[(df["status"] == "Pendente")].copy() if not df.empty else df
    if not pending.empty:
        due_in_range = pending["due_date"].dt.date.between(start, end)
        pending = pending[due_in_range]
    pending_pay = pending.loc[pending["kind"] == "Despesa", "amount"].sum() if not pending.empty else 0
    finance_cols = st.columns(4)
    has_receipts = not df.empty and (df["kind"] == "Receita").any()
    has_expenses = not df.empty and (df["kind"] == "Despesa").any()
    finance_metrics = [
        ("Receitas pagas", money(revenue) if has_receipts else "Não informado", "Lançamentos financeiros"),
        ("Despesas pagas", money(expense) if has_expenses else "Não informado", "Lançamentos financeiros"),
        ("Saldo dos lançamentos", money(result) if has_receipts and has_expenses else "Não informado", "Receitas pagas − despesas pagas"),
        ("A pagar no período", money(pending_pay) if has_expenses else "Não informado", "Por vencimento cadastrado"),
    ]
    for column, (label, value, foot) in zip(finance_cols, finance_metrics):
        with column:
            kpi(
                label,
                value,
                foot,
                info=kpi_explanations.get(label) if show_kpi_info else None,
                hide_values=hide_values,
            )
    st.caption("Os dados do livro financeiro são mantidos separados das vendas importadas; confirme a conciliação antes de usar o saldo como posição bancária.")

    left, right = st.columns([1.65, 1])
    with left:
        st.subheader("Receitas x despesas realizadas")
        if sdf.empty:
            st.info("Sem movimentações financeiras no período selecionado.")
        else:
            chart = sdf[sdf["status"] == "Pago"].copy()
            chart["month"] = chart["date"].dt.to_period("M").dt.to_timestamp()
            chart = chart.groupby(["month", "kind"], as_index=False)["amount"].sum()
            if not chart.empty:
                fig = px.bar(chart, x="month", y="amount", color="kind", barmode="group", labels={"month": "Mês", "amount": "Valor", "kind": "Tipo"})
                fig.update_layout(
                    height=330,
                    margin=dict(l=8, r=8, t=10, b=8),
                    legend_title_text="",
                    xaxis=dict(type="date", tickformat="%m/%Y", hoverformat="%m/%Y"),
                )
                if hide_values:
                    st.caption("Valores do gráfico ocultos. Use o ícone de olho acima para mostrá-los.")
                else:
                    ui_module.render_plotly(fig)
    with right:
        st.subheader("Despesas por categoria")
        exp = sdf[(sdf["kind"] == "Despesa") & (sdf["status"] == "Pago")]
        if exp.empty:
            st.info("Nenhuma despesa realizada neste período.")
        else:
            cat = exp.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
            fig = px.pie(cat, names="category", values="amount", hole=.62)
            fig.update_layout(height=330, margin=dict(l=8, r=8, t=10, b=8), showlegend=False)
            if hide_values:
                st.caption("Valores do gráfico ocultos. Use o ícone de olho acima para mostrá-los.")
            else:
                ui_module.render_plotly(fig)

    st.subheader("Próximos compromissos")
    pending_all = df[df["status"] == "Pendente"].copy() if not df.empty else df
    if pending_all.empty:
        st.success("Não há contas pendentes cadastradas.")
    else:
        pending_all["Vencimento"] = pending_all["due_date"].dt.strftime("%d/%m/%Y").fillna("—")
        pending_all["Tipo"] = pending_all["kind"]
        pending_all["Descrição"] = pending_all["description"]
        pending_all["Categoria"] = pending_all["category"]
        pending_all["Valor"] = "••••••" if hide_values else pending_all["amount"].map(money)
        st.dataframe(pending_all[["Vencimento", "Tipo", "Descrição", "Categoria", "Valor"]].head(8), width="stretch", hide_index=True)


def sales_import_page(sales_df: pd.DataFrame, inventory_df: pd.DataFrame) -> None:
    page_header("Dados comerciais", "Vendas e estoque", "Carregue os dados que alimentam faturamento por produto, clientes, canais, curva ABC e giro.")
    autonomy_ui.daily_summary(company_id, date(1900, 1, 1), date(2200, 12, 31), hide=st.session_state.get("hide_financial_values", True))
    if not can_edit:
        st.info("Seu perfil permite consultar os dados da empresa, mas não importar ou alterar vendas e estoque.")
        if not sales_df.empty:
            st.subheader("Vendas carregadas")
            st.dataframe(
                sales_df[["sale_date", "order_id", "channel", "sku", "title", "quantity", "unit_price", "status"]]
                .rename(columns={"sale_date": "Data", "order_id": "Pedido", "channel": "Canal", "sku": "SKU", "title": PRODUCT_LABEL, "quantity": "Quantidade", "unit_price": "Preço unitário", "status": "Status"})
                .head(100),
                width="stretch",
                hide_index=True,
            )
        if not inventory_df.empty:
            st.subheader("Estoque carregado")
            st.dataframe(inventory_df[["snapshot_date", "sku", "title", "quantity", "unit_cost", "minimum_quantity"]]
                         .rename(columns={"snapshot_date": "Data", "sku": "SKU", "title": PRODUCT_LABEL,
                                          "quantity": "Quantidade", "unit_cost": "Custo unitário", "minimum_quantity": "Estoque mínimo"}),
                         width="stretch", hide_index=True)
        return
    autonomy_ui.import_form("daily", company_id, identity_issuer, identity_subject)
    st.caption("O app também aceita CSV de vendas por item ou consulta pela API. O formato abaixo é por item de pedido: uma linha para cada combinação de pedido e SKU.")
    st.info("Padrão obrigatório: datas DD-MM-AAAA (12-10-2026), números com vírgula decimal (1234,56) e CSV separado por ponto e vírgula (;). Não use separador de milhar, R$, %, ponto decimal ou fórmulas. UTF-8 recomendado. Campos numéricos opcionais vazios valem zero. O arquivo inteiro é bloqueado se houver erro.")
    sales_template = csv_template(SALES_COLUMNS)
    inventory_template = csv_template(INVENTORY_COLUMNS)
    template_cols = st.columns(2)
    with template_cols[0]:
        st.download_button("Baixar modelo de vendas CSV", sales_template, file_name="modelo_vendas_skopos.csv", mime="text/csv", width="stretch")
    with template_cols[1]:
        st.download_button("Baixar modelo de estoque CSV", inventory_template, file_name="modelo_estoque_skopos.csv", mime="text/csv", width="stretch")
    with st.expander("Exemplos preenchidos e instruções"):
        st.caption("Os exemplos contêm dados fictícios. Substitua todas as linhas pelos seus dados antes de importar. Ao salvar no Excel, confira que o CSV usa ponto e vírgula entre colunas, vírgula nos valores e datas DD-MM-AAAA.")
        example_sales = [{"pedido_id": "EXEMPLO-001", "data": "2026-10-01", "sku": "LIVRO-001", "titulo": "Livro de exemplo", "quantidade": "2", "preco_unitario": "49.90", "custo_unitario": "25.00", "desconto": "0", "status": "Concluído"}]
        example_stock = [{"data_ref": "2026-10-01", "sku": "LIVRO-001", "titulo": "Livro de exemplo", "quantidade": "10", "custo_unitario": "25.00", "estoque_minimo": "3"}, {"data_ref": "2026-10-31", "sku": "LIVRO-001", "titulo": "Livro de exemplo", "quantidade": "8", "custo_unitario": "25.00", "estoque_minimo": "3"}]
        with st.container(horizontal=True):
            st.download_button("Exemplo de vendas", csv_template(SALES_COLUMNS, example_sales), file_name="exemplo_vendas_skopos.csv", mime="text/csv")
            st.download_button("Exemplo de estoque", csv_template(INVENTORY_COLUMNS, example_stock), file_name="exemplo_estoque_skopos.csv", mime="text/csv")

    with st.expander("Importar arquivo de vendas", expanded=sales_df.empty):
        st.caption("Obrigatórias: pedido_id, data, sku, titulo, quantidade, preco_unitario e custo_unitario. cliente_id é opcional e identifica compradores com mais precisão. Desconto e impostos são valores da linha; frete cobrado e frete custo são valores do pedido e devem aparecer apenas na primeira linha daquele pedido.")
        uploaded = st.file_uploader("Arquivo CSV de vendas", type=["csv"], key="sales_csv")
        if uploaded is not None:
            try:
                source = read_csv_upload(uploaded)
                rows, errors = normalize_sales_frame(source)
                render_import_errors(errors)
                if not errors:
                    st.caption(f"{len(rows)} linhas prontas para importar.")
                    st.dataframe(brazilian_frame(pd.DataFrame(rows)).head(8), width="stretch", hide_index=True)
                    if st.button("Importar vendas", type="primary", key="import_sales"):
                        count = import_sales_lines(rows, company_id, identity_issuer, identity_subject, source=uploaded.name)
                        st.success(f"{count} linhas de venda importadas ou atualizadas.")
                        st.rerun()
            except Exception as exc:
                st.error(str(exc) if isinstance(exc, ValueError) else "Não consegui importar o CSV. Confira os dados e a conexão com o banco.")

    with st.expander("Importar posição de estoque"):
        st.caption("Obrigatórias: data_ref, sku, titulo, quantidade e custo_unitario. estoque_minimo é opcional. Envie ao menos duas datas para calcular o giro no período.")
        uploaded_stock = st.file_uploader("Arquivo CSV de estoque", type=["csv"], key="inventory_csv")
        if uploaded_stock is not None:
            try:
                source = read_csv_upload(uploaded_stock)
                rows, errors = normalize_inventory_frame(source)
                render_import_errors(errors)
                if not errors:
                    st.caption(f"{len(rows)} posições de SKU prontas para importar.")
                    st.dataframe(brazilian_frame(pd.DataFrame(rows)).head(8), width="stretch", hide_index=True)
                    if st.button("Importar estoque", type="primary", key="import_inventory"):
                        count = import_inventory_snapshots(rows, company_id, identity_issuer, identity_subject, source=uploaded_stock.name)
                        st.success(f"{count} posições de estoque importadas ou atualizadas.")
                        st.rerun()
            except Exception as exc:
                st.error(str(exc) if isinstance(exc, ValueError) else "Não consegui importar o CSV. Confira os dados e a conexão com o banco.")

    if not sales_df.empty:
        st.subheader("Vendas carregadas")
        sales_table = sales_df[["sale_date", "order_id", "customer", "channel", "sku", "title", "quantity", "unit_price", "unit_cost", "status"]].rename(
            columns={"sale_date": "Data", "order_id": "Pedido", "customer": "Cliente", "channel": "Canal", "sku": "SKU", "title": PRODUCT_LABEL, "quantity": "Quantidade", "unit_price": "Preço unitário", "unit_cost": "Custo unitário", "status": "Status"}
        )
        st.dataframe(sales_table.head(100), width="stretch", hide_index=True)
    if not inventory_df.empty:
        st.caption(f"Inventários armazenados: {len(inventory_df)} linhas.")
    autonomy_ui.import_history("daily", company_id, identity_issuer, identity_subject)
    render_import_history(sales_df, inventory_df)


def render_import_history(sales_df, inventory_df):
    with st.expander("Histórico de importações e limpeza de dados"):
        batches = list_import_batches(company_id)
        if batches.empty:
            st.caption("Nenhuma importação registrada.")
        else:
            labels = {r["id"]: f"{r['created_at']} · {r['source']} · {'Vendas' if r['kind'] == 'sales' else 'Estoque'} · {r['current_rows']} linhas atuais" for r in batches.to_dict("records")}
            selected = st.selectbox("Importação", list(labels), format_func=labels.get, key=f"import_batch_{company_id}")
            batch = batches[batches["id"] == selected].iloc[0]
            frame = sales_df if batch["kind"] == "sales" else inventory_df
            current = frame[frame["import_id"] == selected] if not frame.empty else frame
            st.caption(f"Linhas recebidas: {batch['row_count']}. Linhas ainda pertencentes ao lote: {len(current)}. Reimportações transferem a linha para o lote mais recente. A exclusão remove as linhas atuais do lote; não restaura valores anteriores. Dados antigos foram agrupados por tipo, pois o arquivo de origem não foi registrado.")
            st.download_button("Exportar dados do lote antes de excluir", current.to_csv(index=False).encode("utf-8-sig"), file_name="backup_lote_skopos.csv", mime="text/csv", key=f"export_batch_{company_id}")
            if can_manage_team:
                confirmed = st.checkbox("Confirmo a exclusão das linhas deste lote", key=f"confirm_batch_{company_id}_{selected}")
                if st.button("Excluir importação", key=f"delete_batch_{company_id}"):
                    if not confirmed:
                        st.error("Confirme a exclusão do lote antes de continuar.")
                    else:
                        delete_import_batch(selected, company_id, identity_issuer, identity_subject)
                        st.rerun()
            else:
                st.caption("Apenas administradores podem excluir importações.")
        if can_manage_team:
            demo = query_df("SELECT * FROM transactions WHERE company_id=? AND is_demo=1", [company_id])
            if not demo.empty:
                st.caption(f"Lançamentos financeiros marcados como demonstração: {len(demo)}.")
                confirm_demo = st.checkbox("Confirmo a remoção dos lançamentos de demonstração", key=f"confirm_demo_{company_id}")
                if st.button("Apagar demonstração", key=f"delete_demo_{company_id}"):
                    if confirm_demo:
                        delete_demo_transactions(company_id, identity_issuer, identity_subject)
                        st.rerun()
                    else:
                        st.error("Confirme a remoção dos dados de demonstração.")
            st.caption("Lançamentos antigos sem identificação de demonstração podem ser removidos em Lançamentos, selecionando o ID. O app não presume que dados antigos sejam fictícios.")
            st.caption(f"Banco em uso: {database_backend()}.")
            if database_backend() == "SQLite local":
                st.warning("O SQLite local não oferece persistência garantida no Streamlit Cloud. Configure o PostgreSQL externo antes de usar o app em produção na nuvem.")


def abc_page(sales_df: pd.DataFrame, start: date, end: date) -> None:
    page_header("Análise de concentração", "Curva ABC", f"Classifique {PRODUCT_GROUP.lower()} ou clientes pelo peso nas vendas e veja a participação acumulada.")
    start, end = render_period_filter(start, end)
    sales = calculate_sales(sales_df, start, end)
    if sales is None or sales["rows"].empty:
        st.info("Não há vendas concluídas no período. Importe vendas em Vendas e estoque para calcular a curva.")
        return

    controls = st.columns(4)
    with controls[0]:
        dimension = st.selectbox("Analisar", [PRODUCT_GROUP, "Clientes"], key="abc_dimension")
    if dimension == PRODUCT_GROUP:
        measures = ["Faturamento líquido", "Exemplares vendidos"]
    else:
        measures = ["Faturamento líquido", "Pedidos"]
    with controls[1]:
        measure = st.selectbox("Classificar por", measures, key=f"abc_measure_{dimension}")
    with controls[2]:
        limit_a = st.slider("Limite acumulado da classe A (%)", min_value=50, max_value=90, value=80, step=5, key="abc_limit_a")
    with controls[3]:
        limit_b_default = max(95, limit_a + 1)
        limit_b = st.slider("Limite acumulado da classe B (%)", min_value=limit_a + 1, max_value=100, value=limit_b_default, step=1, key="abc_limit_b")

    rows = sales["rows"].copy()
    if dimension == PRODUCT_GROUP:
        table = rows.groupby(["sku", "title"], as_index=False).agg(
            revenue=("net_revenue", "sum"),
            units=("net_units", "sum"),
            orders=("order_id", "nunique"),
        )
        table = table.rename(columns={"sku": "identifier", "title": "name"})
        value_column = "revenue" if measure == "Faturamento líquido" else "units"
        unit_label = "R$" if value_column == "revenue" else "exemplares"
    else:
        rows["customer_key"] = rows["customer_id"].where(rows["customer_id"].astype(str).str.strip() != "", rows["customer"])
        rows = rows[rows["customer_key"].astype(str).str.strip() != ""]
        table = rows.groupby("customer_key", as_index=False).agg(
            name=("customer", "first"),
            revenue=("net_revenue", "sum"),
            units=("net_units", "sum"),
            orders=("order_id", "nunique"),
        )
        table = table.rename(columns={"customer_key": "identifier"})
        if not table.empty:
            table["name"] = table["name"].where(table["name"].astype(str).str.strip() != "", table["identifier"])
        value_column = "revenue" if measure == "Faturamento líquido" else "orders"
        unit_label = "R$" if value_column == "revenue" else "pedidos"

    table = table[table[value_column] > 0].sort_values(value_column, ascending=False).reset_index(drop=True)
    if table.empty:
        st.info(f"Não há valores positivos de {measure.lower()} para classificar no período.")
        return

    total = float(table[value_column].sum())
    table["share_pct"] = table[value_column] / total * 100
    table["cumulative_pct"] = table["share_pct"].cumsum()
    table["share_before"] = table["cumulative_pct"] - table["share_pct"]
    table["class"] = table["share_before"].apply(lambda value: "A" if value < limit_a else ("B" if value < limit_b else "C"))
    table.insert(0, "position", range(1, len(table) + 1))

    st.caption(f"Período: {start:%d/%m/%Y} a {end:%d/%m/%Y}. A última linha que cruza um limite permanece na classe anterior, prática comum na classificação Pareto.")
    st.markdown(f"**Regra aplicada:** A até {limit_a}% acumulado · B até {limit_b}% · C acima de {limit_b}%.")
    summary = []
    for abc_class in ["A", "B", "C"]:
        subset = table[table["class"] == abc_class]
        class_share = float(subset[value_column].sum()) / total * 100 if total else 0.0
        summary.append((abc_class, len(subset), class_share))
    summary_cols = st.columns(3)
    for column, (abc_class, count, class_share) in zip(summary_cols, summary):
        with column:
            kpi(f"Classe {abc_class}", f"{count} itens", f"{class_share:.1f}% do total de {measure.lower()}")

    st.subheader("Pareto")
    top = table.head(30).copy()
    labels = top["name"].astype(str)
    colors = top["class"].map({"A": "#177245", "B": "#e4a11b", "C": "#8b93a1"})
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=top[value_column], marker_color=colors, name=measure))
    fig.add_trace(go.Scatter(x=labels, y=top["cumulative_pct"], mode="lines+markers", name="Participação acumulada", yaxis="y2", line=dict(color="#625fe9", width=3)))
    fig.update_layout(
        height=430,
        margin=dict(l=8, r=48, t=20, b=100),
        xaxis=dict(title="", tickangle=-40),
        yaxis=dict(title=measure),
        yaxis2=dict(title="Acumulado (%)", overlaying="y", side="right", range=[0, 105]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    ui_module.render_plotly(fig)

    st.subheader("Classificação detalhada")
    result = table[["position", "identifier", "name", value_column, "share_pct", "cumulative_pct", "class"]].copy()
    result.columns = ["Posição", "Código", PRODUCT_LABEL if dimension == PRODUCT_GROUP else "Cliente", measure, "Participação %", "Acumulado %", "Classe"]
    if value_column == "revenue":
        result[measure] = result[measure].map(money)
    else:
        result[measure] = result[measure].map(lambda value: f"{value:,.0f}".replace(",", "."))
    result["Participação %"] = result["Participação %"].map(lambda value: f"{value:.2f}%")
    result["Acumulado %"] = result["Acumulado %"].map(lambda value: f"{value:.2f}%")
    st.dataframe(result, width="stretch", hide_index=True)
    st.download_button(
        "Baixar classificação CSV",
        table.drop(columns=["share_before"]).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"curva_abc_{dimension.lower()}_{start}_{end}.csv",
        mime="text/csv",
        width="content",
    )
    st.caption("A Curva ABC organiza o que já foi importado. Clientes são identificados por cliente_id quando informado; sem ele, o nome do cliente é usado como chave.")


def api_configuration_page() -> None:
    if st.session_state.get("horus_session_company_id") != company_id:
        clear_horus_session()
        st.session_state["horus_session_company_id"] = company_id
    page_header("Integrações", "Conexão com o Horus", "Consulte pedidos e itens do Horus S.I.G.A. para alimentar as análises comerciais do Skopos.")
    st.markdown(
        "A conexão usa **Basic Auth** e os endpoints de leitura `Busca_PedidosVenda` e "
        "`Busca_ItensPedidosVenda`. A URL base deve terminar em `/Horus/api/TServerB2B/`."
    )
    st.caption("O usuário e a senha são usados somente na sessão atual ou podem ser carregados de `.streamlit/secrets.toml`; eles nunca são salvos nas configurações do banco.")

    try:
        horus_secrets = st.secrets.get("horus_api", {})
    except StreamlitSecretNotFoundError:
        horus_secrets = {}
    st.session_state.setdefault("horus_username", horus_secrets.get("username", ""))
    st.session_state.setdefault("horus_password", horus_secrets.get("password", ""))

    st.session_state.setdefault("horus_base_url_input", get_app_setting("horus_base_url", company_id))
    st.session_state.setdefault("horus_company_input", get_app_setting("horus_company", company_id))
    st.session_state.setdefault("horus_branch_input", get_app_setting("horus_branch", company_id))
    today = date.today()
    first_day = today.replace(day=1)
    st.session_state.setdefault("horus_period_input", (first_day, today))

    url_base = st.text_input(
        "URL base da API",
        placeholder="https://servidor-da-empresa/Horus/api/TServerB2B/",
        key="horus_base_url_input",
    )
    credential_cols = st.columns(2)
    with credential_cols[0]:
        username = st.text_input("Usuário Basic Auth", key="horus_username")
    with credential_cols[1]:
        password = st.text_input("Senha Basic Auth", type="password", key="horus_password")

    filters_col, period_col, status_col = st.columns([1, 1.5, 1])
    with filters_col:
        company = st.text_input("Código da empresa", key="horus_company_input")
        branch = st.text_input("Código da filial", key="horus_branch_input")
    with period_col:
        selected_period = st.date_input("Período dos pedidos", key="horus_period_input", format="DD/MM/YYYY")
    with status_col:
        st.text_input("Status dos pedidos", value="Faturados (FAT)", disabled=True)

    parsed_url = urlparse(url_base.strip())
    allow_http = parsed_url.scheme.lower() == "http"
    if allow_http:
        st.warning("HTTP não criptografa usuário e senha do Basic Auth. Hosts públicos precisam usar HTTPS. Para um Horus em rede privada/VPN, o administrador também precisa liberar HORUS_ALLOW_PRIVATE_NETWORK=true no servidor.")
        http_confirmed = st.checkbox(
            "Confirmo que este endereço HTTP só é acessível por uma rede privada/VPN confiável.",
            key="horus_http_confirmed",
        )
    else:
        http_confirmed = True

    actions = st.columns(3)
    with actions[0]:
        save_clicked = st.button("Salvar parâmetros", type="primary", width="stretch", key="horus_save")
    with actions[1]:
        test_clicked = st.button("Testar conexão", width="stretch", key="horus_test")
    with actions[2]:
        fetch_clicked = st.button("Consultar vendas", width="stretch", key="horus_fetch")

    if save_clicked:
        set_app_settings({
            "horus_base_url": url_base.strip(),
            "horus_company": company.strip(),
            "horus_branch": branch.strip(),
        }, company_id, identity_issuer, identity_subject)
        st.success("URL e códigos de empresa/filial salvos. As credenciais não foram gravadas no banco.")

    def ready_to_connect(require_filters: bool = False) -> bool:
        if not url_base.strip() or not username.strip() or not password:
            st.error("Preencha a URL base e as credenciais Basic Auth.")
            return False
        if allow_http and not http_confirmed:
            st.error("Confirme que a conexão HTTP está restrita a uma rede privada/VPN, ou use um endereço HTTPS.")
            return False
        if require_filters and (not company.strip() or not branch.strip()):
            st.error("Informe os códigos de empresa e filial do Horus.")
            return False
        return True

    if test_clicked and ready_to_connect():
        try:
            sample_count, _ = test_connection(url_base, username, password)
            st.success(f"Conexão autenticada. A consulta de teste ao catálogo respondeu com {sample_count} registro(s).")
        except HorusAPIError as exc:
            st.error(str(exc))

    if fetch_clicked and ready_to_connect(require_filters=True):
        if not isinstance(selected_period, tuple) or len(selected_period) != 2:
            st.error("Selecione as datas inicial e final do período.")
        elif selected_period[0] > selected_period[1]:
            st.error("A data inicial precisa ser anterior à data final.")
        else:
            try:
                selected_status = "FAT"
                st.session_state.pop("horus_sales_preview", None)
                st.session_state.pop("horus_query_summary", None)
                st.session_state.pop("horus_preview_company_id", None)
                with st.spinner("Consultando pedidos e itens no Horus…"):
                    orders, items = fetch_orders_and_items(
                        url_base,
                        username,
                        password,
                        company.strip(),
                        branch.strip(),
                        selected_period[0],
                        selected_period[1],
                        selected_status,
                    )
                    rows = sales_preview(orders, items, selected_status)
                st.session_state["horus_sales_preview"] = rows
                st.session_state["horus_query_summary"] = (len(orders), len(items))
                st.session_state["horus_preview_company_id"] = company_id
            except HorusAPIError as exc:
                st.error(str(exc))

    preview_rows = st.session_state.get("horus_sales_preview")
    if st.session_state.get("horus_preview_company_id") != company_id:
        preview_rows = None
        st.session_state.pop("horus_sales_preview", None)
        st.session_state.pop("horus_query_summary", None)
    if preview_rows:
        order_count, item_count = st.session_state.get("horus_query_summary", (0, len(preview_rows)))
        st.divider()
        st.subheader("Prévia da consulta")
        st.caption(f"Pedidos retornados: {order_count:,} · Itens retornados: {item_count:,} · Itens vinculados aos pedidos: {len(preview_rows):,}")
        preview_frame = pd.DataFrame(preview_rows)
        cost_values = pd.to_numeric(preview_frame["custo_unitario"], errors="coerce")
        has_all_costs = bool(cost_values.notna().all())
        visible_columns = ["pedido_id", "data", "cliente", "sku", "titulo", "quantidade", "preco_unitario", "desconto", "custo_unitario", "status"]
        st.dataframe(preview_frame[visible_columns], width="stretch", hide_index=True)
        if not has_all_costs:
            st.warning("O Horus não retornou custo unitário nos itens consultados. Para evitar margens fictícias, a gravação no Skopos fica desabilitada até que o custo seja disponibilizado pela API ou preenchido no CSV.")
            st.download_button(
                "Baixar prévia CSV para completar os custos",
                csv_template(SALES_COLUMNS, preview_frame.to_dict("records")),
                file_name="vendas_horus_completar_custos.csv",
                mime="text/csv",
                width="content",
            )
        else:
            normalized_rows, validation_errors = normalize_sales_frame(preview_frame.drop(columns=["valor_liquido_horus"], errors="ignore"), strict=False)
            if validation_errors:
                render_import_errors(validation_errors)
            elif st.button("Importar vendas no Skopos", type="primary", key="horus_import_sales"):
                imported = import_sales_lines(normalized_rows, company_id, identity_issuer, identity_subject, source="API do Horus")
                st.session_state["horus_sales_preview"] = None
                st.success(f"Importação concluída: {imported} linhas de venda.")
    elif preview_rows is not None:
        st.info("A consulta foi concluída, mas não encontrou itens vinculados aos pedidos nesse período.")

    with st.expander("Configurar credenciais pelo arquivo local"):
        st.markdown("Adicione usuário e senha em `.streamlit/secrets.toml` para preenchimento automático. Esse arquivo não deve ser compartilhado nem enviado ao Git.")
        st.code('[horus_api]\nusername = "seu_usuario"\npassword = "sua_senha"', language="toml")
    with st.expander("O que a consulta traz"):
        st.markdown(
            "A consulta usa `Busca_PedidosVenda` e `Busca_ItensPedidosVenda`, com paginação `OFFSET`/`LIMIT`. "
            "O filtro padrão considera somente pedidos faturados (`FAT`). Cliente, número do pedido, código e título do item, "
            "quantidade, preço, desconto e frete são mapeados quando constam na resposta do Horus. "
            "O custo unitário não aparece nos exemplos públicos da API e precisa ser confirmado com a FMZ para habilitar a importação e os KPIs de margem."
        )


def team_page(show_header: bool = True) -> None:
    if show_header:
        page_header(
            "Acesso da empresa",
            "Equipe",
            "Gerencie quem pode consultar e operar os dados desta empresa.",
        )
    if not can_manage_team:
        st.error("Somente proprietários desta empresa podem gerenciar os acessos.")
        return

    notice_key = f"team_invite_notice_{company_id}"
    notice = st.session_state.get(notice_key)
    if notice:
        level, message = notice
        if st.button("Fechar mensagem", key=f"dismiss_team_notice_{company_id}"):
            st.session_state.pop(notice_key, None)
        else:
            getattr(st, level)(message)

    st.caption(
        "Proprietários gerenciam os dados e os acessos. Colaboradores têm acesso somente para consulta. "
        "Os convites precisam ser aceitos pela conta Google correspondente e são válidos por sete dias."
    )
    members = company_members(company_id)
    member_table = pd.DataFrame([
        {"Nome": member["name"], "E-mail": member["email"], "Perfil": ROLE_LABELS.get(member["role"], member["role"])}
        for member in members
    ])
    st.subheader("Pessoas com acesso")
    st.dataframe(member_table, width="stretch", hide_index=True)

    with st.container(border=True):
        st.subheader("Adicionar pessoas à empresa")
        company_invitation_form(company_id, company_name, identity_issuer, identity_subject)

    if members:
        member_options = {
            f"{member['issuer']}|{member['subject']}": member
            for member in members
        }
        with st.container(border=True):
            st.subheader("Alterar perfil ou remover acesso")
            selected_key = st.selectbox(
                "Pessoa",
                list(member_options),
                format_func=lambda key: (
                    f"{member_options[key]['name']} · {member_options[key]['email']} · "
                    f"{ROLE_LABELS.get(member_options[key]['role'], member_options[key]['role'])}"
                ),
                key=f"team_member_selection_{company_id}",
            )
            selected_member = member_options[selected_key]
            with st.form(f"change_member_role_{company_id}"):
                new_role = st.selectbox(
                    "Novo perfil",
                    COMPANY_ROLES,
                    index=COMPANY_ROLES.index(selected_member["role"]),
                    format_func=lambda value: ROLE_LABELS[value],
                )
                role_submitted = st.form_submit_button("Salvar perfil")
            if role_submitted:
                try:
                    update_company_member_role(
                        company_id,
                        selected_member["issuer"],
                        selected_member["subject"],
                        new_role,
                        identity_issuer,
                        identity_subject,
                    )
                    st.success("Perfil atualizado.")
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
            with st.form(f"remove_member_form_{company_id}"):
                confirm_remove = st.checkbox("Confirmo a remoção do acesso desta pessoa")
                remove_submitted = st.form_submit_button("Remover acesso", key=f"remove_member_{company_id}")
            if remove_submitted and not confirm_remove:
                st.error("Confirme a remoção do acesso antes de continuar.")
            if remove_submitted and confirm_remove:
                try:
                    remove_company_member(
                        company_id,
                        selected_member["issuer"],
                        selected_member["subject"],
                        identity_issuer,
                        identity_subject,
                    )
                    st.success("Acesso removido.")
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))

    invitations = pending_company_invitations(company_id)
    if invitations:
        st.subheader("Convites pendentes")
        invitation_table = pd.DataFrame([
            {"E-mail": item["email"], "Perfil": ROLE_LABELS[item["role"]], "Criado em": item["created_at"]}
            for item in invitations
        ])
        st.dataframe(invitation_table, width="stretch", hide_index=True)
        invitation_options = {int(item["id"]): item for item in invitations}
        invitation_id = st.selectbox(
            "Convite para cancelar",
            list(invitation_options),
            format_func=lambda value: invitation_options[value]["email"],
            key=f"pending_invitation_{company_id}",
        )
        if st.button("Cancelar convite", key=f"cancel_invitation_{company_id}"):
            delete_company_invitation(company_id, invitation_id, identity_issuer, identity_subject)
            st.rerun()


def transactions_page(df: pd.DataFrame) -> None:
    page_header("Operação", "Lançamentos", "Registre entradas e saídas com o mínimo de fricção e mantenha o histórico auditável.")
    if can_edit:
        manual_tab, upload_tab, recurring_tab = st.tabs(["Inserção manual", "Enviar arquivo CSV", "Despesas recorrentes"])
        with manual_tab:
            with st.expander("Novo lançamento", expanded=True):
                kind_col, status_col = st.columns(2)
                kind = kind_col.selectbox("Tipo", ["Receita", "Despesa"], key=f"new_transaction_kind_{company_id}")
                status = status_col.selectbox("Status", ["Pago", "Pendente"], key=f"new_transaction_status_{company_id}")
                with st.form("new_transaction", clear_on_submit=True):
                    dt = st.date_input("Data do registro", value=date.today(), format="DD/MM/YYYY")
                    settled = st.date_input("Data do recebimento / pagamento", value=date.today(), disabled=status == "Pendente", format="DD/MM/YYYY")
                    categories = REVENUE_CATEGORIES if kind == "Receita" else EXPENSE_CATEGORIES
                    category = st.selectbox("Categoria", categories)
                    description = st.text_input("Descrição", placeholder="Ex.: compra de 40 exemplares da Editora Horizonte")
                    c4, c5 = st.columns(2)
                    amount = c4.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")
                    payment = c5.selectbox("Forma de pagamento", PAYMENT_METHODS)
                    due = st.date_input("Vencimento", value=dt, disabled=(status == "Pago"), format="DD/MM/YYYY")
                    notes = st.text_area("Observações", placeholder="Opcional", height=80)
                    submitted = st.form_submit_button("Salvar lançamento", type="primary", width="stretch")
                    if submitted:
                        if not description.strip() or amount <= 0:
                            st.error("Informe uma descrição e um valor maior que zero.")
                        else:
                            add_transaction({
                                "date": dt.isoformat(), "kind": kind, "category": category,
                                "description": description.strip(), "amount": amount,
                                "payment_method": payment, "status": status,
                                "due_date": due.isoformat() if status == "Pendente" else None,
                                "payment_date": settled.isoformat() if status == "Pago" else None,
                                "notes": notes.strip(),
                            }, company_id, identity_issuer, identity_subject)
                            st.success("Lançamento salvo.")
                            st.rerun()
        with upload_tab:
            autonomy_ui.import_form("finance", company_id, identity_issuer, identity_subject)
        with recurring_tab:
            autonomy_ui.recurrence_form(company_id, identity_issuer, identity_subject, EXPENSE_CATEGORIES, PAYMENT_METHODS)
    else:
        st.info("Seu perfil permite consultar os lançamentos, mas não cadastrar ou alterar registros.")

    notice = st.session_state.pop(f"transaction_notice_{company_id}", None)
    if notice:
        st.success(notice)

    if df.empty:
        if can_edit:
            autonomy_ui.import_history("finance", company_id, identity_issuer, identity_subject)
        st.info("Ainda não há lançamentos. Cadastre o primeiro acima.")
        return

    st.subheader("Histórico")
    c1, c2, c3 = st.columns(3)
    search = c1.text_input("Buscar", placeholder="Descrição ou categoria")
    kind_f = c2.multiselect("Tipo", ["Receita", "Despesa"], default=["Receita", "Despesa"])
    status_f = c3.multiselect("Status", ["Pago", "Pendente"], default=["Pago", "Pendente"])
    filtered = df[df["kind"].isin(kind_f) & df["status"].isin(status_f)].copy()
    if search:
        mask = filtered["description"].str.contains(search, case=False, na=False, regex=False) | filtered["category"].str.contains(search, case=False, na=False, regex=False)
        filtered = filtered[mask]
    view = filtered.copy()
    view["Data"] = view["date"].dt.strftime("%d/%m/%Y")
    view["Data do registro"] = view["record_date"].dt.strftime("%d/%m/%Y")
    view["Tipo"] = view["kind"]
    view["Categoria"] = view["category"]
    view["Descrição"] = view["description"]
    view["Status"] = view["status"]
    view["Valor"] = view["amount"].map(money)
    st.caption("Data mostra recebimento/pagamento para lançamentos pagos e a data do registro para pendentes. O vencimento de contas pendentes pode ser consultado em Contas.")
    if can_edit and not filtered.empty:
        transaction_ui.status_editor(filtered, view, company_id, identity_issuer, identity_subject)
    else:
        st.dataframe(view[["Data","Data do registro","Tipo","Categoria","Descrição","Status","Valor"]], width="stretch", hide_index=True)

    if can_edit:
        with st.expander("Ações sobre lançamento"):
            ids = filtered["id"].tolist()
            if ids:
                selected = st.selectbox("ID do lançamento", ids, format_func=lambda x: f"#{x} · {filtered.loc[filtered['id']==x, 'description'].iloc[0]}")
                current_row = filtered.loc[filtered["id"] == selected].iloc[0]
                pending_due = None
                previous_payment = pd.to_datetime(current_row.get("payment_date"), errors="coerce")
                settled_date = st.date_input("Data ao confirmar recebimento / pagamento",
                                             value=previous_payment.date() if pd.notna(previous_payment) else date.today(),
                                             format="DD/MM/YYYY", key=f"settle_date_{company_id}_{selected}")
                if current_row["status"] == "Pago":
                    previous_due = current_row["due_date"]
                    pending_due = st.date_input(
                        "Vencimento ao marcar como pendente",
                        value=previous_due.date() if pd.notna(previous_due) else date.today(),
                        format="DD/MM/YYYY",
                        key=f"pending_due_{company_id}_{selected}",
                    )
                    if st.button("Corrigir data do recebimento / pagamento", key=f"correct_payment_{company_id}_{selected}"):
                        update_status(selected, "Pago", company_id, identity_issuer, identity_subject, payment_date=settled_date.isoformat())
                        st.rerun()
                c1, c2 = st.columns(2)
                if c1.button("Alternar status", width="stretch"):
                    update_status(selected, "Pendente" if current_row["status"] == "Pago" else "Pago", company_id, identity_issuer, identity_subject,
                                  due_date=pending_due.isoformat() if pending_due is not None else None,
                                  payment_date=settled_date.isoformat() if settled_date is not None else None)
                    st.rerun()
                if c2.button("Excluir", type="secondary", width="stretch"):
                    delete_transaction(selected, company_id, identity_issuer, identity_subject)
                    st.rerun()

    if can_edit:
        autonomy_ui.import_history("finance", company_id, identity_issuer, identity_subject)


def accounts_page(df: pd.DataFrame, start: date, end: date) -> None:
    page_header("Compromissos", "Contas a pagar e receber", "Visualize o que ainda precisa entrar ou sair do caixa e priorize vencimentos.")
    start, end = render_period_filter(start, end)
    pending = df[df["status"] == "Pendente"].copy() if not df.empty else df
    if not pending.empty:
        pending = pending[pending["due_date"].dt.date.between(start, end)]
    if pending.empty:
        st.success("Nenhuma conta pendente.")
        return
    today = pd.Timestamp(date.today())
    pending["days"] = (pending["due_date"] - today).dt.days
    receivable = pending[pending["kind"] == "Receita"]["amount"].sum()
    payable = pending[pending["kind"] == "Despesa"]["amount"].sum()
    overdue = pending[pending["days"] < 0]["amount"].sum()
    c = st.columns(3)
    with c[0]: kpi("A receber", money(receivable), "Receitas pendentes")
    with c[1]: kpi("A pagar", money(payable), "Despesas pendentes")
    with c[2]: kpi("Vencido", money(overdue), "Itens com prazo ultrapassado")
    st.write("")
    pending = pending.sort_values("due_date")
    pending["Vencimento"] = pending["due_date"].dt.strftime("%d/%m/%Y").fillna("—")
    pending["Situação"] = pending["days"].apply(lambda d: "Vencido" if pd.notna(d) and d < 0 else ("Hoje" if d == 0 else "A vencer"))
    pending["Valor"] = pending["amount"].map(money)
    pending["Descrição"] = pending["description"]
    pending["Tipo"] = pending["kind"]
    st.dataframe(pending[["Vencimento","Situação","Tipo","Descrição","Valor"]], width="stretch", hide_index=True)


def cashflow_page(df: pd.DataFrame, start: date, end: date) -> None:
    page_header("Liquidez", "Fluxo de caixa", "Acompanhe o saldo acumulado e identifique antecipadamente períodos de pressão financeira.")
    start, end = render_period_filter(start, end)
    opening = autonomy_ui.opening_form(company_id, identity_issuer, identity_subject, can_edit)
    if opening is None:
        st.warning("Saldo inicial não informado. O gráfico mostra apenas a variação dos lançamentos no período, sem representar o dinheiro disponível.")
    else:
        st.caption(f"Saldo inicial consolidado: {money(opening['amount'])} no início de {date.fromisoformat(opening['date']):%d/%m/%Y}. O saldo considera somente as movimentações registradas desde essa data.")
    st.caption("Recebimentos e pagamentos realizados usam a data de recebimento/pagamento. Contas pendentes usam o vencimento; pendências anteriores ao período entram na projeção do primeiro dia. Vendas diárias e vendas por item não entram neste caixa automaticamente.")
    if df.empty:
        st.info("Movimentações financeiras não informadas. O saldo inicial sozinho não confirma que os registros estão completos.")
    daily = autonomy.cash_projection(df, opening, start, end)
    if daily["actual"].isna().all():
        st.info("O período selecionado é anterior ao saldo inicial. Escolha um período a partir da data cadastrada.")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["date"], y=daily["actual"], mode="lines", name="Realizado pelos registros"))
    fig.add_trace(go.Scatter(x=daily["date"], y=daily["projected"], mode="lines", name="Projetado com pendências", line=dict(dash="dash")))
    fig.update_layout(
        height=420,
        margin=dict(l=8, r=8, t=18, b=8),
        xaxis=dict(type="date", title="Data", tickformat="%d/%m/%Y", hoverformat="%d/%m/%Y"),
        yaxis_title="Saldo pelos registros" if opening else "Variação dos lançamentos",
    )
    ui_module.render_plotly(fig)
    low = daily.loc[daily["projected"].idxmin()]
    st.caption(f"Menor {'saldo projetado pelos registros' if opening else 'variação projetada'}: {money(low['projected'])} em {low['date']:%d/%m/%Y}.")


def budget_page(df: pd.DataFrame) -> None:
    page_header("Planejamento", "Orçamento", "Defina limites por categoria e compare o planejado com o realizado.")
    current_month = pd.Period(date.today(), freq="M")
    month = st.selectbox("Mês de referência", pd.period_range(current_month-12, current_month+12, freq="M").astype(str),
                         index=12, key=f"budget_month_{company_id}")
    if can_edit:
        with st.form("budget_form"):
            category = st.selectbox("Categoria", EXPENSE_CATEGORIES)
            amount = st.number_input("Orçamento mensal (R$)", min_value=0.0, step=100.0, format="%.2f")
            if st.form_submit_button("Salvar orçamento", type="primary"):
                upsert_budget(month, category, amount, company_id, identity_issuer, identity_subject)
                st.success("Orçamento atualizado.")
                st.rerun()
    else:
        st.info("Seu perfil permite consultar o orçamento, mas não cadastrar ou alterar valores.")
    budgets = query_df("SELECT month, category, amount FROM budgets WHERE company_id = ? AND month = ? ORDER BY category", [company_id, month])
    if budgets.empty:
        st.info("Nenhum orçamento definido para este mês.")
        return
    month_start = pd.Period(month).start_time
    month_end = pd.Period(month).end_time
    realized = df[(df["kind"] == "Despesa") & (df["status"] == "Pago") & (df["date"].between(month_start, month_end))].groupby("category", as_index=False)["amount"].sum()
    comp = budgets.merge(realized, on="category", how="left", suffixes=("_budget", "_real"))
    comp["amount_real"] = comp["amount_real"].fillna(0)
    comp["Uso"] = (comp["amount_real"] / comp["amount_budget"].replace(0, pd.NA) * 100).fillna(0)
    comp["Categoria"] = comp["category"]
    comp["Orçado"] = comp["amount_budget"].map(money)
    comp["Realizado"] = comp["amount_real"].map(money)
    comp["Uso %"] = comp["Uso"].map(lambda x: f"{x:.0f}%")
    st.dataframe(comp[["Categoria","Orçado","Realizado","Uso %"]], width="stretch", hide_index=True)


def reports_page(df: pd.DataFrame, start: date, end: date) -> None:
    page_header("Análise", "Relatórios", "Explore os dados por categoria e exporte a visão filtrada para conciliação ou contabilidade.")
    start, end = render_period_filter(start, end)
    sdf = scope_df(df, start, end)
    if sdf.empty:
        st.info("Sem dados no período selecionado.")
        return
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Resultado por categoria")
        cat = sdf.groupby(["category", "kind"], as_index=False)["amount"].sum().sort_values("amount", ascending=False)
        fig = px.bar(cat, x="amount", y="category", color="kind", orientation="h", labels={"amount":"Valor","category":"Categoria","kind":"Tipo"})
        fig.update_layout(height=430, margin=dict(l=8,r=8,t=10,b=8), legend_title_text="")
        ui_module.render_plotly(fig)
    with c2:
        st.subheader("Meios de pagamento")
        pay = sdf.groupby("payment_method", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
        fig = px.bar(pay, x="payment_method", y="amount", labels={"payment_method":"Meio","amount":"Valor"})
        fig.update_layout(height=430, margin=dict(l=8,r=8,t=10,b=8))
        ui_module.render_plotly(fig)
    export = sdf.copy()
    export["date"] = export["date"].dt.strftime("%Y-%m-%d")
    export["due_date"] = export["due_date"].dt.strftime("%Y-%m-%d")
    st.download_button("Baixar CSV do período", export.to_csv(index=False).encode("utf-8-sig"), file_name=f"financeiro_{start}_{end}.csv", mime="text/csv", width="stretch")


def configured_gemini_key() -> str:
    configured_key = ""
    try:
        gemini_secrets = st.secrets.get("gemini", {})
        configured_key = gemini_secrets.get("api_key", "") if hasattr(gemini_secrets, "get") else ""
        configured_key = configured_key or st.secrets.get("gemini_api_key", "")
    except StreamlitSecretNotFoundError:
        pass
    return (
        st.session_state.get(f"gemini_session_key_{company_id}", "")
        or configured_key
        or os.environ.get("GEMINI_API_KEY", "")
    )


def ai_configuration_page() -> None:
    page_header(
        "Gestão da plataforma",
        "Configuração de IA",
        "Configure o modelo Gemini e a chave usada para gerar insights desta empresa.",
    )
    st.caption("A chave digitada fica somente na sessão atual. Para uso contínuo, configure-a nos secrets do servidor; ela nunca é gravada no banco do Skopos.")
    stored_model = get_app_setting("gemini_model", company_id, "gemini-3.8-flash")
    model_key = f"gemini_model_input_{company_id}"
    st.session_state.setdefault(model_key, stored_model)
    with st.form(f"gemini_settings_form_{company_id}"):
        model = st.text_input(
            "Modelo Gemini",
            help="Informe um modelo habilitado para sua chave Gemini. Modelo inicial: gemini-3.8-flash.",
            key=model_key,
        )
        save_model = st.form_submit_button("Salvar modelo", type="primary")
    if save_model:
        if not model.strip():
            st.error("Informe o identificador de um modelo.")
        else:
            set_app_settings({"gemini_model": model.strip()}, company_id, identity_issuer, identity_subject)
            st.success("Modelo salvo para esta empresa.")

    input_key = f"gemini_key_input_{company_id}"
    session_key = f"gemini_session_key_{company_id}"
    st.session_state.setdefault(input_key, st.session_state.get(session_key, ""))

    def remember_gemini_key() -> None:
        st.session_state[session_key] = st.session_state.get(input_key, "").strip()

    st.text_input(
        "Chave da API Gemini",
        type="password",
        key=input_key,
        on_change=remember_gemini_key,
        persist_state="session",
        help="Usada apenas nesta sessão e nunca gravada no banco do Skopos.",
    )
    if configured_gemini_key():
        st.success("Uma chave Gemini está disponível para esta sessão.")
    else:
        st.info("Digite a chave aqui ou configure GEMINI_API_KEY nos secrets do servidor.")


def ai_insights_page(df: pd.DataFrame, sales_df: pd.DataFrame, inventory_df: pd.DataFrame, start: date, end: date) -> None:
    page_header(
        "Análise assistida",
        "Insights com IA",
        "Use os indicadores da empresa selecionada para gerar uma leitura financeira em linguagem simples.",
    )
    if not can_edit:
        st.info("A geração de análises com IA está disponível para proprietários. Você pode consultar os indicadores nos painéis.")
        return
    st.warning(
        "Ao gerar a análise, o Skopos envia ao Google Gemini indicadores agregados da empresa e do período, incluindo até cinco produtos. "
        "Nomes de clientes, e-mails, descrições de lançamentos e identificadores de empresa não são enviados. "
        "A política do Google difere por nível: no gratuito, solicitações e respostas podem ser usadas para melhorar produtos e revistas por pessoas; no pago, não são usadas para esse fim. Evite enviar informações sigilosas pelo nível gratuito."
    )

    model = get_app_setting("gemini_model", company_id, "gemini-3.8-flash")
    api_key = configured_gemini_key()
    if not api_key:
        st.info("Para gerar insights, informe a chave da API Gemini em Configuração de IA. Depois, autorize o envio dos indicadores abaixo.")
        st.button("Configurar IA", icon=":material/settings:", key=f"insights_settings_{company_id}",
                  on_click=navigate_to, args=("Configuração de IA",))
    if not model.strip():
        st.warning("Escolha um modelo em Configuração de IA antes de gerar a análise.")

    daily_sales = query_df("SELECT date,amount FROM daily_sales WHERE company_id=?", [company_id])
    summary = build_insight_payload(df, sales_df, inventory_df, start, end, daily_sales=daily_sales)
    with st.expander("Ver resumo que será enviado", expanded=False):
        st.json(summary)

    consent = st.checkbox(
        "Autorizo enviar esses indicadores agregados ao Gemini para gerar a análise. Entendo a diferença entre o uso gratuito e o pago.",
        key=f"gemini_data_consent_{company_id}",
    )
    can_generate = bool(api_key and model.strip() and consent)
    if api_key and model.strip() and not consent:
        st.caption("Marque a autorização acima para habilitar Gerar insights.")
    if st.button(
        "Gerar insights",
        type="primary",
        icon=":material/auto_awesome:",
        disabled=not can_generate,
        key=f"generate_gemini_insights_{company_id}",
    ):
        has_data = (
            not scope_df(df, start, end).empty
            or summary["vendas_por_item"] is not None
            or summary["vendas_diarias"] is not None
            or summary["estoque"] is not None
        )
        if not has_data:
            st.info("Não há dados da empresa no período selecionado. Importe vendas ou cadastre lançamentos primeiro.")
        else:
            st.session_state.pop(f"gemini_result_{company_id}", None)
            try:
                with st.spinner("Analisando os indicadores da empresa…"):
                    result = generate_gemini_insights(api_key, model, summary)
                st.session_state[f"gemini_result_{company_id}"] = result
                st.session_state[f"gemini_result_period_{company_id}"] = f"{start:%d/%m/%Y} a {end:%d/%m/%Y}"
            except AIServiceError as exc:
                st.error(str(exc))

    result = st.session_state.get(f"gemini_result_{company_id}")
    if result:
        st.subheader("Análise gerada")
        st.caption(f"Empresa: {company_name} · Período: {st.session_state.get(f'gemini_result_period_{company_id}', '—')}")
        st.markdown(result)


page, start, end, selected_company_id = sidebar()
active_company = next(item for item in user_companies if int(item["id"]) == selected_company_id)
company_id = selected_company_id
company_name = active_company["name"]
membership_role = active_company["role"]
can_edit = membership_role == "administrator"
can_manage_team = membership_role == "administrator"
collapsed_nav_rail(membership_role)
account_menu()
df = load_transactions()
sales_df = load_sales()
inventory_df = load_inventory()

if page == "Home":
    home_page(df, start, end)
elif page == "Visão geral":
    analytics_overview(df, sales_df, inventory_df, start, end)
elif page == "Curva ABC":
    abc_page(sales_df, start, end)
elif page == "Vendas e estoque":
    sales_import_page(sales_df, inventory_df)
elif page == "Lançamentos":
    transactions_page(df)
elif page == "Contas":
    accounts_page(df, start, end)
elif page == "Fluxo de caixa":
    cashflow_page(df, start, end)
elif page == "Orçamento":
    budget_page(df)
elif page == "Relatórios":
    reports_page(df, start, end)
elif page == "Insights com IA":
    ai_insights_page(df, sales_df, inventory_df, start, end)
elif page == "API do Horus":
    if membership_role == "administrator":
        api_configuration_page()
    else:
        st.error("Somente proprietários podem acessar as integrações da empresa.")
elif page == "Configuração de IA":
    if membership_role == "administrator":
        ai_configuration_page()
    else:
        st.error("Somente proprietários podem alterar a configuração de IA da empresa.")
elif page == "Equipe":
    team_page()
elif page == "Meu perfil":
    account_settings_page()
elif page == "Empresa":
    company_settings_page()

