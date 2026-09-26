"""Data access layer. Google Sheets — Valchiusella Mountain Lab.

Scritture e letture avvengono per NOME di intestazione (minuscolo, senza
spazi), mai per posizione: l'ordine delle colonne nel foglio non conta.
"""

import uuid
from datetime import datetime, timedelta

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_LOCATION = "Valchiusella Mountain Lab"

CATEGORY_COLUMNS = [
    "category_id", "name", "coach", "location", "duration_min",
    "price_eur", "payment_link", "description",
]

SLOT_COLUMNS = [
    "slot_id", "date", "time", "category_id", "capacity", "note",
]

# colonne indispensabili per registrare una prenotazione
BOOKING_CORE = [
    "booking_id", "slot_id", "name", "email",
    "phone", "timestamp", "status", "paid",
]

# importi: amount_paid = incassato davvero (può differire dal listino per
# sconti o compensazioni), amount_refunded = quanto è stato restituito
BOOKING_COLUMNS = BOOKING_CORE + ["amount_paid", "amount_refunded"]

# stati che NON occupano lo slot
INACTIVE_STATUSES = ("cancelled", "refunded")

STATUS_LABELS = {
    "confirmed": "Confermata",
    "cancelled": "Annullata",
    "refunded": "Rimborsata",
}


def norm_email(value: str) -> str:
    return str(value or "").strip().lower()


def _is_active(status) -> bool:
    s = str(status or "confirmed").strip().lower() or "confirmed"
    return s not in INACTIVE_STATUSES


@st.cache_resource(show_spinner=False)
def _client() -> gspread.Client:
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)


def _sheet(tab: str) -> gspread.Worksheet:
    return _client().open_by_key(st.secrets["spreadsheet_id"]).worksheet(tab)


# -------------------------------------------------------------
# Helper: lavorare per nome di colonna, non per posizione
# -------------------------------------------------------------

def headers(tab: str) -> list[str]:
    """Intestazioni reali della riga 1, normalizzate a minuscolo senza spazi."""
    return [h.strip().lower() for h in _sheet(tab).row_values(1)]


def _records(tab: str) -> list[dict]:
    """get_all_records con chiavi normalizzate a minuscolo senza spazi."""
    return [
        {str(k).strip().lower(): v for k, v in r.items()}
        for r in _sheet(tab).get_all_records()
    ]


def _check_headers(tab: str, attese: list[str]) -> list[str]:
    reali = headers(tab)
    mancanti = [c for c in attese if c not in reali]
    if mancanti:
        raise RuntimeError(
            f"Nella tab «{tab}» mancano le colonne: {', '.join(mancanti)}. "
            f"Intestazioni trovate: {reali}"
        )
    return reali


def _row_for(reali: list[str], valori: dict):
    """Ordina i valori secondo le intestazioni reali del foglio."""
    return [valori.get(h, "") for h in reali]


def _col_index(tab: str, colonna: str) -> int:
    """Indice 1-based della colonna nel foglio."""
    reali = _check_headers(tab, [colonna])
    return reali.index(colonna) + 1


def _to_num(value) -> float:
    """Numero da cella: gestisce 120, 120.5, "120,50", "1.200,50", "€ 90"."""
    if value is None:
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    s = (
        str(value).strip().replace("€", "")
        .replace(" ", "").replace("\u00a0", "")
    )
    if not s:
        return float("nan")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _parse_time(value):
    s = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%H.%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def clear_all_caches() -> None:
    load_categories.clear()
    load_slots.clear()
    load_bookings.clear()


# =============================================================
# CATEGORIE (tipi di test)
# =============================================================

@st.cache_data(ttl=120, show_spinner=False)
def load_categories() -> pd.DataFrame:
    df = pd.DataFrame(_records("categories"))
    if df.empty:
        return pd.DataFrame(columns=CATEGORY_COLUMNS)
    for col in CATEGORY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["category_id"] = df["category_id"].astype(str).str.strip()
    for col in ("name", "coach", "payment_link", "description"):
        df[col] = df[col].astype(str).fillna("").str.strip()
    df["location"] = (
        df["location"].astype(str).fillna("").str.strip().replace("", DEFAULT_LOCATION)
    )
    df["duration_min"] = (
        pd.to_numeric(df["duration_min"], errors="coerce").fillna(60).astype(int)
    )
    df["price_eur"] = df["price_eur"].map(_to_num).fillna(0.0)
    return df[CATEGORY_COLUMNS]


