"""Public download + demo entry point. No real database, account or credentials."""
import json
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

from demo_ui import render_demo
from welcome_ui import welcome_layout

ROOT = Path(__file__).resolve().parent


def change_view(view):
    st.session_state["public_view"] = view
    if view == "home":
        st.query_params.clear()
    else:
        st.query_params["view"] = view


def release_details():
    try:
        release = json.loads((ROOT / "public_release.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    url = urlparse(release.get("download_url", ""))
    if (not release.get("published") or url.scheme != "https" or not url.netloc
            or url.username or url.password or not release.get("version")
            or not release.get("sha256") or len(release["sha256"]) != 64):
        return None
    return release


def render_public():
    st.set_page_config(page_title="Skopos · Gestão da sua empresa", page_icon=str(ROOT / "assets/logo_novo.png"), layout="wide")
    view = st.session_state.get("public_view", st.query_params.get("view", "home"))
    if view == "demo":
        render_demo(lambda: change_view("home"))
    else:
        with welcome_layout():
            st.title("Conheça o Skopos")
            st.markdown('<div class="login-description">Os números da sua empresa, organizados para você decidir. '
                        'Instale no seu computador ou explore uma demonstração sem cadastro.</div>', unsafe_allow_html=True)
            release = release_details()
            if release:
                st.link_button("Baixar para Windows", release["download_url"], type="primary", icon=":material/download:", width="stretch")
                st.caption(f"Windows 10/11 · 64 bits · Versão {release['version']}")
            else:
                st.button("Baixar para Windows", disabled=True, type="primary", icon=":material/download:", width="stretch")
                st.caption("O instalador está em preparação. O download será liberado após a validação da versão.")
            st.markdown('<div class="login-divider">ou conheça antes de instalar</div>', unsafe_allow_html=True)
            st.button("Explorar demonstração", on_click=change_view, args=("demo",), icon=":material/play_circle:", key="enter_public_demo", width="stretch")
            st.markdown('<div class="login-footnote">Sem conta e sem login. Todos os dados da demonstração são fictícios.</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    render_public()
