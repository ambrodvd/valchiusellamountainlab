"""Invio email di conferma e cancellazione — Valchiusella Mountain Lab."""

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


def _send(to: str, subject: str, body: str) -> None:
    cfg = _cfg()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{cfg['lab_name']} <{cfg['sender']}>"
    msg["To"] = to
    msg["Reply-To"] = cfg.get("reply_to", cfg["sender"])
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
        smtp.login(cfg["sender"], cfg["app_password"])
        smtp.send_message(msg)


def send_confirmation(
    to: str, name: str, title: str, date_str: str, time_str: str,
    ref: str, location: str = "", duration_min: int = 0,
    price_eur: float = 0.0, payment_link: str = "", description: str = "",
) -> None:
    cfg = _cfg()
    lab = cfg["lab_name"]

    durata = f" (durata prevista: circa {duration_min} minuti)" if duration_min else ""
    dove = f"Ci vediamo qui: {location}" if location.strip() else "Ci vediamo in laboratorio."

    if payment_link.strip():
        pagamento = (
            f"Il costo e' di {price_eur:.2f} euro. Puoi saldare da qui:\n\n"
            f"  {payment_link.strip()}\n\n"
            "Se preferisci pagare sul posto scrivimelo pure rispondendo a questa mail."
        )
    elif price_eur:
        pagamento = f"Il costo e' di {price_eur:.2f} euro, da saldare sul posto."
    else:
        pagamento = ""

    extra = f"\n{description.strip()}\n" if description.strip() else ""

    body = f"""Ciao {name},

ti confermo l'appuntamento per {title} del {date_str} alle {time_str}{durata}.

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
