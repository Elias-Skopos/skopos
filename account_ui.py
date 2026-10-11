"""Workspace selection and personal profile, independent of financial screens."""
import smtplib

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

import db
from invitation_email import send_invitation

ROLE_LABELS = {"administrator": "Proprietário", "collaborator": "Colaborador", "demo": "Demonstração"}


def clear_company_session() -> None:
    for key in list(st.session_state):
        if key.startswith(("horus_", "gemini_", "openai_")):
            del st.session_state[key]
    st.session_state.pop("collapsed_rail_open_group", None)


def activate_company(company_id: int, is_demo: bool = False, home: bool = True) -> None:
    clear_company_session()
    st.session_state["active_company_id"] = company_id
    st.session_state["demo_active"] = is_demo
    st.session_state["workspace_picker"] = False
    if home:
        st.session_state["active_page"] = "Home"
        st.query_params["page"] = "Home"
    for key in ("global_period", "period_start_input", "period_end_input", "period_picker"):
        st.session_state.pop(key, None)


def open_workspace_picker() -> None:
    clear_company_session()
    st.session_state["workspace_picker"] = True
    st.session_state["active_page"] = "Home"
    st.query_params["page"] = "Home"


def invite_person(company_id: int, company_name: str, email: str, role: str, issuer: str, subject: str) -> tuple[str, str]:
    result = db.invite_company_member(company_id, email, role, issuer, subject)
    if result == "already_member":
        return "info", "Essa pessoa já participa da empresa. Você pode editar o perfil na equipe."
    try:
        config = dict(st.secrets.get("email", {}))
    except StreamlitSecretNotFoundError:
        config = {}
    try:
        sent = send_invitation(email.strip().casefold(), company_name, ROLE_LABELS[role], config)
    except (OSError, smtplib.SMTPException, ValueError):
        return "warning", "Convite registrado, mas o e-mail não foi enviado. A pessoa pode aceitar ao entrar no Skopos com esse e-mail."
    if sent:
        return "success", "Convite registrado e enviado por e-mail. A pessoa deverá aceitá-lo para receber acesso."
    return "info", "Convite registrado. Compartilhe o endereço do Skopos com a pessoa; ao entrar com esse e-mail, ela poderá aceitar. O envio por e-mail ainda não está configurado."


