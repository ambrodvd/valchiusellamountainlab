import streamlit as st

st.set_page_config(
    page_title="Valchiusella Mountain Lab",
    page_icon="🏔️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

prenota = st.Page("Prenota.py", title="Prenota", icon="🏔️", default=True)
admin = st.Page("Admin.py", title="Gestione", icon="🔒")

st.navigation([prenota, admin]).run()
