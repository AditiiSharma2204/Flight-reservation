import datetime as dt
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from flightapp import store

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIGHT_TODAY", "2026-09-26")
    monkeypatch.setenv("FLIGHT_DB", str(tmp_path / "bookings.db"))


def start():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def click(at, key):
    at.button(key=key).click().run()
    assert not at.exception, at.exception


def select_first_flight(at, leg):
    key = next(b.key for b in at.button if b.key and b.key.startswith(f"sel_{leg}_") and not b.disabled)
    click(at, key)


def fill_passengers(at, names, mobile="98765 43210"):
    for i, (first, last) in enumerate(names):
        at.text_input(key=f"first_{i}").input(first)
        at.text_input(key=f"last_{i}").input(last)
    at.text_input(key="mobile").input(mobile)
    next(b for b in at.button if b.label == "Continue to payment →").click().run()
    assert not at.exception, at.exception


def pay(at):
    next(b for b in at.button if b.label.startswith("Pay ")).click().run()
    assert not at.exception, at.exception


def test_one_way_booking_then_cancel():
    at = start()
    at.date_input(key="depart").set_value(dt.date(2026, 12, 15))
    click(at, "search_btn")
    assert at.session_state.step == 1
    select_first_flight(at, 0)
    click(at, "to_pax")

    fill_passengers(at, [("aditi", "sharma")])
    assert at.session_state.step == 3
    at.text_input(key="upi").input("aditi@okaxis")
    at.checkbox(key="agree").check()
    pay(at)

    assert at.session_state.step == 4
    pnr = at.session_state.confirmed_pnr
    booking = store.find(pnr, "Sharma")
    assert booking.status == "CONFIRMED"
    assert booking.travellers == [{"first": "Aditi", "last": "Sharma"}]
    assert booking.payment == "UPI (aditi@okaxis)"
    assert any(pnr in s.value for s in at.success)

    # Manage booking: find it and cancel.
    at.text_input(key="lookup_pnr").input(pnr.lower())
    at.text_input(key="lookup_last").input("SHARMA")
    next(b for b in at.button if b.label == "Find booking").click().run()
    assert [m.value for m in at.metric if m.label == "Cancellation fee"] == ["₹3,000"]
    at.checkbox(key="cancel_sure").check().run()
    click(at, "cancel_btn")
    assert store.find(pnr, "sharma").status == "CANCELLED"


def test_round_trip_with_card_and_seat_counting():
    at = start()
    at.radio(key="trip").set_value("Round trip").run()
    at.selectbox(key="cabin").set_value("Business")
    at.number_input(key="travellers").set_value(2)
    at.selectbox(key="origin").set_value("BLR")
    at.selectbox(key="dest").set_value("GOI")
    at.date_input(key="depart").set_value(dt.date(2026, 11, 10)).run()
    at.date_input(key="return").set_value(dt.date(2026, 11, 14))
    click(at, "search_btn")
    select_first_flight(at, 0)
    select_first_flight(at, 1)
    click(at, "to_pax")
    fill_passengers(at, [("Aditi", "Sharma"), ("Ravi", "Kumar")])

    at.radio(key="method").set_value("Credit / debit card").run()
    at.text_input(key="card").input("4111 1111 1111 1111")
    at.text_input(key="expiry").input("12/28")
    at.text_input(key="cvv").input("123")
    at.checkbox(key="agree").check()
    pay(at)

    booking = store.find(at.session_state.confirmed_pnr, "sharma")
    assert booking.round_trip and booking.cabin == "Business"
    assert booking.payment == "Card ending 1111"
    assert [f["origin"] for f in booking.flights] == ["BLR", "GOI"]
    assert booking.fare["gst"] == round(booking.fare["base"] * 0.12)
    assert sum(store.seats_booked().values()) == 4


def test_validation_errors_block_progress():
    at = start()
    at.selectbox(key="dest").set_value("DEL")
    click(at, "search_btn")
    assert at.session_state.step == 0
    assert "must be different" in at.error[0].value

    at.selectbox(key="dest").set_value("BOM")
    click(at, "search_btn")
    select_first_flight(at, 0)
    click(at, "to_pax")
    fill_passengers(at, [("A1", "")], mobile="123")
    assert at.session_state.step == 2
    assert len(at.error) == 2

    fill_passengers(at, [("Aditi", "Sharma")])
    at.text_input(key="upi").input("not-an-upi")
    pay(at)
    assert at.session_state.step == 3
    errors = " ".join(e.value for e in at.error)
    assert "UPI" in errors and "accept" in errors
