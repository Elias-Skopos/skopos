"""Workspace selection and personal profile, independent of financial screens."""
import smtplib
import os

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

import db
import company_lifecycle
from invitation_email import send_invitation

ROLE_LABELS = {"administrator": "Proprietário", "collaborator": "Colaborador"}


def clear_company_session() -> None:
    for key in list(st.session_state):
        if key.startswith(("horus_", "gemini_", "openai_")):
            del st.session_state[key]
    st.session_state.pop("collapsed_rail_open_group", None)


def activate_company(company_id: int, home: bool = True) -> None:
    clear_company_session()
    st.session_state["active_company_id"] = company_id
    st.session_state.pop("demo_active", None)
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


def invite_people(company_id: int, company_name: str, invitations: list[tuple[str, str]],
                  issuer: str, subject: str) -> tuple[str, str]:
    results = db.invite_company_members(company_id, invitations, issuer, subject)
    try:
        config = dict(st.secrets.get("email", {}))
    except StreamlitSecretNotFoundError:
        config = {}
    registered = []
    existing = []
    failed = []
    unconfigured = []
    for email, role, result in results:
        if result == "already_member":
            existing.append(email)
            continue
        registered.append(email)
        try:
            if not send_invitation(email, company_name, ROLE_LABELS[role], config):
                unconfigured.append(email)
        except (OSError, smtplib.SMTPException, ValueError):
            failed.append(email)
    messages = []
    if registered:
        messages.append(f"Convites registrados: {', '.join(registered)}. Ao entrar com a conta Google correspondente, cada pessoa poderá aceitar o convite e acessar a empresa.")
    if existing:
        messages.append(f"Já participam da empresa: {', '.join(existing)}. Para alterar o perfil, use a gestão da equipe.")
    if failed:
        messages.append(f"Não foi possível enviar o e-mail para: {', '.join(failed)}. Os convites estão disponíveis no Skopos; compartilhe o endereço do aplicativo.")
    if unconfigured:
        messages.append("O envio por e-mail ainda não está configurado. Compartilhe o endereço do Skopos com as pessoas convidadas.")
    if registered and not failed and not unconfigured:
        messages.append("Os convites também foram enviados por e-mail.")
    level = "warning" if failed else "info" if unconfigured or not registered else "success"
    return level, " ".join(messages)


def company_invitation_form(company_id: int, company_name: str, issuer: str, subject: str) -> None:
    prefix = f"team_invite_{company_id}"
    count_key = f"{prefix}_count"
    if st.session_state.pop(f"{prefix}_reset", False):
        for key in list(st.session_state):
            if key.startswith((f"{prefix}_email_", f"{prefix}_role_")):
                del st.session_state[key]
        st.session_state[count_key] = 1
    count = st.session_state.setdefault(count_key, 1)
    with st.form(f"invite_company_members_{company_id}", enter_to_submit=False):
        invitations = []
        for index in range(count):
            with st.container(horizontal=True, vertical_alignment="bottom"):
                email = st.text_input(f"E-mail {index + 1}", placeholder="pessoa@gmail.com",
                                      key=f"{prefix}_email_{index}", max_chars=254)
                role = st.selectbox(f"Perfil {index + 1}", ("collaborator", "administrator"),
                                     format_func=ROLE_LABELS.get, key=f"{prefix}_role_{index}")
            if email.strip():
                invitations.append((email, role))
        add_row = st.form_submit_button("+", help="Adicionar outro e-mail", key=f"{prefix}_add_row")
        st.caption("Escolha o perfil de cada pessoa. O botão + apenas adiciona outro campo; os convites são registrados ao clicar abaixo.")
        submitted = st.form_submit_button("Adicionar à empresa", type="primary", key=f"{prefix}_submit")
    if add_row:
        st.session_state[count_key] = count + 1
        st.session_state["account_team_expanded"] = True
        st.rerun()
    if submitted:
        try:
            st.session_state[f"team_invite_notice_{company_id}"] = invite_people(
                company_id, company_name, invitations, issuer, subject)
            st.session_state[f"{prefix}_reset"] = True
            st.session_state["account_team_expanded"] = True
            st.rerun()
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))


def workspace_picker(companies: list[dict], issuer: str, subject: str, logout) -> None:
    with st.container(horizontal_alignment="center"):
        with st.container(width=680, key="workspace_picker_panel"):
            _workspace_picker_contents(companies, issuer, subject, logout)


