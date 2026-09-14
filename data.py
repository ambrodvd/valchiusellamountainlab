"""Data access layer. Google Sheets — Valchiusella Mountain Lab."""

import uuid
from datetime import datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_LOCATION = "Valchiusella Mountain Hub, Via delle Miniere 2, 10080 Traversella (TO)"

CATEGORY_COLUMNS = [
    "category_id", "name", "coach", "location", "duration_min",
    "price_eur", "payment_link", "description",
]

SLOT_COLUMNS = [
    "slot_id", "date", "time", "category_id", "capacity", "note",
]

BOOKING_COLUMNS = [
    "booking_id", "slot_id", "name", "email",
    "phone", "timestamp", "status", "paid",
]


def norm_email(value: str) -> str:
    return str(value or "").strip().lower()


@st.cache_resource(show_spinner=False)
def _client() -> gspread.Client:
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)


def _sheet(tab: str) -> gspread.Worksheet:
    return _client().open_by_key(st.secrets["spreadsheet_id"]).worksheet(tab)


def clear_all_caches() -> None:
    load_categories.clear()
    load_slots.clear()
    load_bookings.clear()


# =============================================================
# CATEGORIE (tipi di test)
# =============================================================

@st.cache_data(ttl=120, show_spinner=False)
def load_categories() -> pd.DataFrame:
    df = pd.DataFrame(_sheet("categories").get_all_records())
    if df.empty:
        return pd.DataFrame(columns=CATEGORY_COLUMNS)
    for col in CATEGORY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["category_id"] = df["category_id"].astype(str)
    for col in ("name", "coach", "payment_link", "description"):
        df[col] = df[col].astype(str).fillna("")
    df["location"] = (
        df["location"].astype(str).fillna("").replace("", DEFAULT_LOCATION)
    )
    df["duration_min"] = (
        pd.to_numeric(df["duration_min"], errors="coerce").fillna(60).astype(int)
    )
    df["price_eur"] = pd.to_numeric(df["price_eur"], errors="coerce").fillna(0.0)
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
    records = _sheet("categories").get_all_records()
    nums = []
    for r in records:
        val = str(r.get("category_id", "")).strip().upper()
        if val.startswith("C") and val[1:].isdigit():
            nums.append(int(val[1:]))
    return f"C{(max(nums) + 1) if nums else 1:03d}"


def add_category(
    name: str, coach: str, location: str, duration_min: int,
    price_eur: float, payment_link: str, description: str = "",
) -> str:
    category_id = next_category_id()
    _sheet("categories").append_row(
        [
            category_id, name.strip(), coach.strip(),
            location.strip() or DEFAULT_LOCATION, int(duration_min),
            float(price_eur), payment_link.strip(), description.strip(),
        ],
        value_input_option="USER_ENTERED",
    )
    load_categories.clear()
    return category_id


def update_category(
    category_id: str, name: str, coach: str, location: str, duration_min: int,
    price_eur: float, payment_link: str, description: str = "",
) -> bool:
    ws = _sheet("categories")
    cell = ws.find(str(category_id))
    if cell is None or cell.col != 1:
        return False
    ws.update(
        f"A{cell.row}:H{cell.row}",
        [[
            str(category_id), name.strip(), coach.strip(),
            location.strip() or DEFAULT_LOCATION, int(duration_min),
            float(price_eur), payment_link.strip(), description.strip(),
        ]],
        value_input_option="USER_ENTERED",
    )
    load_categories.clear()
    return True


def delete_category(category_id: str) -> bool:
    ws = _sheet("categories")
    cell = ws.find(str(category_id))
    if cell is None or cell.col != 1:
        return False
    ws.delete_rows(cell.row)
    load_categories.clear()
    return True


