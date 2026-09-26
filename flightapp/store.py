"""SQLite storage for bookings."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from .core import Booking

DEFAULT_DB = Path(__file__).resolve().parent.parent / "bookings.db"


def db_path():
    return Path(os.environ.get("FLIGHT_DB", DEFAULT_DB))


def _connect():
    conn = sqlite3.connect(db_path())
    conn.execute("CREATE TABLE IF NOT EXISTS bookings (pnr TEXT PRIMARY KEY, data TEXT NOT NULL)")
    return conn


def save(booking: Booking):
    data = json.dumps(booking.__dict__)
    with closing(_connect()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO bookings (pnr, data) VALUES (?, ?)", (booking.pnr, data))


def all_bookings():
    with closing(_connect()) as conn:
        return [Booking(**json.loads(row[0])) for row in conn.execute("SELECT data FROM bookings")]


def find(pnr, last_name):
    pnr, last_name = pnr.strip().upper(), last_name.strip().lower()
    with closing(_connect()) as conn:
        row = conn.execute("SELECT data FROM bookings WHERE pnr = ?", (pnr,)).fetchone()
    if not row:
        return None
    booking = Booking(**json.loads(row[0]))
    return booking if booking.lead_last_name.lower() == last_name else None


def taken_pnrs():
    with closing(_connect()) as conn:
        return {row[0] for row in conn.execute("SELECT pnr FROM bookings")}


def seats_booked():
    """Confirmed seats per flight key ("6E 123|2026-12-15")."""
    booked = {}
    for b in all_bookings():
        if b.status == "CONFIRMED":
            for f in b.flights:
                key = f"{f['number']}|{f['date']}"
                booked[key] = booked.get(key, 0) + len(b.travellers)
    return booked
