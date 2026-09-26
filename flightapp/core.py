"""Flight search, fares, validation and PNRs - no Streamlit code here."""

import datetime as dt
import hashlib
import math
import os
import random
import re
import secrets
from dataclasses import asdict, dataclass, field

MAX_TRAVELLERS = 9
BOOKING_WINDOW_DAYS = 365
CANCEL_FEE_PER_SEAT = 3000  # rupees, per traveller per flight

# IATA code -> (city, airport, latitude, longitude)
CITIES = {
    "DEL": ("New Delhi", "Indira Gandhi Intl", 28.5562, 77.1000),
    "BOM": ("Mumbai", "Chhatrapati Shivaji Maharaj Intl", 19.0896, 72.8656),
    "BLR": ("Bengaluru", "Kempegowda Intl", 13.1986, 77.7066),
    "MAA": ("Chennai", "Chennai Intl", 12.9941, 80.1709),
    "CCU": ("Kolkata", "Netaji Subhas Chandra Bose Intl", 22.6547, 88.4467),
    "HYD": ("Hyderabad", "Rajiv Gandhi Intl", 17.2403, 78.4294),
    "GOI": ("Goa", "Dabolim", 15.3808, 73.8314),
    "PNQ": ("Pune", "Pune Intl", 18.5822, 73.9197),
    "AMD": ("Ahmedabad", "Sardar Vallabhbhai Patel Intl", 23.0772, 72.6347),
    "JAI": ("Jaipur", "Jaipur Intl", 26.8242, 75.8122),
    "COK": ("Kochi", "Cochin Intl", 10.1520, 76.4019),
    "LKO": ("Lucknow", "Chaudhary Charan Singh Intl", 26.7606, 80.8893),
    "GAU": ("Guwahati", "Lokpriya Gopinath Bordoloi Intl", 26.1061, 91.5859),
    "SXR": ("Srinagar", "Sheikh ul-Alam Intl", 33.9871, 74.7742),
    "IXC": ("Chandigarh", "Shaheed Bhagat Singh Intl", 30.6735, 76.7885),
    "TRV": ("Thiruvananthapuram", "Trivandrum Intl", 8.4821, 76.9201),
}

# name, IATA airline code, fare factor, brand colour
AIRLINES = [
    ("IndiGo", "6E", 1.00, "#1E3A8A"),
    ("Air India", "AI", 1.18, "#C2410C"),
    ("Akasa Air", "QP", 0.97, "#EA580C"),
    ("SpiceJet", "SG", 0.93, "#DC2626"),
    ("Air India Express", "IX", 0.90, "#B45309"),
]

CABINS = {
    "Economy": {"multiplier": 1.0, "gst": 5, "baggage": "15 kg check-in · 7 kg cabin"},
    "Premium Economy": {"multiplier": 1.6, "gst": 12, "baggage": "25 kg check-in · 7 kg cabin"},
    "Business": {"multiplier": 2.8, "gst": 12, "baggage": "35 kg check-in · 10 kg cabin"},
}


def city_label(code):
    return f"{CITIES[code][0]} ({code})"


def today():
    """Today's date; FLIGHT_TODAY=YYYY-MM-DD overrides it (used by tests)."""
    override = os.environ.get("FLIGHT_TODAY")
    return dt.date.fromisoformat(override) if override else dt.date.today()


def last_bookable_day():
    return today() + dt.timedelta(days=BOOKING_WINDOW_DAYS)


def distance_km(a, b):
    """Great-circle distance between two airports."""
    lat1, lon1 = map(math.radians, CITIES[a][2:])
    lat2, lon2 = map(math.radians, CITIES[b][2:])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def money(rupees):
    """Indian digit grouping: 1234567 -> '₹12,34,567'."""
    sign = "-" if rupees < 0 else ""
    digits = str(abs(int(round(rupees))))
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups + [tail])}"


def clock(minutes):
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def duration_text(minutes):
    return f"{minutes // 60}h {minutes % 60:02d}m"


# ----------------------------------------------------------------------
# Flight search
# ----------------------------------------------------------------------


@dataclass
class Flight:
    airline: str
    code: str
    number: str
    origin: str
    destination: str
    date: str          # ISO date of departure
    depart_min: int    # minutes after midnight
    duration_min: int
    fare: int          # economy fare per seat, rupees
    seats: int         # seats on sale before any bookings
    color: str = "#1E3A8A"

    @property
    def arrive_min(self):
        return self.depart_min + self.duration_min

    @property
    def next_day(self):
        return self.arrive_min >= 24 * 60

    @property
    def key(self):
        return f"{self.number}|{self.date}"

    def cabin_fare(self, cabin):
        return int(round(self.fare * CABINS[cabin]["multiplier"] / 10) * 10)

    def to_dict(self):
        return asdict(self)


