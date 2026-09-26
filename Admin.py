import calendar
import re
from datetime import date, datetime, timedelta
from html import escape

import pandas as pd
import streamlit as st

import data
import mailer

# =============================================================
# HELPER CALENDARIO (usati da Calendario e Prenotazioni)
# =============================================================

MESI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]

PALETTE = [
    "#1e88e5", "#e53935", "#43a047", "#8e24aa", "#fb8c00",
    "#00897b", "#c2185b", "#5e35b1", "#f9a825", "#546e7a",
]
GRIGIO = "#90a4ae"

CSS_CALENDARIO = """
<style>
table.vml-cal { width:100%; border-collapse:collapse;
    table-layout:fixed; font-size:.72rem; }
table.vml-cal th { padding:.3rem; text-align:center;
    font-weight:600; opacity:.7; font-size:.7rem; }
table.vml-cal td { border:1px solid rgba(128,128,128,.28);
    vertical-align:top; height:5.5rem; padding:.2rem; }
table.vml-cal td.vml-vuoto { background:rgba(128,128,128,.07);
    border-color:rgba(128,128,128,.14); }
table.vml-cal td.vml-oggi { outline:2px solid rgba(66,133,244,.7);
    outline-offset:-2px; }
.vml-num { font-weight:700; opacity:.6; margin-bottom:.15rem; }
.vml-chip { border-radius:3px; padding:.1rem .25rem; margin-bottom:.12rem;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
</style>
"""


def rgba(hex_colore: str, alpha: float) -> str:
    h = hex_colore.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def colori_per_coach(categories) -> dict:
    """Un colore per allenatore, stabile: dipende dall'elenco categorie."""
    return {
        c: PALETTE[i % len(PALETTE)]
        for i, c in enumerate(data.coach_list(categories))
    }


def navigatore_mese(prefix: str):
    """Barra ◀ Oggi ▶ con il mese condiviso fra le tab. Ritorna (anno, mese)."""
    if "cal_mese" not in st.session_state:
        _oggi = date.today()
        st.session_state["cal_mese"] = (_oggi.year, _oggi.month)

    n1, n2, n3, n4 = st.columns([1, 1, 4, 1])
    if n1.button("◀", key=f"{prefix}_prev", help="Mese precedente"):
        a, m = st.session_state["cal_mese"]
        st.session_state["cal_mese"] = (a - 1, 12) if m == 1 else (a, m - 1)
    if n2.button("Oggi", key=f"{prefix}_oggi"):
        _oggi = date.today()
        st.session_state["cal_mese"] = (_oggi.year, _oggi.month)
    if n4.button("▶", key=f"{prefix}_next", help="Mese successivo"):
        a, m = st.session_state["cal_mese"]
        st.session_state["cal_mese"] = (a + 1, 1) if m == 12 else (a, m + 1)

    anno, mese = st.session_state["cal_mese"]
    n3.markdown(
        f"<div style='text-align:center;font-weight:600;padding-top:.45rem'>"
        f"{MESI[mese - 1]} {anno}</div>",
        unsafe_allow_html=True,
    )
    return anno, mese


def disegna_griglia(anno: int, mese: int, per_giorno: dict) -> None:
    """per_giorno: {giorno: [(stato, colore, testo), ...]}.

    stato: 'pieno' (tinta piena e grassetto), 'chiuso' (barrato),
    qualsiasi altro valore = tinta tenue.
    """
    celle = []
    for settimana in calendar.monthcalendar(anno, mese):
        riga = []
        for giorno in settimana:
            if giorno == 0:
                riga.append("<td class='vml-vuoto'></td>")
                continue
            chips = "".join(
                "<div class='vml-chip' style='"
                f"border-left:3px solid {colore};"
                f"background:{rgba(colore, .30 if stato == 'pieno' else .10)};"
                + ("font-weight:600;" if stato == "pieno" else "")
                + ("opacity:.45;text-decoration:line-through;"
                   if stato == "chiuso" else "")
                + f"'>{testo}</div>"
                for stato, colore, testo in per_giorno.get(giorno, [])
            )
            oggi_cls = (
                " vml-oggi" if date(anno, mese, giorno) == date.today() else ""
            )
            riga.append(
                f"<td class='vml-cella{oggi_cls}'>"
                f"<div class='vml-num'>{giorno}</div>{chips}</td>"
            )
        celle.append("<tr>" + "".join(riga) + "</tr>")

    st.markdown(CSS_CALENDARIO, unsafe_allow_html=True)
    st.markdown(
        "<table class='vml-cal'><tr>"
        + "".join(
            f"<th>{g}</th>"
            for g in ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
        )
        + "</tr>" + "".join(celle) + "</table>",
        unsafe_allow_html=True,
    )


