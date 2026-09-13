from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import data
import mailer

st.title("🔒 Gestione")

if "admin_ok" not in st.session_state:
    st.session_state.admin_ok = False

if not st.session_state.admin_ok:
    pw = st.text_input("Password", type="password")
    if st.button("Entra"):
        if pw == st.secrets["admin_password"]:
            st.session_state.admin_ok = True
            st.rerun()
        else:
            st.error("Password errata.")
    st.stop()

if st.button("Aggiorna dati"):
    data.clear_all_caches()
    st.rerun()

categories = data.load_categories()
slots = data.load_slots()
bookings = data.load_bookings()

tab_tipi, tab_cal, tab_pren = st.tabs(
    ["Tipi di appuntamento", "Calendario", "Prenotazioni"]
)

# =============================================================
# TIPI DI APPUNTAMENTO
# =============================================================
with tab_tipi:
    st.subheader("Crea un tipo di appuntamento")
    st.caption(
        "Definisci una volta nome, luogo, durata, prezzo e link di pagamento; "
        "poi apri gli slot nel calendario scegliendo il tipo."
    )

    with st.form("nuovo_tipo"):
        t_name = st.text_input("Nome", placeholder="es. Test cardiopolmonare (CPET)")
        t_location = st.text_input(
            "Luogo", placeholder="Valchiusella Mountain Lab, Via ..."
        )
        c1, c2 = st.columns(2)
        t_duration = c1.number_input(
            "Durata (minuti)", min_value=5, max_value=480, value=60, step=5
        )
        t_price = c2.number_input(
            "Prezzo €", min_value=0.0, value=120.0, step=5.0
        )
        t_link = st.text_input(
            "Link di pagamento", placeholder="https://buy.stripe.com/..."
        )
        t_desc = st.text_area(
            "Descrizione (facoltativa)",
            placeholder="Cosa portare, come presentarsi, a chi è rivolto...",
        )
        crea = st.form_submit_button("Crea tipo", type="primary")

    if crea:
        if not t_name.strip():
            st.error("Il nome è obbligatorio.")
        elif t_link.strip() and not t_link.strip().startswith("http"):
            st.error("Il link di pagamento deve iniziare con http.")
        else:
            cid = data.add_category(
                name=t_name,
                location=t_location,
                duration_min=int(t_duration),
                price_eur=float(t_price),
                payment_link=t_link,
                description=t_desc,
            )
            st.success(f"Tipo {cid} creato.")
            st.rerun()

    st.divider()
    st.subheader("Tipi esistenti")

    if categories.empty:
        st.info("Nessun tipo. Creane uno qui sopra per iniziare.")
    else:
        st.dataframe(categories, use_container_width=True, hide_index=True)

        def _label_cat(cid: str) -> str:
            nome = categories.loc[categories["category_id"] == cid, "name"].iloc[0]
            return f"{cid} · {nome}"

        st.markdown("**Modifica un tipo**")
        cid_sel = st.selectbox(
            "Tipo",
            options=list(categories["category_id"]),
            format_func=_label_cat,
            key="cat_edit_sel",
        )
        row = categories[categories["category_id"] == cid_sel].iloc[0]

        with st.form("modifica_tipo"):
            e_name = st.text_input("Nome", value=row["name"], key="cat_e_name")
            e_location = st.text_input(
                "Luogo", value=row["location"], key="cat_e_location"
            )
            d1, d2 = st.columns(2)
            e_duration = d1.number_input(
                "Durata (minuti)", min_value=5, max_value=480,
                value=int(row["duration_min"]) or 60, step=5, key="cat_e_dur",
            )
            e_price = d2.number_input(
                "Prezzo €", min_value=0.0, value=float(row["price_eur"]),
                step=5.0, key="cat_e_price",
            )
            e_link = st.text_input(
                "Link di pagamento", value=row["payment_link"], key="cat_e_link"
            )
            e_desc = st.text_area(
                "Descrizione", value=row["description"], key="cat_e_desc"
            )
            salva = st.form_submit_button("Salva modifiche")

        if salva:
            if data.update_category(
                category_id=cid_sel,
                name=e_name,
                location=e_location,
                duration_min=int(e_duration),
                price_eur=float(e_price),
                payment_link=e_link,
                description=e_desc,
            ):
                st.success("Tipo aggiornato.")
                st.caption(
                    "La modifica vale subito per tutti gli slot di questo tipo, "
                    "anche quelli già pubblicati."
                )
                st.rerun()
            else:
                st.error("Tipo non trovato.")

        st.markdown("**Elimina un tipo**")
        cid_del = st.selectbox(
            "Tipo da eliminare",
            options=list(categories["category_id"]),
            format_func=_label_cat,
            key="cat_del_sel",
        )
        ok_del = st.checkbox("Confermo", key="cat_del_ok")
        if st.button("Elimina tipo", key="cat_del_btn") and ok_del:
            if data.delete_category(cid_del):
                st.success(f"{cid_del} eliminato.")
                st.rerun()
            else:
                st.error("Tipo non trovato.")

