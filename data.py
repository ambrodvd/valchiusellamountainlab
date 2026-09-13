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

CATEGORY_COLUMNS = [
    "category_id", "name", "location", "duration_min",
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
# CATEGORIE (tipi di appuntamento)
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
    for col in ("name", "location", "payment_link", "description"):
        df[col] = df[col].astype(str).fillna("")
    df["duration_min"] = (
        pd.to_numeric(df["duration_min"], errors="coerce").fillna(60).astype(int)
    )
    df["price_eur"] = pd.to_numeric(df["price_eur"], errors="coerce").fillna(0.0)
    return df[CATEGORY_COLUMNS]


def next_category_id() -> str:
    records = _sheet("categories").get_all_records()
    nums = []
    for r in records:
        val = str(r.get("category_id", "")).strip().upper()
        if val.startswith("C") and val[1:].isdigit():
            nums.append(int(val[1:]))
    return f"C{(max(nums) + 1) if nums else 1:03d}"


def add_category(
    name: str, location: str, duration_min: int,
    price_eur: float, payment_link: str, description: str = "",
) -> str:
    category_id = next_category_id()
    _sheet("categories").append_row(
        [
            category_id, name.strip(), location.strip(), int(duration_min),
            float(price_eur), payment_link.strip(), description.strip(),
        ],
        value_input_option="USER_ENTERED",
    )
    load_categories.clear()
    return category_id


def update_category(
    category_id: str, name: str, location: str, duration_min: int,
    price_eur: float, payment_link: str, description: str = "",
) -> bool:
    ws = _sheet("categories")
    cell = ws.find(str(category_id))
    if cell is None or cell.col != 1:
        return False
    ws.update(
        f"A{cell.row}:G{cell.row}",
        [[
            str(category_id), name.strip(), location.strip(), int(duration_min),
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


# =============================================================
# VISTE COMPOSTE
# =============================================================

def slots_with_category(
    slots: pd.DataFrame, categories: pd.DataFrame
) -> pd.DataFrame:
    """Unisce gli slot ai dati della loro categoria."""
    if slots.empty:
        return pd.DataFrame(
            columns=SLOT_COLUMNS + [
                "name", "location", "duration_min", "price_eur", "payment_link",
                "description",
            ]
        )
    if categories.empty:
        out = slots.copy()
        out["name"] = "Appuntamento"
        out["location"] = ""
        out["duration_min"] = 60
        out["price_eur"] = 0.0
        out["payment_link"] = ""
        out["description"] = ""
        return out
    return slots.merge(categories, on="category_id", how="left").fillna({
        "name": "Appuntamento",
        "location": "",
        "duration_min": 60,
        "price_eur": 0.0,
        "payment_link": "",
        "description": "",
    })
