from __future__ import annotations

import base64
import importlib
import json
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import os
import zipfile

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageOps
from streamlit.errors import StreamlitSecretNotFoundError

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
    add_transaction,
    accept_company_invitations,
    companies_for_user,
    company_members,
    create_company,
    delete_company_invitation,
    delete_transaction,
    get_app_setting,
    has_pending_company_invitation,
    import_inventory_snapshots,
    import_sales_lines,
    invite_company_member,
    init_db,
    pending_company_invitations,
    query_df,
    remove_company_member,
    register_identity,
    seed_demo,
    set_app_settings,
    update_status,
    update_company,
    update_company_member_role,
    upsert_budget,
)
from import_contract import read_csv, csv_template
from horus_api import HorusAPIError, fetch_orders_and_items, sales_preview, test_connection
import ui as ui_module

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
    if all(provider_config.get(key) for key in required):
        return [("google", "Google")]
    return []


def render_login_page(identity_providers: list[tuple[str, str]]) -> None:
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] { background: #fff; }
        [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer {
            visibility: hidden; height: 0; min-height: 0;
        }
        [data-testid="stMainBlockContainer"] {
            max-width: none !important; padding: 0 !important; margin: 0 !important;
        }
        [data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] {
            gap: 0 !important;
        }
        .st-key-login_layout [data-testid="stHorizontalBlock"] {
            min-height: 100vh; gap: 0 !important; align-items: stretch !important;
        }
        .st-key-login_left_panel {
            display: flex; align-items: center; justify-content: center;
            padding: clamp(2rem, 5.5vw, 5.5rem); background: #fff;
        }
        .st-key-login_right_panel {
            display: flex; align-items: center; justify-content: center;
            padding: clamp(2rem, 5vw, 5rem); min-height: 100vh;
            color: #fff; background: #625fe9; border-radius: 14px 0 0 14px;
        }
        .st-key-login_left_panel > div[data-testid="stVerticalBlock"],
        .st-key-login_right_panel > div[data-testid="stVerticalBlock"] {
            width: min(100%, 470px); margin: auto; justify-content: center;
        }
        .login-left-marker, .login-right-marker { display: none; }
        .login-brand { display: flex; align-items: center; gap: .65rem; margin-bottom: 2.8rem; color: #171927; }
        .login-brand-mark { display: grid; place-items: center; width: 2.55rem; height: 2.55rem;
            border-radius: .85rem; background: #f0efff; font-size: 1.25rem; }
        .st-key-login_logo_image { width: 100%; margin-bottom: 2.8rem; overflow: visible !important; }
        .st-key-login_logo_image [data-testid="stImage"],
        .st-key-login_logo_image [data-testid="stImage"] > div {
            width: 100% !important; max-width: 420px !important; height: auto !important;
            overflow: visible !important; border-radius: 0 !important; clip-path: none !important;
        }
        .st-key-login_logo_image img {
            display: block !important; width: 100% !important; height: auto !important;
            max-width: 420px !important; object-fit: contain !important; object-position: left center !important;
            border-radius: 0 !important; clip-path: none !important;
        }
        .login-brand-name { font-size: 1.3rem; font-weight: 760; letter-spacing: -.04em; }
        .login-eyebrow { margin-bottom: .7rem; color: #625fe9; font-size: .76rem; font-weight: 750;
            letter-spacing: .04em; }
        .st-key-login_left_panel h1 {
            margin: 0 0 .55rem; color: #171927; font-size: clamp(2.1rem, 3.3vw, 3rem);
            font-weight: 760; letter-spacing: -.045em;
        }
        .login-description { margin-bottom: 1.8rem; color: #73798b; font-size: 1rem; line-height: 1.65; }
        .st-key-login_left_panel button[kind="primary"] {
            min-height: 3.35rem; border: 1px solid #625fe9; border-radius: .7rem;
            color: #fff; background: #625fe9; font-size: .98rem; font-weight: 700;
            box-shadow: 0 8px 22px rgba(98,95,233,.2); transition: transform .15s ease, background .15s ease;
        }
        .st-key-login_left_panel button[kind="primary"]:hover {
            border-color: #514ed5; background: #514ed5; transform: translateY(-1px);
        }
        .login-divider { display: flex; align-items: center; gap: .8rem; margin: 1.55rem 0 1rem;
            color: #a2a6b2; font-size: .78rem; }
        .login-divider::before, .login-divider::after { content: ""; flex: 1; height: 1px; background: #e8e9ef; }
        .login-footnote { color: #9298a6; font-size: .82rem; line-height: 1.6; text-align: center; }
        .login-notice { padding: .9rem 1rem; border: 1px solid #f2dfb5; border-radius: .7rem;
            color: #7a5b21; background: #fff9ec; font-size: .9rem; line-height: 1.5; }
        .login-hero-eyebrow { color: rgba(255,255,255,.74); font-size: .76rem; font-weight: 750;
            letter-spacing: .14em; text-align: center; text-transform: uppercase; }
        .st-key-login_right_panel h2 {
            margin: .6rem 0 .5rem; color: #fff; font-size: clamp(1.8rem, 2.6vw, 2.5rem);
            font-weight: 740; letter-spacing: -.04em; line-height: 1.2; text-align: center;
        }
        .login-hero-copy { max-width: 32rem; margin: 0 auto 1.15rem; color: rgba(255,255,255,.8);
            font-size: 1rem; line-height: 1.6; text-align: center; }
        .login-hero-art { display: block; width: min(100%, 38rem); max-height: 25rem; margin: .2rem auto .7rem; }
        .login-hero-caption { color: rgba(255,255,255,.75); font-size: .83rem; text-align: center; }
        @media (max-width: 760px) {
            .st-key-login_layout [data-testid="stHorizontalBlock"] {
                min-height: 100vh; flex-wrap: wrap !important;
            }
            .st-key-login_left_panel { min-height: 72vh; padding: 2rem 1.5rem; }
            .st-key-login_right_panel {
                min-height: auto; padding: 2.2rem 1.5rem; border-radius: 14px 14px 0 0;
            }
            .st-key-login_left_panel > div[data-testid="stVerticalBlock"] { min-height: 65vh; }
            .login-brand { margin-bottom: 2rem; }
            .login-hero-art { max-height: 15rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="login_layout"):
        left_panel, right_panel = st.columns([0.86, 1.14], gap=None)
    with left_panel.container(key="login_left_panel"):
        st.markdown('<span class="login-left-marker"></span>', unsafe_allow_html=True)
        with st.container(key="login_logo_image"):
            st.image(str(ASSETS_DIR / "logo_login.svg"), width=420)
        st.title("Faça seu login")
        st.markdown(
            '<div class="login-description">Entre com sua conta Google para acompanhar '
            'as finanças e as vendas da sua livraria.</div>',
            unsafe_allow_html=True,
        )
        if identity_providers:
            if st.button(
                "Continuar com Google",
                icon=":material/login:",
                key="login_google",
                type="primary",
                width="stretch",
            ):
                st.login("google")
        else:
            st.markdown(
                '<div class="login-notice">O acesso pelo Google ainda precisa ser configurado. '
                'Confira as credenciais locais do app.</div>',
                unsafe_allow_html=True,
            )
        st.markdown('<div class="login-divider">acesso seguro</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-footnote">No primeiro acesso, entre com o Google e cadastre '
            'o perfil da sua livraria.</div>',
            unsafe_allow_html=True,
        )

    with right_panel.container(key="login_right_panel"):
        st.markdown('<span class="login-right-marker"></span>', unsafe_allow_html=True)
        st.markdown('<div class="login-hero-eyebrow">Visão clara, boas decisões</div>', unsafe_allow_html=True)
        st.markdown('<h2>Sua livraria em equilíbrio.</h2>', unsafe_allow_html=True)
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
        st.markdown('<div class="login-hero-caption">Os números da sua livraria, sempre à vista.</div>', unsafe_allow_html=True)


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
accepted_invitations = accept_company_invitations(
    st.user.get("email", ""), identity_issuer, identity_subject, email_verified
)
user_companies = companies_for_user(identity_issuer, identity_subject)
if not user_companies:
    if has_pending_company_invitation(st.user.get("email", "")) and not email_verified:
        st.error("Há um convite para este e-mail, mas o Google não confirmou que ele foi verificado. Entre em contato com o administrador da livraria.")
        st.stop()
    st.markdown("## Cadastre o perfil da sua livraria")
    st.write("O login continua sendo feito pelo Google. Este perfil separa os dados da sua empresa dos dados de outras livrarias.")
    with st.form("company_onboarding"):
        company_name = st.text_input("Nome da livraria", placeholder="Ex.: Livraria Horizonte")
        submitted = st.form_submit_button("Criar perfil da empresa", type="primary")
        if submitted:
            if not company_name.strip():
                st.error("Informe o nome da livraria.")
            else:
                create_company(company_name, identity_issuer, identity_subject)
                st.rerun()
    st.stop()
company_id = int(user_companies[0]["id"])
company_name = user_companies[0]["name"]
membership_role = user_companies[0]["role"]
st.session_state.setdefault("dark_mode", False)
inject_css(dark_mode=st.session_state["dark_mode"])

ROLE_LABELS = {
    "administrator": "Admin",
    "manager": "Gestor",
    "collaborator": "Colaborador",
}
can_edit = membership_role in {"administrator", "manager"}
can_manage_team = membership_role == "administrator"

REVENUE_CATEGORIES = ["Vendas de livros", "Vendas online", "Eventos", "Assinaturas", "Outras receitas"]
EXPENSE_CATEGORIES = ["Fornecedores", "Aluguel", "Folha e encargos", "Marketing", "Fretes", "Impostos", "Tecnologia", "Outras despesas"]
PAYMENT_METHODS = ["PIX", "Cartão", "Dinheiro", "Boleto", "Transferência"]


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
    if page == "Equipe":
        st.session_state["account_team_expanded"] = True
        page = "Conta"
    st.session_state["active_page"] = page
    st.query_params["page"] = page


def clear_horus_session() -> None:
    for key in list(st.session_state):
        if key.startswith("horus_"):
            del st.session_state[key]


def switch_company(company_id: int) -> None:
    if company_id != st.session_state.get("active_company_id"):
        clear_horus_session()
    st.session_state["active_company_id"] = company_id


def toggle_financial_values() -> None:
    st.session_state["hide_financial_values"] = not st.session_state.get("hide_financial_values", True)


def toggle_dark_mode() -> None:
    st.session_state["dark_mode"] = not st.session_state.get("dark_mode", False)


def logout_user() -> None:
    clear_horus_session()
    for session_key in list(st.session_state.keys()):
        if session_key.startswith(("gemini_session_key_", "gemini_key_input_", "openai_session_key_", "openai_key_input_")):
            del st.session_state[session_key]
    st.logout()


def desktop_shortcut_zip() -> bytes:
    output = BytesIO()
    # Ícone incorporado para o download funcionar mesmo sem um asset separado no Cloud.
    icon = base64.b64decode('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')
    installer = 'Option Explicit\nDim shell, files, sourceDir, iconDir, shortcut\nSet shell = CreateObject("WScript.Shell")\nSet files = CreateObject("Scripting.FileSystemObject")\nsourceDir = files.GetParentFolderName(WScript.ScriptFullName)\niconDir = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\\Skopos"\nIf Not files.FolderExists(iconDir) Then files.CreateFolder(iconDir)\nfiles.CopyFile sourceDir & "\\Skopos.ico", iconDir & "\\Skopos.ico", True\nSet shortcut = shell.CreateShortcut(shell.SpecialFolders("Desktop") & "\\Skopos Online.lnk")\nshortcut.TargetPath = shell.ExpandEnvironmentStrings("%WINDIR%") & "\\explorer.exe"\nshortcut.Arguments = "https://skopos.streamlit.app/"\nshortcut.IconLocation = iconDir & "\\Skopos.ico,0"\nshortcut.Description = "Abrir o Skopos no navegador"\nshortcut.Save\nMsgBox "Atalho Skopos Online criado na area de trabalho.", 64, "Skopos"\n'
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Skopos.ico", icon)
        archive.writestr("Criar atalho.vbs", installer.replace("\n", "\r\n"))
        archive.writestr("LEIA-ME.txt", (
            "1. Clique com o botao direito no ZIP e escolha Extrair tudo.\r\n"
            "2. Abra a pasta extraida e de dois cliques em Criar atalho.vbs.\r\n"
            "3. Use Skopos Online na area de trabalho.\r\n"
            "O icone fica salvo na pasta local do usuario; a pasta extraida pode ser removida.\r\n"
            "O atalho abre o app no navegador e requer internet.\r\n"
        ))
    return output.getvalue()


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
        st.download_button(
            "Atalho desktop",
            data=desktop_shortcut_zip(),
            file_name="Skopos-Atalho.zip",
            mime="application/zip",
            icon=":material/download:",
            help="Extraia o ZIP e execute Criar atalho.vbs para criar o atalho com o logo do Skopos na área de trabalho.",
            on_click="ignore",
            key="download_desktop_shortcut",
        )
        with st.popover("Conta", icon=":material/account_circle:", width="content"):
                account_name = st.user.get("name", "") or "Conta Google"
                account_email = st.user.get("email", "")
                st.markdown(f"**{account_name}**")
                if account_email:
                    st.caption(account_email)
                st.caption(f"Empresa ativa: {company_name}")
                st.caption(f"Perfil: {ROLE_LABELS.get(membership_role, 'Colaborador')}")
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
    "Conta": ":material/account_circle:",
}

SHORTCUT_TARGETS = [
    "Visão geral", "Curva ABC", "Relatórios", "Fluxo de caixa", "Contas",
    "Insights com IA", "Vendas e estoque", "Lançamentos", "Orçamento", "API do Horus",
    "Configuração de IA", "Equipe", "Conta",
]


def accessible_shortcuts(role: str) -> list[str]:
    allowed = {
        "Visão geral", "Curva ABC", "Relatórios", "Fluxo de caixa", "Contas", "Insights com IA"
    }
    if role in {"administrator", "manager"}:
        allowed.update({"Vendas e estoque", "Lançamentos", "Orçamento"})
    if role == "administrator":
        allowed.update({"API do Horus", "Configuração de IA", "Equipe", "Conta"})
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
            "Visão geral", "Curva ABC", "Relatórios", "Fluxo de caixa", "Contas", "Insights com IA",
        ],
        "Alimentar e planejar": ["Vendas e estoque", "Lançamentos", "Orçamento"] if role in {"administrator", "manager"} else [],
        "Gestão da Plataforma": ["API do Horus", "Configuração de IA", "Conta"] if role == "administrator" else [],
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
    current_value = get_app_setting("home_shortcuts", company_id)
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
            help="Os Favoritos aparecem na Home de todas as pessoas com acesso a esta livraria.",
        )
        save = st.form_submit_button("Salvar Favoritos", type="primary")
    if save:
        if not selected:
            st.error("Selecione pelo menos uma tela para manter um atalho na Home.")
        else:
            set_app_settings(
                {"home_shortcuts": json.dumps(selected, ensure_ascii=False)},
                company_id,
                identity_issuer,
                identity_subject,
            )
            st.success("Favoritos da Home atualizados.")


def home_page(df: pd.DataFrame, start: date, end: date) -> None:
    display_name = st.user.get("given_name") or st.user.get("name", "").strip()
    if not display_name:
        display_name = st.user.get("email", "").split("@", 1)[0] or "por aqui"
    render_dashboard_welcome(company_id, display_name)
    start, end = render_period_filter(start, end)

    raw_shortcuts = get_app_setting("home_shortcuts", company_id)
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

    scoped = scope_df(df, start, end)
    paid = scoped[scoped["status"] == "Pago"] if not scoped.empty else scoped
    income = paid.loc[paid["kind"] == "Receita", "amount"].sum() if not paid.empty else 0
    expense = paid.loc[paid["kind"] == "Despesa", "amount"].sum() if not paid.empty else 0
    st.subheader("Entradas e saídas")
    st.caption(f"Lançamentos pagos no período de {start:%d/%m/%Y} a {end:%d/%m/%Y}.")
    hidden = st.session_state.get("hide_financial_values", True)
    incoming_col, outgoing_col = st.columns(2)
    with incoming_col:
        kpi("Entradas", money(income), "Receitas pagas no período", hide_values=hidden)
    with outgoing_col:
        kpi("Saídas", money(expense), "Despesas pagas no período", hide_values=hidden)


def account_settings_page() -> None:
    page_header("Gestão da plataforma", "Conta", "Dados da sua conta e configurações da empresa selecionada.")
    account_name = st.user.get("name", "") or "Conta Google"
    account_email = st.user.get("email", "")
    st.subheader(account_name)
    if account_email:
        st.caption(account_email)
    st.write(f"**Empresa:** {company_name}")
    st.write(f"**Perfil:** {ROLE_LABELS.get(membership_role, 'Colaborador')}")

    if can_manage_team:
        with st.expander("Equipe", expanded=st.session_state.get("account_team_expanded", False)):
            team_page(show_header=False)

    if can_edit:
        render_company_cover_settings(company_id)
        with st.expander("Favoritos da Home"):
            st.caption("Escolha os acessos rápidos exibidos na tela inicial desta livraria.")
            home_shortcuts_settings()
    if can_manage_team:
        with st.expander("Perfil da empresa"):
            with st.form("company_profile_form"):
                updated_name = st.text_input("Nome da livraria", value=company_name)
                if st.form_submit_button("Salvar perfil", type="primary"):
                    if update_company(company_id, updated_name, identity_issuer, identity_subject):
                        st.success("Perfil atualizado.")
                        st.rerun()
                    st.error("Não foi possível atualizar o perfil.")

    if can_edit:
        with st.expander("Acessos de colaboradores"):
            collaborators = [member for member in company_members(company_id) if member["role"] == "collaborator"]
            if not collaborators:
                st.info("Não há colaboradores vinculados a esta empresa.")
            else:
                collaborator_options = {
                    f"{member['issuer']}|{member['subject']}": member
                    for member in collaborators
                }
                with st.form(f"remove_collaborator_form_{company_id}"):
                    selected_key = st.selectbox(
                        "Colaborador",
                        list(collaborator_options),
                        format_func=lambda key: (
                            f"{collaborator_options[key]['name']} · {collaborator_options[key]['email']}"
                        ),
                    )
                    st.caption("Isso remove o acesso desta pessoa à empresa. A conta Google e os dados da livraria não são excluídos.")
                    confirm_remove = st.checkbox("Confirmo a remoção do acesso deste colaborador.")
                    remove_submitted = st.form_submit_button(
                        "Remover acesso",
                        type="secondary",
                    )
                if remove_submitted and not confirm_remove:
                    st.error("Confirme a remoção do acesso antes de continuar.")
                if remove_submitted and confirm_remove:
                    selected = collaborator_options[selected_key]
                    try:
                        remove_company_member(
                            company_id,
                            selected["issuer"],
                            selected["subject"],
                            identity_issuer,
                            identity_subject,
                        )
                        st.success("Acesso do colaborador removido.")
                        st.rerun()
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))

    st.divider()
    if st.button("Sair", icon=":material/logout:", type="secondary", key="logout_button"):
        logout_user()


def load_transactions() -> pd.DataFrame:
    df = query_df("SELECT * FROM transactions WHERE company_id = ? ORDER BY date DESC, id DESC", [company_id])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce")
    return df


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
        st.caption("A capa é compartilhada com as pessoas que têm acesso a esta empresa. Somente o perfil Admin pode alterá-la.")
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
            st.write(f"Bem-vindo(a) à gestão da **{company_name}**. Aqui está o panorama da sua livraria.")
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
            ("Curva ABC", "Curva ABC"),
            ("Relatórios", "Relatórios"),
            ("Fluxo de caixa", "Fluxo de caixa"),
            ("Contas", "Contas"),
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
                ("Conta", "Conta"),
            ])
        old_page = st.query_params.get("page") or st.session_state.get("page_navigation", "Home")
        old_page_map = {"Configuração de API": "API do Horus"}
        st.session_state.setdefault("active_page", old_page_map.get(old_page, old_page))
        if st.session_state["active_page"] == "Equipe":
            navigate_to("Equipe")
        if selected_membership["role"] not in {"administrator", "manager"}:
            data_pages = []
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
    page_header("Painel executivo", "Visão geral", "Indicadores essenciais para acompanhar liquidez, resultado e compromissos da livraria.")
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
        st.info("Ainda não há vendas por item no período. Importe o CSV de vendas ou configure uma API para habilitar os KPIs comerciais.")
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
                ("Clientes ativos", f"{sales['customers']:,}".replace(",", "."), "Clientes identificados no período"),
                ("Frequência de compra", f"{sales['order_frequency']:.2f}", "Pedidos por cliente identificado"),
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
            st.subheader("Curva ABC de títulos")
            rank = sales["product_rank"].head(20)
            if rank.empty:
                st.info("Sem títulos identificados.")
            else:
                fig = px.bar(rank, x="title", y="net_revenue", color="class", labels={"title": "Título", "net_revenue": "Receita", "class": "Classe"})
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
    finance_metrics = [
        ("Receitas pagas", money(revenue), "Lançamentos financeiros"),
        ("Despesas pagas", money(expense), "Lançamentos financeiros"),
        ("Saldo dos lançamentos", money(result), "Receitas pagas − despesas pagas"),
        ("A pagar no período", money(pending_pay), "Por vencimento cadastrado"),
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
    page_header("Dados comerciais", "Vendas e estoque", "Carregue os dados que alimentam faturamento por título, clientes, canais, curva ABC e giro.")
    if not can_edit:
        st.info("Seu perfil permite consultar os dados da empresa, mas não importar ou alterar vendas e estoque.")
        if not sales_df.empty:
            st.subheader("Vendas carregadas")
            st.dataframe(
                sales_df[["sale_date", "order_id", "channel", "sku", "title", "quantity", "unit_price", "status"]]
                .rename(columns={"sale_date": "Data", "order_id": "Pedido", "channel": "Canal", "sku": "SKU", "title": "Título", "quantity": "Quantidade", "unit_price": "Preço unitário", "status": "Status"})
                .head(100),
                width="stretch",
                hide_index=True,
            )
        if not inventory_df.empty:
            st.caption(f"Posições de estoque disponíveis para consulta: {len(inventory_df)}.")
        return
    st.caption("O app aceita CSV ou sincronização pela API. O formato abaixo é por item de pedido: uma linha para cada combinação de pedido e SKU.")
    st.info("Padrão obrigatório: números sem separador de milhar e com ponto decimal (1234.56); datas AAAA-MM-DD. Não use R$, %, vírgula decimal ou fórmulas. CSV separado por vírgula ou ponto e vírgula; UTF-8 recomendado. Campos numéricos opcionais vazios valem zero. O arquivo inteiro é bloqueado se houver erro.")
    sales_template = csv_template(SALES_COLUMNS)
    inventory_template = csv_template(INVENTORY_COLUMNS)
    template_cols = st.columns(2)
    with template_cols[0]:
        st.download_button("Baixar modelo de vendas CSV", sales_template, file_name="modelo_vendas_skopos.csv", mime="text/csv", width="stretch")
    with template_cols[1]:
        st.download_button("Baixar modelo de estoque CSV", inventory_template, file_name="modelo_estoque_skopos.csv", mime="text/csv", width="stretch")
    with st.expander("Exemplos preenchidos e instruções"):
        st.caption("Os exemplos contêm dados fictícios. Use-os como referência e substitua todas as linhas pelos seus dados antes de importar. No Excel, confira o CSV em um editor de texto após exportar: a configuração regional pode transformar o ponto decimal em vírgula.")
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
                    st.dataframe(pd.DataFrame(rows).head(8), width="stretch", hide_index=True)
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
                    st.dataframe(pd.DataFrame(rows).head(8), width="stretch", hide_index=True)
                    if st.button("Importar estoque", type="primary", key="import_inventory"):
                        count = import_inventory_snapshots(rows, company_id, identity_issuer, identity_subject, source=uploaded_stock.name)
                        st.success(f"{count} posições de estoque importadas ou atualizadas.")
                        st.rerun()
            except Exception as exc:
                st.error(str(exc) if isinstance(exc, ValueError) else "Não consegui importar o CSV. Confira os dados e a conexão com o banco.")

    if not sales_df.empty:
        st.subheader("Vendas carregadas")
        sales_table = sales_df[["sale_date", "order_id", "customer", "channel", "sku", "title", "quantity", "unit_price", "unit_cost", "status"]].rename(
            columns={"sale_date": "Data", "order_id": "Pedido", "customer": "Cliente", "channel": "Canal", "sku": "SKU", "title": "Título", "quantity": "Quantidade", "unit_price": "Preço unitário", "unit_cost": "Custo unitário", "status": "Status"}
        )
        st.dataframe(sales_table.head(100), width="stretch", hide_index=True)
    if not inventory_df.empty:
        st.caption(f"Inventários armazenados: {len(inventory_df)} linhas.")
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
    page_header("Análise de concentração", "Curva ABC", "Classifique títulos ou clientes pelo peso nas vendas e veja a participação acumulada.")
    start, end = render_period_filter(start, end)
    sales = calculate_sales(sales_df, start, end)
    if sales is None or sales["rows"].empty:
        st.info("Não há vendas concluídas no período. Importe vendas em Vendas e estoque para calcular a curva.")
        return

    controls = st.columns(4)
    with controls[0]:
        dimension = st.selectbox("Analisar", ["Títulos", "Clientes"], key="abc_dimension")
    if dimension == "Títulos":
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
    if dimension == "Títulos":
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
    result.columns = ["Posição", "Código", "Título" if dimension == "Títulos" else "Cliente", measure, "Participação %", "Acumulado %", "Classe"]
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
        placeholder="https://servidor-da-livraria/Horus/api/TServerB2B/",
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
                preview_frame.drop(columns=["valor_liquido_horus"]).to_csv(index=False).encode("utf-8-sig"),
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
            "Gerencie quem pode consultar e operar os dados desta livraria.",
        )
    if not can_manage_team:
        st.error("Somente um administrador/suporte desta empresa pode gerenciar os acessos.")
        return

    notice_key = f"team_invite_notice_{company_id}"
    notice = st.session_state.get(notice_key)
    if notice:
        level, message = notice
        if st.button("Fechar mensagem", key=f"dismiss_team_notice_{company_id}"):
            st.session_state.pop(notice_key, None)
        else:
            if level == "success":
                st.success(message)
            else:
                st.info(message)

    st.caption(
        "Administrador/suporte e gestor podem operar os dados. Colaborador tem acesso somente para consulta. "
        "Convites são vinculados ao e-mail usado no login Google; o app não envia e-mails automaticamente."
    )
    members = company_members(company_id)
    member_table = pd.DataFrame([
        {"Nome": member["name"], "E-mail": member["email"], "Perfil": ROLE_LABELS.get(member["role"], member["role"])}
        for member in members
    ])
    st.subheader("Pessoas com acesso")
    st.dataframe(member_table, width="stretch", hide_index=True)

    with st.container(border=True):
        st.subheader("Adicionar pessoa")
        with st.form(f"invite_company_member_{company_id}"):
            invite_email = st.text_input("E-mail da conta Google", placeholder="pessoa@gmail.com")
            invite_role = st.selectbox(
                "Perfil",
                COMPANY_ROLES,
                format_func=lambda value: ROLE_LABELS[value],
            )
            invite_submitted = st.form_submit_button("Adicionar ou convidar", type="primary")
        if invite_submitted:
            try:
                result = invite_company_member(
                    company_id, invite_email, invite_role, identity_issuer, identity_subject
                )
                if result == "already_member":
                    st.session_state[notice_key] = ("info", "Essa pessoa já tem acesso à empresa.")
                elif result == "added":
                    st.session_state[notice_key] = ("success", "Pessoa adicionada à equipe.")
                else:
                    st.session_state[notice_key] = (
                        "success",
                        "Convite registrado. A pessoa receberá acesso quando entrar com o Google usando esse e-mail.",
                    )
                st.session_state["account_team_expanded"] = True
                st.rerun()
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))

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
            if st.button("Remover acesso", key=f"remove_member_{company_id}"):
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
        with st.expander("＋ Novo lançamento", expanded=df.empty):
            kind_col, status_col = st.columns(2)
            kind = kind_col.selectbox("Tipo", ["Receita", "Despesa"], key=f"new_transaction_kind_{company_id}")
            status = status_col.selectbox("Status", ["Pago", "Pendente"], key=f"new_transaction_status_{company_id}")
            with st.form("new_transaction", clear_on_submit=True):
                dt = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
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
                            "notes": notes.strip(),
                        }, company_id, identity_issuer, identity_subject)
                        st.success("Lançamento salvo.")
                        st.rerun()
    else:
        st.info("Seu perfil permite consultar os lançamentos, mas não cadastrar ou alterar registros.")

    if df.empty:
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
    view["Tipo"] = view["kind"]
    view["Categoria"] = view["category"]
    view["Descrição"] = view["description"]
    view["Status"] = view["status"]
    view["Valor"] = view["amount"].map(money)
    st.dataframe(view[["Data","Tipo","Categoria","Descrição","Status","Valor"]], width="stretch", hide_index=True)

    if can_edit:
        with st.expander("Ações sobre lançamento"):
            ids = filtered["id"].tolist()
            if ids:
                selected = st.selectbox("ID do lançamento", ids, format_func=lambda x: f"#{x} · {filtered.loc[filtered['id']==x, 'description'].iloc[0]}")
                current_row = filtered.loc[filtered["id"] == selected].iloc[0]
                pending_due = None
                if current_row["status"] == "Pago":
                    previous_due = current_row["due_date"]
                    pending_due = st.date_input(
                        "Vencimento ao marcar como pendente",
                        value=previous_due.date() if pd.notna(previous_due) else date.today(),
                        format="DD/MM/YYYY",
                        key=f"pending_due_{company_id}_{selected}",
                    )
                c1, c2 = st.columns(2)
                if c1.button("Alternar status", width="stretch"):
                    update_status(selected, "Pendente" if current_row["status"] == "Pago" else "Pago", company_id, identity_issuer, identity_subject,
                                  due_date=pending_due.isoformat() if pending_due is not None else None)
                    st.rerun()
                if c2.button("Excluir", type="secondary", width="stretch"):
                    delete_transaction(selected, company_id, identity_issuer, identity_subject)
                    st.rerun()


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
    if df.empty:
        st.info("Sem dados para montar o fluxo de caixa.")
        return
    cf = df.copy()
    cf["signed"] = cf["amount"].where(cf["kind"] == "Receita", -cf["amount"])
    cf["cash_date"] = cf["date"].where(cf["status"] == "Pago", cf["due_date"])
    cf = cf.dropna(subset=["cash_date"]).sort_values("cash_date")
    cf = cf[cf["cash_date"].dt.date.between(start, end)]
    if cf.empty:
        st.info("Não há entradas ou saídas no período selecionado.")
        return
    daily = cf.groupby("cash_date", as_index=False)["signed"].sum()
    daily["saldo_acumulado"] = daily["signed"].cumsum()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["cash_date"], y=daily["saldo_acumulado"], mode="lines+markers", name="Saldo acumulado", fill="tozeroy"))
    fig.update_layout(
        height=420,
        margin=dict(l=8, r=8, t=18, b=8),
        xaxis=dict(type="date", title="Data", tickformat="%d/%m/%Y", hoverformat="%d/%m/%Y"),
        yaxis_title="Saldo projetado",
    )
    ui_module.render_plotly(fig)
    low = daily.loc[daily["saldo_acumulado"].idxmin()]
    st.caption(f"Menor saldo projetado: {money(low['saldo_acumulado'])} em {low['cash_date']:%d/%m/%Y}.")