# =============================================================
# CALENDARIO
# =============================================================
with tab_cal:
    st.subheader("Apri nuovi slot")

    if categories.empty:
        st.warning("Crea prima almeno un tipo di appuntamento.")
    else:
        def _label_cat_new(cid: str) -> str:
            r = categories[categories["category_id"] == cid].iloc[0]
            return f"{r['name']} · {int(r['duration_min'])} min · € {r['price_eur']:.0f}"

        with st.form("nuovi_slot"):
            s_cat = st.selectbox(
                "Tipo di appuntamento",
                options=list(categories["category_id"]),
                format_func=_label_cat_new,
                key="slot_cat",
            )
            c1, c2 = st.columns(2)
            s_date = c1.date_input("Data", value=date.today(), key="slot_date")
            s_cap = c2.number_input(
                "Posti per slot", min_value=1, max_value=50, value=1, key="slot_cap"
            )
            s_times = st.text_input(
                "Orari (separati da virgola)",
                value="09:00, 10:30, 14:00",
                key="slot_times",
            )
            c3, c4 = st.columns(2)
            s_weeks = c3.number_input(
                "Ripeti per N settimane", min_value=0, max_value=52, value=0,
                key="slot_weeks", help="0 = solo questa data",
            )
            s_note = c4.text_input("Nota interna (facoltativa)", key="slot_note")
            crea_slot = st.form_submit_button("Crea slot", type="primary")

        if crea_slot:
            orari = []
            errore = None
            for raw in s_times.split(","):
                token = raw.strip()
                if not token:
                    continue
                try:
                    orari.append(datetime.strptime(token, "%H:%M").strftime("%H:%M"))
                except ValueError:
                    errore = token
                    break

            if errore:
                st.error(f"Orario non valido: «{errore}». Usa il formato HH:MM.")
            elif not orari:
                st.error("Inserisci almeno un orario.")
            else:
                righe = []
                for w in range(int(s_weeks) + 1):
                    giorno = s_date + timedelta(weeks=w)
                    for t in orari:
                        righe.append(
                            (giorno.isoformat(), t, s_cat, int(s_cap), s_note)
                        )
                ids = data.add_slots_bulk(righe)
                st.success(f"{len(ids)} slot creati ({ids[0]} → {ids[-1]}).")
                st.rerun()

    st.divider()
    st.subheader("Slot in calendario")

    if slots.empty:
        st.info("Nessuno slot.")
    else:
        vista_slot = data.slots_with_category(slots, categories)
        taken = data.seats_taken(bookings)
        vista_slot = vista_slot.assign(
            prenotati=lambda d: d["slot_id"].map(taken).fillna(0).astype(int)
        )
        vista_slot = vista_slot.assign(
            liberi=lambda d: (d["capacity"] - d["prenotati"]).clip(lower=0)
        )

        solo_futuri = st.checkbox("Solo slot futuri", value=True, key="slot_fut")
        if solo_futuri:
            vista_slot = vista_slot[vista_slot["date"] >= date.today()]
        vista_slot = vista_slot.sort_values(["date", "time"])

        st.dataframe(
            vista_slot[[
                "slot_id", "date", "time", "name", "capacity",
                "prenotati", "liberi", "note",
            ]],
            use_container_width=True,
            hide_index=True,
        )

        if not vista_slot.empty:
            def _label_slot(sid: str) -> str:
                r = vista_slot[vista_slot["slot_id"] == sid].iloc[0]
                return (
                    f"{sid} · {r['date'].strftime('%d/%m/%Y')} {r['time']} · "
                    f"{r['name']} ({r['prenotati']}/{r['capacity']})"
                )

            st.markdown("**Elimina uno slot**")
            sid_del = st.selectbox(
                "Slot da eliminare",
                options=list(vista_slot["slot_id"]),
                format_func=_label_slot,
                key="slot_del_sel",
            )
            conferma = st.checkbox("Confermo l'eliminazione", key="slot_del_ok")
            if st.button("Elimina slot", key="slot_del_btn") and conferma:
                if data.delete_slot(sid_del):
                    st.success(f"{sid_del} eliminato.")
                    st.rerun()
                else:
                    st.error("Slot non trovato.")

