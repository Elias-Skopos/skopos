"""The public landing page shares the actual login stylesheet and brand assets."""
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent


@contextmanager
def welcome_layout():
    st.html(ROOT / "welcome.css")
    with st.container(key="login_layout"):
        left, right = st.columns([0.86, 1.14], gap=None)
    with left.container(key="login_left_panel"):
        with st.container(key="login_logo_image"):
            st.image(str(ROOT / "assets/logo_login.svg"), width=420)
        yield
    with right.container(key="login_right_panel"):
        st.markdown('<div class="login-hero-eyebrow">Visão clara, boas decisões</div>', unsafe_allow_html=True)
        st.markdown('<h2>Sua empresa em equilíbrio.</h2>', unsafe_allow_html=True)
        st.markdown('<div class="login-hero-copy">Acompanhe faturamento, caixa e estoque em um só lugar, '
                    'com os números que ajudam você a seguir em frente.</div>', unsafe_allow_html=True)
        st.image(str(ROOT / "assets/login_illustration.svg"), width="stretch")
        st.markdown('<div class="login-hero-caption">Os números da sua empresa, sempre à vista.</div>', unsafe_allow_html=True)

