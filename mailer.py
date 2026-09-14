"""Invio email di conferma, cancellazione e notifica interna — Valchiusella Mountain Lab."""

import smtplib
from email.message import EmailMessage

import streamlit as st


def _cfg() -> dict:
    """Legge e valida la configurazione email dai secrets."""
    try:
        cfg = dict(st.secrets["email"])
    except KeyError:
        raise RuntimeError(
            "Configurazione email assente: manca la sezione [email] nei secrets."
        )
    mancanti = [k for k in ("sender", "app_password", "lab_name") if not cfg.get(k)]
    if mancanti:
        raise RuntimeError(f"Configurazione email incompleta: {', '.join(mancanti)}")
    return cfg


def _send(to: str, subject: str, body: str, reply_to: str = "") -> None:
    cfg = _cfg()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{cfg['lab_name']} <{cfg['sender']}>"
    msg["To"] = to
    msg["Reply-To"] = reply_to.strip() or cfg.get("reply_to", cfg["sender"])
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
        smtp.login(cfg["sender"], cfg["app_password"])
        smtp.send_message(msg)


def _euro(valore: float) -> str:
    """300.0 -> '300,00'."""
    return f"{valore:.2f}".replace(".", ",")


def _blocco_dove(cfg: dict, location: str, maps_url: str) -> str:
    """Indirizzo leggibile piu' link Maps esplicito, quando disponibili."""
    indirizzo = location.strip() or str(cfg.get("lab_address", "")).strip()
    mappa = maps_url.strip() or str(cfg.get("lab_maps_url", "")).strip()

    if not indirizzo:
        return "Ci vediamo in laboratorio."

    righe = [f"Ci vediamo qui: {indirizzo}"]
    if mappa:
        righe.append(f"Posizione esatta sulla mappa: {mappa}")
    return "\n".join(righe)


def _riga(etichetta: str, valore: str) -> str:
    return f"  {etichetta:<10}{valore}"


# --------------------------------------------------------------------------
# Mail al cliente
# --------------------------------------------------------------------------

def send_confirmation(
    to: str, name: str, title: str, date_str: str, time_str: str,
    ref: str, coach: str = "", location: str = "", duration_min: int = 0,
    price_eur: float = 0.0, payment_link: str = "", description: str = "",
    maps_url: str = "", phone: str = "", notes: str = "",
) -> None:
    """Conferma inviata al cliente. `phone` e `notes` sono ignorati qui:
    servono solo perche' la stessa mappa di dati alimenti anche la notifica interna."""
    cfg = _cfg()
    lab = cfg["lab_name"]

    durata = f" (durata prevista: circa {duration_min} minuti)" if duration_min else ""
    dove = _blocco_dove(cfg, location, maps_url)

    if payment_link.strip():
        pagamento = (
            f"Il costo e' di {_euro(price_eur)} euro. La prenotazione si perfeziona\n"
            "con il pagamento, che puoi effettuare qui:\n\n"
            f"  {payment_link.strip()}\n"
        )
    elif price_eur:
        pagamento = (
            f"Il costo e' di {_euro(price_eur)} euro. Ti mando a breve il link\n"
            "per il pagamento."
        )
    else:
        pagamento = ""

    extra = f"\n{description.strip()}\n" if description.strip() else ""

    con_chi = f" con {coach.strip()}" if coach.strip() else ""

    body = f"""Ciao {name},

ti confermo l'appuntamento per {title}{con_chi} del {date_str} alle {time_str}{durata}.

{dove}
{extra}
{pagamento}

Codice appuntamento: {ref}

Se poi non riesci a venire scrivimi rispondendo qui, cosi' libero lo slot per qualcun altro.

A presto,
{lab}
"""
    _send(to, f"Appuntamento confermato - {title}, {date_str}", body)


def send_cancellation(
    to: str, name: str, title: str, date_str: str, time_str: str
) -> None:
    lab = _cfg()["lab_name"]
    body = f"""Ciao {name},

il tuo appuntamento per {title} del {date_str} alle {time_str} e' stato annullato.

Se vuoi riprogrammarlo rispondi pure a questa mail.

{lab}
"""
    _send(to, f"Appuntamento annullato - {title}, {date_str}", body)


