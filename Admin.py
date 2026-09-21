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

tab_pren, tab_cal, tab_tipi = st.tabs(
    ["Prenotazioni", "Calendario", "Categorie test"]
)

# =============================================================
# CALENDARIO
# =============================================================
with tab_cal:
    st.subheader("Apri nuovi slot")

    msg_slot = st.session_state.pop("msg_slot", None)
    if msg_slot:
        st.success(msg_slot)
    warn_slot = st.session_state.pop("warn_slot", None)
    if warn_slot:
        st.warning(warn_slot)

    if categories.empty:
        st.warning("Crea prima almeno una categoria di test.")
    else:
        def _label_cat_new(cid: str) -> str:
            r = categories[categories["category_id"] == cid].iloc[0]
            coach = f" · {r['coach']}" if str(r["coach"]).strip() else ""
            return (
                f"{r['name']}{coach} · {int(r['duration_min'])} min "
                f"· € {r['price_eur']:.0f}"
            )

        with st.form("nuovi_slot"):
            s_cat = st.selectbox(
                "Tipo di test",
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
                candidati = [
                    (s_date + timedelta(weeks=w), t)
                    for w in range(int(s_weeks) + 1)
                    for t in orari
                ]
                ok, bloccati = data.check_new_slots(
                    candidati, s_cat, slots, categories, bookings
                )

                if ok:
                    righe = [
                        (d.isoformat(), t, s_cat, int(s_cap), s_note)
                        for d, t in ok
                    ]
                    ids = data.add_slots_bulk(righe)
                    st.session_state["msg_slot"] = (
                        f"{len(ids)} slot creati ({ids[0]} → {ids[-1]})."
                    )
                if bloccati:
                    st.session_state["warn_slot"] = (
                        f"{len(bloccati)} slot non creati: si sovrappongono "
                        "a slot già prenotati.\n\n"
                        + "\n".join(
                            f"- {d.strftime('%d/%m/%Y')} ore {t}: {motivo}"
                            for d, t, motivo in bloccati
                        )
                    )
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
        bloccati_cal = data.blocked_slots(vista_slot, bookings)
        vista_slot["stato"] = [
            "prenotato" if p > 0 else ("bloccato" if s in bloccati_cal else "libero")
            for s, p in zip(vista_slot["slot_id"], vista_slot["prenotati"])
        ]
        vista_slot.loc[vista_slot["slot_id"].isin(bloccati_cal), "liberi"] = 0

        solo_futuri = st.checkbox("Solo slot futuri", value=True, key="slot_fut")
        if solo_futuri:
            vista_slot = vista_slot[vista_slot["date"] >= date.today()]
        vista_slot = vista_slot.sort_values(["date", "time"])

        st.dataframe(
            vista_slot[[
                "slot_id", "date", "time", "name", "coach", "stato",
                "capacity", "prenotati", "liberi", "note",
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
        merged = merged.rename(columns={"name_x": "cliente", "name_y": "test"})
        merged["price_eur"] = merged["price_eur"].fillna(0.0)

        # incassato: se non indicato (prenotazioni vecchie) vale il listino
        merged["incassato"] = merged["amount_paid"].where(
            merged["amount_paid"].notna(), merged["price_eur"]
        )
        merged.loc[merged["paid"] != "si", "incassato"] = 0.0
        merged["rimborsato"] = merged["amount_refunded"].fillna(0.0)

        active = merged[~merged["status"].isin(data.INACTIVE_STATUSES)]
        da_incassare = active[active["paid"] != "si"]
        incassate = active[active["paid"] == "si"]
        rimborsate = merged[merged["status"] == "refunded"]
        oggi = pd.Timestamp(date.today())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Confermate", len(active))
        c2.metric("Annullate", int((merged["status"] == "cancelled").sum()))
        c3.metric("Rimborsate", len(rimborsate))
        c4.metric(
            "Future",
            int((active["date"] >= oggi).sum()) if not active.empty else 0,
        )

        def _giorni(serie) -> list[str]:
            return [d.strftime("%d/%m/%Y") if pd.notna(d) else "" for d in serie]

        def _base(df: pd.DataFrame) -> dict:
            return {
                "codice": df["booking_id"].values,
                "giorno": _giorni(df["date"]),
                "ora": df["time"].fillna("").values,
                "cliente": df["cliente"].fillna("").values,
                "test": df["test"].fillna("").values,
                "coach": df["coach"].fillna("").values,
            }

        _euro = {"format": "€ %.2f"}

        # =========================================================
        # PAGAMENTI
        # =========================================================
        # Termini e condizioni: cancellazione oltre 144 h → buono 100%,
        # tra 72 e 144 h → buono 50%, sotto 72 h → nessun rimborso.
        PERC_PARZIALE = 0.5

        st.divider()
        st.subheader("Pagamenti")

        msg = st.session_state.pop("msg_pagamenti", None)
        if msg:
            st.success(msg)

        tot_da_incassare = float(da_incassare["price_eur"].sum())
        tot_incassato = float(merged.loc[merged["paid"] == "si", "incassato"].sum())
        tot_rimborsato = float(rimborsate["rimborsato"].sum())

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Da incassare", f"€ {tot_da_incassare:,.2f}")
        m2.metric("Incassato", f"€ {tot_incassato:,.2f}")
        m3.metric("Rimborsato", f"€ {tot_rimborsato:,.2f}")
        m4.metric("Netto", f"€ {tot_incassato - tot_rimborsato:,.2f}")

        def _tabella_selezionabile(df: pd.DataFrame, key: str, importi: dict) -> list:
            """Tabella con checkbox di selezione; ritorna i codici selezionati."""
            tab = pd.DataFrame({
                "seleziona": [False] * len(df),
                **_base(df),
                **{nome: valori for nome, valori in importi.items()},
            })
            mod = st.data_editor(
                tab,
                use_container_width=True,
                hide_index=True,
                key=key,
                column_config={
                    "seleziona": st.column_config.CheckboxColumn("✓"),
                    **{
                        nome: st.column_config.NumberColumn(nome.capitalize(), **_euro)
                        for nome in importi
                    },
                },
                disabled=[c for c in tab.columns if c != "seleziona"],
            )
            return [str(c).upper() for c in mod.loc[mod["seleziona"], "codice"]]

        # ---------- da incassare ----------
        st.markdown(f"**Da incassare ({len(da_incassare)})**")

        if da_incassare.empty:
            st.success("Tutto incassato.")
        else:
            scelti_da = _tabella_selezionabile(
                da_incassare, "ed_da_incassare",
                {"listino": da_incassare["price_eur"].values},
            )
            listino_di = {
                str(b).upper(): float(p)
                for b, p in zip(da_incassare["booking_id"], da_incassare["price_eur"])
            }

            diverso = st.checkbox(
                "L'importo incassato è diverso",
                key="chk_importo_diverso",
            )
            importo_diverso = None
            if diverso:
                if len(scelti_da) == 1:
                    importo_diverso = st.number_input(
                        f"Importo incassato per {scelti_da[0]} (€)",
                        min_value=0.0,
                        value=listino_di[scelti_da[0]],
                        step=1.0,
                        key=f"imp_diverso_{scelti_da[0]}",
                    )
                else:
                    st.caption(
                        "Seleziona una sola prenotazione per indicare un importo diverso."
                    )

            pronto = bool(scelti_da) and (not diverso or importo_diverso is not None)

            b1, b2 = st.columns([1, 3])
            if b1.button(
                "Segna come incassate", type="primary",
                key="btn_incassa", disabled=not pronto,
            ):
                if diverso:
                    importi = {scelti_da[0]: importo_diverso}
                else:
                    importi = {c: listino_di[c] for c in scelti_da}
                n = data.mark_paid_bulk(importi)
                st.session_state["msg_pagamenti"] = (
                    f"{n} prenotazioni segnate come incassate "
                    f"(€ {sum(importi.values()):,.2f})."
                )
                st.rerun()
            if scelti_da:
                totale = (
                    importo_diverso if importo_diverso is not None
                    else sum(listino_di[c] for c in scelti_da)
                )
                b2.caption(f"{len(scelti_da)} selezionate · € {totale:,.2f}")

        # ---------- incassate ----------
        st.markdown(f"**Incassate ({len(incassate)})**")

        if incassate.empty:
            st.caption("Nessun incasso registrato.")
        else:
            scelti_inc = _tabella_selezionabile(
                incassate, "ed_incassate",
                {
                    "listino": incassate["price_eur"].values,
                    "incassato": incassate["incassato"].values,
                },
            )
            incassato_di = {
                str(b).upper(): float(v)
                for b, v in zip(incassate["booking_id"], incassate["incassato"])
            }

            if scelti_inc:
                tot = sum(incassato_di[c] for c in scelti_inc)
                st.caption(
                    f"{len(scelti_inc)} selezionate · incassato € {tot:,.2f} · "
                    f"integrale (100%) € {tot:,.2f} · "
                    f"parziale ({PERC_PARZIALE:.0%}) € {tot * PERC_PARZIALE:,.2f}"
                )

            ok_rimb = st.checkbox(
                "Confermo il rimborso delle prenotazioni selezionate",
                key="chk_rimborso",
            )

            b1, b2, b3 = st.columns(3)
            if b1.button(
                "Togli dagli incassati", key="btn_togli_incassati",
                disabled=not scelti_inc,
            ):
                n = data.unmark_paid_bulk(scelti_inc)
                st.session_state["msg_pagamenti"] = (
                    f"{n} prenotazioni riportate fra quelle da incassare."
                )
                st.rerun()
            if b2.button(
                "Rimborso integrale", key="btn_rimb_integrale",
                disabled=not (scelti_inc and ok_rimb),
            ):
                rimborsi = {c: incassato_di[c] for c in scelti_inc}
                n = data.refund_bulk(rimborsi)
                st.session_state["msg_pagamenti"] = (
                    f"{n} rimborsi integrali registrati "
                    f"(€ {sum(rimborsi.values()):,.2f}). "
                    "Gli slot sono di nuovo prenotabili."
                )
                st.rerun()
            if b3.button(
                "Rimborso parziale", key="btn_rimb_parziale",
                disabled=not (scelti_inc and ok_rimb),
            ):
                rimborsi = {
                    c: round(incassato_di[c] * PERC_PARZIALE, 2) for c in scelti_inc
                }
                n = data.refund_bulk(rimborsi)
                st.session_state["msg_pagamenti"] = (
                    f"{n} rimborsi parziali ({PERC_PARZIALE:.0%}) registrati "
                    f"(€ {sum(rimborsi.values()):,.2f}). "
                    "Gli slot sono di nuovo prenotabili."
                )
                st.rerun()

        # ---------- rimborsate ----------
        st.markdown(f"**Rimborsate ({len(rimborsate)})**")

        if rimborsate.empty:
            st.caption("Nessun rimborso.")
        else:
            tipo = [
                "Integrale" if rb >= inc - 0.005 else "Parziale"
                for rb, inc in zip(rimborsate["rimborsato"], rimborsate["incassato"])
            ]
            st.dataframe(
                pd.DataFrame({
                    **_base(rimborsate),
                    "email": rimborsate["email"].fillna("").values,
                    "tipo": tipo,
                    "incassato": rimborsate["incassato"].values,
                    "rimborsato": rimborsate["rimborsato"].values,
                    "trattenuto": (
                        rimborsate["incassato"] - rimborsate["rimborsato"]
                    ).values,
                }),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "incassato": st.column_config.NumberColumn("Incassato", **_euro),
                    "rimborsato": st.column_config.NumberColumn("Rimborsato", **_euro),
                    "trattenuto": st.column_config.NumberColumn("Trattenuto", **_euro),
                },
            )

        # =========================================================
        # ELENCO COMPLETO
        # =========================================================
        st.divider()
        st.subheader("Tutte le prenotazioni")

        colonne = [
            c for c in [
                "booking_id", "date", "time", "test", "coach", "cliente",
                "email", "phone", "status", "paid", "price_eur",
                "incassato", "rimborsato", "timestamp",
            ] if c in merged.columns
        ]
        tabella = merged[colonne].copy()
        tabella["status"] = tabella["status"].map(
            lambda s: data.STATUS_LABELS.get(s, s)
        )
        st.dataframe(tabella, use_container_width=True, hide_index=True)
        st.download_button(
            "Scarica prenotazioni CSV",
            tabella.to_csv(index=False).encode("utf-8"),
            file_name=f"prenotazioni_{date.today().isoformat()}.csv",
            mime="text/csv",
            key="dl_pren",
        )

        # =========================================================
        # ANNULLAMENTO
        # =========================================================
        st.divider()
        st.subheader("Annulla una prenotazione")

        if active.empty:
            st.info("Niente da annullare.")
        else:
            def _label_pren(bid: str) -> str:
                r = active[active["booking_id"] == bid].iloc[0]
                giorno = (
                    r["date"].strftime("%d/%m/%Y") if pd.notna(r["date"]) else "—"
                )
                return f"{bid} · {r['cliente']} · {giorno} {r['time']}"

            code = st.selectbox(
                "Prenotazione",
                options=list(active["booking_id"]),
                format_func=_label_pren,
                key="pren_sel",
            )
            avvisa = st.checkbox(
                "Invia email di annullamento", value=True, key="pren_avvisa"
            )
            if st.button("Annulla", type="primary", key="pren_btn"):
                row = merged[merged["booking_id"] == code]
                if data.cancel_booking(code):
                    st.success(f"{code} annullata.")
                    if avvisa and not row.empty:
                        r = row.iloc[0]
                        try:
                            mailer.send_cancellation(
                                to=r["email"],
                                name=r.get("cliente", ""),
                                title=r.get("test", ""),
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

# =============================================================
# CATEGORIE TEST
# =============================================================
with tab_tipi:
    st.subheader("Crea una categoria di test")
    st.caption(
        "Definisci una volta nome, allenatore, luogo, durata, prezzo e link di "
        "pagamento; poi apri gli slot nel calendario scegliendo la categoria."
    )

    coaches = data.coach_list(categories)

    with st.form("nuovo_tipo"):
        t_name = st.text_input("Nome", placeholder="es. Test cardiopolmonare (CPET)")
        t_coach = st.text_input(
            "Allenatore",
            placeholder="Nome e cognome",
            help=(
                "Allenatori già inseriti: " + ", ".join(coaches)
                if coaches else "Il primo allenatore che inserisci"
            ),
        )
        t_location = st.text_input("Luogo", value=data.DEFAULT_LOCATION)
        c1, c2 = st.columns(2)
        t_duration = c1.number_input(
            "Durata (minuti)", min_value=5, max_value=480, value=60, step=5
        )
        t_price = c2.number_input(
            "Prezzo €", min_value=0.0, value=120.0, step=5.0
        )
        t_link = st.text_input(
            "Link di pagamento dell'allenatore",
            placeholder="https://buy.stripe.com/...",
        )
        t_desc = st.text_area(
            "Descrizione (facoltativa)",
            placeholder="Cosa portare, come presentarsi, a chi è rivolto...",
        )
        crea = st.form_submit_button("Crea categoria", type="primary")

    if crea:
        link = t_link.strip() or data.payment_link_for_coach(categories, t_coach)
        if not t_name.strip():
            st.error("Il nome è obbligatorio.")
        elif not t_coach.strip():
            st.error("L'allenatore è obbligatorio.")
        elif link and not link.startswith("http"):
            st.error("Il link di pagamento deve iniziare con http.")
        else:
            cid = data.add_category(
                name=t_name,
                coach=t_coach,
                location=t_location,
                duration_min=int(t_duration),
                price_eur=float(t_price),
                payment_link=link,
                description=t_desc,
            )
            st.success(f"Categoria {cid} creata.")
            if not t_link.strip() and link:
                st.caption(f"Ho riusato il link già noto per {t_coach.strip()}.")
            st.rerun()

    st.divider()
    st.subheader("Categorie esistenti")

    if categories.empty:
        st.info("Nessuna categoria. Creane una qui sopra per iniziare.")
    else:
        st.dataframe(categories, use_container_width=True, hide_index=True)

        def _label_cat(cid: str) -> str:
            r = categories[categories["category_id"] == cid].iloc[0]
            coach = f" · {r['coach']}" if str(r["coach"]).strip() else ""
            return f"{cid} · {r['name']}{coach}"

        st.markdown("**Modifica una categoria**")
        cid_sel = st.selectbox(
            "Categoria",
            options=list(categories["category_id"]),
            format_func=_label_cat,
            key="cat_edit_sel",
        )
        row = categories[categories["category_id"] == cid_sel].iloc[0]

        k = cid_sel  # chiavi diverse per ogni categoria: i campi si ricaricano
        with st.form(f"modifica_tipo_{k}"):
            e_name = st.text_input("Nome", value=row["name"], key=f"cat_e_name_{k}")
            e_coach = st.text_input(
                "Allenatore", value=row["coach"], key=f"cat_e_coach_{k}"
            )
            e_location = st.text_input(
                "Luogo",
                value=row["location"] or data.DEFAULT_LOCATION,
                key=f"cat_e_location_{k}",
            )
            d1, d2 = st.columns(2)
            e_duration = d1.number_input(
                "Durata (minuti)", min_value=5, max_value=480,
                value=int(row["duration_min"]) or 60, step=5, key=f"cat_e_dur_{k}",
            )
            e_price = d2.number_input(
                "Prezzo €", min_value=0.0, value=float(row["price_eur"]),
                step=5.0, key=f"cat_e_price_{k}",
            )
            e_link = st.text_input(
                "Link di pagamento dell'allenatore",
                value=row["payment_link"], key=f"cat_e_link_{k}",
            )
            e_desc = st.text_area(
                "Descrizione", value=row["description"], key=f"cat_e_desc_{k}"
            )
            salva = st.form_submit_button("Salva modifiche")

        if salva:
            if not e_coach.strip():
                st.error("L'allenatore è obbligatorio.")
            elif data.update_category(
                category_id=cid_sel,
                name=e_name,
                coach=e_coach,
                location=e_location,
                duration_min=int(e_duration),
                price_eur=float(e_price),
                payment_link=e_link,
                description=e_desc,
            ):
                st.success("Categoria aggiornata.")
                st.caption(
                    "La modifica vale subito per tutti gli slot di questa "
                    "categoria, anche quelli già pubblicati."
                )
                st.rerun()
            else:
                st.error("Categoria non trovata.")

        st.markdown("**Elimina una categoria**")
        cid_del = st.selectbox(
            "Categoria da eliminare",
            options=list(categories["category_id"]),
            format_func=_label_cat,
            key="cat_del_sel",
        )
        ok_del = st.checkbox("Confermo", key="cat_del_ok")
        if st.button("Elimina categoria", key="cat_del_btn") and ok_del:
            if data.delete_category(cid_del):
                st.success(f"{cid_del} eliminata.")
                st.rerun()
            else:
                st.error("Categoria non trovata.")