# =============================================================
# SLOT (appuntamenti disponibili)
# =============================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_slots() -> pd.DataFrame:
    df = pd.DataFrame(_sheet("slots").get_all_records())
    if df.empty:
        return pd.DataFrame(columns=SLOT_COLUMNS)
    for col in SLOT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["slot_id"] = df["slot_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["time"] = df["time"].astype(str).str.strip()
    df["category_id"] = df["category_id"].astype(str).str.strip()
    df["capacity"] = (
        pd.to_numeric(df["capacity"], errors="coerce").fillna(1).astype(int)
    )
    df["note"] = df["note"].astype(str).fillna("")
    return df.dropna(subset=["date"])[SLOT_COLUMNS]


def next_slot_id() -> str:
    records = _sheet("slots").get_all_records()
    nums = []
    for r in records:
        val = str(r.get("slot_id", "")).strip().upper()
        if val.startswith("S") and val[1:].isdigit():
            nums.append(int(val[1:]))
    return f"S{(max(nums) + 1) if nums else 1:04d}"


def add_slots_bulk(rows: list[tuple]) -> list[str]:
    """rows: lista di (date_str, time_str, category_id, capacity, note)."""
    if not rows:
        return []
    ws = _sheet("slots")
    records = ws.get_all_records()
    nums = [
        int(str(r.get("slot_id", "")).strip().upper()[1:])
        for r in records
        if str(r.get("slot_id", "")).strip().upper().startswith("S")
        and str(r.get("slot_id", "")).strip().upper()[1:].isdigit()
    ]
    start = (max(nums) + 1) if nums else 1

    payload, ids = [], []
    for i, (d, t, cid, cap, note) in enumerate(rows):
        sid = f"S{start + i:04d}"
        ids.append(sid)
        payload.append([sid, d, t, str(cid), int(cap), str(note).strip()])

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


def delete_slot(slot_id: str) -> bool:
    ws = _sheet("slots")
    cell = ws.find(str(slot_id))
    if cell is None or cell.col != 1:
        return False
    ws.delete_rows(cell.row)
    load_slots.clear()
    return True


# =============================================================
# PRENOTAZIONI
# =============================================================

@st.cache_data(ttl=20, show_spinner=False)
def load_bookings() -> pd.DataFrame:
    df = pd.DataFrame(_sheet("bookings").get_all_records())
    if df.empty:
        return pd.DataFrame(columns=BOOKING_COLUMNS)
    for col in BOOKING_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["slot_id"] = df["slot_id"].astype(str)
    df["email"] = df["email"].map(norm_email)
    df["status"] = df["status"].replace("", "confirmed").fillna("confirmed")
    df["paid"] = (
        df["paid"].astype(str).str.strip().str.lower()
        .replace({"true": "si", "sì": "si", "yes": "si", "x": "si"})
        .replace("", "no").fillna("no")
    )
    return df[BOOKING_COLUMNS]


def seats_taken(bookings: pd.DataFrame) -> pd.Series:
    if bookings.empty:
        return pd.Series(dtype=int)
    active = bookings[bookings["status"] != "cancelled"]
    if active.empty:
        return pd.Series(dtype=int)
    return active.groupby("slot_id").size()


def count_live(slot_id: str) -> int:
    records = _sheet("bookings").get_all_records()
    return sum(
        1 for r in records
        if str(r.get("slot_id")) == str(slot_id)
        and (r.get("status") or "confirmed") != "cancelled"
    )


def already_booked(slot_id: str, email: str) -> bool:
    records = _sheet("bookings").get_all_records()
    target = norm_email(email)
    return any(
        str(r.get("slot_id")) == str(slot_id)
        and norm_email(r.get("email")) == target
        and (r.get("status") or "confirmed") != "cancelled"
        for r in records
    )


def add_booking(slot_id: str, name: str, email: str, phone: str = "") -> str:
    booking_id = uuid.uuid4().hex[:8].upper()
    _sheet("bookings").append_row(
        [
            booking_id, str(slot_id), name.strip(), norm_email(email),
            phone.strip(), datetime.now().isoformat(timespec="seconds"),
            "confirmed", "no",
        ],
        value_input_option="USER_ENTERED",
    )
    load_bookings.clear()
    return booking_id


def cancel_booking(booking_id: str) -> bool:
    ws = _sheet("bookings")
    cell = ws.find(str(booking_id))
    if cell is None or cell.col != 1:
        return False
    ws.update_cell(cell.row, BOOKING_COLUMNS.index("status") + 1, "cancelled")
    load_bookings.clear()
    return True


def set_paid(booking_id: str, paid: bool = True) -> bool:
    ws = _sheet("bookings")
    cell = ws.find(str(booking_id))
    if cell is None or cell.col != 1:
        return False
    ws.update_cell(
        cell.row, BOOKING_COLUMNS.index("paid") + 1, "si" if paid else "no"
    )
    load_bookings.clear()
    return True


def set_paid_bulk(changes: dict) -> int:
    """changes: {booking_id: bool}. Ritorna quante righe sono state aggiornate."""
    if not changes:
        return 0
    ws = _sheet("bookings")
    col = BOOKING_COLUMNS.index("paid") + 1
    records = ws.get_all_records()

    aggiornamenti = []
    for i, r in enumerate(records, start=2):   # riga 1 = intestazioni
        bid = str(r.get("booking_id", "")).strip().upper()
        if bid in changes:
            aggiornamenti.append({
                "range": gspread.utils.rowcol_to_a1(i, col),
                "values": [["si" if changes[bid] else "no"]],
            })

    if aggiornamenti:
        ws.batch_update(aggiornamenti, value_input_option="USER_ENTERED")
        load_bookings.clear()
    return len(aggiornamenti)


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