def _workspace_picker_contents(companies: list[dict], issuer: str, subject: str, logout) -> None:
    st.title("Bem-vindo ao Skopos")
    st.write("Escolha uma empresa ou crie a sua.")
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
            st.caption("Você ainda não participa de uma empresa. Crie a sua para começar.")
        for company in companies:
            st.button(f"Entrar em {company['name']} · {ROLE_LABELS[company['role']]}",
                      key=f"enter_company_{company['id']}", icon=":material/store:", width="stretch",
                      on_click=activate_company, args=(int(company["id"]),))

    with st.expander("Criar uma empresa", expanded=not companies and not invitations, icon=":material/add_business:"):
        st.caption("Você será o proprietário desta empresa, com acesso completo. Após criar, poderá convidar sua equipe.")
        with st.form("company_onboarding"):
            name = st.text_input("Nome da empresa", key="onboarding_name", max_chars=120)
            segment = st.selectbox("Tipo de empresa", db.COMPANY_SEGMENTS, key="onboarding_segment")
            city = st.text_input("Cidade (opcional)", key="onboarding_city", max_chars=120)
            contact = st.text_input("E-mail de contato da empresa (opcional)", key="onboarding_contact", max_chars=254)
            create = st.form_submit_button("Criar empresa", type="primary")
        if create:
            try:
                cid = db.create_company(name, issuer, subject, segment, contact, city)
                activate_company(cid)
                st.session_state["active_page"] = "Empresa"
                st.query_params["page"] = "Empresa"
                st.session_state["account_team_expanded"] = True
                st.session_state[f"team_invite_notice_{cid}"] = ("success", "Empresa criada. Adicione os e-mails da sua equipe abaixo ou comece a usar o aplicativo pelo menu.")
                st.rerun()
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))

    company_recovery_panel(issuer, subject)
    st.button("Sair da conta", on_click=logout, key="workspace_logout", icon=":material/logout:")


def company_deletion_panel(company: dict, issuer: str, subject: str) -> None:
    if company.get("role") != "administrator":
        return
    company_id = int(company["id"])
    with st.expander("Excluir empresa", icon=":material/delete:"):
        st.warning(f"Excluir {company['name']} remove a empresa, seus dados e todos os acessos da área ativa do Skopos.")
        st.caption("Seu perfil pessoal e as outras empresas serão mantidos. Uma cópia para recuperação será guardada neste banco; somente o proprietário que fizer a exclusão poderá recuperá-la em Empresas e convites.")
        with st.form(f"company_delete_form_{company_id}", enter_to_submit=False):
            name = st.text_input("Digite o nome exato da empresa", key=f"company_delete_name_{company_id}", max_chars=120)
            confirmed = st.checkbox("Confirmo a exclusão desta empresa e entendo que toda a equipe perderá o acesso.",
                                    key=f"company_delete_confirm_{company_id}")
            submitted = st.form_submit_button("Excluir empresa", key=f"company_delete_submit_{company_id}")
        if submitted:
            try:
                company_lifecycle.delete_company(company_id, issuer, subject, name, confirmed)
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
            except Exception:
                st.error("A exclusão não foi concluída. Os dados da empresa foram preservados; tente novamente ou confira o banco.")
            else:
                st.session_state.pop("active_company_id", None)
                open_workspace_picker()
                st.session_state["workspace_notice"] = f"{company['name']} foi excluída. A cópia está disponível em Empresas excluídas para recuperação."
                st.rerun()


def company_recovery_panel(issuer: str, subject: str) -> None:
    backups = company_lifecycle.deleted_companies(issuer, subject)
    if not backups:
        return
    with st.expander("Empresas excluídas", icon=":material/restore:"):
        st.caption("Cópias das empresas que você excluiu. Elas ficam neste mesmo banco e também entram nos backups do Skopos.")
        for backup in backups:
            backup_id = backup["id"]
            with st.container(border=True):
                st.subheader(backup["company_name"])
                st.caption("A recuperação devolve os dados e os acessos da equipe como estavam na exclusão.")
                with st.form(f"company_restore_form_{backup_id}", enter_to_submit=False):
                    confirmed = st.checkbox("Confirmo a recuperação dos dados e dos acessos desta empresa.", key=f"company_restore_confirm_{backup_id}")
                    submitted = st.form_submit_button("Recuperar empresa", key=f"company_restore_submit_{backup_id}")
                if submitted:
                    try:
                        company_id = company_lifecycle.restore_company(backup_id, issuer, subject, confirmed)
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
                    except Exception:
                        st.error("A recuperação não foi concluída. Nenhum dado foi substituído.")
                    else:
                        activate_company(company_id)
                        st.rerun()


def personal_profile(company: dict, issuer: str, subject: str, logout, shortcuts, theme_toggle) -> None:
    st.subheader(st.user.get("name", "") or "Conta Google")
    st.caption(st.user.get("email", ""))
    if os.environ.get("SKOPOS_DESKTOP") == "1":
        st.caption("Acesso local e Google podem ser vinculados ao mesmo perfil.")
        from local_config import load_config
        st.link_button("Gerenciar senha local e Google", load_config().url + "/identity/account", icon=":material/lock:")
    else:
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
                        st.session_state.pop("demo_active", None)
                        open_workspace_picker()
                        st.session_state["workspace_notice"] = "Você saiu da empresa. Seus dados de login foram preservados."
                        st.rerun()
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
    st.button("Sair da conta", on_click=logout, key="logout_button", icon=":material/logout:")