# =============================================================
# PRENOTAZIONI
# =============================================================
with tab_pren:
    if bookings.empty:
        st.info("Nessuna prenotazione.")
    else:
        base = data.slots_with_category(slots, categories)
        merged = bookings.merge(base, on="slot_id", how="left")
        merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
        merged = merged.sort_values(["date", "time", "timestamp"], na_position="last")
        active = merged[merged["status"] != "cancelled"]
        oggi = pd.Timestamp(date.today())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Confermate", len(active))
        c2.metric("Annullate", len(merged) - len(active))
        c3.metric(
            "Future",
            int((active["date"] >= oggi).sum()) if not active.empty else 0,
        )
        da_incassare = (
            active[active["paid"] != "si"]["price_eur"].sum()
            if not active.empty else 0.0
        )
        c4.metric("Da incassare", f"€ {da_incassare:,.2f}")

        colonne = [
            c for c in [
                "booking_id", "date", "time", "name_y", "name_x", "email",
                "phone", "paid", "status", "timestamp",
            ] if c in merged.columns
        ]
        tabella = merged[colonne].rename(
            columns={"name_y": "appuntamento", "name_x": "cliente"}
        )
        st.dataframe(tabella, use_container_width=True, hide_index=True)
        st.download_button(
            "Scarica prenotazioni CSV",
            tabella.to_csv(index=False).encode("utf-8"),
            file_name=f"prenotazioni_{date.today().isoformat()}.csv",
            mime="text/csv",
            key="dl_pren",
        )

        st.divider()
        st.subheader("Segna come pagato")
        ref_pay = st.text_input("Codice appuntamento", key="pay_ref")
        cp1, cp2 = st.columns(2)
        if cp1.button("Segna pagato", key="pay_si") and ref_pay.strip():
            if data.set_paid(ref_pay.strip().upper(), True):
                st.success("Aggiornato.")
                st.rerun()
            else:
                st.error("Codice non trovato.")
        if cp2.button("Togli pagato", key="pay_no") and ref_pay.strip():
            if data.set_paid(ref_pay.strip().upper(), False):
                st.success("Aggiornato.")
                st.rerun()
            else:
                st.error("Codice non trovato.")

        st.divider()
        st.subheader("Annulla una prenotazione")
        ref = st.text_input("Codice prenotazione", key="pren_ref")
        avvisa = st.checkbox(
            "Invia email di annullamento", value=True, key="pren_avvisa"
        )
        if st.button("Annulla", type="primary", key="pren_btn") and ref.strip():
            code = ref.strip().upper()
            row = merged[merged["booking_id"] == code]
            if data.cancel_booking(code):
                st.success(f"{code} annullata.")
                if avvisa and not row.empty:
                    r = row.iloc[0]
                    try:
                        mailer.send_cancellation(
                            to=r["email"],
                            name=r.get("name_x", ""),
                            title=r.get("name_y", ""),
                            date_str=(
                                r["date"].strftime("%d/%m/%Y")
                                if pd.notna(r.get("date")) else ""
                            ),
                            time_str=r.get("time", ""),
                        )
                    except Exception:
                        st.warning("Annullata, ma l'email non è partita.")
                st.rerun()
            else:
                st.error("Codice non trovato.")
