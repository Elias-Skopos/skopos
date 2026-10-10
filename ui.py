from html import escape
import re

import streamlit as st

CHART_COLORS = ["#625fe9", "#9b7be8", "#4d8df5", "#36a3c7", "#177245", "#e4a11b", "#8b93a1"]


def inject_css(dark_mode: bool = False) -> None:
    st.html(
        """
        <style>
        :root {
          color-scheme: only light;
          --surface: #ffffff;
          --app-bg: #f8f8ff;
          --surface-2: #f2f3ff;
          --border: #e4e5f5;
          --text: #17191f;
          --muted: #68707f;
          --positive: #177245;
          --negative: #625fe9;
          --accent: #625fe9;
          --nav-group-bg: #eef0fb;
          --nav-group-text: #343b50;
          --nav-group-border: #cbd0e6;
        }
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            background: var(--app-bg); color: var(--text); color-scheme: light;
        }
        [data-testid="stSidebar"] { background: #f5f5ff; color: var(--text); }
        h1, h2, h3, h4, label, [data-testid="stWidgetLabel"] { color: var(--text); }
        /* Controles da hospedagem são tratados apenas em app_chrome.css. */
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapseButton"] {
            visibility: visible !important;
            pointer-events: auto !important;
        }
        .block-container { max-width: 1440px; padding-top: 4.5rem; padding-bottom: 3rem; }
        /* Barras fixas não devem deixar linhas vazias antes do conteúdo. */
        [data-testid="stLayoutWrapper"]:has(> .st-key-app_topbar),
        [data-testid="stLayoutWrapper"]:has(> .st-key-collapsed_nav_rail),
        [data-testid="stLayoutWrapper"]:has(> .st-key-collapsed_nav_rail_expanded) {
            position: absolute; width: 0; height: 0;
        }
        .st-key-app_topbar {
            position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
            box-sizing: border-box; width: 100%;
            background: var(--app-bg);
            padding: .35rem 1.5rem .55rem; margin: 0;
            border-bottom: 1px solid var(--border); box-shadow: 0 2px 8px rgba(23,25,31,.04);
            pointer-events: none;
        }
        .st-key-app_topbar button,
        .st-key-app_topbar [data-testid^="stBaseButton-"],
        .st-key-app_topbar [data-testid*="Popover"] { pointer-events: auto !important; }
        .st-key-toggle_dark_mode_topbar_light button,
        .st-key-toggle_dark_mode_topbar_dark button {
            position: relative; width: 4.5rem; min-width: 4.5rem; height: 2.4rem;
            min-height: 2.4rem; padding: 0; overflow: hidden; border-radius: 999px !important;
            background: #625fe9 !important; border: 1px solid #514ed0 !important;
        }
        .st-key-toggle_dark_mode_topbar_light button > div,
        .st-key-toggle_dark_mode_topbar_dark button > div {
            position: static !important; display: flex; align-items: center;
            justify-content: flex-end; width: 100%; height: 100%; padding-right: .55rem;
        }
        .st-key-toggle_dark_mode_topbar_light button p,
        .st-key-toggle_dark_mode_topbar_dark button p {
            position: relative; z-index: 2; margin: 0; color: #fff !important;
            font-size: 1.05rem; line-height: 1; white-space: nowrap;
        }
        .st-key-toggle_dark_mode_topbar_light button::before,
        .st-key-toggle_dark_mode_topbar_dark button::before {
            content: "☀"; position: absolute; left: .55rem; top: 50%; z-index: 2;
            transform: translateY(-53%); color: #fff; font-size: 1.05rem; line-height: 1;
        }
        .st-key-toggle_dark_mode_topbar_light button::after,
        .st-key-toggle_dark_mode_topbar_dark button::after {
            content: ""; position: absolute; top: .18rem; z-index: 3;
            width: 1.95rem; height: 1.95rem; border-radius: 50%;
            background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.22);
            transition: left .18s ease, right .18s ease;
        }
        .st-key-toggle_dark_mode_topbar_light button::after { right: .18rem; }
        .st-key-toggle_dark_mode_topbar_dark button::after { left: .18rem; }
        [data-testid="stSidebar"] { border-right: 1px solid var(--border); }
        [data-testid="stSidebar"] > div:first-child { padding-top: .75rem; }
        [data-testid="stTooltipHoverTarget"] {
            background: transparent !important; border: 0 !important;
            outline: 0 !important; box-shadow: none !important;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-app_topbar {
            background: #f8f8ff;
        }
        .st-key-collapsed_nav_rail,
        .st-key-collapsed_nav_rail_expanded { display: none !important; }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail {
            display: flex !important; flex-direction: column; align-items: center; gap: .3rem;
            position: fixed !important; left: .4rem; top: 4.5rem; bottom: .75rem;
            width: 3.2rem; max-height: calc(100vh - 5.25rem); overflow-y: auto;
            z-index: 1001; padding: .4rem; box-sizing: border-box;
            background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
            box-shadow: 0 4px 18px rgba(20,25,40,.12);
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail [data-testid="stButton"] {
            width: 100%; margin: 0;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail button {
            width: 100%; height: 2.45rem; min-height: 2.45rem; padding: 0;
            justify-content: center; border-radius: 10px;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail button > div {
            width: 100%; justify-content: center;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail button p {
            display: none;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded {
            display: flex !important; flex-direction: column; align-items: stretch; gap: .25rem;
            position: fixed !important; left: .4rem; top: 4.5rem; bottom: .75rem;
            width: 15rem; max-height: calc(100vh - 5.25rem); overflow-y: auto;
            z-index: 1001; padding: .5rem; box-sizing: border-box;
            background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
            box-shadow: 0 4px 18px rgba(20,25,40,.12);
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded [data-testid="stButton"] {
            width: 100%; margin: 0;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded button {
            width: 100%; min-height: 2.45rem; padding: .35rem .55rem;
            justify-content: flex-start; border-radius: 10px;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded button > div {
            width: 100%; justify-content: flex-start;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded .st-key-collapsed_nav_home button {
            font-weight: 750; background: var(--surface-2); border-color: var(--border);
        }
        .collapsed-rail-group-separator {
            height: 1px; margin: .25rem 0; background: var(--border);
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded [class*="st-key-collapsed_nav_group_"] button {
            font-weight: 750; background: var(--nav-group-bg) !important;
            color: var(--nav-group-text) !important; border: 1px solid var(--nav-group-border) !important;
            border-left: 4px solid var(--accent) !important; margin-top: .1rem;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded [class*="st-key-collapsed_nav_submenu_"] {
            gap: .2rem; margin: .05rem 0 .3rem .65rem; padding-left: .35rem;
            border-left: 2px solid var(--border);
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded [class*="st-key-collapsed_nav_submenu_"] [data-testid="stBaseButton-secondary"] {
            background: transparent !important; border-color: transparent !important;
            color: var(--text) !important; font-weight: 500;
        }
        body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded [class*="st-key-collapsed_nav_submenu_"] [data-testid="stBaseButton-secondary"]:hover {
            background: var(--surface-2) !important;
        }
        .sidebar-brand { font-size: 1.75rem; font-weight: 700; line-height: 1.15; margin: 0 0 1rem; }
        .sidebar-brand span { display: inline-block; margin: .2rem 0 0; font-size: .72rem; font-weight: 400; font-style: italic; color: var(--muted); }
        [data-testid="stSidebar"] .st-key-sidebar_logo_home button {
            width: 100%; height: auto; min-height: 0; padding: 0 !important;
            background: transparent !important; border: 0 !important;
            border-radius: 0; box-shadow: none;
        }
        .st-key-sidebar_logo_home button > div,
        .st-key-sidebar_logo_home [data-testid="stMarkdownContainer"],
        .st-key-sidebar_logo_home button p {
            width: 100%; margin: 0;
        }
        .st-key-sidebar_logo_home button img {
            display: block; width: 100%; height: auto !important; max-height: none !important;
        }
        [data-testid="stSidebar"] [data-testid^="stBaseButton-"] {
            box-sizing: border-box; width: 100%; justify-content: flex-start; text-align: left;
            padding: .62rem .8rem; border-radius: 9px; font-weight: 550;
            transition: background-color .15s ease, border-color .15s ease, color .15s ease;
        }
        [data-testid="stSidebar"] [data-testid^="stBaseButton-"] > div {
            justify-content: flex-start !important; text-align: left !important; width: 100%;
        }
        [data-testid="stSidebar"] [data-testid^="stBaseButton-"] p {
            text-align: left !important; width: 100%;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            justify-content: flex-start !important; text-align: left !important;
        }
        [data-testid="stSidebar"] .st-key-sidebar_home_brand [data-testid^="stBaseButton-"] {
            width: auto; padding: 0; border: 0; color: var(--text); font-size: 2.4rem;
            font-weight: 800; line-height: 1.05; text-align: left;
        }
        [data-testid="stSidebar"] .st-key-sidebar_home_brand button {
            width: auto; padding: 0; border: 0; color: var(--text);
            font-size: 2.4rem !important; font-weight: 800 !important; line-height: 1.05;
            text-align: left;
        }
        [data-testid="stSidebar"] .st-key-sidebar_home_brand button p,
        [data-testid="stSidebar"] .st-key-sidebar_home_brand button span,
        [data-testid="stSidebar"] .st-key-sidebar_home_brand button div {
            font-size: inherit !important; font-weight: inherit !important; line-height: inherit;
        }
        [data-testid="stSidebar"] .st-key-sidebar_home_brand button p { margin: 0; }
        [data-testid="stSidebar"] .st-key-sidebar_home_brand [data-testid^="stBaseButton-"] > div {
            width: auto;
        }
        [data-testid="stSidebar"] .st-key-sidebar_home_brand [data-testid^="stBaseButton-"]:hover {
            color: var(--accent); background: transparent;
        }
        [data-testid="stSidebar"] .st-key-sidebar_home_brand [data-testid="stCaption"] {
            margin-top: -.45rem;
        }
        [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
            background: transparent; border-color: transparent; color: #414652;
        }
        [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
            background: #f0efff; border-color: transparent; color: #3936a5;
        }
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
            background: #e9e8ff; border: 0; border-left: 3px solid var(--accent);
            color: #3936a5; font-weight: 650;
        }
        [data-testid="stSidebar"] [data-testid^="stBaseButton-"]:focus-visible {
            outline: 2px solid var(--accent); outline-offset: 2px;
        }
        h1, h2, h3 { letter-spacing: -0.025em; }
        .eyebrow { color: var(--accent); font-size: 1.56rem; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }
        .subtle { color: var(--muted); font-size: .93rem; }
        .kpi {
            background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
            padding: 18px 18px 16px; min-height: 126px;
            box-shadow: 0 1px 2px rgba(0,0,0,.03);
        }
        .kpi-label { color: var(--muted); font-size: .82rem; font-weight: 600; margin-bottom: 10px; }
        .kpi-heading { display:flex; align-items:center; gap:7px; margin-bottom:10px; }
        .kpi-heading .kpi-label { margin:0; }
        .kpi-info {
            display:inline-flex; align-items:center; justify-content:center; flex:0 0 auto;
            width:17px; height:17px; border:1px solid #a9a8d8; border-radius:50%;
            color:#5c59bd; font-size:11px; font-weight:700; line-height:1; cursor:help;
        }
        .kpi-info:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
        .kpi-value { color: var(--text); font-size: 1.72rem; font-weight: 760; letter-spacing: -.03em; }
        .kpi-foot { color: var(--muted); font-size: .78rem; margin-top: 8px; }
        .section-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 18px; }
        .pill { display:inline-block; border-radius:999px; padding:4px 9px; font-size:.74rem; font-weight:700; background:#efeeff; color:#4946bd; }
        div[data-testid="stMetric"] { background:white; border:1px solid var(--border); padding:14px; border-radius:14px; }
        div[data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:14px; overflow:hidden; }
        .stButton > button, .stDownloadButton > button { border-radius: 10px; font-weight: 650; }
        [data-testid^="stBaseButton-"], [data-testid="stPopoverButton"] {
            background: var(--surface) !important;
            color: var(--text) !important;
            border-color: var(--border) !important;
            -webkit-appearance: none;
            appearance: none;
        }
        [data-testid^="stBaseButton-"] p, [data-testid^="stBaseButton-"] span,
        [data-testid="stPopoverButton"] p, [data-testid="stPopoverButton"] span {
            color: inherit !important;
            -webkit-text-fill-color: currentColor;
        }
        .stApp { --primary-color: #625fe9; }
        .stButton > button:hover, .stDownloadButton > button:hover,
        [data-testid="stPopoverButton"]:hover {
            color: #514ed5 !important; border-color: #625fe9 !important;
        }
        .stButton > button:focus-visible, .stDownloadButton > button:focus-visible {
            outline: 2px solid #625fe9 !important; border-color: #625fe9 !important;
        }
        button[kind="primary"], button[kind="primaryFormSubmit"],
        [data-testid="stBaseButton-primary"],
        [data-testid="stBaseButton-primaryFormSubmit"] {
            background: #625fe9 !important; color: #fff !important; border-color: #625fe9 !important;
        }
        button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {
            background: #514ed5 !important; color: #fff !important;
        }
        @media (max-width: 700px) {
            .st-key-app_topbar { left: 0; padding: .35rem .5rem .35rem 3.3rem; gap: .35rem; }
            .st-key-app_topbar > div { min-width: 0; }
            .block-container { padding: 4.25rem 1rem 2rem; }
            .st-key-app_topbar button { min-height: 44px; padding: .4rem .5rem; }
            .st-key-top_home_button button p,
            .st-key-toggle_overview_values button p,
            .st-key-app_topbar [data-testid="stPopoverButton"] p {
                position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
                overflow: hidden; clip-path: inset(50%); white-space: nowrap;
            }
            .st-key-download_desktop_shortcut { display: none !important; }
            body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail,
            body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-collapsed_nav_rail_expanded {
                display: none !important;
            }
            .kpi { padding: 14px; min-height: 110px; }
            .kpi-value { font-size: 1.5rem; overflow-wrap: anywhere; }
            [data-testid="stCaptionContainer"] p { white-space: normal; overflow-wrap: anywhere; }
            .eyebrow { font-size: 1rem; }
            h1 { font-size: 1.9rem; }
            [data-testid="stTabs"] [role="tablist"] { overflow-x: auto; }
            [data-testid="stFileUploader"] section { flex-wrap: wrap; }
            [data-testid="stSidebar"] { max-width: calc(100vw - 3rem); }
            .st-key-toggle_dark_mode_topbar_light button, .st-key-toggle_dark_mode_topbar_dark button {
                width: 4.1rem; min-width: 4.1rem;
            }
        }
        </style>
        """,
    )
    if dark_mode:
        st.html(
            """
            <style>
            :root {
              color-scheme: only dark;
              --surface: #1b2432;
              --app-bg: #111722;
              --surface-2: #242e3e;
              --border: #354154;
              --text: #edf1f7;
              --muted: #a8b2c1;
              --accent: #8b87ff;
              --negative: #bcb9ff;
              --skopos-error-bg: #292b52;
              --skopos-error-text: #d7d5ff;
              --nav-group-bg: #242e3e;
              --nav-group-text: #edf1f7;
              --nav-group-border: #46536a;
            }
            .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
              background: #111722; color: #edf1f7; color-scheme: dark;
            }
            [data-testid="stSidebar"] { background: #151d2a; border-color: #303b4d; }
            .st-key-app_topbar {
              background: #111722 !important;
              border-color: #303b4d;
            }
            body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-app_topbar {
              background: #111722 !important;
            }
            h1, h2, h3, h4, p, label, [data-testid="stWidgetLabel"],
            [data-testid="stMarkdownContainer"] { color: #edf1f7; }
            .subtle, .kpi-label, .kpi-foot, [data-testid="stCaption"] { color: #a8b2c1; }
            .kpi, .section-card, div[data-testid="stMetric"],
            [data-testid="stVerticalBlockBorderWrapper"] {
              background: #1b2432; border-color: #354154; color: #edf1f7;
            }
            [data-testid="stDataFrame"] { border-color: #354154; }
            .stButton > button, .stDownloadButton > button {
              background: #202b3a; color: #edf1f7; border-color: #3a465a;
            }
            .st-key-app_topbar button,
            .st-key-app_topbar [data-testid*="Popover"] {
              background: #202b3a !important; color: #edf1f7 !important;
              border-color: #46536a !important;
            }
            .st-key-app_topbar button *,
            .st-key-app_topbar [data-testid*="Popover"] * { color: #edf1f7 !important; }
            .st-key-app_topbar .st-key-toggle_dark_mode_topbar_dark button {
              background: #625fe9 !important; border-color: #514ed0 !important;
            }
            .stButton > button:hover, .stDownloadButton > button:hover {
              background: #2a3749; color: #fff; border-color: #7772ef;
            }
            [data-testid="stBaseButton-primary"] {
              background: #625fe9 !important; color: #fff !important; border-color: #625fe9 !important;
            }
            [data-testid="stBaseButton-secondary"] {
              background: #202b3a !important; color: #d5dbea !important; border-color: #3a465a !important;
            }
            [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
              background: transparent !important; border-color: transparent !important;
            }
            [data-testid="stBaseButton-secondary"]:hover {
              background: #273247 !important; color: #fff !important;
            }
            [data-baseweb="input"] > div, [data-baseweb="select"] > div,
            [data-baseweb="textarea"], input, textarea {
              background: #1b2432 !important; color: #edf1f7 !important; border-color: #46536a !important;
            }
            [data-baseweb="input"] *, [data-baseweb="select"] *,
            input::placeholder, textarea::placeholder {
              color: #edf1f7 !important; opacity: 1 !important;
            }
            [data-baseweb="popover"] { background: #1b2432; color: #edf1f7; }
            [role="tooltip"], [data-baseweb="tooltip"], [data-testid="stTooltipContent"] {
              background: #202b3a !important; color: #edf1f7 !important;
              border: 0 !important; outline: 0 !important; box-shadow: none !important;
            }
            [role="tooltip"] *, [data-baseweb="tooltip"] *, [data-testid="stTooltipContent"] * {
              color: #edf1f7 !important; opacity: 1 !important;
            }
            [data-testid="stExpander"] details, [data-testid="stExpander"] summary {
              color: #edf1f7 !important; background: #151d2a !important;
            }
            [data-testid="stExpander"], [data-testid="stExpander"] details {
              background: #151d2a !important; border-color: #354154 !important;
            }
            [data-testid="stExpander"] summary *,
            [data-testid="stExpander"] summary svg { color: #edf1f7 !important; fill: #edf1f7 !important; }
            [role="listbox"], [role="option"], [data-baseweb="menu"],
            [data-baseweb="popover"] {
              background: #1b2432 !important; color: #edf1f7 !important;
            }
            [role="option"]:hover, [role="option"][aria-selected="true"] { background: #2a3749 !important; }
            [role="option"] *, [data-baseweb="menu"] * { color: #edf1f7 !important; }
            .sidebar-brand, [data-testid="stSidebar"] p { color: #edf1f7; }
            [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
              background: #292b52 !important; color: #d7d5ff !important;
              border-left-color: #8b87ff !important;
            }
            [data-testid="stPopoverButton"] {
              background: #202b3a !important; color: #edf1f7 !important; border-color: #46536a !important;
            }
            [data-testid="stVerticalBlock"] { border-color: #354154; }
            .st-key-sidebar_logo img { filter: brightness(0) invert(1); }
            </style>
            """,
        )


