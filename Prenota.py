import re
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

import data
import mailer

st.set_page_config(
    page_title="Prenota un appuntamento", page_icon="🏔️", layout="centered"
)

# --- logo ---

try:
    _tema = st.context.theme.type          # "light" oppure "dark"
except Exception:
    _tema = "light"

LOGO = Path(__file__).parent / (
    "logo_vmh_bianco.png" if _tema == "dark" else "logo_vmh_blu.png"
)
if LOGO.exists():
    _, center, _ = st.columns([1, 2, 1])
    center.image(str(LOGO), use_container_width=True)

st.title("🏔️ Prenota un appuntamento")

try:
    categories = data.load_categories()
    slots = data.load_slots()
    bookings = data.load_bookings()
except Exception:
    st.error("Impossibile caricare il calendario. Riprova tra un momento.")
    st.stop()

vista_base = data.slots_with_category(slots, categories)

if vista_base.empty:
    st.info("Nessun appuntamento disponibile al momento.")
    st.stop()

upcoming = vista_base[vista_base["date"] >= date.today()]
if upcoming.empty:
    st.info("Nessun appuntamento disponibile al momento.")
    st.stop()

taken = data.seats_taken(bookings)
upcoming = upcoming.assign(
    booked=lambda d: d["slot_id"].map(taken).fillna(0).astype(int)
)
upcoming = upcoming.assign(free=lambda d: (d["capacity"] - d["booked"]).clip(lower=0))

# solo slot con posti liberi: quelli pieni non vengono mostrati affatto
upcoming = upcoming[upcoming["free"] > 0]

if upcoming.empty:
    st.info("Al momento non ci sono slot liberi. Riprova tra qualche giorno.")
    st.stop()

# --- filtri ---

c1, c2 = st.columns(2)

cat_options = ["tutti"] + sorted(upcoming["category_id"].unique().tolist())
nomi_cat = dict(zip(upcoming["category_id"], upcoming["name"]))

filtro_cat = c1.selectbox(
    "Tipo di appuntamento",
    options=cat_options,
    format_func=lambda c: "Tutti" if c == "tutti" else nomi_cat.get(c, c),
)

periodo = c2.selectbox(
    "Periodo",
    options=["tutti", "questa_settimana", "prossima_settimana"],
    format_func=lambda p: {
        "tutti": "Tutte le date",
        "questa_settimana": "📅 Questa settimana",
        "prossima_settimana": "📅 Prossima settimana",
    }[p],
)

oggi = date.today()
lunedi = oggi - timedelta(days=oggi.weekday())
domenica = lunedi + timedelta(days=6)

vista = upcoming
if filtro_cat != "tutti":
    vista = vista[vista["category_id"] == filtro_cat]
if periodo == "questa_settimana":
    vista = vista[vista["date"] <= domenica]
elif periodo == "prossima_settimana":
    vista = vista[
        (vista["date"] > domenica) & (vista["date"] <= domenica + timedelta(days=7))
    ]

vista = vista.sort_values(["date", "time"])

st.divider()

GIORNI = {
    0: "lunedì", 1: "martedì", 2: "mercoledì", 3: "giovedì",
    4: "venerdì", 5: "sabato", 6: "domenica",
}


def etichetta(row) -> str:
    giorno = GIORNI[row.date.weekday()]
    prezzo = f" — € {row.price_eur:.0f}" if row.price_eur else ""
    stato = "" if row.capacity == 1 else f"  ·  _{row.free} posti_"
    return (
        f"**{row.name}** — {giorno} {row.date.strftime('%d/%m/%Y')}, "
        f"ore {row.time}{prezzo}{stato}"
    )


disponibili = list(vista.itertuples(index=False))

if not disponibili:
    st.warning("Nessuno slot libero con questi filtri.")
    st.stop()

st.caption(f"{len(disponibili)} appuntamenti disponibili")

choice = st.radio(
    "Scegli lo slot",
    options=disponibili,
    format_func=etichetta,
    label_visibility="collapsed",
)

st.divider()

if choice.location:
    st.info(f"📍 {choice.location}")
if choice.description:
    st.markdown(choice.description)

dettagli = []
if choice.duration_min:
    dettagli.append(f"Durata: circa {int(choice.duration_min)} minuti")
if choice.price_eur:
    dettagli.append(f"Costo: € {choice.price_eur:.2f}")
if choice.note:
    dettagli.append(str(choice.note))
if dettagli:
    st.caption("  ·  ".join(dettagli))

# --- form ---

with st.form("booking_form"):
    name = st.text_input("Nome e cognome")
    email = st.text_input("Email")
    phone = st.text_input("Telefono", placeholder="es. 333 1234567")
    consent = st.checkbox(
        "Acconsento al trattamento dei miei dati per la gestione dell'appuntamento."
    )
    submitted = st.form_submit_button("Conferma appuntamento", type="primary")

if submitted:
    cifre = re.sub(r"\D", "", phone)
    if not name.strip():
        st.error("Inserisci il tuo nome.")
    elif "@" not in email or "." not in email.split("@")[-1]:
        st.error("Inserisci un indirizzo email valido.")
    elif len(cifre) < 8:
        st.error("Inserisci un numero di telefono valido.")
    elif not consent:
        st.error("Devi accettare l'informativa per procedere.")
    else:
        with st.spinner("Confermo..."):
            if data.already_booked(choice.slot_id, email):
                st.warning("Risulti già prenotato per questo slot.")
            elif data.count_live(choice.slot_id) >= choice.capacity:
                st.error("Qualcuno ha appena preso questo slot. Scegline un altro.")
                data.load_bookings.clear()
            else:
                ref = data.add_booking(choice.slot_id, name, email, phone)

                st.success(
                    f"Prenotato — {choice.name} il "
                    f"{choice.date.strftime('%d/%m/%Y')} alle {choice.time}.\n\n"
                    f"Codice: **{ref}**"
                )

                if choice.payment_link:
                    st.link_button(
                        f"Paga ora € {choice.price_eur:.2f}",
                        choice.payment_link,
                        type="primary",
                    )
                    st.caption(
                        "Trovi lo stesso link nella mail di conferma: "
                        "puoi pagare anche più tardi."
                    )
                elif choice.price_eur:
                    st.info(f"Costo: € {choice.price_eur:.2f}, da saldare sul posto.")

                st.balloons()

                try:
                    mailer.send_confirmation(
                        to=email,
                        name=name.strip(),
                        title=choice.name,
                        date_str=choice.date.strftime("%d/%m/%Y"),
                        time_str=choice.time,
                        ref=ref,
                        location=choice.location,
                        duration_min=int(choice.duration_min or 0),
                        price_eur=float(choice.price_eur or 0),
                        payment_link=choice.payment_link,
                        description=choice.description,
                    )
                    st.caption(
                        "Ti ho mandato una mail di conferma. Se non la trovi, "
                        "controlla nello spam e segnala il messaggio come attendibile."
                    )
                except Exception as exc:
                    st.warning(
                        "Appuntamento registrato, ma l'email di conferma non è partita. "
                        f"Conserva il codice {ref}."
                    )
                    st.caption(f"Debug: {type(exc).__name__} — {exc}")