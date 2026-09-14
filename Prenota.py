import re
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

import data
import mailer

st.set_page_config(
    page_title="Prenota un appuntamento", layout="centered"
)

EMAIL_LAB = "valchiusellamountainlab@gmail.com"

TERMINI = """
**PRESTAZIONI**

I servizi offerti hanno natura esclusivamente sportiva e non costituiscono in
alcun modo prestazione sanitaria, medica o diagnostica. I test non sono
finalizzati alla diagnosi, prevenzione o cura di alcuna patologia, non
sostituiscono la visita medico-sportiva né il rilascio di certificazioni di
idoneità, e non sono eseguiti da personale medico. I risultati hanno finalità
esclusivamente allenante e di monitoraggio della prestazione.

L'accesso ai test è riservato a soggetti maggiorenni in buono stato di salute.

Il Cliente dichiara e garantisce, sotto la propria responsabilità:

a) di essere in possesso di certificato medico di idoneità all'attività
sportiva agonistica in corso di validità, che si impegna a esibire prima
dell'inizio del test;

b) di non essere a conoscenza di alcuna condizione, patologia, infortunio o
terapia in corso che renda sconsigliabile o pericoloso lo svolgimento di uno
sforzo fisico intenso e progressivo fino a esaurimento;

c) di aver compilato in modo veritiero e completo il questionario anamnestico
pre-test fornito dal Laboratorio.

Il Laboratorio si riserva il diritto insindacabile di non erogare il test in
assenza di certificato valido, in caso di dichiarazioni incomplete, o qualora
ritenga che le condizioni del Cliente non ne consentano lo svolgimento in
sicurezza.

**PRENOTAZIONE E PAGAMENTO**

La prenotazione si perfeziona esclusivamente con il pagamento integrale del
corrispettivo tramite la piattaforma Stripe al momento della richiesta. Gli
slot sono confermati in ordine di pagamento ricevuto e in numero limitato.

Il contratto si intende concluso con l'invio da parte del Laboratorio della
email di conferma contenente data, ora e tipologia di test.

Il Cliente riceve fattura elettronica sulla base dei dati di fatturazione da
lui inseriti nella piattaforma Stripe al momento del pagamento. È onere del
Cliente fornire dati corretti e completi.

**CANCELLAZIONI E RIMBORSI**

Le cancellazioni devono essere comunicate via email a
valchiusellamountainlab@gmail.com. Fa fede l'orario di ricezione della email da
parte del Laboratorio.

Cancellazione con più di 144 ore (6 giorni) di preavviso rispetto all'orario
dell'appuntamento: nessuna penale. Il Laboratorio invia all'indirizzo email
utilizzato per la prenotazione un buono sconto pari al 100% del corrispettivo
versato, utilizzabile per una prenotazione successiva.

Cancellazione con preavviso compreso tra 72 ore (3 giorni) e 144 ore
(6 giorni): il Laboratorio invia all'indirizzo email utilizzato per la
prenotazione un buono sconto pari al 50% del corrispettivo versato,
utilizzabile per una prenotazione successiva. Il restante 50% è trattenuto a
titolo di penale.

Cancellazione con meno di 72 ore (3 giorni) di preavviso: nessun rimborso e
nessun buono sconto.

Le somme non rimborsate sono trattenute a titolo di penale ai sensi dell'art.
1382 c.c., a ristoro forfettario del mancato utilizzo dello slot e delle
risorse riservate. Le parti riconoscono tali importi congrui e proporzionati
rispetto all'interesse del Laboratorio.
"""

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

st.title("Prenota un appuntamento")


def blocco_termini() -> None:
    """Avviso sulle cancellazioni piu' termini e condizioni, in fondo alla pagina."""
    st.divider()
    st.warning(
        "Per cancellare o spostare una prenotazione è necessario inviare "
        f"una mail a {EMAIL_LAB}"
    )
    with st.expander("Termini e condizioni"):
        st.markdown(TERMINI)


try:
    categories = data.load_categories()
    slots = data.load_slots()
    bookings = data.load_bookings()
except Exception:
    st.error("Impossibile caricare il calendario. Riprova tra un momento.")
    blocco_termini()
    st.stop()

vista_base = data.slots_with_category(slots, categories)

if vista_base.empty:
    st.info("Nessun appuntamento disponibile al momento.")
    blocco_termini()
    st.stop()

upcoming = vista_base[vista_base["date"] >= date.today()]
if upcoming.empty:
    st.info("Nessun appuntamento disponibile al momento.")
    blocco_termini()
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
    blocco_termini()
    st.stop()

# --- filtri ---

c1, c2, c3 = st.columns(3)

cat_options = ["tutti"] + sorted(upcoming["category_id"].unique().tolist())
nomi_cat = dict(zip(upcoming["category_id"], upcoming["name"]))

filtro_cat = c1.selectbox(
    "Tipo di appuntamento",
    options=cat_options,
    format_func=lambda c: "Tutti" if c == "tutti" else nomi_cat.get(c, c),
)

periodo = c2.selectbox(
    "Periodo",
    options=[
        "prossima_settimana", "questa_settimana",
        "questo_mese", "prossimo_mese", "tutti",
    ],
    format_func=lambda p: {
        "tutti": "Tutte le date",
        "questa_settimana": "📅 Questa settimana",
        "prossima_settimana": "📅 Prossima settimana",
        "questo_mese": "🗓️ Questo mese",
        "prossimo_mese": "🗓️ Prossimo mese",
    }[p],
)