# --------------------------------------------------------------------------
# Notifica interna al laboratorio
# --------------------------------------------------------------------------

def send_admin_notification(
    to: str, name: str, title: str, date_str: str, time_str: str,
    ref: str, coach: str = "", location: str = "", duration_min: int = 0,
    price_eur: float = 0.0, payment_link: str = "", description: str = "",
    maps_url: str = "", phone: str = "", notes: str = "",
) -> None:
    """Riepilogo della prenotazione inviato al laboratorio.

    Attenzione: `to` e' l'indirizzo del CLIENTE, non il destinatario.
    Viene usato come Reply-To cosi' un semplice 'rispondi' scrive al cliente.
    Il destinatario vero e' `admin_to` nei secrets (fallback: `sender`).
    """
    cfg = _cfg()
    destinatario = str(cfg.get("admin_to") or cfg["sender"]).strip()

    sede = location.strip() or str(cfg.get("lab_address", "")).strip() or "-"

    appuntamento = [
        "APPUNTAMENTO",
        _riga("Tipo:", title),
        _riga("Data:", date_str),
        _riga("Ora:", time_str),
    ]
    if duration_min:
        appuntamento.append(_riga("Durata:", f"{duration_min} minuti"))
    if coach.strip():
        appuntamento.append(_riga("Coach:", coach.strip()))
    appuntamento.append(_riga("Sede:", sede))

    cliente = [
        "CLIENTE",
        _riga("Nome:", name),
        _riga("Email:", to),
    ]
    if phone.strip():
        cliente.append(_riga("Telefono:", phone.strip()))

    pagamento = ["PAGAMENTO"]
    if price_eur:
        pagamento.append(_riga("Importo:", f"{_euro(price_eur)} euro"))
    else:
        pagamento.append(_riga("Importo:", "non indicato"))
    if payment_link.strip():
        pagamento.append(_riga("Modalita:", "link di pagamento inviato al cliente"))
        pagamento.append(_riga("Link:", payment_link.strip()))
    elif price_eur:
        pagamento.append(
            _riga("ATTENZIONE:", "link di pagamento mancante, va inviato a mano")
        )

    sezioni = [
        "\n".join(appuntamento),
        "\n".join(cliente),
        "\n".join(pagamento),
        f"Codice appuntamento: {ref}",
    ]

    if description.strip():
        sezioni.append(f"DESCRIZIONE\n  {description.strip()}")
    if notes.strip():
        sezioni.append(f"NOTE DEL CLIENTE\n  {notes.strip()}")

    body = "Nuova prenotazione ricevuta.\n\n" + "\n\n".join(sezioni) + "\n"

    subject = f"Nuova prenotazione - {date_str} {time_str} - {title} - {name}"
    _send(destinatario, subject, body, reply_to=to)


def send_booking_emails(
    to: str, name: str, title: str, date_str: str, time_str: str,
    ref: str, coach: str = "", location: str = "", duration_min: int = 0,
    price_eur: float = 0.0, payment_link: str = "", description: str = "",
    maps_url: str = "", phone: str = "", notes: str = "",
) -> dict[str, str]:
    """Manda conferma al cliente e notifica al laboratorio in modo indipendente.

    Restituisce un dizionario degli errori, vuoto se e' andato tutto bene:
      - chiave "cliente" -> la conferma al cliente non e' partita
      - chiave "lab"     -> la notifica interna non e' partita
    Un fallimento non impedisce l'altro invio.
    """
    dati = dict(
        to=to, name=name, title=title, date_str=date_str, time_str=time_str,
        ref=ref, coach=coach, location=location, duration_min=duration_min,
        price_eur=price_eur, payment_link=payment_link, description=description,
        maps_url=maps_url, phone=phone, notes=notes,
    )

    errori: dict[str, str] = {}
    for chiave, funzione in (
        ("cliente", send_confirmation),
        ("lab", send_admin_notification),
    ):
        try:
            funzione(**dati)
        except Exception as exc:
            errori[chiave] = f"{type(exc).__name__} — {exc}"
    return errori