def _rng(*parts):
    seed = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


def search_flights(origin, destination, date):
    """Flights for a route and day. The same search always gives the same flights."""
    if origin == destination:
        raise ValueError("Origin and destination must be different.")
    km = distance_km(origin, destination)
    block = 35 + km / 780 * 60  # taxi + cruise at ~780 km/h
    base = 1400 + 3.3 * km
    days_out = (date - today()).days
    demand = 1.35 if days_out < 7 else 1.12 if days_out < 21 else 1.0
    if date.weekday() >= 4:  # Friday - Sunday
        demand *= 1.05

    rng = _rng(origin, destination, date.isoformat())
    flights = []
    for name, code, factor, color in AIRLINES:
        for _ in range(rng.choice([1, 1, 2])):
            duration = int(round((block + rng.randint(-10, 15)) / 5) * 5)
            fare = int(round(base * factor * demand * rng.uniform(0.9, 1.25) / 10) * 10)
            flights.append(
                Flight(
                    airline=name,
                    code=code,
                    number=f"{code} {rng.randint(101, 989)}",
                    origin=origin,
                    destination=destination,
                    date=date.isoformat(),
                    depart_min=rng.randrange(5 * 60, 23 * 60, 5),
                    duration_min=duration,
                    fare=fare,
                    seats=rng.randint(4, 60),
                    color=color,
                )
            )
    return sorted(flights, key=lambda f: f.depart_min)


# ----------------------------------------------------------------------
# Fares
# ----------------------------------------------------------------------


def fare_breakdown(flights, cabin, travellers):
    per_seat = sum(f.cabin_fare(cabin) for f in flights)
    base = per_seat * travellers
    gst = int(round(base * CABINS[cabin]["gst"] / 100))
    return {"per_seat": per_seat, "base": base, "gst": gst, "total": base + gst}


def cancellation_quote(total, travellers, legs):
    fee = min(total, CANCEL_FEE_PER_SEAT * travellers * legs)
    return {"fee": fee, "refund": total - fee}


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------

NAME_RE = re.compile(r"^[A-Za-z]+([ .'-]+[A-Za-z]+)*\.?$")
UPI_RE = re.compile(r"^[A-Za-z0-9._-]{2,256}@[A-Za-z]{2,64}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def clean_name(value):
    value = " ".join(value.split())
    if not value or len(value) > 40 or not NAME_RE.match(value):
        return None
    return " ".join(w[:1].upper() + w[1:].lower() for w in value.split(" "))


def clean_mobile(value):
    """Indian mobile number: 10 digits starting 6-9, optional +91."""
    digits = re.sub(r"[\s-]", "", value)
    if digits.startswith("+91"):
        digits = digits[3:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def valid_email(value):
    return bool(EMAIL_RE.match(value.strip()))


def valid_upi(value):
    return bool(UPI_RE.match(value.strip()))


def luhn_valid(number):
    digits = re.sub(r"[\s-]", "", number)
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def valid_expiry(value, on=None):
    """MM/YY, not expired as of `on` (default today)."""
    m = re.fullmatch(r"\s*(\d{2})\s*/\s*(\d{2})\s*", value)
    if not m:
        return False
    month, year = int(m.group(1)), 2000 + int(m.group(2))
    on = on or today()
    return 1 <= month <= 12 and (year, month) >= (on.year, on.month)


def valid_cvv(value):
    return bool(re.fullmatch(r"\d{3,4}", value.strip()))


PNR_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0 or 1


def new_pnr(taken=()):
    while True:
        pnr = "".join(secrets.choice(PNR_CHARS) for _ in range(6))
        if pnr not in taken:
            return pnr


@dataclass
class Booking:
    pnr: str
    status: str
    cabin: str
    travellers: list          # [{"first": ..., "last": ...}]
    flights: list             # Flight dicts, outbound first
    mobile: str
    email: str
    payment: str
    fare: dict
    booked_on: str = field(default_factory=lambda: today().isoformat())

    @property
    def lead_last_name(self):
        return self.travellers[0]["last"]

    @property
    def round_trip(self):
        return len(self.flights) == 2

    def flight_objects(self):
        return [Flight(**f) for f in self.flights]