def coach_list(categories: pd.DataFrame) -> list[str]:
    """Allenatori già usati, per il completamento nei form."""
    if categories.empty:
        return []
    return sorted({c.strip() for c in categories["coach"] if str(c).strip()})


def payment_link_for_coach(categories: pd.DataFrame, coach: str) -> str:
    """Ultimo link di pagamento noto per quell'allenatore."""
    if categories.empty or not str(coach).strip():
        return ""
    righe = categories[
        (categories["coach"].str.strip().str.lower() == str(coach).strip().lower())
        & (categories["payment_link"].str.strip() != "")
    ]
    return "" if righe.empty else str(righe.iloc[-1]["payment_link"]).strip()


def next_category_id() -> str:
    nums = []
    for r in _records("categories"):
        val = str(r.get("category_id", "")).strip().upper()
        if val.startswith("C") and val[1:].isdigit():
            nums.append(int(val[1:]))
    return f"C{(max(nums) + 1) if nums else 1:03d}"


def _category_values(
    category_id: str, name: str, coach: str, location: str,
    duration_min: int, price_eur: float, payment_link: str, description: str,
) -> dict:
    return {
        "category_id": str(category_id),
        "name": name.strip(),
        "coach": coach.strip(),
        "location": location.strip() or DEFAULT_LOCATION,
        "duration_min": int(duration_min),
        "price_eur": float(price_eur),
        "payment_link": payment_link.strip(),
        "description": description.strip(),
    }


def add_category(
    name: str, coach: str, location: str, duration_min: int,
    price_eur: float, payment_link: str, description: str = "",
) -> str:
    reali = _check_headers("categories", CATEGORY_COLUMNS)
    category_id = next_category_id()
    valori = _category_values(
        category_id, name, coach, location,
        duration_min, price_eur, payment_link, description,
    )
    _sheet("categories").append_row(
        _row_for(reali, valori), value_input_option="USER_ENTERED"
    )
    load_categories.clear()
    return category_id


def update_category(
    category_id: str, name: str, coach: str, location: str, duration_min: int,
    price_eur: float, payment_link: str, description: str = "",
) -> bool:
    reali = _check_headers("categories", CATEGORY_COLUMNS)
    ws = _sheet("categories")
    col_id = reali.index("category_id") + 1

    cell = ws.find(str(category_id).strip())
    if cell is None or cell.col != col_id:
        return False

    valori = _category_values(
        category_id, name, coach, location,
        duration_min, price_eur, payment_link, description,
    )
    inizio = gspread.utils.rowcol_to_a1(cell.row, 1)
    fine = gspread.utils.rowcol_to_a1(cell.row, len(reali))
    ws.update(
        f"{inizio}:{fine}",
        [_row_for(reali, valori)],
        value_input_option="USER_ENTERED",
    )
    load_categories.clear()
    return True


def delete_category(category_id: str) -> bool:
    col_id = _col_index("categories", "category_id")
    ws = _sheet("categories")
    cell = ws.find(str(category_id).strip())
    if cell is None or cell.col != col_id:
        return False
    ws.delete_rows(cell.row)
    load_categories.clear()
    return True


# =============================================================
# SLOT (appuntamenti disponibili)
# =============================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_slots() -> pd.DataFrame:
    df = pd.DataFrame(_records("slots"))
    if df.empty:
        return pd.DataFrame(columns=SLOT_COLUMNS)
    for col in SLOT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["slot_id"] = df["slot_id"].astype(str).str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["time"] = df["time"].astype(str).str.strip()
    df["category_id"] = df["category_id"].astype(str).str.strip()
    df["capacity"] = (
        pd.to_numeric(df["capacity"], errors="coerce").fillna(1).astype(int)
    )
    df["note"] = df["note"].astype(str).fillna("")
    return df.dropna(subset=["date"])[SLOT_COLUMNS]


def next_slot_id() -> str:
    nums = []
    for r in _records("slots"):
        val = str(r.get("slot_id", "")).strip().upper()
        if val.startswith("S") and val[1:].isdigit():
            nums.append(int(val[1:]))
    return f"S{(max(nums) + 1) if nums else 1:04d}"


