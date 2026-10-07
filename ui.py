from html import escape
import re

import streamlit as st


def inject_css(dark_mode: bool = False) -> None:
    st.markdown(
        """
        <style>
        :root {
          --surface: #ffffff;
          --surface-2: #f2f3ff;
          --border: #e4e5f5;
          --text: #17191f;
          --muted: #68707f;
          --positive: #177245;
          --negative: #b3261e;
          --accent: #625fe9;
          --nav-group-bg: #eef0fb;
          --nav-group-text: #343b50;
          --nav-group-border: #cbd0e6;
        }
        .stApp { background: #f8f8ff; }
        /* Remove os controles da hospedagem que cobrem a barra do Skopos. */
        [data-testid="stHeader"] {
            background: transparent !important;
            height: 0 !important;
            pointer-events: none !important;
        }
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stAppDeployButton"],
        [data-testid="stStatusWidget"],
        [data-testid="stCloudViewerBadge"],
        .viewerBadge_container__r5tak,
        .viewerBadge_link__qRIco,
        #MainMenu, footer {
            display: none !important;
        }
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapseButton"] {
            pointer-events: auto !important;
        }
        .block-container { max-width: 1440px; padding-top: 5.5rem; padding-bottom: 3rem; }
        .st-key-app_topbar {
            position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
            box-sizing: border-box; width: 100%;
            background: linear-gradient(to right, transparent 21rem, #f8f8ff 21rem);
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
        [data-testid="stSidebarCollapseButton"] svg,
        [data-testid="stExpandSidebarButton"] svg { display: none !important; }
        [data-testid="stSidebarCollapseButton"] button::after,
        [data-testid="stExpandSidebarButton"]::after {
            content: ""; display: block; flex: 0 0 18px; width: 18px; height: 18px;
            box-sizing: border-box; border: 1.7px solid currentColor; border-radius: 3px;
            background: linear-gradient(to right, currentColor 0 1.5px, transparent 1.5px);
            background-size: 5px 100%; background-position: 4px 0; background-repeat: no-repeat;
        }
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
        @media (max-width: 700px) {
            .st-key-app_topbar { left: 0; padding: .25rem .45rem .45rem; }
            .block-container { padding-top: 5rem; }
            .st-key-app_topbar [data-testid="stBaseButton"] { padding-left: .35rem; padding-right: .35rem; }
            .st-key-toggle_dark_mode_topbar_light button, .st-key-toggle_dark_mode_topbar_dark button {
                width: 4.1rem; min-width: 4.1rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if dark_mode:
        st.markdown(
            """
            <style>
            :root {
              --surface: #1b2432;
              --surface-2: #242e3e;
              --border: #354154;
              --text: #edf1f7;
              --muted: #a8b2c1;
              --accent: #8b87ff;
              --nav-group-bg: #242e3e;
              --nav-group-text: #edf1f7;
              --nav-group-border: #46536a;
            }
            .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
              background: #111722; color: #edf1f7;
            }
            [data-testid="stSidebar"] { background: #151d2a; border-color: #303b4d; }
            .st-key-app_topbar {
              background: linear-gradient(to right, transparent 21rem, #111722 21rem) !important;
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
              background: transparent !important; color: #d5dbea !important; border-color: transparent !important;
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
            </style>
            """,
            unsafe_allow_html=True,
        )


def money(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