coach_options = ["tutti"] + sorted(
    {str(c).strip() for c in upcoming["coach"] if str(c).strip()}
)
filtro_coach = c3.selectbox(
    "Allenatore",
    options=coach_options,
    format_func=lambda c: "Tutti" if c == "tutti" else c,
    disabled=len(coach_options) < 3,
)


def primo_del_mese_dopo(giorno: date) -> date:
    """Primo giorno del mese successivo a quello di `giorno`."""
    if giorno.month == 12:
        return date(giorno.year + 1, 1, 1)
    return date(giorno.year, giorno.month + 1, 1)


oggi = date.today()
lunedi = oggi - timedelta(days=oggi.weekday())
domenica = lunedi + timedelta(days=6)
inizio_prossimo_mese = primo_del_mese_dopo(oggi)
inizio_terzo_mese = primo_del_mese_dopo(inizio_prossimo_mese)

vista = upcoming
if filtro_cat != "tutti":
    vista = vista[vista["category_id"] == filtro_cat]
if filtro_coach != "tutti":
    vista = vista[vista["coach"].astype(str).str.strip() == filtro_coach]
if periodo == "questa_settimana":
    vista = vista[vista["date"] <= domenica]
elif periodo == "prossima_settimana":
    vista = vista[
        (vista["date"] > domenica) & (vista["date"] <= domenica + timedelta(days=7))
    ]
elif periodo == "questo_mese":
    vista = vista[vista["date"] < inizio_prossimo_mese]
elif periodo == "prossimo_mese":
    vista = vista[
        (vista["date"] >= inizio_prossimo_mese)
        & (vista["date"] < inizio_terzo_mese)
    ]

vista = vista.sort_values(["date", "time"])

st.divider()

GIORNI = {
    0: "lunedì", 1: "martedì", 2: "mercoledì", 3: "giovedì",
    4: "venerdì", 5: "sabato", 6: "domenica",
}


def etichetta(row) -> str:
    giorno = GIORNI[row.date.weekday()]
    coach = f" con {row.coach}" if str(row.coach).strip() else ""
    prezzo = f" — € {row.price_eur:.0f}" if row.price_eur else ""
    stato = "" if row.capacity == 1 else f"  ·  _{row.free} posti_"
    return (
        f"**{row.name}**{coach} — {giorno} {row.date.strftime('%d/%m/%Y')}, "
        f"ore {row.time}{prezzo}{stato}"
    )


disponibili = list(vista.itertuples(index=False))

if not disponibili:
    st.warning("Nessuno slot libero con questi filtri.")
    blocco_termini()
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
if str(choice.coach).strip():
    dettagli.append(f"Con {choice.coach}")
if choice.duration_min:
    dettagli.append(f"Durata: circa {int(choice.duration_min)} minuti")
if choice.price_eur:
    dettagli.append(f"Costo: € {choice.price_eur:.2f}")
if choice.note:
    dettagli.append(str(choice.note))
if dettagli:
    st.caption("  ·  ".join(dettagli))

# Si paga solo tramite Stripe: uno slot a pagamento senza link non e' prenotabile.
pagamento_mancante = bool(choice.price_eur) and not str(choice.payment_link).strip()
if pagamento_mancante:
    st.error(
        "Questo appuntamento non è prenotabile online in questo momento: "
        f"manca il link di pagamento. Scrivimi a {EMAIL_LAB} e lo sistemo."
    )

# --- form ---

with st.form("booking_form"):
    name = st.text_input("Nome e cognome")
    email = st.text_input("Email")
    phone = st.text_input("Telefono", placeholder="es. 333 1234567")
    consent = st.checkbox(
        "Acconsento al trattamento dei miei dati per la gestione dell'appuntamento."
    )
    accetta = st.checkbox(
        "Ho letto e accetto i termini e condizioni, e approvo specificamente le "
        "clausole su cancellazioni, rimborsi e penale (art. 1382 c.c.)."
    )
    st.caption("Trovi il testo completo in fondo alla pagina.")
    submitted = st.form_submit_button(
        "Conferma appuntamento", type="primary", disabled=pagamento_mancante
    )

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
    elif not accetta:
        st.error("Devi accettare i termini e condizioni per procedere.")
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
                        "Trovi lo stesso link nella mail di conferma. "
                        "La prenotazione si perfeziona con il pagamento."
                    )

                st.balloons()

                errori = mailer.send_booking_emails(
                    to=email,
                    name=name.strip(),
                    title=choice.name,
                    date_str=choice.date.strftime("%d/%m/%Y"),
                    time_str=choice.time,
                    ref=ref,
                    coach=choice.coach,
                    location=choice.location,
                    duration_min=int(choice.duration_min or 0),
                    price_eur=float(choice.price_eur or 0),
                    payment_link=choice.payment_link,
                    description=choice.description,
                    phone=phone.strip(),
                )

                # La notifica interna non riguarda il cliente: se fallisce la
                # registro nei log di Streamlit Cloud senza dirglielo.
                if "lab" in errori:
                    print(
                        f"[NOTIFICA LAB FALLITA] ref={ref} "
                        f"slot={choice.slot_id} email={email} — {errori['lab']}"
                    )

                if "cliente" in errori:
                    st.warning(
                        "Appuntamento registrato, ma l'email di conferma non è partita. "
                        f"Conserva il codice {ref}."
                    )
                    st.caption(f"Debug: {errori['cliente']}")
                else:
                    st.caption(
                        "Ti ho mandato una mail di conferma. Se non la trovi, "
                        "controlla nello spam e segnala il messaggio come attendibile."
                    )

blocco_termini()