def add_slots_bulk(rows: list[tuple]) -> list[str]:
    """rows: lista di (date_str, time_str, category_id, capacity, note)."""
    if not rows:
        return []
    reali = _check_headers("slots", SLOT_COLUMNS)
    ws = _sheet("slots")

    nums = [
        int(str(r.get("slot_id", "")).strip().upper()[1:])
        for r in _records("slots")
        if str(r.get("slot_id", "")).strip().upper().startswith("S")
        and str(r.get("slot_id", "")).strip().upper()[1:].isdigit()
    ]
    start = (max(nums) + 1) if nums else 1

    payload, ids = [], []
    for i, (d, t, cid, cap, note) in enumerate(rows):
        sid = f"S{start + i:04d}"
        ids.append(sid)
        payload.append(_row_for(reali, {
            "slot_id": sid,
            "date": d,
            "time": t,
            "category_id": str(cid),
            "capacity": int(cap),
            "note": str(note).strip(),
        }))

    ws.append_rows(payload, value_input_option="USER_ENTERED")
    load_slots.clear()
    return ids


def add_slot(
    date_str: str, time_str: str, category_id: str,
    capacity: int = 1, note: str = "",
) -> str:
    return add_slots_bulk(
        [(date_str, time_str, category_id, capacity, note)]
    )[0]


def update_slot(
    slot_id: str, date_str: str, time_str: str, category_id: str,
    capacity: int = 1, note: str = "",
) -> bool:
    reali = _check_headers("slots", SLOT_COLUMNS)
    ws = _sheet("slots")
    col_id = reali.index("slot_id") + 1

    cell = ws.find(str(slot_id).strip())
    if cell is None or cell.col != col_id:
        return False

    valori = {
        "slot_id": str(slot_id),
        "date": date_str,
        "time": time_str,
        "category_id": str(category_id),
        "capacity": int(capacity),
        "note": str(note).strip(),
    }
    inizio = gspread.utils.rowcol_to_a1(cell.row, 1)
    fine = gspread.utils.rowcol_to_a1(cell.row, len(reali))
    ws.update(
        f"{inizio}:{fine}",
        [_row_for(reali, valori)],
        value_input_option="USER_ENTERED",
    )
    load_slots.clear()
    return True


def delete_slot(slot_id: str) -> bool:
    col_id = _col_index("slots", "slot_id")
    ws = _sheet("slots")
    cell = ws.find(str(slot_id).strip())
    if cell is None or cell.col != col_id:
        return False
    ws.delete_rows(cell.row)
    load_slots.clear()
    return True


# =============================================================
# PRENOTAZIONI
# =============================================================

@st.cache_data(ttl=20, show_spinner=False)
def load_bookings() -> pd.DataFrame:
    df = pd.DataFrame(_records("bookings"))
    if df.empty:
        return pd.DataFrame(columns=BOOKING_COLUMNS)
    for col in BOOKING_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["booking_id"] = df["booking_id"].astype(str).str.strip()
    df["slot_id"] = df["slot_id"].astype(str).str.strip()
    df["email"] = df["email"].map(norm_email)
    df["status"] = (
        df["status"].astype(str).str.strip().str.lower()
        .replace("", "confirmed").fillna("confirmed")
    )
    df["paid"] = (
        df["paid"].astype(str).str.strip().str.lower()
        .replace({"true": "si", "sì": "si", "yes": "si", "x": "si"})
        .replace("", "no").fillna("no")
    )
    df["amount_paid"] = df["amount_paid"].map(_to_num)          # NaN = non indicato
    df["amount_refunded"] = df["amount_refunded"].map(_to_num).fillna(0.0)
    return df[BOOKING_COLUMNS]


def seats_taken(bookings: pd.DataFrame) -> pd.Series:
    if bookings.empty:
        return pd.Series(dtype=int)
    active = bookings[~bookings["status"].isin(INACTIVE_STATUSES)]
    if active.empty:
        return pd.Series(dtype=int)
    return active.groupby("slot_id").size()