def legenda_coach(colore_coach: dict) -> None:
    if not colore_coach:
        return
    legenda = " ".join(
        f"<span style='display:inline-block;width:.6rem;height:.6rem;"
        f"border-radius:50%;background:{colore};margin-right:.25rem'></span>"
        f"<span style='margin-right:.9rem'>{escape(c)}</span>"
        for c, colore in colore_coach.items()
    )
    st.markdown(
        f"<div style='font-size:.75rem;opacity:.85'>{legenda}</div>",
        unsafe_allow_html=True,
    )


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

        # ---------- filtro allenatore (vale per calendario ed elenco) ----------
        coach_cal = ["tutti"] + sorted(
            {str(c).strip() for c in vista_slot["coach"] if str(c).strip()}
        )
        filtro_coach_cal = st.selectbox(
            "Allenatore",
            options=coach_cal,
            format_func=lambda c: "Tutti gli allenatori" if c == "tutti" else c,
            key="cal_coach",
            disabled=len(coach_cal) < 3,
        )
        if filtro_coach_cal != "tutti":
            vista_slot = vista_slot[
                vista_slot["coach"].astype(str).str.strip() == filtro_coach_cal
            ]

        # ---------- vista calendario ----------
        st.markdown("**Vista calendario**")

        anno_cal, mese_cal = navigatore_mese("cal")
        colore_coach = colori_per_coach(categories)

        del_mese = vista_slot[
            vista_slot["date"].map(
                lambda d: d.year == anno_cal and d.month == mese_cal
            )
        ].sort_values(["date", "time"])

        per_giorno = {}
        for r in del_mese.itertuples(index=False):
            coach_txt = f" · {r.coach}" if str(r.coach).strip() else ""
            posti = "" if r.capacity == 1 else f" ({r.prenotati}/{r.capacity})"
            stato = (
                "pieno" if r.stato == "prenotato"
                else "chiuso" if r.stato == "bloccato" else "libero"
            )
            per_giorno.setdefault(r.date.day, []).append((
                stato,
                colore_coach.get(str(r.coach).strip(), GRIGIO),
                f"{r.time} {escape(str(r.name))}{escape(coach_txt)}{posti}",
            ))

        disegna_griglia(anno_cal, mese_cal, per_giorno)
        legenda_coach(colore_coach)
        st.caption(
            "Colore = allenatore · tinta piena e grassetto = prenotato · "
            "barrato = bloccato da una prenotazione sovrapposta — "
            f"{len(del_mese)} slot in {MESI[mese_cal - 1].lower()}"
        )

        st.divider()
        st.subheader("Modifica o elimina uno slot")

        vista_slot = vista_slot.sort_values(["date", "time"])

        if not vista_slot.empty:
            def _label_slot(sid: str) -> str:
                r = vista_slot[vista_slot["slot_id"] == sid].iloc[0]
                return (
                    f"{sid} · {r['date'].strftime('%d/%m/%Y')} {r['time']} · "
                    f"{r['name']} ({r['prenotati']}/{r['capacity']})"
                )

            with st.expander("✏️ Modifica o elimina uno slot"):
                sid_sel = st.selectbox(
                    "Slot",
                    options=list(vista_slot["slot_id"]),
                    format_func=_label_slot,
                    key="slot_edit_sel",
                )
                riga_slot = vista_slot[vista_slot["slot_id"] == sid_sel].iloc[0]

                st.markdown("**Modifica**")
                if riga_slot["prenotati"] > 0:
                    st.info(
                        "Questo slot ha già una prenotazione e non è modificabile. "
                        "Per spostarlo annulla la prenotazione e reinseriscila, "
                        "così il cliente riceve le email corrette."
                    )
                elif categories.empty:
                    st.caption("Nessuna categoria disponibile.")
                else:
                    ids_cat = list(categories["category_id"])
                    idx_cat = (
                        ids_cat.index(riga_slot["category_id"])
                        if riga_slot["category_id"] in ids_cat else 0
                    )
                    with st.form(f"modifica_slot_{sid_sel}"):
                        e1, e2 = st.columns(2)
                        e_date = e1.date_input(
                            "Data", value=riga_slot["date"],
                            key=f"slot_e_date_{sid_sel}",
                        )
                        e_time = e2.text_input(
                            "Ora (HH:MM)", value=str(riga_slot["time"]),
                            key=f"slot_e_time_{sid_sel}",
                        )
                        e_cat = st.selectbox(
                            "Tipo di test",
                            options=ids_cat,
                            index=idx_cat,
                            format_func=_label_cat_new,
                            key=f"slot_e_cat_{sid_sel}",
                        )
                        e3, e4 = st.columns(2)
                        e_cap = e3.number_input(
                            "Posti", min_value=1, max_value=50,
                            value=int(riga_slot["capacity"]),
                            key=f"slot_e_cap_{sid_sel}",
                        )
                        e_note = e4.text_input(
                            "Nota interna", value=str(riga_slot["note"]),
                            key=f"slot_e_note_{sid_sel}",
                        )
                        salva_slot = st.form_submit_button("Salva modifiche")

                    if salva_slot:
                        try:
                            ora_new = datetime.strptime(
                                e_time.strip(), "%H:%M"
                            ).strftime("%H:%M")
                        except ValueError:
                            ora_new = None

                        if ora_new is None:
                            st.error(
                                f"Orario non valido: «{e_time}». Usa il formato HH:MM."
                            )
                        else:
                            _, bloccati_edit = data.check_new_slots(
                                [(e_date, ora_new)], e_cat,
                                slots[slots["slot_id"] != sid_sel],
                                categories, bookings,
                            )
                            if bloccati_edit:
                                st.error(
                                    "Modifica non salvata: " + bloccati_edit[0][2]
                                )
                            elif data.update_slot(
                                slot_id=sid_sel,
                                date_str=e_date.isoformat(),
                                time_str=ora_new,
                                category_id=e_cat,
                                capacity=int(e_cap),
                                note=e_note,
                            ):
                                st.session_state["msg_slot"] = (
                                    f"{sid_sel} aggiornato: "
                                    f"{e_date.strftime('%d/%m/%Y')} alle {ora_new}."
                                )
                                st.rerun()
                            else:
                                st.error("Slot non trovato.")

                st.divider()
                st.markdown("**Elimina**")
                if riga_slot["prenotati"] > 0:
                    st.caption(
                        "Eliminando lo slot la prenotazione resta nel foglio "
                        "ma senza appuntamento: meglio annullarla prima."
                    )
                conferma = st.checkbox(
                    f"Confermo l'eliminazione di {sid_sel}", key="slot_del_ok"
                )
                if st.button("Elimina slot", key="slot_del_btn") and conferma:
                    if data.delete_slot(sid_sel):
                        st.session_state["msg_slot"] = f"{sid_sel} eliminato."
                        st.rerun()
                    else:
                        st.error("Slot non trovato.")

        st.divider()
        st.markdown("**Elenco slot**")

        solo_futuri = st.checkbox("Solo slot futuri", value=True, key="slot_fut")
        elenco = (
            vista_slot[vista_slot["date"] >= date.today()]
            if solo_futuri else vista_slot
        )

        st.dataframe(
            elenco[[
                "slot_id", "date", "time", "name", "coach", "stato",
                "capacity", "prenotati", "liberi", "note",
            ]],
            use_container_width=True,
            hide_index=True,
        )