def workspace_picker(companies: list[dict], issuer: str, subject: str, logout) -> None:
    st.title("Bem-vindo ao Skopos")
    st.write("Escolha uma empresa, crie a sua ou explore a demonstração.")
    st.caption(f"Conectado como {st.user.get('email', '')}")
    notice = st.session_state.pop("workspace_notice", None)
    if notice:
        st.success(notice)
    invitations = db.invitations_for_user(issuer, subject)
    if invitations:
        st.subheader("Convites para você")
        for invitation in invitations:
            iid = int(invitation["id"])
            with st.container(border=True):
                st.subheader(invitation["name"])
                st.caption(f"{invitation['segment']} · {ROLE_LABELS[invitation['role']]} · Válido por sete dias após o envio")
                with st.container(horizontal=True):
                    accepted = st.button("Aceitar convite", key=f"accept_invite_{iid}", type="primary")
                    declined = st.button("Recusar", key=f"decline_invite_{iid}")
                if accepted or declined:
                    try:
                        cid = db.respond_company_invitation(iid, issuer, subject, accepted)
                        if accepted:
                            activate_company(cid)
                        else:
                            st.session_state["workspace_notice"] = "Convite recusado."
                        st.rerun()
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
    elif not st.user.get("email_verified", False) and db.has_pending_company_invitation(st.user.get("email", "")):
        st.warning("O Google precisa confirmar seu e-mail para você responder aos convites.")

    with st.container(border=True):
        st.subheader("Minhas empresas")
        if not companies:
            st.caption("Você ainda não participa de uma empresa. Pode criar a sua ou usar o Demo abaixo.")
        for company in companies:
            st.button(f"Entrar em {company['name']} · {ROLE_LABELS[company['role']]}",
                      key=f"enter_company_{company['id']}", icon=":material/store:", width="stretch",
                      on_click=activate_company, args=(int(company["id"]),))

    with st.expander("Criar uma empresa", expanded=not companies and not invitations, icon=":material/add_business:"):
        st.caption("Você será o proprietário desta empresa, com acesso completo. Os convites são opcionais.")
        with st.form("company_onboarding"):
            name = st.text_input("Nome da empresa", key="onboarding_name", max_chars=120)
            segment = st.selectbox("Tipo de empresa", db.COMPANY_SEGMENTS, key="onboarding_segment")
            city = st.text_input("Cidade (opcional)", key="onboarding_city", max_chars=120)
            contact = st.text_input("E-mail de contato da empresa (opcional)", key="onboarding_contact", max_chars=254)
            st.markdown("**Convidar uma pessoa (opcional)**")
            email = st.text_input("E-mail da pessoa", key="onboarding_invite", max_chars=254)
            role = st.selectbox("Perfil da pessoa convidada", ("collaborator", "administrator"), format_func=ROLE_LABELS.get)
            st.caption("Colaborador consulta os dados. Proprietário também pode alterar dados e gerenciar acessos.")
            create = st.form_submit_button("Criar empresa", type="primary")
        if create:
            try:
                if email.strip() and ("@" not in email or "." not in email.rsplit("@", 1)[-1]):
                    raise ValueError("Confira o e-mail da pessoa convidada.")
                cid = db.create_company(name, issuer, subject, segment, contact, city)
                if email.strip():
                    st.session_state[f"team_invite_notice_{cid}"] = invite_person(cid, name.strip(), email, role, issuer, subject)
                    activate_company(cid)
                    st.session_state["active_page"] = "Empresa"
                    st.query_params["page"] = "Empresa"
                    st.session_state["account_team_expanded"] = True
                else:
                    activate_company(cid)
                st.rerun()
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))

    with st.container(border=True):
        st.subheader("Experimentar o Demo")
        st.write("Conheça os indicadores com vendas, estoque, despesas e orçamento de uma livraria fictícia.")
        st.caption("Somente consulta. Os dados de demonstração ficam separados das suas empresas.")
        if st.button("Acessar Demo", key="enter_demo", icon=":material/play_circle:"):
            company = db.demo_company()
            activate_company(int(company["id"]), True)
            st.rerun()
    st.button("Sair da conta", on_click=logout, key="workspace_logout", icon=":material/logout:")


def personal_profile(company: dict, issuer: str, subject: str, logout, shortcuts, theme_toggle) -> None:
    st.subheader(st.user.get("name", "") or "Conta Google")
    st.caption(st.user.get("email", ""))
    st.caption("Nome e e-mail de login são gerenciados na sua conta Google.")
    with st.form("personal_profile"):
        name = st.text_input("Como você quer ser chamado", value=db.get_user_setting("display_name", issuer, subject), max_chars=120)
        if st.form_submit_button("Salvar meu perfil", type="primary"):
            db.set_user_settings({"display_name": name.strip()}, issuer, subject)
            st.success("Seu perfil foi atualizado.")
    with st.expander("Minhas preferências"):
        st.button("Alternar modo claro / escuro", on_click=theme_toggle, key="personal_theme")
        shortcuts()
    with st.container(border=True):
        st.subheader("Minhas empresas")
        companies = db.companies_for_user(issuer, subject)
        for item in companies:
            st.write(f"**{item['name']}** · {item['segment']} · {ROLE_LABELS[item['role']]}")
        if not companies:
            st.caption("Você ainda não participa de uma empresa.")
        st.button("Escolher empresa, criar ou ver convites", on_click=open_workspace_picker, key="profile_choose_company")
    if not company.get("is_demo"):
        with st.expander("Sair da empresa selecionada"):
            st.caption(f"Isso remove seu acesso a {company['name']}. Os dados da empresa e sua conta Google são preservados.")
            with st.form(f"leave_company_{company['id']}"):
                confirmed = st.checkbox("Confirmo que quero sair desta empresa", key=f"leave_confirm_{company['id']}")
                leave = st.form_submit_button("Sair da empresa")
            if leave:
                if not confirmed:
                    st.error("Confirme que deseja sair da empresa.")
                else:
                    try:
                        db.leave_company(int(company["id"]), issuer, subject)
                        st.session_state.pop("active_company_id", None)
                        st.session_state["demo_active"] = False
                        open_workspace_picker()
                        st.session_state["workspace_notice"] = "Você saiu da empresa. Seus dados de login foram preservados."
                        st.rerun()
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
    st.button("Sair da conta", on_click=logout, key="logout_button", icon=":material/logout:")