def count_live(slot_id: str) -> int:
    return sum(
        1 for r in _records("bookings")
        if str(r.get("slot_id")).strip() == str(slot_id).strip()
        and _is_active(r.get("status"))
    )


def already_booked(slot_id: str, email: str) -> bool:
    target = norm_email(email)
    return any(
        str(r.get("slot_id")).strip() == str(slot_id).strip()
        and norm_email(r.get("email")) == target
        and _is_active(r.get("status"))
        for r in _records("bookings")
    )


def add_booking(slot_id: str, name: str, email: str, phone: str = "") -> str:
    reali = _check_headers("bookings", BOOKING_CORE)
    booking_id = uuid.uuid4().hex[:8].upper()
    _sheet("bookings").append_row(
        _row_for(reali, {
            "booking_id": booking_id,
            "slot_id": str(slot_id),
            "name": name.strip(),
            "email": norm_email(email),
            "phone": phone.strip(),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": "confirmed",
            "paid": "no",
        }),
        value_input_option="USER_ENTERED",
    )
    load_bookings.clear()
    return booking_id


def cancel_booking(booking_id: str) -> bool:
    reali = _check_headers("bookings", ["booking_id", "status"])
    ws = _sheet("bookings")
    col_id = reali.index("booking_id") + 1
    cell = ws.find(str(booking_id).strip())
    if cell is None or cell.col != col_id:
        return False
    ws.update_cell(cell.row, reali.index("status") + 1, "cancelled")
    load_bookings.clear()
    return True


def _update_bookings(updates: dict) -> int:
    """updates: {booking_id: {colonna: valore}}. Un solo batch sul foglio.

    Ritorna quante prenotazioni sono state aggiornate.
    """
    if not updates:
        return 0
    target = {str(k).strip().upper(): v for k, v in updates.items()}
    colonne = sorted({c for campi in target.values() for c in campi})
    reali = _check_headers("bookings", ["booking_id"] + colonne)
    ws = _sheet("bookings")

    batch, trovate = [], 0
    for i, r in enumerate(_records("bookings"), start=2):   # riga 1 = intestazioni
        bid = str(r.get("booking_id", "")).strip().upper()
        if bid in target:
            trovate += 1
            for col, val in target[bid].items():
                batch.append({
                    "range": gspread.utils.rowcol_to_a1(i, reali.index(col) + 1),
                    "values": [[val]],
                })

    if batch:
        ws.batch_update(batch, value_input_option="USER_ENTERED")
        load_bookings.clear()
    return trovate


def mark_paid_bulk(amounts: dict) -> int:
    """amounts: {booking_id: importo incassato}. Segna come incassate."""
    return _update_bookings({
        bid: {"paid": "si", "amount_paid": round(float(imp), 2)}
        for bid, imp in amounts.items()
    })


def unmark_paid_bulk(booking_ids: list[str]) -> int:
    """Riporta fra le non incassate (per correggere un errore)."""
    return _update_bookings({
        bid: {"paid": "no", "amount_paid": ""} for bid in booking_ids
    })


def refund_bulk(refunds: dict) -> int:
    """refunds: {booking_id: importo rimborsato}.

    Il rimborso vero e la comunicazione col cliente avvengono fuori
    dall'app (Stripe + email): qui si registrano stato e importo.
    Lo slot si libera automaticamente, perché le prenotazioni rimborsate
    non contano più come posti occupati.
    """
    return _update_bookings({
        bid: {"status": "refunded", "amount_refunded": round(float(imp), 2)}
        for bid, imp in refunds.items()
    })


# =============================================================
# VISTE COMPOSTE
# =============================================================

def slots_with_category(
    slots: pd.DataFrame, categories: pd.DataFrame
) -> pd.DataFrame:
    """Unisce gli slot ai dati della loro categoria."""
    extra = [
        "name", "coach", "location", "duration_min",
        "price_eur", "payment_link", "description",
    ]
    if slots.empty:
        return pd.DataFrame(columns=SLOT_COLUMNS + extra)
    if categories.empty:
        out = slots.copy()
        out["name"] = "Appuntamento"
        out["coach"] = ""
        out["location"] = DEFAULT_LOCATION
        out["duration_min"] = 60
        out["price_eur"] = 0.0
        out["payment_link"] = ""
        out["description"] = ""
        return out
    return slots.merge(categories, on="category_id", how="left").fillna({
        "name": "Appuntamento",
        "coach": "",
        "location": DEFAULT_LOCATION,
        "duration_min": 60,
        "price_eur": 0.0,
        "payment_link": "",
        "description": "",
    })