# =============================================================
# PRENOTAZIONI
# =============================================================
with tab_pren:
    # =========================================================
    # INSERIMENTO MANUALE (telefono, di persona, ecc.)
    # =========================================================
    msg_manuale = st.session_state.pop("msg_manuale", None)
    if msg_manuale:
        st.success(msg_manuale)
    warn_manuale = st.session_state.pop("warn_manuale", None)
    if warn_manuale:
        st.warning(warn_manuale)

    with st.expander("➕ Inserisci una prenotazione a mano"):
        if categories.empty:
            st.warning("Crea prima almeno una categoria di test.")
        else:
            def _label_cat_man(cid: str) -> str:
                r = categories[categories["category_id"] == cid].iloc[0]
                coach = f" · {r['coach']}" if str(r["coach"]).strip() else ""
                return (
                    f"{r['name']}{coach} · {int(r['duration_min'])} min "
                    f"· € {r['price_eur']:.0f}"
                )

            # fuori dal form: cambiando categoria si aggiornano i valori sotto
            m_cat = st.selectbox(
                "Tipo di test",
                options=list(categories["category_id"]),
                format_func=_label_cat_man,
                key="man_cat",
            )
            cat_man = categories[categories["category_id"] == m_cat].iloc[0]

            with st.form(f"prenotazione_manuale_{m_cat}"):
                f1, f2, f3 = st.columns(3)
                m_date = f1.date_input("Data", value=date.today(), key="man_date")
                m_time = f2.text_input("Ora (HH:MM)", value="09:00", key="man_time")
                m_price = f3.number_input(
                    "Prezzo €", min_value=0.0,
                    value=float(cat_man["price_eur"]), step=5.0, key="man_price",
                )

                g1, g2 = st.columns(2)
                m_name = g1.text_input("Nome e cognome", key="man_name")
                m_email = g2.text_input("Email", key="man_email")

                h1, h2 = st.columns(2)
                m_phone = h1.text_input("Telefono", key="man_phone")
                m_note = h2.text_input(
                    "Nota interna (facoltativa)", key="man_note",
                    placeholder="es. prenotata al telefono",
                )

                m_mail = st.checkbox(
                    "Invia email di conferma al cliente e notifica al lab",
                    value=True, key="man_mail",
                )
                m_incassata = st.checkbox(
                    "Già incassata (registra il prezzo qui sopra come incasso)",
                    key="man_incassata",
                )
                st.caption(
                    f"Allenatore: {cat_man['coach'] or '—'} · "
                    f"durata {int(cat_man['duration_min'])} min · "
                    f"{cat_man['location']}"
                )
                crea_man = st.form_submit_button(
                    "Crea prenotazione", type="primary"
                )

            if crea_man:
                cifre_man = re.sub(r"\D", "", m_phone)
                try:
                    ora_man = datetime.strptime(
                        m_time.strip(), "%H:%M"
                    ).strftime("%H:%M")
                except ValueError:
                    ora_man = None

                if not m_name.strip():
                    st.error("Inserisci nome e cognome.")
                elif "@" not in m_email or "." not in m_email.split("@")[-1]:
                    st.error("Inserisci un indirizzo email valido.")
                elif len(cifre_man) < 8:
                    st.error("Inserisci un numero di telefono valido.")
                elif ora_man is None:
                    st.error(f"Orario non valido: «{m_time}». Usa il formato HH:MM.")
                else:
                    ok_man, bloccati_man = data.check_new_slots(
                        [(m_date, ora_man)], m_cat, slots, categories, bookings
                    )
                    if bloccati_man:
                        st.error(
                            "Prenotazione non creata: "
                            + bloccati_man[0][2]
                        )
                    else:
                        with st.spinner("Registro..."):
                            sid = data.add_slots_bulk([(
                                m_date.isoformat(), ora_man, m_cat, 1,
                                m_note.strip() or "inserita a mano",
                            )])[0]
                            ref_man = data.add_booking(
                                sid, m_name, m_email, m_phone
                            )
                            if m_incassata:
                                data.mark_paid_bulk({ref_man: float(m_price)})

                            errori_man = {}
                            if m_mail:
                                errori_man = mailer.send_booking_emails(
                                    to=m_email,
                                    name=m_name.strip(),
                                    title=cat_man["name"],
                                    date_str=m_date.strftime("%d/%m/%Y"),
                                    time_str=ora_man,
                                    ref=ref_man,
                                    coach=cat_man["coach"],
                                    location=cat_man["location"],
                                    duration_min=int(cat_man["duration_min"] or 0),
                                    price_eur=float(m_price),
                                    # se è già incassata non serve il link di pagamento
                                    payment_link=(
                                        "" if m_incassata
                                        else cat_man["payment_link"]
                                    ),
                                    description=cat_man["description"],
                                    phone=m_phone.strip(),
                                )

                        st.session_state["msg_manuale"] = (
                            f"Prenotazione {ref_man} creata su slot {sid} — "
                            f"{cat_man['name']}, {m_date.strftime('%d/%m/%Y')} "
                            f"alle {ora_man}."
                            + (f" Incassata € {float(m_price):,.2f}."
                               if m_incassata else "")
                        )
                        if errori_man:
                            st.session_state["warn_manuale"] = (
                                "Prenotazione registrata, ma alcune email non "
                                "sono partite: "
                                + "; ".join(
                                    f"{k} — {v}" for k, v in errori_man.items()
                                )
                            )
                        st.rerun()

    st.divider()

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
        merged["coach"] = merged["coach"].fillna("")

        # ---------- filtro allenatore (vale per tutta la scheda) ----------
        coach_pren = ["tutti"] + sorted(
            {str(c).strip() for c in merged["coach"] if str(c).strip()}
        )
        filtro_coach_pren = st.selectbox(
            "Allenatore",
            options=coach_pren,
            format_func=lambda c: "Tutti gli allenatori" if c == "tutti" else c,
            key="pren_coach",
            disabled=len(coach_pren) < 3,
        )
        if filtro_coach_pren != "tutti":
            merged = merged[
                merged["coach"].astype(str).str.strip() == filtro_coach_pren
            ]

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

        # ---------- vista calendario ----------
        st.divider()
        st.markdown("**Vista calendario**")

        anno_pren, mese_pren = navigatore_mese("pren")
        colore_coach_pren = colori_per_coach(categories)

        pren_mese = merged[
            merged["date"].notna()
            & merged["date"].map(
                lambda d: d.year == anno_pren and d.month == mese_pren
                if pd.notna(d) else False
            )
        ].sort_values(["date", "time"])

        per_giorno_pren = {}
        for r in pren_mese.itertuples(index=False):
            if r.status in data.INACTIVE_STATUSES:
                stato = "chiuso"
            elif r.paid == "si":
                stato = "pieno"
            else:
                stato = "aperto"
            etichetta = f"{r.time} {escape(str(r.cliente))}"
            if str(r.test).strip():
                etichetta += f" · {escape(str(r.test))}"
            per_giorno_pren.setdefault(r.date.day, []).append((
                stato,
                colore_coach_pren.get(str(r.coach).strip(), GRIGIO),
                etichetta,
            ))

        disegna_griglia(anno_pren, mese_pren, per_giorno_pren)
        legenda_coach(colore_coach_pren)
        st.caption(
            "Colore = allenatore · tinta piena e grassetto = incassata · "
            "barrato = annullata o rimborsata — "
            f"{len(pren_mese)} prenotazioni in {MESI[mese_pren - 1].lower()}"
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
                "L'importo incassato è diverso da quello a schermo",
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
        with st.expander("✖️ Annulla una prenotazione"):
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

        with st.expander("✏️ Modifica o elimina una categoria"):
            st.markdown("**Modifica**")
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

            st.divider()
            st.markdown("**Elimina**")
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