def money(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render_plotly(fig) -> None:
    dark = st.session_state.get("dark_mode", False)
    background = "#111722" if dark else "#f8f8ff"
    text = "#edf1f7" if dark else "#17191f"
    grid = "#354154" if dark else "#e4e5f5"
    fig.update_layout(template="plotly_dark" if dark else "plotly_white",
                      colorway=CHART_COLORS,
                      paper_bgcolor=background, plot_bgcolor=background,
                      font_color=text, hoverlabel=dict(bgcolor=background, font_color=text))
    fig.update_xaxes(gridcolor=grid, zerolinecolor=grid)
    fig.update_yaxes(gridcolor=grid, zerolinecolor=grid)
    st.plotly_chart(fig, theme=None, width="stretch")


def kpi(
    label: str,
    value: str,
    foot: str = "",
    info: str | None = None,
    hide_values: bool = False,
) -> None:
    if hide_values:
        if re.search(r"\d|R\$|%|×", value):
            value = "••••••"
        foot = re.sub(r"R\$\s*[\d.,]+|(?<![\w])\d+(?:[.,/]\d+)*(?:\s?[×x%])?", "••••", foot)
    info_icon = (
        f'<span class="kpi-info" tabindex="0" title="{escape(info, quote=True)}" '
        f'aria-label="Sobre {escape(label, quote=True)}">i</span>'
        if info
        else ""
    )
    st.markdown(
        f"""
        <div class="kpi">
          <div class="kpi-heading"><div class="kpi-label">{escape(label)}</div>{info_icon}</div>
          <div class="kpi-value">{escape(value)}</div>
          <div class="kpi-foot">{escape(foot)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="subtle">{subtitle}</div>', unsafe_allow_html=True)