def blocked_slots(vista: pd.DataFrame, bookings: pd.DataFrame) -> set:
    """Slot non prenotabili perché si sovrappongono a un ALTRO slot già prenotato.

    Il laboratorio è uno solo: se l'allenatore A ha una prenotazione dalle
    9:00 alle 10:00, gli slot di qualsiasi altro allenatore che si
    sovrappongono a quell'intervallo diventano indisponibili.
    `vista` deve contenere slot_id, date, time, duration_min
    (cioè l'output di slots_with_category).
    """
    if vista.empty or bookings.empty:
        return set()
    occupati = set(seats_taken(bookings).index.astype(str))
    if not occupati:
        return set()

    intervalli = {}
    for r in vista.itertuples(index=False):
        t = _parse_time(r.time)
        if t is None or pd.isna(r.date):
            continue
        start = datetime.combine(r.date, t)
        try:
            dur = int(r.duration_min)
        except (TypeError, ValueError):
            dur = 60
        intervalli[str(r.slot_id)] = (start, start + timedelta(minutes=dur or 60))

    bloccati = set()
    for sid_occ in occupati:
        if sid_occ not in intervalli:
            continue
        a0, a1 = intervalli[sid_occ]
        for sid, (b0, b1) in intervalli.items():
            if sid != sid_occ and a0 < b1 and b0 < a1:
                bloccati.add(sid)
    return bloccati


def conflict_live(slot_id: str) -> bool:
    """Controllo al momento della prenotazione, con dati freschi dal foglio."""
    clear_all_caches()
    vista = slots_with_category(load_slots(), load_categories())
    return str(slot_id).strip() in blocked_slots(vista, load_bookings())


def _intervallo(giorno, orario, durata):
    """(inizio, fine) come datetime, oppure None se data/ora non leggibili."""
    t = _parse_time(orario)
    if t is None or giorno is None or pd.isna(giorno):
        return None
    try:
        minuti = int(durata) or 60
    except (TypeError, ValueError):
        minuti = 60
    inizio = datetime.combine(giorno, t)
    return inizio, inizio + timedelta(minutes=minuti)


def check_new_slots(
    candidati: list, category_id: str,
    slots: pd.DataFrame, categories: pd.DataFrame, bookings: pd.DataFrame,
):
    """Separa i nuovi slot creabili da quelli sovrapposti a slot già prenotati.

    Slot in contemporanea sono ammessi (stesso o altro allenatore): si blocca
    solo la sovrapposizione con uno slot che ha già una prenotazione attiva,
    considerando la durata di entrambi.

    candidati: lista di (date, "HH:MM").
    Ritorna (ok, bloccati): ok = lista di (date, "HH:MM"),
    bloccati = lista di (date, "HH:MM", motivo).
    """
    cat = categories[categories["category_id"] == str(category_id)]
    if cat.empty:
        return [], [(d, t, "categoria non trovata") for d, t in candidati]
    durata = cat.iloc[0]["duration_min"]

    vista = slots_with_category(slots, categories)
    occupati = set(seats_taken(bookings).index.astype(str))
    prenotati = []
    for r in vista.itertuples(index=False):
        if str(r.slot_id) in occupati:
            iv = _intervallo(r.date, r.time, r.duration_min)
            if iv:
                prenotati.append((r, iv))

    ok, bloccati = [], []
    for d, t in candidati:
        iv = _intervallo(d, t, durata)
        if iv is None:
            bloccati.append((d, t, "orario non valido"))
            continue
        a0, a1 = iv
        motivo = None
        for r, (b0, b1) in prenotati:
            if a0 < b1 and b0 < a1:
                coach = f" di {r.coach}" if str(r.coach).strip() else ""
                motivo = (
                    f"lab già prenotato — {r.name}{coach}, "
                    f"{r.time}–{b1.strftime('%H:%M')}"
                )
                break
        if motivo:
            bloccati.append((d, t, motivo))
        else:
            ok.append((d, t))

    return ok, bloccati