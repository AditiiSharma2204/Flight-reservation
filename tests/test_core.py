import datetime as dt

import pytest

from flightapp import core, store
from flightapp.core import (
    Booking,
    cancellation_quote,
    clean_mobile,
    clean_name,
    distance_km,
    fare_breakdown,
    luhn_valid,
    money,
    new_pnr,
    search_flights,
    valid_email,
    valid_expiry,
    valid_upi,
)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIGHT_TODAY", "2026-09-26")
    monkeypatch.setenv("FLIGHT_DB", str(tmp_path / "bookings.db"))


def test_distance_is_realistic_and_symmetric():
    assert 1100 < distance_km("DEL", "BOM") < 1200
    assert distance_km("DEL", "BOM") == pytest.approx(distance_km("BOM", "DEL"))


def test_search_is_deterministic_and_sensible():
    day = dt.date(2026, 12, 15)
    a = search_flights("DEL", "BOM", day)
    assert [f.to_dict() for f in a] == [f.to_dict() for f in search_flights("DEL", "BOM", day)]
    assert 5 <= len(a) <= 10
    assert [f.depart_min for f in a] == sorted(f.depart_min for f in a)
    assert len({f.number for f in a}) == len(a)
    for f in a:
        assert 5 * 60 <= f.depart_min < 23 * 60 and f.depart_min % 5 == 0
        assert 100 <= f.duration_min <= 160          # ~2h for DEL-BOM
        assert f.fare % 10 == 0 and f.fare > 0
    with pytest.raises(ValueError):
        search_flights("DEL", "DEL", day)


def test_longer_routes_take_longer_and_cost_more():
    day = dt.date(2026, 12, 15)
    short = search_flights("DEL", "JAI", day)
    long = search_flights("DEL", "TRV", day)
    assert max(f.duration_min for f in short) < min(f.duration_min for f in long)
    assert sum(f.fare for f in short) / len(short) < sum(f.fare for f in long) / len(long)


def test_last_minute_fares_are_higher():
    soon = search_flights("BLR", "HYD", dt.date(2026, 9, 28))
    later = search_flights("BLR", "HYD", dt.date(2026, 11, 24))
    avg = lambda fs: sum(f.fare for f in fs) / len(fs)
    assert avg(soon) > avg(later)


def test_fares_and_cancellation():
    f = search_flights("DEL", "BOM", dt.date(2026, 12, 15))[0]
    assert f.cabin_fare("Business") == round(f.fare * 2.8 / 10) * 10
    fare = fare_breakdown([f], "Business", 2)
    assert fare["base"] == f.cabin_fare("Business") * 2
    assert fare["gst"] == round(fare["base"] * 0.12)
    assert fare["total"] == fare["base"] + fare["gst"]
    assert cancellation_quote(20000, 2, 2) == {"fee": 12000, "refund": 8000}
    assert cancellation_quote(5000, 2, 2) == {"fee": 5000, "refund": 0}


def test_money_uses_indian_grouping():
    assert money(0) == "₹0"
    assert money(999) == "₹999"
    assert money(1234567) == "₹12,34,567"
    assert money(-1500) == "-₹1,500"


@pytest.mark.parametrize("raw, expected", [
    ("aditi", "Aditi"), ("  mary   jane ", "Mary Jane"), ("o'neil", "O'neil"), ("d'souza-rao", "D'souza-rao"),
    ("", None), ("x1", None), ("a" * 41, None),
])
def test_clean_name(raw, expected):
    assert clean_name(raw) == expected


def test_contact_and_payment_validation():
    assert clean_mobile("+91 98765 43210") == "9876543210"
    assert clean_mobile("12345") is None and clean_mobile("5876543210") is None
    assert valid_email("a@b.co") and not valid_email("a@b")
    assert valid_upi("ravi@okaxis") and not valid_upi("ravi") and not valid_upi("r@1")
    assert luhn_valid("4111 1111 1111 1111") and not luhn_valid("4111 1111 1111 1112")
    assert valid_expiry("12/28") and valid_expiry("09/26")
    assert not valid_expiry("08/26") and not valid_expiry("13/28") and not valid_expiry("1228")


def test_pnr_format_and_uniqueness():
    pnr = new_pnr()
    assert len(pnr) == 6 and set(pnr) <= set(core.PNR_CHARS)
    assert not set(pnr) & set("IO01")


def test_store_roundtrip_and_seat_counts():
    f = search_flights("DEL", "BOM", dt.date(2026, 12, 15))[0]
    b = Booking(
        pnr="ABC234", status="CONFIRMED", cabin="Economy",
        travellers=[{"first": "Aditi", "last": "Sharma"}, {"first": "Ravi", "last": "Kumar"}],
        flights=[f.to_dict()], mobile="9876543210", email="", payment="UPI (a@okaxis)",
        fare=fare_breakdown([f], "Economy", 2),
    )
    store.save(b)
    assert store.find("abc234", "SHARMA").pnr == "ABC234"
    assert store.find("ABC234", "Kumar") is None
    assert store.seats_booked() == {f.key: 2}
    b.status = "CANCELLED"
    store.save(b)
    assert store.seats_booked() == {}
    assert store.taken_pnrs() == {"ABC234"}