def budget_page(df: pd.DataFrame) -> None:
    page_header("Planejamento", "Orçamento", "Defina limites por categoria e compare o planejado com o realizado.")
    month = st.selectbox("Mês de referência", pd.period_range("2026-01", "2027-12", freq="M").astype(str), index=8)
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
    st.warning(
        "Ao gerar a análise, o Skopos envia ao Google Gemini indicadores agregados da empresa e do período, incluindo até cinco títulos de livros. "
        "Nomes de clientes, e-mails, descrições de lançamentos e identificadores de empresa não são enviados. "
        "A política do Google difere por nível: no gratuito, solicitações e respostas podem ser usadas para melhorar produtos e revistas por pessoas; no pago, não são usadas para esse fim. Evite enviar informações sigilosas pelo nível gratuito."
    )

    model = get_app_setting("gemini_model", company_id, "gemini-3.8-flash")
    api_key = configured_gemini_key()

    summary = build_insight_payload(df, sales_df, inventory_df, start, end)
    with st.expander("Ver resumo que será enviado", expanded=False):
        st.json(summary)

    consent = st.checkbox(
        "Autorizo enviar esses indicadores agregados ao Gemini para gerar a análise. Entendo a diferença entre o uso gratuito e o pago.",
        key=f"gemini_data_consent_{company_id}",
    )
    can_generate = bool(api_key and model.strip() and consent)
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
can_edit = membership_role in {"administrator", "manager"}
can_manage_team = membership_role == "administrator"
collapsed_nav_rail(membership_role)
account_menu()
if accepted_invitations:
    st.success(f"Acesso concedido a {accepted_invitations} empresa(s) pelo convite recebido no Google.")
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
        st.error("Somente o perfil Admin pode acessar as integrações da empresa.")
elif page == "Configuração de IA":
    if membership_role == "administrator":
        ai_configuration_page()
    else:
        st.error("Somente o perfil Admin pode alterar a configuração de IA da empresa.")
elif page == "Equipe":
    team_page()
elif page == "Conta":
    account_settings_page()

with st.sidebar:
    st.divider()
    if can_edit and st.button("Carregar dados de demonstração", width="stretch"):
        seed_demo(company_id, identity_issuer, identity_subject)
        st.rerun()
